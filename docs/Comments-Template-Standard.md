# Comments Template Standard

## 1. Purpose

The Comments Template Standard defines the reusable HTML structure and content rules for populating the Calibre `comments` field as part of the Calibre Metadata Toolkit.

The comments field should help make a Calibre library more browsable, memorable, and useful. It should not merely summarize a book. It should help a future reader understand:

- what the book is
- what argument, premise, or purpose drives it
- why it matters
- why it may be worth reading
- what details make it interesting
- how it fits into a larger collection
- where the generated information came from

The goal is to create comments that feel like a thoughtful curator wrote them: useful, source-grounded, readable, and interesting.

This standard is designed first for scholarly and general nonfiction, while still allowing adaptive handling for fiction, reference works, poetry, drama, edited collections, gaming books, technical manuals, and other special cases.

## 2. Design Philosophy

The comments field should serve four jobs.

### 2.1 Orientation

Answer:

```text
What is this book?
```

The reader should quickly understand the subject, period, place, genre, problem, or scope of the work.

### 2.2 Significance

Answer:

```text
Why does this book matter?
```

This may mean scholarly importance, historical importance, cultural importance, genre importance, practical usefulness, or collection relevance.

### 2.3 Reader Hook

Answer:

```text
Why might future-me want to open this?
```

This should not read like generic marketing copy. It should feel like a smart recommendation from someone who understands the library and the reader's interests.

### 2.4 Source Transparency

Answer:

```text
Where did this information come from?
```

The comments field should not become an unsourced AI summary blob. Source Notes should explain the evidence basis for the generated content.

## 3. Template Model

The comments module should use:

```text
One canonical section registry
+
Template profiles
+
Conditional rendering
+
Type-aware section labels
```

This avoids maintaining a large number of separate hard-coded templates while still allowing the generated comments to fit different kinds of books.

For example, the same conceptual section may render differently depending on work type:

| Work Type | Section Label |
|---|---|
| Scholarly nonfiction | Central Argument |
| General nonfiction | Core Argument |
| Fiction | Premise |
| Reference | Scope & Use |
| Poetry / Drama | Voice & Form |
| Edited collection / Anthology | Editorial Frame |
| Gaming / Technical / Manual | Practical Use |

The underlying slot is the same:

```text
Core Claim / Premise / Scope
```

The visible label changes based on the selected template profile.

## 4. Template Profiles

The comments module should support these profiles.

### 4.1 Scholarly Nonfiction

Primary use case for academic history, scholarly monographs, university press books, intellectual history, social history, political history, cultural studies, and similar works.

Likely sections:

- Overview
- Central Argument
- Why It Matters
- Historical / Intellectual Context
- Notable Details
- Themes & Threads
- Reading Experience
- Author Context
- Awards & Recognition
- Reception & Response
- Companion Reads
- Source Notes

### 4.2 General Nonfiction

Use for trade nonfiction, biography, narrative history, popular science, essays, travel, current affairs, and broadly accessible nonfiction.

Likely sections:

- Overview
- Core Argument
- Why It Matters
- Notable Details
- Themes & Threads
- Reading Experience
- Author Context
- Awards & Recognition
- Reception & Response
- Companion Reads
- Source Notes

### 4.3 Fiction

Use for novels, novellas, short story collections, and genre fiction.

Likely sections:

- Overview
- Premise
- Why Read It
- Setting & Context
- Themes & Threads
- Reading Experience
- Series / Sequence Notes
- Awards & Recognition
- Reception & Response
- Companion Reads
- Source Notes

Spoiler discipline is required. Fiction comments should avoid major plot revelations unless the work is old enough and culturally saturated enough that spoiler sensitivity is not useful.

### 4.4 Reference

Use for dictionaries, encyclopedias, bibliographies, atlases, handbooks, catalogs, guides, and other works primarily used for consultation.

Likely sections:

- Overview
- Scope & Use
- Why It Matters
- Best Used For
- Structure & Features
- Edition Notes
- Source Notes

