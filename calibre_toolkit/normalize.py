"""
Deterministic text normalization applied after AI suggestions.
Converts non-ASCII characters to their ASCII equivalents so the
library uses plain characters throughout.
"""

import unicodedata

# Characters that don't decompose cleanly via NFKD and need explicit mapping.
# Lowercase entries — uppercase variants are handled automatically below.
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


def remove_diacritics(text: str) -> str:
    """
    Convert all accented/special characters to plain ASCII equivalents.
    Uses Unicode decomposition for most characters; explicit map for
    characters that don't decompose cleanly (ß, æ, œ, etc.).
    """
    # Apply explicit special-case map first
    for char, replacement in _CHAR_MAP.items():
        text = text.replace(char, replacement)

    # Decompose remaining accented characters (é→e, ä→a, ñ→n, etc.)
    # NFKD splits characters into base + combining diacritic codepoints
    decomposed = unicodedata.normalize('NFKD', text)

    # Keep only non-combining characters (strips the diacritic marks)
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Full normalization pipeline for a title or author string."""
    return remove_diacritics(text)
