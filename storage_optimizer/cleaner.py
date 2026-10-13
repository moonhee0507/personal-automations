from __future__ import annotations

from dataclasses import dataclass

from storage_optimizer.scanner import Category


@dataclass
class CleanResult:
    id: str
    label: str
    freed_bytes: int
    dry_run: bool


def run_clean(categories: list[Category], dry_run: bool = False) -> list[CleanResult]:
    results = []
    for category in categories:
        before = category.measure()
        if dry_run:
            freed = before
        else:
            category.clean()
            freed = max(before - category.measure(), 0)
        results.append(CleanResult(category.id, category.label, freed, dry_run))
    return results