A reference work may not need a "Why Read It" section. It may be more useful to explain when and how to consult it.

### 4.5 Poetry / Drama

Use for poetry collections, plays, verse anthologies, dramatic works, and literary editions.

Likely sections:

- Overview
- Voice & Form
- Why It Matters
- Themes & Threads
- Reading Experience
- Edition / Translation Notes
- Reception & Response
- Source Notes

### 4.6 Edited Collection / Anthology

Use for essay collections, conference volumes, edited scholarly collections, primary source readers, and multi-author anthologies.

Likely sections:

- Overview
- Editorial Frame
- Why It Matters
- Notable Contributions
- Themes & Threads
- Reading Experience
- Editor Context
- Source Notes

### 4.7 Gaming / Technical / Manual

Use for gaming books, strategy guides, technical manuals, software books, hardware references, tabletop roleplaying books, and practical guides.

Likely sections:

- Overview
- Practical Use
- Why It Matters
- Best Used For
- Structure & Features
- Notable Details
- Edition / Version Notes
- Source Notes

## 5. Section Registry

The following section registry defines the available sections. Sections should be conditionally rendered. Do not output empty headers.

## 5.1 Overview

### Purpose

Provide a concise orientation to the book.

### Use For

Most books.

### Target Length

```text
80-140 words
```

### Content Rules

The Overview should answer:

- what the book is about
- what subject, period, place, genre, or problem it covers
- what kind of book it is
- what makes its scope distinct

### HTML Pattern

```html
<h3>Overview</h3>
<p>...</p>
```

## 5.2 Central Argument / Core Argument / Premise / Scope & Use

### Purpose

Capture the intellectual engine, story premise, or functional purpose of the work.

### Use For

Most books, with profile-specific label.

### Target Length

```text
50-100 words
```

### Label Mapping

| Profile | Header |
|---|---|
| Scholarly Nonfiction | Central Argument |
| General Nonfiction | Core Argument |
| Fiction | Premise |
| Reference | Scope & Use |
| Poetry / Drama | Voice & Form |
| Edited Collection / Anthology | Editorial Frame |
| Gaming / Technical / Manual | Practical Use |

### Content Rules

For nonfiction, identify the main claim, argument, or interpretive move.

For fiction, describe the premise without major spoilers.

For reference works, describe the scope and intended use.

For poetry/drama, describe voice, form, mode, or dramatic/literary orientation.

For edited collections, describe the organizing editorial frame.

### HTML Pattern

```html
<h3>Central Argument</h3>
<p>...</p>
```

The header text may vary by profile.

## 5.3 Why It Matters

### Purpose

Explain the book's significance.

### Use For

Most nonfiction, scholarly works, reference works, edited collections, and major fiction.

### Target Length

```text
60-120 words
```

### Content Rules

This section may explain:

- why the book is important in its field
- what gap it fills
- what debate or topic it contributes to
- why it belongs in the collection
- why it is useful for research or reading projects

Avoid generic claims such as:

```text
This is an important book.
This is a must-read.
This book is fascinating.
```

State why.

### HTML Pattern

```html
<h3>Why It Matters</h3>
<p>...</p>
```

## 5.4 Why Read It

### Purpose

Provide the reader-facing hook.

This section should actively make the case for why the book is worth opening, especially by highlighting the most compelling angle, question, tension, oddity, or payoff.

### Use For

Most books, especially when the comments field is meant to encourage rediscovery.

### Target Length

60-120 words

### Content Rules

This section should answer:

- why the reader might choose this book over nearby books
- what reading mood or research interest the book fits
- what kind of curiosity it rewards
- what makes the book tempting beyond its subject label
- what payoff the reader can expect

Good framing:

- Read this when you want...
- The draw here is...
- This is especially useful if...
- What makes this one tempting is...

The goal is not hype. The goal is a persuasive, specific, curator-style reading pitch.

Avoid:

- generic praise
- vague claims that the book is important or fascinating
- sales-copy tone
- repeating the Overview in softer language

### HTML Pattern

