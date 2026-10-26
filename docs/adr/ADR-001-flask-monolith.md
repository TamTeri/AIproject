# ADR-001: One Flask application (modular monolith)

**Status:** `[TEAM]` accepted (Call 2/3). Supports system-003 and system-004.

## Context
Version one is a single website with a small team and a six-week build. The customer asked for Python and Flask.

## Decision
- Build one Flask application with one package per C4 component: `identity`, `catalog`, `pricing`, `inventory`, `purchase`, `orders`, `audit`, `admin`.
- Components talk to each other through Python calls, not HTTP.
- `app/__init__.py:create_app()` is the main program, and `app/wiring.py` connects the components.

## Consequences
- There is one deployable unit and one place to configure things.
- Module boundaries are kept by convention and tests, not by the network. ADR-006 explains how the modules stay testable on their own.
