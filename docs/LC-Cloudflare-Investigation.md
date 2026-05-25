# LC Catalog Reachability — Cloudflare Investigation

**Discovered:** v1.3 item 12 smoke-test session (post-merge of PRs #10, #11).
**Status:** Open. Captures the investigation context so a future session can
resume without re-deriving anything. See ROADMAP.md item 12a for the
planned work.

---

## TL;DR

The Library of Congress public APIs (`www.loc.gov`, `lx2.loc.gov`) are
behind Cloudflare's JavaScript challenge. Python's `urllib` cannot solve
the challenge, so **every LC HTTP request from this tool currently
fails** — silently, with timeouts or HTML challenge pages where JSON was
expected. This has been the case for the entire v1.3 development cycle,
not just on the day of discovery. Item 8's honest-source-attribution
work means we are not silently claiming false LC hits (every fallback
correctly resolves to `[AI]`), but the v1.1 / v1.2 / v1.3 LC catalog
pipeline is effectively dormant until a workaround ships.

---

## What we tested

### 1. Direct HTTP via PowerShell `Invoke-WebRequest`, default UA

```powershell
Invoke-WebRequest -Uri "https://www.loc.gov/books/?q=9780394720241&fo=json&c=1" -UseBasicParsing
```

Response: a Cloudflare HTML challenge page (`"Just a moment..."` with
`_cf_chl_opt`, `__cf_chl_tk`, `cf-mitigated: challenge`). No JSON body.

### 2. Direct HTTP via PowerShell with a real-browser User-Agent

```powershell
$browserUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
Invoke-WebRequest -Uri "https://www.loc.gov/books/?q=9780394720241&fo=json&c=1" -UseBasicParsing -Headers @{"User-Agent" = $browserUA}
```

Response: same Cloudflare challenge page. **A realistic UA is not
sufficient.** Cloudflare requires actually solving the JS challenge,
which requires a JS engine and cookie persistence.

### 3. Python via the toolkit's own client (`lcc-enrich --dry-run`)

Every call to `www.loc.gov/books/?q=…` and `lx2.loc.gov/sru/?…` timed out
or failed with SSL handshake timeouts. The retry helper logged three
attempts per request and surrendered. Roughly equivalent to the
PowerShell behaviour — Cloudflare slow-drops the request because the
client can't solve the challenge.

---

## Why simple workarounds fail

| Approach | Why it doesn't work |
|---|---|
| Custom User-Agent | Cloudflare fingerprints far more than UA — TLS handshake, header order, cookie behaviour, etc. Tested; same challenge page. |
| Setting an `Accept: application/json` header | Doesn't bypass the challenge. The challenge fires before content negotiation. |
| Sending a fake `cf_clearance` cookie | Cookies are bound to a successful challenge solve. Can't be fabricated. |
| Hitting LC's `/item/{lccn}/?fo=json` instead of `/books/?q=` | Same Cloudflare zone, same protection. |
| Using `lx2.loc.gov` (SRU) instead of `www.loc.gov` | Subdomain is also protected. SSL handshake timeouts in our test runs. |

---

## What might work (each its own can of worms)

### Option A — `cloudscraper` Python library

- Small dependency (~150KB) that solves Cloudflare's older v1/v2
  challenges via a pure-Python evaluator.
- **Pros:** drop-in replacement for `urllib.request`. No browser needed.
- **Cons:** Cloudflare's v3 challenges are not always solvable. The
  library is community-maintained and lags behind Cloudflare updates by
  weeks. May silently start failing again at any point. The author
  reads the room and bumps the library when challenges change, but
  there's no SLA.

### Option B — `curl_cffi`

- Wraps libcurl with TLS-fingerprint impersonation. Mimics Chrome /
  Firefox at the TLS handshake level, which is the layer Cloudflare's
  bot detection inspects most closely.
- **Pros:** more robust against Cloudflare updates. Solves the TLS
  fingerprint problem at the network layer rather than the JS layer.
- **Cons:** much larger dependency (compiled C, platform-specific
  wheels). Doesn't solve JS challenges — only the
  fingerprint-detection layer. Cloudflare's stricter modes still
  challenge it.

### Option C — LC's bulk MARC datasets

- LC publishes bibliographic data as monthly MARC dumps via
  https://www.loc.gov/cds/products/MDSConnect-bibliographic.html
- **Pros:** no Cloudflare, no per-request lookups, no dependency on LC's
  live service.
- **Cons:** datasets are 10+ GB compressed. Requires local storage and
  index-building (a separate "LC database" mode for the toolkit).
  Updates are monthly, not live. Significant engineering work.

### Option D — LC OAI-PMH endpoint

- The OAI-PMH (Open Archives Initiative Protocol for Metadata
  Harvesting) endpoint at `http://lx2.loc.gov/cgi-bin/oai2_0` was
  historically whitelisted for harvesters. Not certain whether
  Cloudflare exempts it now.
- **Pros:** specifically designed for programmatic access; bots are the
  intended audience.
- **Cons:** XML-heavy; intended for bulk harvest, not single-record
  lookups; rate-limited.

### Option E — Drop direct LC and lean on Open Library

- Open Library does not Cloudflare-protect their public API.
- **Pros:** zero new dependencies. Already works in the cascade today.
- **Cons:** OL's LCC data is community-sourced and incomplete —
  particularly thin for older non-US editions, which is the population
  we most need LC for in the first place.

---

## Provenance: where each LCC field comes from today (LC unreachable)

With LC behind Cloudflare, the actual data flow is:

```
1. LC LCCN lookup        → blocked by Cloudflare → None
2. LC ISBN lookup        → blocked by Cloudflare → None
3. OL edition cascade
     ├─ OL work lookup   → works ✓
     ├─ OL editions list → works ✓
     └─ LC sibling ISBN  → blocked by Cloudflare → None
4. LC SRU title+author   → blocked by Cloudflare → None
5. OL direct ISBN        → works ✓ (when OL has lc_classifications)
6. AI fallback           → fires for every book without an OL hit
```

**For most books in the user's literary-prize library, the active path
is step 6 (AI).** This means:

| Output field | Real source today | Confidence |
|---|---|---|
| `lcc` (call number) | AI's training memory of how LC catalogues this author | Class letters reliable; specific Cutter / year are educated guesses |
| `lcc_primary_class` | Code-derived from the call number's first letter via `_derive_classes()` | Deterministic from the call number; reliable if class letter is right |
| `lcc_secondary_class` | Code-derived from the first 1–3 letters via `_derive_classes()` | Same as primary |
| `lcc_summary` | AI summary grounded in the Google Books description (item 11) | High — the description is authoritative source material |

The `[AI]` prefix on every Source-column entry today is correctly
reporting this. It is the v1.2 item 8 work doing exactly what it was
designed for.

---

## Pro / con: is `lcc_summary` (and the whole call-number field) worth
## keeping in this state?

This is an open product question raised by the user. Capturing it here
so a future session can take it on with full context.

### Case for keeping the call number (`lcc`) field as-is

- The **class letters** (P, D, Q, etc.) are reliable from the AI and
  drive the primary/secondary class fields, which *are* useful for
  shelf-style sorting and filtering.
- A "good guess" call number is better than no call number for personal
  use — it gives the book a place in the LC hierarchy.
- If LC reachability is restored later, the same AI-generated call
  numbers can be cross-checked and corrected without re-running the
  whole pipeline.

### Case for dropping or de-emphasising the `lcc` field

- The full call number with Cutter and year looks authoritative in the
  Calibre UI but is not catalog-verified. Without item 8's `[AI]`
  prefix in the review table, a future user could mistake it for a real
  catalog value.
- The Cutter is where AI fabrication is most likely (the AI may invent
  a Cutter that's plausible-looking but not the one LC actually uses
  for that author).
- The downstream value of having an exact Cutter is small for a
  personal library — sorting works fine on `lcc_primary_class` and
  `lcc_secondary_class` alone.
- Truncating to just the class portion (e.g. `PR9619.3` instead of
  `PR9619.3.K46 C66 1979`) communicates the confidence level honestly.

### Case for keeping `lcc_summary`

- Item 11 grounds it in the Google Books publisher description — this
  is the **most reliable** of the four LCC fields today.
- It's the field with the highest reading value: a one-sentence
  description that contextualises the book's subject without requiring
  the user to know what "PR9619.3.K46" means.
- It does not depend on LC reachability at all.

### Case for dropping `lcc_summary`

- Calibre already has a `comments` field (populated by step 04) that
  serves a similar prose-description role. Two prose fields per book
  may be redundant.
- The summary is currently AI-written even when grounded by Google
  Books — it's not a catalog-sourced field even in principle.

### Possible directions for a future PR

- **Option 1:** Keep all four fields as-is. The `[AI]` prefix already
  communicates the provenance honestly.
- **Option 2:** Truncate the call number to its supportable portion
  when LC is unreachable (`PR9619.3` not `PR9619.3.K46 C66 1979`).
  Document in `rules/lcc.md` PATH-04 or a new rule.
- **Option 3:** Make the call-number field optional — let users
  configure whether they want AI-generated call numbers at all, with
  the default being class letters only.
- **Option 4:** Drop `lcc_summary` if `comments` covers the same need.

No decision needed now. This is captured so the conversation can resume.

---

## What we actually built in PR #12

The item-12 cascade architecture is correct and will activate the
moment LC becomes reachable again. Today it produces value via the
re-enabled Open Library direct ISBN path only (step 5 above). The
hermetic tests cover the LC paths too, so the code is ready — only the
network reachability is missing.

When LC reachability is restored (via any of options A–E above), the
cascade lights up with zero further code changes. Hit-rate improvement
for UK / Commonwealth / international editions becomes measurable at
that point.
