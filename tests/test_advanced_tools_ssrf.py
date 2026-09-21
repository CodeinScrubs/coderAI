"""
tests/test_advanced_tools_ssrf.py - SSRF policy must cover the *other*
outbound tools, not just fetch_url (P1 #7 follow-up).

test_api_endpoint used to call urllib.request.urlopen(url) directly on a
model-supplied URL, and navigate_web / take_screenshot called Playwright
page.goto(url) — none applied the SSRF policy that fetch_url has. A model
could therefore reach the cloud metadata endpoint (169.254.169.254), loopback,
private hosts, or file:// even though fetch_url blocked the same target.

These tests pin the fix: every outbound tool refuses non-http schemes and
private/metadata destinations.
"""

import socket

import pytest

import coderai.tools.advanced_tools as at
import coderai.tools.tools as tools


@pytest.fixture
def block_dns(monkeypatch):
    """Force any hostname to resolve to a private/metadata address so the
    policy's IP check fires without real network access."""
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


# ── test_api_endpoint ─────────────────────────────────────────────────────────

def test_api_endpoint_blocks_metadata_ip(block_dns):
    out = at.tool_test_api_endpoint("http://metadata.internal/")
    assert "blocked" in out.lower() or "error" in out.lower()
    # Must be the SSRF policy message, not a successful fetch.
    assert '"status"' not in out


def test_api_endpoint_blocks_loopback_literal(block_dns):
    out = at.tool_test_api_endpoint("http://127.0.0.1/admin")
    assert "loopback" in out.lower() or "error" in out.lower()
    assert '"status"' not in out


def test_api_endpoint_blocks_non_http_scheme():
    out = at.tool_test_api_endpoint("file:///etc/passwd")
    assert "scheme" in out.lower()
    assert '"status"' not in out


# ── navigate_web / take_screenshot (Playwright) ───────────────────────────────

def test_navigate_web_blocks_metadata_ip(block_dns):
    # Blocked by the policy *before* a browser is launched (no playwright cost).
    out = at.tool_navigate_web("http://metadata.internal/")
    assert "blocked by SSRF policy" in out


def test_navigate_web_blocks_non_http_scheme():
    out = at.tool_navigate_web("file:///C:/Windows/win.ini")
    assert "scheme" in out.lower()


def test_take_screenshot_blocks_metadata_ip(block_dns):
    out = at.tool_take_screenshot("http://metadata.internal/", "shot.png")
    assert "blocked by SSRF policy" in out


def test_take_screenshot_blocks_non_http_scheme():
    out = at.tool_take_screenshot("file:///etc/passwd", "shot.png")
    assert "scheme" in out.lower()


# ── shared helper sanity ──────────────────────────────────────────────────────

def test_advanced_ssrf_ok_delegates_to_shared_policy(block_dns):
    # The advanced_tools guard must apply the same policy as tools._is_url_safe.
    ok, reason = at._ssrf_ok("http://metadata.internal/")
    assert ok is False
    assert reason  # non-empty reason