<h3>Why Read It</h3>
<p>...</p>

## 5.5 Notable Details

### Purpose

Capture concrete, memorable, curiosity-triggering details.

This is the primary draw-me-in section.

### Use For

Any book where specific details can be sourced or responsibly inferred.

### Target Length

2-4 bullets

### Content Rules

Prefer book-specific details whenever possible.

Use this section for:

- surprising archival finds
- unusual case studies
- memorable examples
- odd historical details
- distinctive methods
- authorial backstory
- unusual illustrations, maps, tables, or appendices
- significant primary sources
- production or edition details
- strange or compelling subject-matter hooks

If book-specific details are unavailable, include subject-specific details that honestly reflect the book's topic, setting, problem, or historical world.

This fallback should still be concrete. It should not pretend to know details that were not sourced.

Weak:

<li>Explores many interesting historical issues.</li>

Better:

<li>Uses French Guiana as a lens for exploring penal exile, citizenship, and legal exclusion after the French Revolution.</li>

Best:

<li>Draws on navigation manuals and classroom practices to show how early modern sailors learned mathematical techniques in practical settings.</li>

### HTML Pattern

<h3>Notable Details</h3>
<ul>
  <li>...</li>
  <li>...</li>
</ul>

## 5.6 Themes & Threads

### Purpose

Connect the book to broader conceptual interests and browsing paths.

### Use For

Most books.

### Target Length

4-8 short bullet phrases

### Content Rules

This section should help identify conceptual through-lines.

Themes & Threads should render as a bullet list.

Use polished Title Case for each bullet.

Preferred style:

- French Revolution and Empire
- Citizenship and Noncitizenship
- Legal Identity and Exclusion
- Penal Colonies and Exile
- Rights Language and State Violence

Avoid inconsistent casing such as mixing all-lowercase bullets with Title Case bullets in the same comment.

This section should not simply duplicate Calibre Tags. It may overlap with tags, but it should be more curated and interpretive.

### HTML Pattern

<h3>Themes & Threads</h3>
<ul>
  <li>...</li>
  <li>...</li>
</ul>

## 5.7 Reading Experience

### Purpose

Set expectations for the act of reading.

### Use For

Most books where useful.

### Target Length

```text
40-90 words
```

### Content Rules

This section may describe:

- accessibility
- density
- narrative quality
- theoretical intensity
- archival detail
- use of figures, tables, maps, or illustrations
- whether it is better read straight through or consulted by chapter
- whether it assumes specialist knowledge

This section should be practical rather than judgmental.

Good:

```text
The book is best approached as a scholarly monograph with a clear argument and archival texture, rather than as a fast narrative history.
```

Avoid:

```text
This is boring.
This is easy.
This is hard.
```

### HTML Pattern

```html
<h3>Reading Experience</h3>
<p>...</p>
```

## 5.8 Author Context / Editor Context

### Purpose

Explain why the author, editor, or contributor is positioned to produce the work.

### Use For

Scholarly nonfiction, edited collections, major fiction, technical works, and cases where author identity is useful.

### Target Length

```text
40-90 words
```

### Content Rules

This is not a full biography.

It should focus on:

- scholarly field
- institutional or professional context
- prior or related work
- relevance to the book's subject
- editorial role, when applicable

Header may vary:

| Profile | Header |
|---|---|
| Single-author works | Author Context |
| Edited collections | Editor Context |
| Multi-author works | Contributor Context |

### HTML Pattern

```html
<h3>Author Context</h3>
<p>...</p>
```

## 5.9 Historical / Cultural Context

### Purpose

Provide background needed to understand the world, period, or problem the book addresses.

### Use For

History, historical fiction, area studies, cultural studies, political works, religious history, social history, and similar works.

### Target Length

```text
60-130 words
```

### Content Rules

This section may explain:

- historical period
- geographic setting
- political/social/cultural problem
- relevant scholarly context
- broader event or movement

For fiction, this may render as:

```text
Setting & Context
```

### HTML Pattern

```html
<h3>Historical Context</h3>
<p>...</p>
```

