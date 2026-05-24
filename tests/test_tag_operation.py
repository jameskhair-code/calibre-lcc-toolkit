"""Tests for the TagOperation dataclass — its kind/display_arrow are used
by every cleanup UI surface and must stay stable."""

from calibre_toolkit.ai import TagOperation


def make(source, target, **kw):
    return TagOperation(source_tags=source, target_tags=target,
                       reason=kw.get("reason", "test"))


class TestKind:
    def test_drop_when_no_target(self):
        assert make(["X"], []).kind == "drop"

    def test_rename_when_one_to_one_distinct(self):
        assert make(["X"], ["Y"]).kind == "rename"

    def test_noop_when_one_to_one_same(self):
        assert make(["X"], ["X"]).kind == "noop"

    def test_merge_when_many_to_one(self):
        assert make(["X", "Y"], ["Z"]).kind == "merge"

    def test_split_when_one_to_many(self):
        assert make(["X"], ["Y", "Z"]).kind == "split"

    def test_rewrite_when_many_to_many(self):
        assert make(["X", "Y"], ["A", "B"]).kind == "rewrite"


class TestDisplayArrow:
    def test_drop(self):
        assert make(["X"], []).display_arrow == "X → (drop)"

    def test_rename(self):
        assert make(["X"], ["Y"]).display_arrow == "X → Y"

    def test_merge(self):
        assert make(["X", "Y"], ["Z"]).display_arrow == "X, Y → Z"

    def test_split(self):
        assert make(["X"], ["Y", "Z"]).display_arrow == "X → Y + Z"
