from storage_optimizer.formatting import human_size


def test_human_size_bytes():
    assert human_size(512) == "512.0B"


def test_human_size_kilobytes():
    assert human_size(2048) == "2.0KB"


def test_human_size_gigabytes():
    assert human_size(30 * 1024**3) == "30.0GB"


def test_human_size_zero():
    assert human_size(0) == "0.0B"
