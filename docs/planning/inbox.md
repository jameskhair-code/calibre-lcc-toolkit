# Inbox — untriaged observations

Standing capture buffer for ideas noticed during real use. Not tied to any
single version. Entries are triaged and routed to a specific cycle (or the
roadmap's LATER layer, `docs/planning/roadmap.md`) at each post-release
re-audit, then cleared. Add freely; routing is decided at version boundaries.
See `docs/planning/workflow.md` (phases 4–5) for the full lifecycle.

*Last cleared: 2026-06-11 (post-v1.9 re-audit). All entries routed —
dispositions recorded in `docs/planning/roadmap.md` (the manual-flag
audit-logging gap, the rules-audit findings, and the price-table refresh
went to the v1.10 preflight, `docs/planning/v1.10-charter.md`; the 429
pacing item, the TUI/polish cluster, and AI-judgment subject coherence went
to the pull-list / LATER layer; the parking-lot consolidation was executed;
the A-Z vision became the LATER layer's destination).*

---

- **2026-06-11 (v1.10 item 4):** `tags-cleanup` makes AI calls
  (step_label "tags-cleanup") but was not in the charter's
  budget-guardrail touch-point list, so it has no cost gate. Its batches
  are large (150/call) and call counts low, so exposure is small —
  consider extending the guardrail at a campaign wave boundary. Also
  verified: `enrich-identifiers` constructs no AI client at all (the
  charter's "verify" note) — nothing to gate there.

- **2026-06-12 (v1.10 campaign, wave 1 — clean-titles):** clean-titles has
  no manual / declined-as-done state. Declining (`n`) does not mark the book
  complete, and there is no `#mqg_title_author_manual` column, so a declined
  book re-prompts with the same suggestion every run, forever. The other four
  steps have `_manual` columns. Fix candidate (needs a design call):
  mark-reviewed-on-decline, or add a `#mqg_title_author_manual` column.
  Workaround in use: edit (`e`) to the desired value instead of declining.

- **2026-06-12 (v1.10 campaign, wave 1 — clean-titles, rules):** recurring
  AI mis-removal of editors/translators. The model proposes removing a
  translator/editor and cites A-ROL-01/02/03 — rules that actually say KEEP
  the person (strip only the role label). Two instances in two batches:
  run 1 #14 (Madame Curie / Vincent Sheean, translator) and run 2 #6
  (Porter / Darlene Harbour Unrue, LOA editor). Systematic. Next rules-pass
  target: an explicit guard that editor/translator/compiler roles are
  retained and may never be the basis for removing a person. The v1.8
  review-only gate caught every instance — no auto-corruption.

- **2026-06-13 (v1.10 campaign, wave 1 — clean-titles, audit/calibration):**
  clean-titles does not audit its title/author value writes — only the MQG
  completion flag is logged (`apply_metadata_batch` deliberately skips
  `audit_log` because it runs in worker threads, `db.py:259`). Consequence:
  applied-vs-clean is not reconstructable from the audit log (only
  complete-vs-declined, via flag count vs batch size), and clean-titles
  changes carry no per-field trail the way lcc-enrich does. Open question to
  verify: whether `audit-confidence` / `regrade` for clean-titles depend on
  value-write entries — if so, the step may be un-calibratable / un-regradable
  as-is. Surfaced while reconstructing run 1's split for the campaign log.
