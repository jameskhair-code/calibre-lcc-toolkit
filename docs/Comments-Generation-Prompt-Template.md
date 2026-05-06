# Comments Generation Prompt Template

## 1. Purpose

This document defines the reusable prompt/template used to generate structured HTML comments for the Calibre Metadata Toolkit Comments module.

The goal is not to create a generic book summary.

The goal is to create a source-grounded curator note that makes the book more discoverable, more interesting, and more likely to be opened later.

The generated comment should help answer:

```text
What is this book?
What is it arguing or doing?
Why does it matter?
Why would I want to read it?
What unique or memorable details make it appealing?
What awards or recognition can be identified?
Where did the information come from?
```

For v0.6, generated comments are used only for:

```text
Export -> Dry Run -> Summary
```

Apply and verify behavior are deferred.

## 2. Required Input Context

When generating comments, use the exported comments source/import TSV row as the primary input.

Recommended input fields:

```text
CalibreId
Title
Authors
ISBN
Identifiers
Publisher
Published
Series
SeriesIndex
Tags
ExistingComments
ExistingCommentsTextPreview
ExistingCommentsLength
ExistingCommentsHash
Award Programs
Award Names
Award Entries
Existing LCC
Existing LCC Primary Class
Existing LCC Secondary Class
Existing LCC Classification Path
```

The input row may not have all fields populated.

Do not invent missing metadata.

If a field is blank, work from available metadata and research.

## 3. Recommended Generation Workflow

For each book:

```text
1. Confirm book identity from title, author, identifiers, publisher, and publication date.
2. Use existing Calibre comments as a starting point, not as text to copy wholesale.
3. Research or infer the central argument/premise from reliable sources.
4. Research awards and recognition.
5. Identify book-specific notable details when possible.
6. If book-specific details are thin, use honest subject-specific hooks.
7. Use LCC/tags/awards/context to enrich Themes & Threads.
8. Write original structured HTML.
9. Include visible Source Notes.
10. Return TSV-ready workflow fields.
```

## 4. Research Priorities

When research is available, prioritize:

```text
Publisher page
Library catalog record
Award body page
Author/institutional biography
Table of contents or preview
Reliable review or scholarly reception source
Known series or edition information
```

Do not rely on a single marketing blurb when better sources are available.

Do not copy publisher descriptions directly. Use them as evidence and paraphrase.

## 5. Awards & Recognition Research

The Awards & Recognition section should be declarative and research-driven.

It should not be limited only to awards already present in Calibre metadata.

When generating comments, actively check whether the book has identifiable awards, finalist placements, shortlist/longlist status, honorable mentions, best-book recognition, or other meaningful recognition.

Use precise status language when known:

```text
Winner
Finalist
Shortlisted
Longlisted
Honorable Mention
Named a Best Book by...
```

Avoid using `nominated` unless the source itself uses that wording.

Only include award claims when the evidence is solid.

If an award claim is uncertain, omit it from the visible Awards & Recognition section.

If useful, mention in Source Notes that award research was performed and no additional recognition was confidently identified.

## 6. Notable Details / Curiosity Hook Standard

The Notable Details section should help sell the book.

Prefer book-specific details:

```text
surprising archival sources
unusual case studies
memorable people/events/settings
distinctive method
authorial backstory
important primary sources
strange historical episode
unusual maps/illustrations/tables/appendices
```

If book-specific details are unavailable, use subject-specific hooks that honestly reflect the book's topic, setting, problem, or historical world.

Good Notable Details should make the reader think:

```text
I did not know that.
That is a weirdly specific angle.
That sounds like a book worth opening.
```

Avoid vague bullets such as:

```text
Explores many interesting issues.
Provides important historical context.
Covers a fascinating topic.
```

## 7. Why Read It Standard

The Why Read It section should actively make the case for opening the book.

It should answer:

```text
Why would I pick this up instead of another award-winning book?
What curiosity does it reward?
What tension, oddity, problem, or payoff makes it worth reading?
What mood or research interest does it fit?
```

Good framing:

```text
Read this when you want...
The draw here is...
This is especially useful if...
What makes this one tempting is...
```

Avoid hype, sales-copy tone, and generic praise.

## 8. Why It Matters Standard

Keep the section label:

```text
Why It Matters
```

This section should explain the book's intellectual, historical, cultural, scholarly, or field significance.

It should not simply say that the book matters because it won or was shortlisted for an award.

It should explain significance beyond the award label:

```text
What debate does it contribute to?
What topic does it illuminate?
What common interpretation does it complicate?
What gap does it fill?
Why would scholars, reviewers, or prize committees have cared?
```

## 9. Default Scholarly Nonfiction Section Order

Use this default section order for scholarly nonfiction:

```text
Overview
Central Argument
Why It Matters
Why Read It
Notable Details
Themes & Threads
Reading Experience
Awards & Recognition
Source Notes
```

Optional sections may be added when strongly useful:

```text
Author Context
Historical Context
Reception & Response
Series / Sequence Notes
Edition / Translation Notes
Companion Reads
```

Do not output empty headers.

## 10. HTML Output Rules

Use simple Calibre-friendly HTML.

