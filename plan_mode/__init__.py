"""Plan Mode service for CoderAI.

A modular, TDD-built service that lets the agent explore the codebase read-only,
draft a set of concrete steps, hold them for human approval, and only then
execute them. Layered clean-architecture style:

    plan_mode/
      domain/       pure: state machine, entities, tool gate (no I/O)
      application/  use cases: PlanModeService + ports
      adapters/     file store, path workspace, tools agent loop
      http_api/     HTTP-agnostic request handlers

The domain layer is importable without the web app, tools, or workspace, so it
can be unit-tested in isolation.
"""

from __future__ import annotations

__version__ = "1.3.0"
