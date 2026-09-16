"""HTTP-agnostic request handlers for Plan Mode (the web adapter seam).

Re-exports the public handler API.
"""

from __future__ import annotations

from plan_mode.http_api.handlers import dispatch

__all__ = ["dispatch"]