## 5.10 Awards & Recognition

### Purpose

Record awards, shortlists, longlists, finalist placements, honorable mentions, best-book list appearances, or other meaningful recognition identified during the comments research pass.

### Use For

Books with meaningful awards or recognition.

### Target Length

1-4 bullets

### Content Rules

This section should not be limited only to awards already present in Calibre metadata.

During comments generation, the Awards & Recognition section should reflect confidently identified awards and recognition for the book, including newly discovered awards that may not yet be tracked elsewhere.

Use precise status language when known:

- Winner
- Finalist
- Shortlisted
- Longlisted
- Honorable Mention
- Named a Best Book by...

Avoid using nominated unless the source itself uses that wording.

Only include award claims declaratively when the evidence is solid. If an award or recognition detail is uncertain, omit it from this section rather than presenting it as fact.

When useful, distinguish existing metadata from newly identified recognition in the wording.

Examples:

<li>Existing Calibre metadata lists the book under the AHA - J. Russell Major Prize award program.</li>
<li>Research during this comments pass also identified the book as a finalist for [Award Name].</li>

Award names should remain in comments and/or award-tracking fields. They should not be automatically pushed into Tags merely because a book won something.

### HTML Pattern

<h3>Awards & Recognition</h3>
<ul>
  <li>...</li>
</ul>

## 5.11 Reception & Response

### Purpose

Summarize meaningful review, scholarly, critical, or reader response.

### Use For

Books with useful reception evidence.

### Target Length

```text
40-120 words
```

### Content Rules

Use paraphrase-first handling.

Allowed:

- short paraphrased review/reception summaries
- scholarly response
- debate or controversy
- reputation over time
- common praise or criticism when source-grounded

Avoid:

- long review quotes
- copied blurbs
- unsupported claims of acclaim
- publisher hype treated as independent reception

### HTML Pattern

```html
<h3>Reception & Response</h3>
<p>...</p>
```

## 5.12 Series / Sequence Notes

### Purpose

Explain series placement, reading order, or standalone status.

### Use For

Series fiction, multi-volume nonfiction, numbered scholarly series, gaming series, and technical book series.

### Target Length

```text
1-3 sentences or 1-3 bullets
```

### Content Rules

Include:

- series name
- book number or sequence position
- whether it stands alone
- where it fits chronologically or thematically

### HTML Pattern

```html
<h3>Series / Sequence Notes</h3>
<p>...</p>
```

## 5.13 Edition / Translation Notes

### Purpose

Capture meaningful edition, translation, revision, or publication-state information.

### Use For

Translated works, revised editions, critical editions, reprints, major edition differences, older works, technical manuals, and gaming guides.

### Target Length

```text
1-4 bullets
```

### Content Rules

Use for:

- revised edition
- expanded edition
- translation history
- critical edition features
- original publication date
- edition-specific features
- version/platform relevance for technical or gaming works

### HTML Pattern

```html
<h3>Edition / Translation Notes</h3>
<ul>
  <li>...</li>
</ul>
```

## 5.14 Companion Reads

### Purpose

Suggest related books for discovery and collection navigation.

### Use For

Only when useful and reasonably supported.

### Target Length

```text
2-4 bullets
```

### Content Rules

This section should be conservative.

Companion reads may come from:

- known books in the user's library
- widely related scholarly works
- related books in the same field or topic
- prior/subsequent works by the same author
- books sharing a subject, period, method, or theme

Each companion read should include a short reason.

Avoid inventing ownership or claiming a book is in the library unless confirmed.

### HTML Pattern

```html
<h3>Companion Reads</h3>
<ul>
  <li><i>Title</i> by Author - reason.</li>
</ul>
```

## 5.15 Source Notes

### Purpose

Document the evidence basis for the generated comments.

### Use For

Always.

### Target Length

```text
3-6 bullets
```

### Content Rules

Source Notes should explain what kinds of sources informed the comment.

Examples:

