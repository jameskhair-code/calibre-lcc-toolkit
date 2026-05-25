"""
Deterministic text normalization applied after AI suggestions.

Scope and intent
----------------
This module is designed to "Americanize" Latin-script titles and author
names — strip Latin diacritics (café → cafe, Müller → Muller) and
normalise dash variants (em-dash, en-dash, etc.) to a plain
hyphen-minus. The collection it ships with is a personal English-
language reading list, and the chosen behaviour is to keep all stored
text in plain ASCII where possible.

Non-Latin scripts pass through intact. Specifically:

  - CJK characters are preserved as-is.
  - Cyrillic letters with combining marks (e.g. й, ў) are preserved as
    their composed form — they are distinct letters, not decorated
    versions of a base letter, and demoting them would change the word.
  - Greek polytonic accents are preserved.
  - Arabic and Hebrew vowel marks are preserved.
  - Emoji and pictographs pass through.

Combining marks are stripped **only** when the base character is in the
Latin script. This is the rule that prevents Достоевский ("Dostoevsky"
in Russian) from being silently rewritten as Достоевскии.

See ROADMAP.md item 15.
"""

import unicodedata

# Characters that don't decompose cleanly via NFKD and need explicit mapping.
# All entries here are Latin script — the "Americanization" intent only
# applies to Latin. Lowercase entries; uppercase variants generated below.
_SPECIAL = {
    'ß': 'ss',
    'æ': 'ae',
    'œ': 'oe',
    'þ': 'th',
    'ð': 'd',
    'ø': 'o',
    'ł': 'l',
    'đ': 'd',
    'ħ': 'h',
    'ı': 'i',   # Turkish dotless i
    'ŋ': 'n',
    'ŧ': 't',
}

# Build a full map including uppercase forms
_CHAR_MAP: dict[str, str] = {}
for _lower, _ascii in _SPECIAL.items():
    _CHAR_MAP[_lower] = _ascii
    _upper = _lower.upper()
    if _upper != _lower:
        _CHAR_MAP[_upper] = _ascii.capitalize()


def _is_latin_base(char: str) -> bool:
    """Whether `char` is a base (non-combining) character in the Latin
    script. Used to decide whether a following combining mark should be
    stripped (Latin: yes; everything else: keep)."""
    if not char:
        return False
    try:
        return unicodedata.name(char, "").startswith("LATIN ")
    except ValueError:
        return False


def remove_diacritics(text: str) -> str:
    """
    Strip Latin-script diacritics, replacing characters that don't
    decompose cleanly (ß, æ, œ, etc.) via the explicit map.

    Non-Latin scripts are preserved intact — see module docstring for the
    rationale and the list of scripts covered.
    """
    # 1. Explicit-map substitutions (Latin-only by construction).
    for char, replacement in _CHAR_MAP.items():
        text = text.replace(char, replacement)

    # 2. NFKD-decompose and strip combining marks ONLY when the preceding
    #    base character is Latin. This is the rule that protects Cyrillic
    #    Й, Greek polytonic, Arabic/Hebrew vowel marks, etc. from silent
    #    demotion.
    decomposed = unicodedata.normalize("NFKD", text)
    out: list[str] = []
    last_base = ""
    for ch in decomposed:
        if unicodedata.combining(ch):
            if _is_latin_base(last_base):
                continue  # Strip — Latin base, plain ASCII downstream.
            out.append(ch)   # Keep — non-Latin base, mark is significant.
        else:
            out.append(ch)
            last_base = ch

    # 3. Re-compose so non-Latin base+mark sequences land as single
    #    precomposed codepoints (e.g. И + ◌̆ → Й) for downstream
    #    rendering predictability.
    return unicodedata.normalize("NFC", "".join(out))


# Dash characters to normalize to plain hyphen-minus
_DASH_MAP = {
    '—': '-',   # em-dash —
    '–': '-',   # en-dash –
    '‒': '-',   # figure dash ‒
    '‑': '-',   # non-breaking hyphen ‑
    '‐': '-',   # hyphen ‐
    '―': '-',   # horizontal bar ―
    '−': '-',   # minus sign −
    '﹘': '-',   # small em-dash ﹘
    '﹣': '-',   # small hyphen-minus ﹣
    '－': '-',   # fullwidth hyphen-minus －
}


def normalize_dashes(text: str) -> str:
    """Convert all dash variants to a plain hyphen-minus (-)."""
    for dash, replacement in _DASH_MAP.items():
        text = text.replace(dash, replacement)
    return text


def normalize_text(text: str) -> str:
    """Full normalization pipeline for a title or author string."""
    text = normalize_dashes(text)
    text = remove_diacritics(text)
    return text
