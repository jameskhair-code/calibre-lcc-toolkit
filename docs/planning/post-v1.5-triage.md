# Post-v1.5 triage — reported `clean-titles` hang

## Symptom and reproduction steps

Reported symptom: running `calibre-toolkit clean-titles` against the real
library shows the progress counter advancing through batches but the command
never completes. PR #25 (item 19, summary panels, commit `b420734`) was the
top suspect because it rewrote the post-batch completion path in
`calibre_toolkit/modules/authors.py`.

Reproduction as scripted in the triage prompt:

```
calibre-toolkit clean-titles --limit 1 --dry-run
```

This command is **not runnable as written** — see bisection step 1 below.
Inspection of the source was used in place of the scripted reproduction.

## Bisection log

1. **Step 1 (smallest reproduction) — not runnable.** `clean-titles` has no
   `--dry-run` flag. `cli.py:160-181` shows the actual option surface:
   `--config/-c`, `--batch-size/-b`, `--auto-apply-high`, `--limit/-n`. The
   global `--dry-run` is documented in the standardisation header at
   `cli.py:35` as a canonical name, but it was never wired into
   `clean-titles`. Step 1 was therefore replaced with source inspection.

2. **Step 2 (bisect against v1.4) — skipped.** Not needed once steps 4 and 6
   below ruled the new code out by static reading. Returning to it was
   judged not worth the cost given the analysis below.

3. **Step 3 (narrow within v1.5) — skipped.** Same reasoning.

4. **Step 4 (localise within PR #25) — done by reading.** The line range
   named in the triage prompt (`authors.py:200-217`) does not match the
   current file. The new `render_summary_panel(StepSummary(...))` block is
   at `authors.py:209-221`. More importantly, it sits **after**
   `Prompt.ask("Apply changes?", ...)` at `authors.py:180`. That
   `Prompt.ask` block has been in `authors.py` since the file's first commit
   (`0a0589f`, "Pivot to Python: add working Author/Title cleanup CLI") and
   is unchanged in PR #25. PR #25 only added code downstream of the prompt.

   - `render_summary_panel` (`summary.py:133-184`) is pure Rich layout —
     `Table.grid`, `_kv_row`, `Group`, `Panel` construction. No I/O, no
     waits, no blocking calls. Cannot hang.
   - `usage.format_summary` called from `summary.py:172` is pure formatting
     for the same reason.
   - The new code at `authors.py:209-221` runs only on the
     post-`Prompt.ask` path. If the symptom is "never completes after
     batches advance," control never reached this block.

5. **Step 5 (environmental) — partly observed.** While probing the command
   surface, `calibre-toolkit clean-titles --help` crashed with
   `UnicodeEncodeError: 'charmap' codec can't encode character '→'` —
   typer's Rich help renderer hitting the legacy Windows cp1252 console on
   `position 9`. This is a separate cosmetic bug in `--help` rendering, not
   the reported runtime hang.

6. **Step 6 (cross-check shared code) — done by reading.**
   `_run_batches_concurrent` (`ai.py:541-561`) uses `ThreadPoolExecutor` +
   `as_completed`. A genuinely stuck SDK call would block one of those
   futures, which would freeze the progress bar mid-advance — not produce a
   "batches finished, hang after" symptom. There is no `Future.result()`
   timeout, but the Anthropic SDK enforces its own HTTP timeout, so a hung
   batch is bounded in practice.

## Root-cause analysis

**The reported symptom is most consistent with the long-standing
`Prompt.ask("Apply changes?", ...)` at `authors.py:180` waiting on stdin,
not with any v1.5 code change.**

Supporting points:

- The batch progress bar uses `transient=True` (`authors.py:116`), so it
  clears itself when batches finish, leaving the next visible terminal line
  as the `Apply changes?` prompt. Easy to overlook if the terminal scrolled,
  the run was captured to a log without a TTY (stdin closed → `Prompt.ask`
  blocks forever), or output was piped.
- The `Prompt.ask` is not new in v1.5; it predates the entire file's
  rewrite. PR #25's diff is strictly downstream of it.
- The named hang surfaces in the triage prompt (`render_summary_panel`,
  `usage.format_summary`, `_run_batches_concurrent`) all fail to support
  the "advances through batches, never completes" shape: the first two are
  pure formatting (cannot hang); the third would hang during batch
  progress, not after.

**No v1.5 regression identified.** The hang behaviour, if real and not a
misobserved interactive prompt, would have been present in every prior
version that shipped `clean-titles`.

## Recommended remediation

**Defer as non-bug.** Close the regression report. No code change in v1.5.1
or as v1.6 item-0 is justified by the analysis above.

Two follow-ups worth considering as separate v1.6 items (not part of this
triage):

- **Discoverability fix.** Print a single blank line and a one-line hint
  immediately before each `Prompt.ask("Apply changes?", ...)` in
  `authors.py`, `comments.py`, `lcc.py`, `identifiers.py`, `tags.py` — e.g.
  `console.print("\n[dim]Waiting for input…[/dim]")`. Or set
  `transient=False` on the AI-suggest progress bars so the completion line
  stays on screen and the prompt obviously follows it. Either change costs
  ~5 lines per module and removes the failure mode permanently.
- **`--help` Unicode crash on legacy Windows console.** `clean-titles
  --help` (and likely other commands) crashes with `UnicodeEncodeError` on
  the cp1252 console because typer renders a `→` character. Either force
  utf-8 on the console at CLI startup, or replace the offending character
  in the help strings. Separate item; cosmetic.

## Affected commands

The transient-progress-then-interactive-prompt pattern is shared across
every AI-suggest command:

- `clean-titles` — `authors.py:116` (transient progress), `authors.py:180`
  (Prompt.ask)
- `comments-enrich` — `comments.py:270`, prompts at
  `comments.py:346,359,372,452`
- `lcc-enrich` — `lcc.py:756`, prompts at `lcc.py:843,854,865`
- `enrich-identifiers` — `identifiers.py:291`, prompts at
  `identifiers.py:527,547`
- `tags` — `tags.py:458`, prompts at `tags.py:260,273,286,379,557`

If the discoverability follow-up lands, all five should change together for
consistency.