```text
Publisher description used for scope and overview.
Library catalog metadata used for publication and subject context.
Award record used for recognition note.
Review/reception details paraphrased from available source summaries.
Author or institutional biography used for author context.
No independent reception source found during this pass.
```

Source Notes should distinguish between:

- publisher description
- library catalog metadata
- award body information
- review/reception source
- author/institutional biography
- inferred classification or reading guidance

Source Notes should be concise. They are not a research essay.

### HTML Pattern

```html
<h3>Source Notes</h3>
<ul>
  <li>...</li>
  <li>...</li>
</ul>
```

Source Notes should normally be the final section.

## 6. Conditional Rendering Rules

Do not render empty headers.

If a section has no useful content, omit the section entirely.

Required behavior:

```text
No empty headers.
No placeholder text.
No "not available" sections unless absence itself is useful.
No generic filler.
```

Bad:

```html
<h3>Reception & Response</h3>
<p>No reception found.</p>
```

Better:

```text
Omit the section.
```

Exception:

A Source Notes bullet may mention absence of evidence when it matters:

```html
<li>No independent reception source was used during this pass.</li>
```

## 7. Length and Density Rules

The comments field should be rich and inviting, but not bloated.

Recommended section caps:

| Section | Target Length |
|---|---:|
| Overview | 80-140 words |
| Central Argument / Premise / Scope | 50-100 words |
| Why It Matters | 60-120 words |
| Why Read It | 60-120 words |
| Notable Details | 2-4 bullets |
| Themes & Threads | 4-8 phrases or short bullets |
| Reading Experience | 40-90 words |
| Author / Editor Context | 40-90 words |
| Historical / Cultural Context | 60-130 words |
| Awards & Recognition | 1-4 bullets |
| Reception & Response | 40-120 words |
| Series / Sequence Notes | 1-3 sentences or bullets |
| Edition / Translation Notes | 1-4 bullets |
| Companion Reads | 2-4 bullets |
| Source Notes | 3-6 bullets |

A typical generated comment should usually remain in the range:

```text
700-1,500 words
```

Longer comments may be acceptable for especially important, complex, or collection-defining works, but should be intentional.

## 8. HTML Markup Standard

Use simple, portable HTML.

Recommended tags:

```html
<h3>Section Header</h3>
<p>Paragraph text.</p>
<ul>
  <li>Bullet text.</li>
</ul>
<i>Title</i>
<b>Label:</b>
```

Avoid:

```html
<h1>
<h2>
<table>
<div>
<span style="">
inline CSS
images
scripts
complex nested structures
copied publisher blurbs
long review quotes
```

Reasons:

- simple HTML is more portable
- simple HTML is easier to diff
- simple HTML is easier to validate in TSV/report workflows
- simple HTML is less likely to render strangely in Calibre

## 9. Copyright and Quotation Rules

The comments module should be paraphrase-first.

Avoid copying:

- long publisher descriptions
- long review excerpts
- jacket copy
- blurbs
- copyrighted summaries
- lengthy author bios

Short quotes may be used only when clearly useful and compliant with applicable quotation limits.

Preferred approach:

```text
Use sources to understand the book.
Write original, concise, source-grounded descriptions.
Mention source types in Source Notes.
```

## 10. Confidence Model

The Comments module should use a confidence value for proposed generated comments.

Allowed values:

```text
High - Source Grounded
Medium - Source Supported
Low - Manual Review Recommended
```

### High - Source Grounded

Use when most key claims are supported by strong sources such as publisher pages, library catalog records, award records, review sources, author/institutional pages, or table-of-contents/preview material.

### Medium - Source Supported

Use when the comment is mostly supported, but some sections depend on broader inference from metadata, subject matter, or limited source availability.

### Low - Manual Review Recommended

Use when source coverage is thin, claims are uncertain, the book is obscure, or the generated comment includes content that should be reviewed before apply.

Rows with this confidence should normally use:

```text
ManualReviewRequired = Yes
```

## 11. Manual Review Triggers

Manual review should be required when:

