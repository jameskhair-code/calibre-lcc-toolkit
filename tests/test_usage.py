"""Tests for token usage telemetry (item 13).

Covers TokenUsage arithmetic, Anthropic response parsing (both dict and
mock-object shapes), pricing math against the published Anthropic
rates, the UsageAggregate threadsafe accumulator, the persistent JSONL
log round-trip, and the human-formatted summary string.

AIClient integration is exercised at the call-stamping layer — we
verify that a stubbed Anthropic response's usage block flows into the
client's aggregate without making any real HTTP calls.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from calibre_toolkit import usage as usage_mod
from calibre_toolkit.usage import (
    TokenUsage,
    UsageAggregate,
    _resolve_price_table,
    cost_estimate_usd,
    format_summary,
    log_usage,
    parse_usage,
    replay_usage_log,
)


# ── TokenUsage ───────────────────────────────────────────────────────────────


class TestTokenUsage:
    def test_addition_sums_all_fields(self):
        a = TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=10, cache_read_input_tokens=200,
        )
        b = TokenUsage(
            input_tokens=5, output_tokens=2,
            cache_creation_input_tokens=1, cache_read_input_tokens=20,
        )
        c = a + b
        assert c.input_tokens == 105
        assert c.output_tokens == 52
        assert c.cache_creation_input_tokens == 11
        assert c.cache_read_input_tokens == 220

    def test_total_input_sums_every_input_tier(self):
        u = TokenUsage(
            input_tokens=100,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=700,
        )
        assert u.total_input == 1000

    def test_cache_hit_rate_zero_when_no_cache_reads(self):
        u = TokenUsage(input_tokens=1000)
        assert u.cache_hit_rate == 0.0

    def test_cache_hit_rate_one_when_everything_cached(self):
        u = TokenUsage(cache_read_input_tokens=1000)
        assert u.cache_hit_rate == 1.0

    def test_cache_hit_rate_none_when_no_input(self):
        assert TokenUsage().cache_hit_rate is None

    def test_cache_hit_rate_typical(self):
        # 80 fresh + 700 cached + 20 cache-creation = 800 input total
        # cache_read / total = 700 / 800 = 0.875
        u = TokenUsage(
            input_tokens=80,
            cache_creation_input_tokens=20,
            cache_read_input_tokens=700,
        )
        assert u.cache_hit_rate == pytest.approx(0.875)


# ── parse_usage ──────────────────────────────────────────────────────────────


class TestParseUsage:
    def test_returns_empty_on_none(self):
        assert parse_usage(None) == TokenUsage()

    def test_parses_dict_shape(self):
        raw = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 200,
        }
        assert parse_usage(raw) == TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=10, cache_read_input_tokens=200,
        )

    def test_parses_object_shape(self):
        """Anthropic SDK exposes usage as a Pydantic-ish object."""
        raw = SimpleNamespace(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=10, cache_read_input_tokens=200,
        )
        assert parse_usage(raw) == TokenUsage(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=10, cache_read_input_tokens=200,
        )

    def test_missing_cache_fields_default_to_zero(self):
        """Older Anthropic SDK responses may lack the cache fields entirely."""
        raw = SimpleNamespace(input_tokens=100, output_tokens=50)
        result = parse_usage(raw)
        assert result.cache_creation_input_tokens == 0
        assert result.cache_read_input_tokens == 0

    def test_handles_non_int_values_gracefully(self):
        raw = {"input_tokens": "not a number", "output_tokens": None}
        result = parse_usage(raw)
        assert result.input_tokens == 0
        assert result.output_tokens == 0


# ── Pricing ──────────────────────────────────────────────────────────────────


class TestPricing:
    def test_resolves_sonnet_4_6_prefix(self):
        # claude-sonnet-4-6 should resolve via "claude-sonnet-4" prefix.
        table = _resolve_price_table("claude-sonnet-4-6")
        assert table is not None
        assert table.input_per_million == 3.00
        assert table.output_per_million == 15.00

    def test_resolves_opus_prefix(self):
        # Opus 4.5+ bills at $5/MTok; the bare claude-opus-4 prefix keeps
        # the old $15 rate for 4.0/4.1-era IDs.
        table = _resolve_price_table("claude-opus-4-8")
        assert table is not None
        assert table.input_per_million == 5.00
        legacy = _resolve_price_table("claude-opus-4-20250514")
        assert legacy is not None
        assert legacy.input_per_million == 15.00

    def test_resolves_haiku_prefix(self):
        table = _resolve_price_table("claude-haiku-4-5-20251001")
        assert table is not None
        assert table.input_per_million == 1.00

    def test_unknown_model_returns_none(self):
        assert _resolve_price_table("gpt-4") is None
        assert _resolve_price_table("") is None
        assert _resolve_price_table("claude-future-model-99") is None

    def test_cost_estimate_sonnet_typical(self):
        """1M input + 250k output + 500k cache-read + 100k cache-write on Sonnet:
        3.00 + (0.25 * 15.00) + (0.5 * 0.30) + (0.1 * 3.75) = 3 + 3.75 + 0.15 + 0.375 = $7.275
        """
        u = TokenUsage(
            input_tokens=1_000_000, output_tokens=250_000,
            cache_read_input_tokens=500_000, cache_creation_input_tokens=100_000,
        )
        cost = cost_estimate_usd(u, "claude-sonnet-4-6")
        assert cost == pytest.approx(7.275)

    def test_cost_estimate_unknown_model_returns_none(self):
        u = TokenUsage(input_tokens=100, output_tokens=50)
        assert cost_estimate_usd(u, "unknown-model") is None

    def test_cost_estimate_zero_usage_is_zero(self):
        assert cost_estimate_usd(TokenUsage(), "claude-sonnet-4-6") == 0.0


# ── UsageAggregate ───────────────────────────────────────────────────────────


class TestUsageAggregate:
    def test_records_per_model_and_total(self):
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=100, output_tokens=50), "claude-sonnet-4-6")
        agg.record(TokenUsage(input_tokens=200, output_tokens=20), "claude-sonnet-4-6")
        agg.record(TokenUsage(input_tokens=10, output_tokens=5), "claude-haiku-4-5")
        assert agg.call_count == 3
        assert agg.total.input_tokens == 310
        assert agg.total.output_tokens == 75
        assert agg.by_model["claude-sonnet-4-6"].input_tokens == 300
        assert agg.by_model["claude-haiku-4-5"].input_tokens == 10

    def test_threadsafe_accumulation(self):
        """Hammer the aggregate from many threads and verify nothing is lost."""
        agg = UsageAggregate()
        per_thread = 100

        def _worker():
            for _ in range(per_thread):
                agg.record(TokenUsage(input_tokens=1, output_tokens=1), "claude-sonnet-4-6")

        threads = [threading.Thread(target=_worker) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert agg.call_count == 20 * per_thread
        assert agg.total.input_tokens == 20 * per_thread

    def test_cost_estimate_combines_per_model(self):
        agg = UsageAggregate()
        # 1M Sonnet input → $3.00
        agg.record(TokenUsage(input_tokens=1_000_000), "claude-sonnet-4-6")
        # 1M Haiku input → $1.00
        agg.record(TokenUsage(input_tokens=1_000_000), "claude-haiku-4-5")
        assert agg.cost_estimate_usd() == pytest.approx(4.00)

    def test_cost_estimate_none_when_every_model_unpriced(self):
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=100), "mystery-model")
        assert agg.cost_estimate_usd() is None

    def test_cost_estimate_partial_pricing(self):
        """If some models are priced and others aren't, we still report a
        (possibly under-counted) cost rather than refusing to estimate."""
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=1_000_000), "claude-sonnet-4-6")  # $3
        agg.record(TokenUsage(input_tokens=1_000_000), "mystery-model")       # ?
        cost = agg.cost_estimate_usd()
        assert cost is not None
        assert cost == pytest.approx(3.00)


# ── format_summary ───────────────────────────────────────────────────────────


class TestFormatSummary:
    def test_zero_calls_message(self):
        assert "no AI calls" in format_summary(UsageAggregate())

    def test_includes_tokens_and_count(self):
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=1000, output_tokens=500), "claude-sonnet-4-6")
        s = format_summary(agg)
        assert "1,000 input" in s
        assert "500 output" in s
        assert "1 API call" in s

    def test_includes_dollar_estimate_for_priced_model(self):
        agg = UsageAggregate()
        agg.record(
            TokenUsage(input_tokens=1_000_000, output_tokens=0),
            "claude-sonnet-4-6",
        )
        assert "$3.00" in format_summary(agg)

    def test_omits_dollar_estimate_for_unpriced_model(self):
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=1000), "mystery-model")
        s = format_summary(agg)
        assert "$" not in s

    def test_includes_cache_hit_rate_when_cache_used(self):
        agg = UsageAggregate()
        agg.record(
            TokenUsage(input_tokens=100, cache_read_input_tokens=900),
            "claude-sonnet-4-6",
        )
        s = format_summary(agg)
        assert "cache" in s
        assert "90.0% hit rate" in s

    def test_omits_cache_block_when_no_cache_activity(self):
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=100, output_tokens=50), "claude-sonnet-4-6")
        s = format_summary(agg)
        assert "cache" not in s

    def test_includes_step_label_when_provided(self):
        agg = UsageAggregate()
        agg.record(TokenUsage(input_tokens=100), "claude-sonnet-4-6")
        s = format_summary(agg, step_label="lcc-enrich")
        assert "lcc-enrich" in s


# ── Persistent log ───────────────────────────────────────────────────────────


@pytest.fixture
def temp_usage_log(tmp_path, monkeypatch):
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("CALIBRE_TOOLKIT_USAGE_LOG", str(log_path))
    return log_path


class TestPersistentLog:
    def test_log_usage_appends_jsonl(self, temp_usage_log):
        log_usage(
            TokenUsage(input_tokens=100, output_tokens=50,
                       cache_read_input_tokens=10),
            model="claude-sonnet-4-6", step="lcc-enrich",
        )
        lines = temp_usage_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["model"] == "claude-sonnet-4-6"
        assert record["step"] == "lcc-enrich"
        assert record["input_tokens"] == 100
        assert record["output_tokens"] == 50
        assert record["cache_read_input_tokens"] == 10
        assert "timestamp" in record
        # Cost is included for priced models.
        assert "estimated_cost_usd" in record

    def test_log_usage_omits_cost_for_unpriced_model(self, temp_usage_log):
        log_usage(TokenUsage(input_tokens=100), model="mystery-model")
        record = json.loads(temp_usage_log.read_text(encoding="utf-8").strip())
        assert "estimated_cost_usd" not in record

    def test_log_usage_swallows_filesystem_errors(self, tmp_path, monkeypatch):
        """Telemetry failure must never break a batch."""
        # Point the log at a file path whose parent already exists as a file
        # (not a directory) so mkdir(parents=True) will fail.
        not_a_dir = tmp_path / "not-a-dir"
        not_a_dir.write_text("just a file", encoding="utf-8")
        monkeypatch.setenv("CALIBRE_TOOLKIT_USAGE_LOG", str(not_a_dir / "usage.jsonl"))
        # Should not raise — only log a warning.
        log_usage(TokenUsage(input_tokens=100), model="claude-sonnet-4-6")

    def test_replay_empty_log_returns_empty_aggregate(self, temp_usage_log):
        agg = replay_usage_log()
        assert agg.call_count == 0
        assert agg.total == TokenUsage()

    def test_replay_missing_log_returns_empty_aggregate(self, tmp_path):
        agg = replay_usage_log(tmp_path / "nope.jsonl")
        assert agg.call_count == 0

    def test_replay_round_trips(self, temp_usage_log):
        log_usage(TokenUsage(input_tokens=100, output_tokens=50), "claude-sonnet-4-6", "lcc")
        log_usage(TokenUsage(input_tokens=200, output_tokens=80), "claude-sonnet-4-6", "comments")
        log_usage(TokenUsage(input_tokens=10), "claude-haiku-4-5", "tags")
        agg = replay_usage_log()
        assert agg.call_count == 3
        assert agg.total.input_tokens == 310
        assert agg.total.output_tokens == 130
        # Per-model breakdown survives the round trip.
        assert agg.by_model["claude-sonnet-4-6"].input_tokens == 300
        assert agg.by_model["claude-haiku-4-5"].input_tokens == 10

    def test_replay_skips_corrupted_lines(self, temp_usage_log):
        # First line is valid; second is junk; third is valid.
        temp_usage_log.write_text(
            json.dumps({
                "model": "claude-sonnet-4-6", "input_tokens": 100,
                "output_tokens": 50, "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }) + "\n"
            "{this is not json at all\n"
            + json.dumps({
                "model": "claude-sonnet-4-6", "input_tokens": 200,
                "output_tokens": 80, "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }) + "\n",
            encoding="utf-8",
        )
        agg = replay_usage_log()
        assert agg.call_count == 2
        assert agg.total.input_tokens == 300


# ── AIClient integration ─────────────────────────────────────────────────────


class TestAIClientIntegration:
    """Verify that a stubbed Anthropic response's usage block flows into
    the AIClient's aggregate without touching the network."""

    def test_call_records_usage_into_aggregate(self, temp_usage_log):
        from calibre_toolkit.ai import AIClient

        client = AIClient(api_key="test", model="claude-sonnet-4-6", step_label="test-step")

        # Build a fake Anthropic response object.
        fake_response = SimpleNamespace(
            content=[SimpleNamespace(text="hello")],
            usage=SimpleNamespace(
                input_tokens=100, output_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=200,
            ),
        )
        fake_messages = MagicMock()
        fake_messages.create.return_value = fake_response
        fake_anthropic = SimpleNamespace(messages=fake_messages)

        with patch.object(client, "_anthropic", return_value=fake_anthropic):
            client._call("user", "system")

        assert client.usage.call_count == 1
        assert client.usage.total.input_tokens == 100
        assert client.usage.total.output_tokens == 50
        assert client.usage.total.cache_read_input_tokens == 200
        # The persisted log should also have one event tagged with step_label.
        log_path = temp_usage_log
        line = log_path.read_text(encoding="utf-8").strip().splitlines()[0]
        record = json.loads(line)
        assert record["step"] == "test-step"

    def test_call_accumulates_across_multiple_calls(self, temp_usage_log):
        from calibre_toolkit.ai import AIClient

        client = AIClient(api_key="test", model="claude-sonnet-4-6")

        def _fake_call_n(input_tokens, output_tokens):
            return SimpleNamespace(
                content=[SimpleNamespace(text="x")],
                usage=SimpleNamespace(
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    cache_creation_input_tokens=0, cache_read_input_tokens=0,
                ),
            )

        responses = [_fake_call_n(100, 50), _fake_call_n(200, 30), _fake_call_n(50, 10)]
        fake_messages = MagicMock()
        fake_messages.create.side_effect = responses
        fake_anthropic = SimpleNamespace(messages=fake_messages)

        with patch.object(client, "_anthropic", return_value=fake_anthropic):
            for _ in range(3):
                client._call("u", "s")

        assert client.usage.call_count == 3
        assert client.usage.total.input_tokens == 350
        assert client.usage.total.output_tokens == 90

    def test_missing_usage_block_does_not_crash(self, temp_usage_log):
        """Defensive: an older SDK or unusual response shape without
        `usage` must not break the call."""
        from calibre_toolkit.ai import AIClient

        client = AIClient(api_key="test", model="claude-sonnet-4-6")
        fake_response = SimpleNamespace(content=[SimpleNamespace(text="hi")])  # no usage
        fake_messages = MagicMock()
        fake_messages.create.return_value = fake_response
        fake_anthropic = SimpleNamespace(messages=fake_messages)

        with patch.object(client, "_anthropic", return_value=fake_anthropic):
            result = client._call("u", "s")
        assert result == "hi"
        assert client.usage.call_count == 1
        assert client.usage.total == TokenUsage()
