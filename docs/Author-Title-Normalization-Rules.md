# Author/Title Normalization Rules

## Profile

**Profile Name:** Keith Author/Title Normalization Rules  
**Profile Version:** v0.1  
**Scope:** Author and title cleanup for Calibre metadata workflows  
**Status:** Active draft  
**Last Updated:** 2026-05-10

## Purpose

This document defines the house-style rules used when proposing Author/Title cleanup changes for the Calibre Metadata Toolkit.

The goal is not strict bibliographic purity. The goal is a clean, consistent, searchable, keyboard-friendly Calibre library that supports practical long-term maintenance.

AI-assisted Author/Title proposals should follow this profile unless the user explicitly overrides it.

---

## Core Principles

1. Prefer consistency across the library over one-off bibliographic perfection.
2. Preserve meaningful title and subtitle information.
3. Remove marketing, edition, award, and format clutter from titles.
4. Use keyboard-friendly author names unless the user explicitly chooses otherwise.
5. Make only changes that improve clarity, consistency, or searchability.
6. Do not rewrite titles or author names just to make them more formal.
7. When uncertain, mark the proposal for manual review instead of forcing a change.

---

## Author Normalization Rules

### A01 - Author names should use keyboard-friendly ASCII

Prefer ASCII / keyboard-friendly author names.

Examples:

| Source Form | Preferred Form |
|---|---|
| Junot Díaz | Junot Diaz |
| Colm Tóibín | Colm Toibin |
| Francisco Cantú | Francisco Cantu |
| Mélikah Abdelmoumen | Melikah Abdelmoumen |

Rationale: easier typing, searching, sorting, and long-term maintenance.

### A02 - Author names should use First Last order

Use First Name Last Name format.

Example:

| Source Form | Preferred Form |
|---|---|
| Massie, Robert K. | Robert K. Massie |

Do not use Last Name, First Name unless the field is explicitly designed for sort ordering.

### A03 - Multiple authors should use ampersand separator

Use an ampersand separator for multiple authors.

Preferred:

Author One & Author Two

Avoid mixed separators such as semicolons, commas, or "and" unless needed for a special case.

### A04 - Preserve commonly used initials

Keep middle initials when they are part of the commonly published name.

Examples:

- Robert K. Massie
- Ibram X. Kendi
- W. W. Norton & Company is a publisher example, not an author example
- E. O. Wilson should keep initials when referring to the person or award name

### A05 - Preserve hyphenated names

Keep hyphenated names.

Examples:

- Ta-Nehisi Coates
- Chang-Rae Lee

### A06 - Remove duplicate or erroneous author fragments

Fix obviously malformed author fields.

Example:

| Source Form | Preferred Form |
|---|---|
| Francisco Cantú & Francisco | Francisco Cantu |
| Francisco Cantu & Francisco | Francisco Cantu |

### A07 - Do not add contributor roles to the Authors field

Avoid adding role labels such as editor, translator, illustrator, introduction by, foreword by, etc., unless the workflow explicitly supports contributor roles.

The Authors field should normally contain only the primary author or primary authors.

### A08 - Leave corporate or group authors unchanged unless clearly malformed

Do not aggressively rewrite corporate or group authors without a clear reason.

### A09 - Prefer simple, searchable author forms

When there are multiple plausible forms of a name, prefer the form that is easiest to type, search, and recognize in Calibre.

---

## Title Normalization Rules

### T01 - Remove generic fiction format subtitles

Remove generic subtitles that are merely format labels.

Common examples:

- : A Novel
- : A Story

Examples:

| Source Title | Preferred Title |
|---|---|
| Matrix: A Novel | Matrix |
| James: A Novel | James |
| The Water Dancer: A Novel | The Water Dancer |
| A Burning: A Novel | A Burning |
| Greenland: A Novel | Greenland |
| The Book of Aron: A Novel | The Book of Aron |
| Cinema Love: A Novel | Cinema Love |
| The Unworthy: A Novel | The Unworthy |
| We Do Not Part: A Novel | We Do Not Part |
| A Guardian and a Thief: A Novel | A Guardian and a Thief |

### T02 - Remove award, marketing, and promotional parentheticals

Remove parenthetical title clutter that belongs in awards, tags, edition, or notes metadata.

Example:

| Source Title | Preferred Title |
|---|---|
| The Goldfinch (Pulitzer Prize Winner) | The Goldfinch |

### T03 - Remove edition or anniversary text from title when it is not the canonical title

Remove edition-specific clutter while preserving meaningful subtitles.

Example:

| Source Title | Preferred Title |
|---|---|
| The Sixth Extinction (10th Anniversary Edition): An Unnatural History | The Sixth Extinction: An Unnatural History |

### T04 - Keep meaningful nonfiction subtitles

Preserve subtitles that clarify the subject, scope, argument, or identity of the book.

Examples to keep:

