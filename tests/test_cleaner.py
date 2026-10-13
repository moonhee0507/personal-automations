from storage_optimizer.cleaner import run_clean
from storage_optimizer.scanner import Category


def _fake_category(id, sizes):
    """sizes: sequence of values returned by successive measure() calls."""
    it = iter(sizes)
    cleaned = {"called": False}

    def measure():
        return next(it)

    def clean():
        cleaned["called"] = True

    cat = Category(id, f"label-{id}", "safe", measure, clean)
    cat._cleaned = cleaned
    return cat


def test_run_clean_reports_bytes_actually_freed():
    category = _fake_category("a", [100, 20])  # before=100, after=20
    [result] = run_clean([category], dry_run=False)
    assert result.freed_bytes == 80
    assert category._cleaned["called"] is True


def test_run_clean_dry_run_does_not_call_clean():
    category = _fake_category("a", [100])
    [result] = run_clean([category], dry_run=True)
    assert result.freed_bytes == 100
    assert category._cleaned["called"] is False


def test_run_clean_never_reports_negative_freed():
    category = _fake_category("a", [50, 70])  # clean somehow "grew" it
    [result] = run_clean([category], dry_run=False)
    assert result.freed_bytes == 0
