# Quickstart: Mapping Studio

**Feature**: 004-mapping-studio — end-to-end walkthrough (mirrors SC-001's acceptance journey).

## Install & launch

```bash
uv sync --group studio          # studio deps are an optional group (FR-042)
uv run rmu studio               # binds 127.0.0.1, prints http://127.0.0.1:<port>/?key=<secret>
```

The URL opens automatically; the `?key=` secret is per-launch and never stored. A URL from a
previous launch is refused — just run `rmu studio` again.

## The acceptance journey (no YAML hand-edits anywhere)

1. **Dashboard** — registries, sessions, proposals, recent runs with SafeCard verdicts, AI health.
2. **Onboard a target** — *Start new → onboarding draft*, upload the target PDF. Review visually:
   spatial elements overlay the pages (keyboard triage: **Y** confirm, **E** rename, **X** remove,
   auto-advance; per-page bulk-confirm for the long tail); drag/resize a region or draw a missed
   one. *Approve* runs verify-on-approve; failures deep-link to the implicated elements.
3. **Start a session** — *Start new → mapping session*: pick profile@version, template@version,
   upload the exemplar. Assist defaults to local AI; manual always works; external only with
   client consent.
4. **Map on the canvas** — source pages left, target right. Accept/reject pending (amber) AI
   links; click source element → target field to draw manual links. Red entries in the link list
   are unmapped required fields. The readiness bar is the approval gate, live.
5. **Value-map at the link** — open a link, map observed source values to target vocabulary
   (AI suggestions marked until accepted), then **Register & pin** to create the append-only
   ValueMap version. Configure constants/formulas/per-batch prompts in the same detail view.
6. **Preview** — the real render: PDF inline, CSV as a table, docx as the actual file to open
   locally. Unresolved markers counted, render problems verbatim.
7. **Approve** — same gate as `rmu map approve`; refusals verbatim; success stores the versioned
   Transform.
8. **Batch from the CLI** (batch stays CLI-canonical):

   ```bash
   uv run rmu apply run --transform <name@version> --input <dir> --out <dir>
   ```

Any draft can be finished from the other surface at any point — the studio and CLI edit the same
files and rows. If both edited the same draft, the studio blocks the save and offers
reload-latest / overwrite-with-mine.

## Manual demo checklist (per research.md R9 — items not covered by automated tests)

- [ ] Overlays land on-region across all pages of the seed + Eskom holdout docs, incl. the
      rotated-landscape pages (SC-007 by eye; coordinate contract is unit-tested)
- [ ] 100+-page image-heavy exemplar opens interactive < 5 s; page nav renders on demand (SC-010)
- [ ] Grid-heavy holdout proposal fully reviewed < 30 min via keyboard triage (SC-008)
- [ ] First-attempt unaided P1 canvas journey by a CLI-experienced analyst (SC-009)
