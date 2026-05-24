"""Tests for the model alias resolver.

Pure-function tests; no Anthropic calls.
"""

from __future__ import annotations

import pytest

from calibre_toolkit import models as models_mod
from calibre_toolkit.models import ResolvedModel, list_aliases, resolve_model


class TestResolveAliases:
    def test_fast_resolves_to_haiku(self):
        r = resolve_model("fast")
        assert r.alias == "fast"
        assert "haiku" in r.model_id.lower()

    def test_latest_resolves_to_opus(self):
        r = resolve_model("latest")
        assert r.alias == "latest"
        # Whatever "latest" maps to today, the alias name round-trips.
        assert r.model_id == list_aliases()["latest"]

    def test_legacy_resolves_to_sonnet_4_6(self):
        r = resolve_model("legacy")
        assert r.alias == "legacy"
        assert r.model_id == "claude-sonnet-4-6"

    def test_case_insensitive_alias(self):
        r = resolve_model("LATEST")
        assert r.alias == "latest"


class TestResolveLiteralIds:
    def test_full_model_id_passes_through(self):
        r = resolve_model("claude-sonnet-4-6")
        assert r.model_id == "claude-sonnet-4-6"
        assert r.alias is None

    def test_unknown_id_passes_through(self):
        """Future models we don't know about must not be blocked."""
        r = resolve_model("claude-future-99-9")
        assert r.model_id == "claude-future-99-9"
        assert r.alias is None
        assert r.deprecation_note is None


class TestResolveDefaults:
    def test_none_defaults_to_latest(self):
        r = resolve_model(None)
        assert r.alias == "latest"
        assert r.model_id == list_aliases()["latest"]

    def test_empty_string_defaults_to_latest(self):
        r = resolve_model("")
        assert r.alias == "latest"

    def test_whitespace_only_defaults_to_latest(self):
        r = resolve_model("   ")
        assert r.alias == "latest"


class TestDeprecation:
    def test_deprecated_alias_emits_note_and_resolves(self, monkeypatch, caplog):
        """When a previously-shipped alias is moved into the deprecation
        table, the resolver should pass through to the replacement and
        attach a deprecation_note."""
        monkeypatch.setitem(
            models_mod._DEPRECATED_ALIASES, "previous", "latest",
        )
        r = resolve_model("previous")
        assert r.alias == "latest"
        assert r.deprecation_note is not None
        assert "deprecated" in r.deprecation_note

    def test_deprecated_model_id_passes_through_with_warning(self, monkeypatch):
        """A retired full model ID still resolves to itself (so reproducibility
        pins keep working), but a deprecation note is attached."""
        monkeypatch.setitem(
            models_mod._DEPRECATED_MODELS, "claude-test-deprecated", "claude-sonnet-4-6",
        )
        r = resolve_model("claude-test-deprecated")
        assert r.model_id == "claude-test-deprecated"
        assert r.alias is None
        assert r.deprecation_note is not None
        assert "claude-sonnet-4-6" in r.deprecation_note


class TestListAliases:
    def test_returns_known_aliases(self):
        aliases = list_aliases()
        assert {"fast", "latest", "legacy"} <= set(aliases)

    def test_returned_dict_is_a_copy(self):
        aliases = list_aliases()
        aliases["x"] = "y"
        # Internal table unaffected.
        assert "x" not in list_aliases()


class TestAIClientIntegration:
    """AIClient.__init__ must resolve the alias and expose both the
    concrete model ID and the alias name."""

    def test_alias_resolved_on_construction(self):
        from calibre_toolkit.ai import AIClient
        c = AIClient(api_key="x", model="fast")
        assert c.model_alias == "fast"
        assert "haiku" in c.model.lower()

    def test_literal_id_unchanged(self):
        from calibre_toolkit.ai import AIClient
        c = AIClient(api_key="x", model="claude-sonnet-4-6")
        assert c.model == "claude-sonnet-4-6"
        assert c.model_alias is None

    def test_none_model_uses_latest_alias(self):
        from calibre_toolkit.ai import AIClient
        c = AIClient(api_key="x")
        assert c.model_alias == "latest"
        assert c.model == list_aliases()["latest"]
