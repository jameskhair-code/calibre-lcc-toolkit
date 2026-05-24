"""
Wraps Calibre's fetch-ebook-metadata CLI to look up external identifiers.
Returns OPF XML parsed into a FetchResult with a dict of identifier type → value.
"""

from __future__ import annotations
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Literal

from .logging_config import get_logger
from .retry import retry_with_backoff

_log = get_logger(__name__)


class _TransientFetchError(Exception):
    """Internal sentinel — a fetch failure worth retrying."""


# Identifier types we surface, in display order
IDENTIFIER_TYPES = ["isbn", "amazon", "goodreads", "google", "oclc", "openlibrary", "librarything"]

# Internal Calibre identifiers to ignore
_SKIP_TYPES = {"calibre", "uuid"}

_DC_NS  = "http://purl.org/dc/elements/1.1/"
_OPF_NS = "http://www.idpf.org/2007/opf"


@dataclass
class FetchResult:
    identifiers: dict[str, str] = field(default_factory=dict)
    title: str = ""
    authors: list[str] = field(default_factory=list)
    lookup_method: Literal["isbn", "title_author"] = "isbn"
    confidence: Literal["high", "low"] = "high"
    error: str | None = None  # None = success; otherwise short error description


class IdentifierFetcher:
    def __init__(
        self,
        fetch_path: str = "fetch-ebook-metadata",
        timeout: int = 45,
        max_retries: int = 2,
    ):
        self.fetch_path = fetch_path
        self.timeout = timeout
        self.max_retries = max(1, max_retries)

    def probe(self) -> str | None:
        """Return None if the binary is reachable, or an error string if not."""
        try:
            result = subprocess.run(
                [self.fetch_path, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            return None
        except FileNotFoundError:
            return (
                f"fetch-ebook-metadata not found at '{self.fetch_path}'.\n\n"
                "Add 'fetch_ebook_metadata_path' to config.json under the 'identifiers' "
                "section, pointing to fetch-ebook-metadata.exe in your Calibre folder.\n\n"
                "Example: \"fetch_ebook_metadata_path\": "
                "\"C:\\\\Program Files\\\\Calibre2\\\\fetch-ebook-metadata.exe\""
            )
        except subprocess.TimeoutExpired:
            return f"fetch-ebook-metadata timed out during probe ('{self.fetch_path}')."

    def fetch(
        self,
        isbn: str | None = None,
        title: str | None = None,
        authors: list[str] | None = None,
    ) -> FetchResult:
        """Fetch identifiers using ISBN if available, otherwise title+author."""
        if isbn:
            return self._run(["--isbn", isbn], "isbn", "high")
        if title and authors:
            return self._run(["-t", title, "-a", authors[0]], "title_author", "low")
        return FetchResult(error="no_input")

    def _run(
        self,
        extra_args: list[str],
        method: Literal["isbn", "title_author"],
        confidence: Literal["high", "low"],
    ) -> FetchResult:
        cmd = [self.fetch_path, "--opf"] + extra_args

        def _attempt() -> FetchResult:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout,
                )
            except FileNotFoundError:
                # Missing binary won't recover on retry.
                return FetchResult(lookup_method=method, confidence=confidence, error="binary_not_found")
            except subprocess.TimeoutExpired as e:
                # Timeouts may be transient — let retry_with_backoff handle them.
                raise _TransientFetchError("timeout") from e

            if not result.stdout.strip():
                stderr = result.stderr.strip()
                # Heuristic: stderr mentioning network/timeout/ssl => transient.
                lowered = stderr.lower()
                if any(tok in lowered for tok in ("timeout", "network", "temporar", "ssl", "connection")):
                    raise _TransientFetchError(stderr[:120] or "transient")
                error_msg = f"no_results: {stderr[:120]}" if stderr else "no_results"
                return FetchResult(lookup_method=method, confidence=confidence, error=error_msg)

            fr = _parse_opf(result.stdout)
            fr.lookup_method = method
            fr.confidence = confidence
            return fr

        try:
            return retry_with_backoff(
                _attempt,
                max_retries=self.max_retries,
                retry_on=(_TransientFetchError,),
                description=f"fetch-ebook-metadata ({method})",
            )
        except _TransientFetchError as e:
            # Final attempt timed out or hit a transient stderr — surface
            # the same error code the previous version would have produced
            # so downstream display is unchanged.
            msg = str(e)
            error = "timeout" if msg == "timeout" else f"no_results: {msg}"
            return FetchResult(lookup_method=method, confidence=confidence, error=error)


def _parse_opf(xml_str: str) -> FetchResult:
    result = FetchResult()
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        result.error = "opf_parse_error"
        return result

    # Title
    el = root.find(f".//{{{_DC_NS}}}title")
    if el is not None and el.text:
        result.title = el.text.strip()

    # Authors
    for creator in root.findall(f".//{{{_DC_NS}}}creator"):
        if creator.text:
            result.authors.append(creator.text.strip())

    # Identifiers — scheme attribute may use full namespace or plain name
    for ident in root.findall(f".//{{{_DC_NS}}}identifier"):
        scheme = (
            ident.get(f"{{{_OPF_NS}}}scheme")
            or ident.get("opf:scheme")
            or ident.get("scheme")
            or ""
        ).lower().strip()
        value = (ident.text or "").strip()
        if scheme and value and scheme not in _SKIP_TYPES:
            result.identifiers[scheme] = value

    return result
