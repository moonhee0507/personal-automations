from pathlib import Path

from storage_optimizer.scanner import _android_studio_version_key, select_categories


def test_android_studio_version_key_orders_numerically_not_lexically():
    names = ["AndroidStudio2025.9.1", "AndroidStudio2025.10.2", "AndroidStudio2025.2.3"]
    ordered = sorted(names, key=_android_studio_version_key)
    assert ordered == ["AndroidStudio2025.2.3", "AndroidStudio2025.9.1", "AndroidStudio2025.10.2"]


def test_android_studio_version_key_ignores_non_matching_name():
    assert _android_studio_version_key("not-a-version") == (0, 0, 0)


class _FakeCategory:
    def __init__(self, id):
        self.id = id


def test_select_categories_filters_by_id_and_preserves_catalog_order():
    categories = [_FakeCategory("a"), _FakeCategory("b"), _FakeCategory("c")]
    selected = select_categories(categories, ["c", "a"])
    assert [c.id for c in selected] == ["a", "c"]


def test_select_categories_all_keyword_returns_everything():
    categories = [_FakeCategory("a"), _FakeCategory("b")]
    assert select_categories(categories, ["all"]) == categories


def test_select_categories_unknown_id_is_ignored():
    categories = [_FakeCategory("a")]
    assert select_categories(categories, ["a", "does-not-exist"]) == categories
