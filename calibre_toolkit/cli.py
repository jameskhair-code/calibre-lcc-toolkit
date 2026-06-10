"""
Calibre Toolkit CLI entry point.
Run: calibre-toolkit --help
"""

from __future__ import annotations

from .commands._common import app, _TIER_DEFAULTS_HELP

# Importing each command module registers its handlers on `app` as a
# side-effect. Import order is registration order — kept identical to the
# pre-v1.9 single-file cli.py so help output is unchanged.
from .commands import clean_titles as _clean_titles
from .commands import enrich_identifiers as _enrich_identifiers
from .commands import lcc_enrich as _lcc_enrich
from .commands import tags_enrich as _tags_enrich
from .commands import tags_cleanup as _tags_cleanup
from .commands import comments_enrich as _comments_enrich
from .commands import clean_identifiers as _clean_identifiers
from .commands import unflag_manual as _unflag_manual
from .commands import tags_review as _tags_review
from .commands import audit as _audit
from .commands import audit_log as _audit_log
from .commands import regrade as _regrade
from .commands import menu as _menu
from .commands import library_info as _library_info
from .commands import doctor as _doctor
from .commands import init as _init
from .commands import setup_columns as _setup_columns

# Append the tier-defaults block to every command that runs a tiered
# bulk-approval prompt. Typer reads __doc__ when rendering --help, so
# mutating it after definition keeps the single-source-of-truth block out
# of every individual docstring.
for _cmd in (_clean_titles.clean_titles, _enrich_identifiers.enrich_identifiers,
             _lcc_enrich.lcc_enrich, _tags_enrich.tags_enrich,
             _comments_enrich.comments_enrich):
    _cmd.__doc__ = (_cmd.__doc__ or "").rstrip() + "\n" + _TIER_DEFAULTS_HELP + "\n"


if __name__ == "__main__":
    app()
