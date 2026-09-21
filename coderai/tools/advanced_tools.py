"""
advanced_tools.py - Low-level executors for the browser/API tool family.

Every public function here is a DUMB executor: it performs no approval or
sandbox decisions. All gating lives in coderai/tools/tools.py (see
_guarded_command, _run_via_sandbox, _run_host_subprocess, and
_guarded_sql_query there), which imports advanced_tools — never the other
way around. If you see a direct import of advanced_tools from anywhere
other than tools.py, that is a bug.
"""


def _ssrf_ok(url: str) -> tuple[bool, str]:
    """Apply the shared SSRF policy to *url* (http/https + public IPs only).

    Imported lazily from ``tools`` because ``tools`` imports ``advanced_tools``
    at module load; a module-level import back here would be a circular import.
    By call time the ``tools`` module is fully loaded, so the lazy import is
    safe and keeps the policy in exactly one place.
    """
    from coderai.tools.tools import _is_url_safe
    return _is_url_safe(url)


def _block_private_destination(route) -> None:
    """Playwright route handler: allow only public-IP http(s) destinations.

    Applied to *every* request a page makes (including subresources and
    redirect follows), so a public page that pulls in ``file://`` or a private
    IP is blocked at the network layer, not just at the top-level URL.
    """
    try:
        ok, _ = _ssrf_ok(route.request.url)
    except Exception:
        ok = False
    if ok:
        route.continue_()
    else:
        route.abort()


def tool_navigate_web(url: str) -> str:
    # SSRF guard: refuse non-http schemes and private/metadata destinations
    # before we spend the cost of launching a browser. The per-request
    # route handler below additionally blocks any subresource or redirect
    # that a fetched page pulls in to a private destination.
    ok, reason = _ssrf_ok(url)
    if not ok:
        return f"Error: blocked by SSRF policy: {reason}"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            ctx.route("**/*", _block_private_destination)
            page = ctx.new_page()
            page.goto(url)
            title = page.title()
            content = page.content()
            browser.close()
            try:
                from bs4 import BeautifulSoup
                text = BeautifulSoup(content, 'html.parser').get_text(separator=' ', strip=True)
            except ImportError:
                text = content
            return f"Title: {title}\nContent snippet: {text[:2000]}"
    except ImportError:
        return "Error: playwright is not installed (pip install playwright && playwright install)."
    except Exception as e:
        return f"Error navigating to {url}: {e}"


def tool_take_screenshot(url: str, output_path: str) -> str:
    ok, reason = _ssrf_ok(url)
    if not ok:
        return f"Error: blocked by SSRF policy: {reason}"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            ctx.route("**/*", _block_private_destination)
            page = ctx.new_page()
            page.goto(url)
            page.screenshot(path=output_path, full_page=True)
            browser.close()
            return f"Screenshot saved to {output_path}"
    except ImportError:
        return "Error: playwright is not installed."
    except Exception as e:
        return f"Error taking screenshot: {e}"


def tool_test_api_endpoint(url: str, method: str = "GET", headers: dict = None, json_body: dict = None) -> str:
    # SSRF guard: the old implementation called urllib.request.urlopen(url)
    # directly on a model-supplied URL, so the model could reach
    # 169.254.169.254 (cloud metadata), loopback, or private hosts even though
    # fetch_url's SSRF policy blocked the same targets. Route through the same
    # pinned/redirect-validated fetcher as fetch_url.
    import json
    try:
        from coderai.tools.tools import _ssrf_safe_fetch  # lazy: avoid circular import
    except Exception as e:
        return f"Error: SSRF fetcher unavailable: {e}"

    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "CoderAI-Agent/1.0")
    data = None
    if json_body:
        data = json.dumps(json_body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    try:
        with _ssrf_safe_fetch(
            url, method=method, data=data, headers=req_headers, timeout=30,
        ) as response:
            status = response.status
            resp_headers = dict(response.headers)
            body = response.read().decode("utf-8", errors="replace")
        return json.dumps({
            "status": status,
            "headers": resp_headers,
            "body_snippet": body[:2000]
        }, indent=2)
    except Exception as e:
        # _ssrf_safe_fetch raises ValueError on a policy violation; surface
        # it as an error string rather than leaking a stack trace.
        return f"API Test error: {e}"
