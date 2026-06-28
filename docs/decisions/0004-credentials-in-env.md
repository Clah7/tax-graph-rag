# 0004 — Neo4j credentials in `.env`, not committed

- **Status:** Accepted
- **Date:** 2026-06-23

## Context

`src/config.py` hardcoded the Neo4j password and was committed to git. The repo
will likely be shared with the supervisor and may be published with the thesis.

## Decision

- Credentials are read from environment variables, loaded from a gitignored
  `.env` (a minimal dependency-free loader in `config.py`).
- `config.py` raises a clear `RuntimeError` if `NEO4J_PASSWORD` is unset.
- `.env.example` is committed as a template with empty values.

## Consequences

- No secret in the working tree. New environments must copy `.env.example` → `.env`.
- The old password remains in git **history** — it must be rotated in Neo4j (and
  optionally scrubbed with `git filter-repo`) to be fully neutralised.
- No new pip dependency added (loader is hand-rolled).
