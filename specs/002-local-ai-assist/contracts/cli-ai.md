# CLI Contract — Local AI Assistance (002-local-ai-assist)

The CLI is the tool's public interface; these commands/flags are the feature's contract. Exit codes: `0` success, `2` usage error (Typer default), `3` approval blocked (existing), `4` consent refused (new), `5` mode unavailable (new).

## Changed: `rmu map start`

```
rmu map start --profile <key@ver> --template <name@ver> --exemplar <pdf>
              [--assist none|local|external]   # default: resolved (flag > RMU_ASSIST_MODE > ai.yaml > local)
              [--client <id>]                  # REQUIRED for --assist external; recorded on the session
              [--no-ai]                        # hard alias for --assist none (Constitution VII)
              [--stub-ai]                      # tests only, unchanged
```

Behavior contract:
- `--assist external` without `--client` ⇒ exit 4, message names the missing flag.
- `--assist external --client X` with no consent entry for `X` ⇒ exit 4, message says how the owner records consent (`rmu ai consent grant`).
- `--assist local` with no assets at all ⇒ session proceeds manually; stderr explains which assets are missing and points at `rmu ai setup` (FR-011). Exit 0.
- `--assist local` with embeddings only ⇒ rankings produced, value-map proposals skipped with message (per-tier degradation). Exit 0.
- Progress lines on stderr during generation: `ranking fields…`, `proposing value maps (k/n)…` (SC-008).
- Output additionally prints: `assist: <mode> shown=<n> dropped=<m>` and the shortlist block per unmapped field.

## New: `rmu ai` command group

```
rmu ai doctor                      # asset/runtime health: embedding cache present? ollama reachable on
                                   # loopback? model pulled? host loopback-bound? prints per-tier verdicts;
                                   # exit 0 always (reporting tool), machine-readable with --json
rmu ai setup                       # prints the documented MANUAL setup steps (FR-014); downloads nothing
rmu ai consent grant --client <id> [--note <text>] --by <owner>
rmu ai consent revoke --client <id> --by <owner>
rmu ai consent list
```

Consent commands are the ONLY writers of `ai.yaml`'s `consent:` block; each prints an audit line (`consent granted: <client> by <owner> at <ts>`).

## New: `rmu map regenerate`

```
rmu map regenerate --session <id> [--assist ...] [--client ...]
```

- Explicit replacement of the persisted proposal set (FR-016): prior proposals + stats move to `assist_stats.superseded[]`; prints `superseded <n> proposals from <ts>`.
- Refused (exit 3) on sessions with status `approved`.

## New: `rmu profile suggest`

```
rmu profile suggest <pdf>
```

- Prints registered profiles ranked by structural resemblance with scores, e.g. `resembles scopito.pdf.powerline@v2020 (0.87)`; wording never claims a match (Principle V).
- Requires tier-1 assets; without them prints the degradation message and exits 5.
- Never writes anything; apply-time detection is a different, unchanged code path.

## Test-visible fixture contract

- `tests/conftest.py::block_non_loopback_network` — autouse-able fixture: any non-loopback `connect()`/`getaddrinfo()` raises. The SC-001 test runs a FULL `map start --assist local` under it.
- `tests/fixtures/fake_ollama.py` — stdlib HTTP server on `127.0.0.1:<free port>` implementing `/api/chat` (canned JSON bodies) + `/api/tags`; used where the real runtime is absent (CI).
