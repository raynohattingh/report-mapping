# Contract: `rmu studio` CLI subcommand

**Feature**: 004-mapping-studio | **Status**: Phase 1 design contract

## Command

```
rmu studio [--port INT] [--no-browser]
```

| Option | Default | Behavior |
|---|---|---|
| `--port` | auto (first free in a small fixed range) | Port to bind on 127.0.0.1 |
| `--no-browser` | open browser | Skip auto-opening; URL is printed either way |

## Behavior

1. Lazily imports `rmu.studio`; if the optional `studio` dependency group is not installed,
   exits non-zero with: how to install it (`uv sync --group studio`) — the core CLI is
   otherwise unaffected (FR-042).
2. Generates the per-launch secret (`secrets.token_urlsafe(32)`); held in process memory only,
   never written to disk (FR-040a).
3. Binds uvicorn to `127.0.0.1` — the bind address is hardcoded, not configurable (FR-040).
4. Prints exactly one launch line containing the full URL with `?key=<token>`, then opens the
   browser unless `--no-browser`.
5. Runs in the foreground; Ctrl-C shuts down cleanly. On exit the token dies — stale URLs are
   refused by later launches (each launch has a fresh token).

## Guarantees

- No flag can make the server bind a non-loopback address or disable token/Host/Origin checks
  (SC-003/SC-011 — enforced by invariant tests).
- The command performs no domain action itself; everything happens via the HTTP surface, which
  calls the same code paths as the other `rmu` subcommands (FR-001).
