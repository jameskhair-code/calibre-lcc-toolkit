"""Tests for logging_config.audit_log and setup_logging."""

import json
import logging

import pytest

from calibre_toolkit import logging_config
from calibre_toolkit.logging_config import (
    audit_log,
    get_logger,
    setup_logging,
)


@pytest.fixture
def audit_path(tmp_path, monkeypatch):
    """Redirect the audit log to a tmp path via the env var override."""
    path = tmp_path / "audit.log"
    monkeypatch.setenv("CALIBRE_TOOLKIT_AUDIT_LOG", str(path))
    return path


class TestAuditLog:
    def test_writes_one_jsonl_line(self, audit_path):
        audit_log(book_id=1, field="#lcc", new_value="PR6059",
                  confidence="high", source="LC catalog (ISBN 9780571)")
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["book_id"] == 1
        assert rec["field"] == "#lcc"
        assert rec["new_value"] == "PR6059"
        assert rec["confidence"] == "high"
        assert rec["source"] == "LC catalog (ISBN 9780571)"
        assert "timestamp" in rec

    def test_appends_across_calls(self, audit_path):
        audit_log(book_id=1, field="#lcc", new_value="A")
        audit_log(book_id=2, field="#lcc", new_value="B")
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["book_id"] == 1
        assert json.loads(lines[1])["book_id"] == 2

    def test_extra_kwargs_merged_into_record(self, audit_path):
        audit_log(book_id=5, field="tags", new_value=["A", "B"],
                  step="tags-enrich", batch_id="abc")
        rec = json.loads(audit_path.read_text().strip())
        assert rec["step"] == "tags-enrich"
        assert rec["batch_id"] == "abc"
        assert rec["new_value"] == ["A", "B"]

    def test_skips_empty_confidence_and_source(self, audit_path):
        audit_log(book_id=1, field="x", new_value="y")
        rec = json.loads(audit_path.read_text().strip())
        assert "confidence" not in rec
        assert "source" not in rec

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        path = tmp_path / "nested" / "more" / "audit.log"
        monkeypatch.setenv("CALIBRE_TOOLKIT_AUDIT_LOG", str(path))
        audit_log(book_id=1, field="x", new_value="y")
        assert path.exists()

    def test_concurrent_writes_serialised(self, audit_path):
        """Multiple threads writing at once must produce N well-formed lines."""
        import threading
        n = 20
        threads = [
            threading.Thread(target=audit_log,
                             kwargs={"book_id": i, "field": "x", "new_value": i})
            for i in range(n)
        ]
        for t in threads: t.start()
        for t in threads: t.join()
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == n
        # Every line parses as JSON — proves no interleaving.
        for line in lines:
            json.loads(line)


class TestSetupLogging:
    def teardown_method(self):
        # Reset between tests to avoid handler leaks.
        for h in list(logging.getLogger("calibre_toolkit").handlers):
            logging.getLogger("calibre_toolkit").removeHandler(h)

    def test_default_is_warning(self):
        log = setup_logging()
        assert log.level == logging.WARNING

    def test_verbose_is_debug(self):
        log = setup_logging(verbose=True)
        assert log.level == logging.DEBUG

    def test_log_file_writes_debug(self, tmp_path):
        log_path = tmp_path / "calibre-toolkit.log"
        log = setup_logging(verbose=False, log_file=log_path)
        # When --log-file is set, root level drops to DEBUG so file handler can
        # capture DEBUG records even though stderr is still WARNING-only.
        assert log.level == logging.DEBUG
        get_logger("ai").debug("test debug record")
        assert "test debug record" in log_path.read_text(encoding="utf-8")

    def test_repeated_setup_does_not_duplicate_handlers(self):
        log = setup_logging()
        n = len(log.handlers)
        setup_logging()
        setup_logging()
        assert len(log.handlers) == n

    def test_get_logger_is_child_of_package(self):
        assert get_logger("ai").name == "calibre_toolkit.ai"
        # Passing a fully-qualified name should be left alone.
        assert get_logger("calibre_toolkit.modules.lcc").name == \
            "calibre_toolkit.modules.lcc"
