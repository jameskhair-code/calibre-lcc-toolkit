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
