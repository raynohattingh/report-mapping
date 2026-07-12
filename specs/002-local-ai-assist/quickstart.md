# Quickstart — Local AI Assistance (002-local-ai-assist)

Manual setup (FR-014: nothing auto-downloads at session time) plus the offline demo walkthrough. All commands run on the A9 reference machine (CPU-only Apple-silicon, ≥16GB).

## 1. Install assets (one-time, needs network — do this BEFORE going offline)

```bash
# Python deps (tier 1 embeddings run in-process)
uv sync                                  # picks up fastembed + ollama client (A12a/A12b)

# Warm the embedding model cache (~130MB, cached under ~/.cache)
uv run python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Optional tier 2 — local LLM runtime
brew install ollama                      # or download from ollama.com
ollama pull qwen3:4b                     # A12b (Apache-2.0); fallback: ollama pull gemma3:4b
```

## 2. Verify

```bash
uv run rmu ai doctor
# tier 1 embeddings : OK  (fastembed cache: BAAI/bge-small-en-v1.5)
# tier 2 local LLM  : OK  (ollama on 127.0.0.1:11434, loopback-bound, qwen3:4b pulled)
# external          : NOT CONFIGURED (no consent entries — expected)
```

Partial installs are fine: `doctor` reports per-tier, and sessions degrade per tier (FR-011).

## 3. Run an assisted mapping session — provably offline

```bash
# Turn Wi-Fi off if you want the theatrical proof; the test suite proves it mechanically.
uv run rmu db init && uv run rmu seed load
uv run rmu map start \
  --profile scopito.pdf.powerline@v2020 \
  --template interim.defect_csv@1 \
  --exemplar seed/source_samples/Distribution-report.pdf \
  --assist local
# stderr: ranking fields… proposing value maps (2/2)…
# stdout: session: 1  draft: store/…/draft.yaml
#         assist: local shown=8 dropped=1  (details on review sheet)
```

Draft routes arrive at tier T2 with rationales; unproposed required fields at T3 with a ranked shortlist in the draft comments. Review/approve exactly as before — nothing is auto-accepted:

```bash
uv run rmu map review --session 1     # HTML sheet: T2 rows distinct + shown/dropped banner
# edit draft YAML: promote T2→T0/T1, resolve T3s, create value maps from starters
uv run rmu map approve --session 1 --by rayno
```

## 4. Mode switching (config only — no artifact changes)

```bash
uv run rmu map start … --no-ai                      # manual floor, always works (D3)
RMU_ASSIST_MODE=none uv run rmu map start …          # same via env
uv run rmu ai consent grant --client demo --by rayno --note "demo data only"
uv run rmu map start … --assist external --client demo   # only path that leaves the machine
```

External without consent exits 4 with an explanation — that's SC-005 working.

Note: consent records live in `<store>/ai.yaml`. Include that file in whatever backs up your `store/` directory — it is the audit trail of who authorized external processing for which client.

## 5. Prove the guarantees (test suite)

```bash
uv run pytest tests/integration/test_local_session_offline.py   # SC-001: full session, non-loopback sockets blocked
uv run pytest tests/unit/test_ranking.py                        # SC-002: ≥90% top-3 on seed ground truth
uv run pytest tests/invariants/                                  # SC-004: untouched determinism/append-only/drift suites
```
