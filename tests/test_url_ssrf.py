"""
tests/test_url_ssrf.py - SSRF guard for fetch_url (P1 #7).

_is_url_safe used to check only the scheme and whether the hostname *string*
looked local/private, so a DNS name that resolves to a private/metadata address
(localtest.me -> 127.0.0.1) sailed through, and a 302 to 169.254.169.254 was
never re-checked. Now every resolved address is validated and every redirect
hop is re-validated.
"""

import socket
import types
import urllib.parse

import pytest

from coderai.tools.tools import (
    _SSRFPolicyRedirectHandler,
    _is_url_safe,
    _resolve_public_target,
    tool_fetch_url,
)


def test_non_http_scheme_blocked():
    ok, reason = _is_url_safe("file:///etc/passwd")
    assert ok is False
    assert "scheme" in reason.lower()


def test_loopback_literal_blocked():
    ok, reason = _is_url_safe("http://127.0.0.1/admin")
    assert ok is False
    assert "loopback" in reason.lower()


def test_link_local_metadata_blocked():
    # The cloud instance-metadata endpoint.
    ok, reason = _is_url_safe("http://169.254.169.254/latest/meta-data/")
    assert ok is False
    assert "link-local" in reason.lower()


def test_private_ip_blocked():
    ok, reason = _is_url_safe("http://10.0.0.5/internal")
    assert ok is False
    assert "private" in reason.lower()


def test_hostname_resolving_to_loopback_is_blocked(monkeypatch):
    # The live vector: a *name* that getaddrinfo maps to 127.0.0.1.
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, reason = _is_url_safe("http://localtest.me/")
    assert ok is False
    assert "127.0.0.1" in reason


def test_hostname_resolving_to_public_is_allowed(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, reason = _is_url_safe("http://example.com/")
    assert ok is True
    assert reason == ""


def test_any_private_resolution_blocks_even_if_public_listed_first(monkeypatch):
    # A DNS rebinding style response: one public, one private. All must pass.
    def fake_getaddrinfo(host, port, *a, **k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 0)),
        ]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, reason = _is_url_safe("http://tricky.example/")
    assert ok is False


def test_unresolvable_hostname_blocked(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **k):
        raise socket.gaierror("name does not resolve")
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ok, reason = _is_url_safe("http://does-not-exist.invalid/")
    assert ok is False
    assert "resolve" in reason.lower()


def test_redirect_handler_refuses_private_target(monkeypatch):
    # Patch _is_url_safe so the redirect target is treated as private/blocked
    # without needing real DNS.
    monkeypatch.setattr("coderai.tools.tools._is_url_safe", lambda u: (False, "private"))
    handler = _SSRFPolicyRedirectHandler()

    base = urllib.parse.urlparse("http://public.example/page")
    orig_req = urllib.request.Request(base.geturl(), method="GET")

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        handler.redirect_request(
            orig_req, fp=None, code=302, msg="Found", headers={},
            newurl="http://169.254.169.254/latest/meta-data/",
        )
    assert excinfo.value.code == 302
    assert "blocked" in str(excinfo.value.msg).lower()


def test_fetch_url_blocks_before_connecting(monkeypatch):
    # If _is_url_safe says no, fetch_url must not attempt any network I/O.
    monkeypatch.setattr("coderai.tools.tools._is_url_safe", lambda u: (False, "private"))
    def boom(*a, **k):
        raise AssertionError("network access attempted despite SSRF block")
    monkeypatch.setattr("coderai.tools.tools.urllib.request.build_opener", boom)
    out = tool_fetch_url("http://internal.example/secret")
    assert "Error" in out
    assert "private" in out.lower()


def test_resolver_returns_pin_ip_for_public(monkeypatch):
    # The connect path should pin the socket to the validated public IP.
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ip, reason = _resolve_public_target("http://example.com/")
    assert reason == ""
    assert ip == "93.184.216.34"


def test_resolver_pins_even_when_public_listed_first(monkeypatch):
    # One public + one private: must be blocked (private must not be skipped
    # because a public record was seen first).
    def fake_getaddrinfo(host, port, *a, **k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 0)),
        ]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ip, reason = _resolve_public_target("http://tricky.example/")
    assert ip is None
    assert "192.168.1.10" in reason


def test_fetch_pins_socket_to_validated_ip(monkeypatch):
    # The socket must connect to the IP we validated, not re-resolve the
    # hostname. Capture the address the fetcher connects to.
    import http.client
    import io
    import email.message

    connected = []

    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    class _FakeHTTPResponse:
        def __init__(self):
            self.msg = email.message.Message()
            self.status = 200
            self.closed = False
            self._data = io.BytesIO(b"ok")
        def read(self, *a):
            return self._data.read(*a)
        def close(self):
            self.closed = True

    def fake_conn(host, port, context=None, timeout=None, **k):
        connected.append(host)
        conn = types.SimpleNamespace(
            request=lambda *a, **kw: None,
            getresponse=lambda: _FakeHTTPResponse(),
            close=lambda: None,
        )
        return conn

    # _open_pinned_http does `import http.client` and references
    # http.client.HTTPConnection, so patch the real module attribute.
    monkeypatch.setattr(http.client, "HTTPConnection", fake_conn)
    out = tool_fetch_url("http://example.com/")
    # The socket went to the resolved public IP, never the hostname.
    assert connected == ["93.184.216.34"], connected
    assert "Error" not in out
    assert "ok" in out


def test_fetch_refuses_redirect_to_private_target(monkeypatch):
    # A public URL that 302-redirects to the cloud-metadata endpoint must be
    # refused on the second hop, not followed.
    import email.message
    from coderai.tools import tools

    def fake_getaddrinfo(host, port, *a, **k):
        # first hop resolves public; the redirect target resolves to metadata.
        if host == "public.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    class _RedirectResp:
        status = 302
        def __init__(self):
            m = email.message.Message()
            m["Location"] = "http://169.254.169.254/latest/meta-data/"
            self.headers = m
        def close(self):
            pass

    opened_urls = []

    def fake_open(url, method, data, headers, timeout):
        opened_urls.append(url)
        return _RedirectResp()
    monkeypatch.setattr(tools, "_open_pinned_http", fake_open)

    out = tool_fetch_url("http://public.example/")
    assert "Error" in out
    assert "blocked" in out.lower() or "169.254.169.254" in out
    # The fetcher must never have opened a connection to the metadata host.
    assert "169.254.169.254" not in " ".join(opened_urls)