Allowed/recommended:

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
iframes
large copied blurbs
long review quotes
```

The output should be easy to store in a TSV cell and easy to review in dry-run summaries.

## 11. Length Targets

Recommended length targets:

```text
Overview: 80-140 words
Central Argument: 50-100 words
Why It Matters: 60-120 words
Why Read It: 60-120 words
Notable Details: 2-4 bullets
Themes & Threads: 4-8 bullets
Reading Experience: 40-90 words
Awards & Recognition: 1-4 bullets
Source Notes: 3-6 bullets
```

Typical total proposed comment length:

```text
2,000-5,000 characters
```

Longer is acceptable when justified, but avoid runaway essays.

## 12. Source Notes Standard

Every generated comment must include a visible final section:

```html
<h3>Source Notes</h3>
<ul>
  <li>...</li>
</ul>
```

Source Notes should identify the types of sources used.

Examples:

```text
Publisher description used for scope and overview.
Library catalog metadata used for bibliographic context.
Award body records used for awards and recognition.
Existing Calibre LCC classification used for subject framing.
Review or reception sources used for reception notes.
No additional award recognition was confidently identified during this pass.
```

Source Notes should be concise.

Do not turn Source Notes into a bibliography unless specifically needed.

## 13. Workflow Fields to Return

For each generated comments row, return the following workflow fields:

```text
CommentsTemplateProfile
CommentsMode
ChangeReason
Confidence
ManualReviewRequired
SourceNotes
ProposedComments
```

Default values for this library's scholarly nonfiction pilot:

```text
CommentsTemplateProfile = Scholarly Nonfiction
CommentsMode = Prepend
ChangeReason = Structured comments generation for review
Confidence = Medium - Source Supported
ManualReviewRequired = No
```

Use `High - Source Grounded` only when the comment is strongly supported by multiple reliable sources.

Use `Low - Manual Review Recommended` when identity, awards, reception, edition details, or major claims are uncertain.

## 14. Recommended Output Format for ChatGPT

When generating comments in chat, return one block per book.

Use this structure:

```text
Title:
Authors:
CalibreId:

CommentsTemplateProfile:
CommentsMode:
ChangeReason:
Confidence:
ManualReviewRequired:
SourceNotes:

ProposedComments:
<single-line HTML here>
```

The `ProposedComments` value should be one line of HTML where possible.

Avoid Markdown bullets inside `ProposedComments`. Use HTML lists.

## 15. Copy/Paste Safety

Before returning generated comments, check:

```text
No empty headers.
No Markdown syntax inside ProposedComments.
No unsupported HTML tags.
No placeholder text.
No copied publisher blurb.
No uncertain award claims stated as fact.
Source Notes HTML section is present.
SourceNotes workflow field is populated.
```

If any item fails, set:

```text
ManualReviewRequired = Yes
```

and explain why.

## 16. Master Prompt

Use this prompt when generating proposed comments from exported Calibre metadata.

```text
You are generating structured HTML comments for a Calibre library using the Calibre Metadata Toolkit Comments module.

Goal:
Create a source-grounded curator note that makes the book more discoverable, more interesting, and more likely to be opened later. Do not write a generic summary.

Use the provided Calibre metadata row as the starting point. Use existing comments as evidence, but do not copy them wholesale. If external research is available, use reliable sources to verify book identity, central argument, awards/recognition, author context, notable details, and reception when useful.

Preserve the section label "Why It Matters."

Awards & Recognition:
Research awards and recognition beyond the existing Calibre award metadata when possible. Include only confidently supported awards or recognition. Use precise status language such as Winner, Finalist, Shortlisted, Longlisted, Honorable Mention, or Named a Best Book by. Avoid "nominated" unless the source uses that wording.

Notable Details:
Prefer book-specific details. If book-specific details are thin, include subject-specific hooks that honestly reflect the book's topic, setting, problem, or historical world. This section should help sell the book.

Why Read It:
Make a specific, persuasive case for why this book is worth opening. Avoid hype and generic praise.

HTML:
Use simple Calibre-friendly HTML only: h3, p, ul, ol, li, i, em, b, strong, br. Do not use h1, h2, tables, divs, inline styles, images, scripts, or iframes.

Required sections for scholarly nonfiction:
Overview
Central Argument
Why It Matters
Why Read It
Notable Details
Themes & Threads
Reading Experience
Awards & Recognition
Source Notes

Do not output empty headers.

Return:
CommentsTemplateProfile
CommentsMode
ChangeReason
Confidence
ManualReviewRequired
SourceNotes
ProposedComments

Default values:
CommentsTemplateProfile = Scholarly Nonfiction
CommentsMode = Prepend
ChangeReason = Structured comments generation for review
Confidence = Medium - Source Supported
ManualReviewRequired = No

Use High - Source Grounded only when strongly supported by multiple reliable sources.
Use Low - Manual Review Recommended when major claims are uncertain.

The ProposedComments value must be TSV-friendly single-line HTML when possible.
```

## 17. Acceptance Criteria

A generated comment is acceptable when:

```text
It passes the dry-run safety gate.
It makes the book more discoverable.
It makes the book more appealing to open.
It includes concrete Notable Details or honest subject-specific hooks.
It explains Why It Matters beyond the award label.
It includes researched, declarative awards/recognition when confidently supported.
It includes Source Notes.
It preserves existing comments by using Prepend when substantial existing comments exist.
```