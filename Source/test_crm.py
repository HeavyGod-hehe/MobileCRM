"""Pytest entry point — runs the CRM logic stress harness."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))


@pytest.fixture(scope="module")
def stress_report():
    fd, path = tempfile.mkstemp(suffix="_crm_pytest.db")
    os.close(fd)
    os.environ["CRM_DB_PATH"] = path
    os.environ["CRM_SKIP_LICENSE"] = "1"
    import stress_test_crm as harness

    report = harness.main()
    yield report
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def test_all_logic_checks_pass(stress_report):
    failed = [t for t in stress_report.results if not t.passed]
    assert not failed, "\n".join(f"{t.name}: {t.detail}" for t in failed)


def test_no_orphan_ledger_links(stress_report):
    assert stress_report.stats.get("orphan_ledger_cash_links", 0) == 0
    assert stress_report.stats.get("orphan_ledger_account_links", 0) == 0