- An Immense World: How Animal Senses Reveal the Hidden Realms Around Us
- The Bully Pulpit: Theodore Roosevelt, William Howard Taft, and the Golden Age of Journalism
- Dopesick: Dealers, Doctors, and the Drug Company That Addicted America
- Just Mercy: A Story of Justice and Redemption
- Killers of the Flower Moon: The Osage Murders and the Birth of the FBI
- Five Days at Memorial: Life and Death in a Storm-Ravaged Hospital

### T05 - Keep memoir subtitles by default

Do not remove memoir subtitles by default.

Examples to keep:

- Hold Still: A Memoir With Photographs
- Constructing a Nervous System: A Memoir
- Memorial Drive: A Daughter's Memoir

### T06 - Fix obvious capitalization issues in names and particles

Correct obvious name-particle capitalization when it appears inside a title.

Example:

| Source Title | Preferred Title |
|---|---|
| The Invention of Nature: Alexander Von Humboldt's New World | The Invention of Nature: Alexander von Humboldt's New World |

### T07 - Do not remove meaningful subtitles from nonfiction or history titles

If the subtitle helps identify the work, keep it.

### T08 - Do not shorten titles just because they are long

Long titles are acceptable when they are canonical and meaningful.

### T09 - Remove series, edition, or packaging clutter if it belongs elsewhere

Remove title fragments that clearly belong in edition, series, tags, awards, or comments metadata rather than in the title.

### T10 - When uncertain, require manual review

If a change is plausible but not obvious, mark it as requiring manual review rather than applying it automatically.

---

## Proposal Field Standards

When generating Author/Title proposals, use these fields.

### ProposedTitle

Populate only when the title should change.

Leave blank when the title should remain unchanged.

### ProposedAuthors

Populate only when the author field should change.

Leave blank when the author field should remain unchanged.

### ChangeReason

Use concise, human-readable reasons.

Recommended reason phrases:

- Removed generic fiction format subtitle.
- Removed award/marketing parenthetical from title.
- Removed edition text while preserving meaningful subtitle.
- Corrected title capitalization for historical name particle.
- Removed duplicate/erroneous author fragment.
- Normalized author name to keyboard-friendly ASCII.

### Confidence

Use one of:

- High
- Medium
- Low

### ManualReviewRequired

Use one of:

- Yes
- No

Use Yes when the change is uncertain, culturally sensitive, or dependent on user preference.

---

## Current Active Preferences

- Author diacritics: normalize to ASCII.
- Generic fiction subtitles such as ": A Novel": remove.
- Edition, award, and marketing parentheticals: remove.
- Meaningful nonfiction subtitles: keep.
- Memoir subtitles: keep by default.
- Multiple authors: separate with " & ".
- Author order: First Last.
- Middle initials: keep when commonly used.
- Hyphenated names: preserve.
- Ambiguous cases: mark for manual review.

---

## Andrew Carnegie Medal Batch Examples

### Strong title cleanup examples

| Source Title | Preferred Title | Rule |
|---|---|---|
| Matrix: A Novel | Matrix | T01 |
| The Goldfinch (Pulitzer Prize Winner) | The Goldfinch | T02 |
| James: A Novel | James | T01 |
| The Water Dancer: A Novel | The Water Dancer | T01 |
| A Burning: A Novel | A Burning | T01 |
| Greenland: A Novel | Greenland | T01 |
| The Book of Aron: A Novel | The Book of Aron | T01 |
| The Sixth Extinction (10th Anniversary Edition): An Unnatural History | The Sixth Extinction: An Unnatural History | T03 |
| Cinema Love: A Novel | Cinema Love | T01 |
| The Unworthy: A Novel | The Unworthy | T01 |
| We Do Not Part: A Novel | We Do Not Part | T01 |
| A Guardian and a Thief: A Novel | A Guardian and a Thief | T01 |

### Strong author cleanup examples

| Source Author | Preferred Author | Rule |
|---|---|---|
| Francisco Cantú & Francisco | Francisco Cantu | A01, A06 |
| Mélikah Abdelmoumen | Melikah Abdelmoumen | A01 |

### Do-not-change examples under this profile

| Source Form | Reason |
|---|---|
| Junot Diaz | Already matches keyboard-friendly ASCII preference |
| Colm Toibin | Already matches keyboard-friendly ASCII preference |
| Hold Still: A Memoir With Photographs | Meaningful memoir subtitle |
| An Immense World: How Animal Senses Reveal the Hidden Realms Around Us | Meaningful nonfiction subtitle |
| Dopesick: Dealers, Doctors, and the Drug Company That Addicted America | Meaningful nonfiction subtitle |

---

## Future Expansion Notes

Future rulesets may be added for:

- LCC classification proposal logic
- Tags normalization
- Comments generation
- Awards metadata cleanup
- Identifier cleanup
- Cover metadata workflow

Each ruleset should have its own profile name, version, scope, status, and examples.
