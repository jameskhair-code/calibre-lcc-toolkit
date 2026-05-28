# Inbox — untriaged observations

Standing capture buffer for ideas noticed during real use. Not tied to any
single version. Entries are triaged and routed to a specific cycle (or the
ROADMAP parking lot) at each post-release re-audit, then cleared. Add freely;
routing is decided at version boundaries. See `docs/planning/workflow.md`
(phases 4–5) for the full lifecycle.

---

**TUI: highlight the selected pipeline step in the left panel.** The active
step shows in the right detail panel but the left ListView rows have no clear
selected-state treatment — hard to confirm focus at a glance when navigating
with arrows or digit-jumps. Display-only CSS change in `tui/app.py`
(`StepItem` highlighted/focused styling). Low risk. Pairs with v1.8 item 8
(both touch the TUI render path). Surfaced from real use 2026-05-28.