- source coverage is weak
- book identity is uncertain
- title/author metadata may be wrong
- edition identity is uncertain
- generated comment includes uncertain reception claims
- generated comment includes companion reads that were not verified
- generated comment includes complex series/sequence claims
- generated comment includes possible spoilers
- existing comments contain substantial content that may be overwritten
- proposed comments are unusually long
- proposed comments contain raw copied source text
- generated HTML appears malformed
- confidence is `Low - Manual Review Recommended`

## 12. Existing Comments Handling

The comments module should treat existing comments as high-value data.

Default behavior should be:

```text
Do not overwrite substantial existing comments without review.
```

Potential future handling modes:

| Mode | Meaning |
|---|---|
| Replace | Replace existing comments entirely |
| Append | Append generated comments below existing comments |
| Prepend | Place generated comments above existing comments |
| Merge | Attempt structured merge |
| Skip | Do not modify comments |

For v0.6, the safest initial mode should be:

```text
Replace only when existing comments are blank or clearly low-value.
Manual review required when existing comments are substantial.
```

## 13. Section Ordering

Default order:

```text
Overview
Central Argument / Premise / Scope
Why It Matters
Why Read It
Historical / Cultural Context
Notable Details
Themes & Threads
Reading Experience
Author / Editor Context
Awards & Recognition
Reception & Response
Series / Sequence Notes
Edition / Translation Notes
Companion Reads
Source Notes
```

Notes:

- Source Notes should normally remain last.
- Historical / Cultural Context may move earlier for history-heavy books.
- Series / Sequence Notes may move earlier for series fiction.
- Edition / Translation Notes may move earlier when edition identity is central.
- Not all sections should appear for every book.

## 14. Minimum Useful Comment

A minimum useful generated comment should include:

```text
Overview
Central Argument / Premise / Scope
Why It Matters or Why Read It
Source Notes
```

For reference works, this may become:

```text
Overview
Scope & Use
Best Used For
Source Notes
```

For fiction, this may become:

```text
Overview
Premise
Why Read It
Source Notes
```

## 15. Ideal Scholarly Nonfiction Example Skeleton

```html
<h3>Overview</h3>
<p>...</p>

<h3>Central Argument</h3>
<p>...</p>

<h3>Why It Matters</h3>
<p>...</p>

<h3>Why Read It</h3>
<p>...</p>

<h3>Historical Context</h3>
<p>...</p>

<h3>Notable Details</h3>
<ul>
  <li>...</li>
  <li>...</li>
  <li>...</li>
</ul>

<h3>Themes & Threads</h3>
<ul>
  <li>...</li>
  <li>...</li>
  <li>...</li>
</ul>

<h3>Reading Experience</h3>
<p>...</p>

<h3>Author Context</h3>
<p>...</p>

<h3>Awards & Recognition</h3>
<ul>
  <li>...</li>
</ul>

<h3>Source Notes</h3>
<ul>
  <li>...</li>
  <li>...</li>
  <li>...</li>
</ul>
```

## 16. Operating Rules

The comments field should be:

```text
Useful
Readable
Source-grounded
Curiosity-building
HTML-simple
Conditionally rendered
Safe to review
Safe to diff
```

The comments field should not be:

```text
Generic
Bloated
Unsourced
Overwritten carelessly
Filled with empty headers
A dumping ground for copied blurbs
A substitute for structured metadata fields
```

## 17. Implementation Notes for Future Scripts

Future scripts should support:

- export of current title, authors, identifiers, tags, existing comments, awards, LCC, and other context fields
- proposed comments as HTML
- template profile tracking
- change reason tracking
- confidence tracking
- manual review blocking
- source notes tracking
- dry-run comparison
- summary reporting
- apply confirmation
- verification after apply

Initial comments scripts should be built in this order:

```text
Export-CalibreBatchForComments.ps1
Test-CommentsDryRun.ps1
Write-CommentsSummary.ps1
Invoke-CommentsApply.ps1
Test-CommentsVerify.ps1
```

Apply should be deferred until export, dry run, and summary behavior are stable.

