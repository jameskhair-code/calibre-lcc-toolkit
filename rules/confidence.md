# Confidence Taxonomy
# Shared definitions referenced by all AI step rule files.
#
# Each step (LCC, comments, tags, tag-cleanup) returns a "confidence" value
# of "high" | "medium" | "low" on every row. The semantic intent of those
# tiers is shared across steps so the downstream auto-apply / review / skip
# logic behaves consistently. Step-specific calibration tables in the
# individual rules files refine *what evidence* maps to each tier; the
# definitions here are the canonical meaning of the tier itself.


---
## TIER DEFINITIONS
---

CONF-T-HIGH:
  "high" — Strong, directly verifiable evidence supports every field returned.
  Auto-apply is safe by default (`--auto-apply-high` / `--auto-approve`).
  Typical signals:
    - Authoritative catalog / external source confirms the proposed value
      (e.g. LC ISBN match for LCC; publisher description for comments; full
      LCC subject coverage for tags).
    - The proposed value is the obvious choice — no judgment call needed.
    - Multiple independent signals agree.

CONF-T-MEDIUM:
  "medium" — Solid inference from partial evidence. The proposal is likely
  correct but warrants a human glance. Defaults to the review queue.
  Typical signals:
    - Catalog consensus across editions, not an exact-edition match.
    - One field rests on inference or a single source.
    - A judgment call was required between two reasonable options.
    - The Python validator had to repair a structural issue (Form-tag
      count, etc.) — see step-specific CONF rules.

CONF-T-LOW:
  "low" — Weak or absent evidence; proposal is a best-effort fallback.
  Defaults to skip / manual classification.
  Typical signals:
    - No catalog or external record was found.
    - Sources disagree and no clear winner.
    - Subject / identity is ambiguous.
    - Only a partial value (e.g. class letter only, no Cutter) can be
      supported.

CONF-T-LIBERAL:
  Use "low" liberally rather than inflating confidence. A "low" row is
  routed to manual review — that is the correct outcome when evidence
  is weak. Do not inflate confidence to avoid the review flag.

CONF-T-SCOPE:
  Confidence applies to the entire row (the full set of fields the step
  returns for one book). If one field is well-supported but another is
  shaky, downgrade the whole row to reflect the weakest field.


---
## STEP-SPECIFIC ELABORATION
---

Each step's rules file contains a `SECTION CONF` that maps these tiers
onto the concrete evidence types available to that step:

  - rules/lcc.md       SECTION CONF — catalog-confirmed vs. schedule-derived.
  - rules/comments.md  SECTION CONF — source breadth per section.
  - rules/tags.md      SECTION CONF — LCC signal strength and Form-tag clarity.
  - rules/tags_cleanup.md (no explicit CONF section — operations are
                          structural and either apply or do not).

When the step rules conflict with this file, this file wins on the meaning
of the tier; the step rules win on which evidence maps to which tier.


---
## CALIBRATION — MEASURING WHETHER THESE TIERS HOLD UP
---

The tier definitions above are aspirational unless verified. To check
whether high-confidence really is more accurate than medium for a given
step, sample applied writes from the persistent audit log and rate them:

    calibre-toolkit audit-confidence
    calibre-toolkit audit-confidence --step comments-enrich --sample-size 30

Results are appended one session per line to
`~/.calibre-toolkit/calibration.jsonl` and tiers below the configured
strict-precision threshold (default 70%) are flagged in the session
summary. When a tier is consistently flagged across sessions, the
corresponding step rules file CONF section needs revision — either the
tier definition is too generous, or the evidence-to-tier mapping is
out of calibration.
