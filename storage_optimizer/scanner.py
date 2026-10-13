"""Defines cleanup categories (what can be reclaimed, how risky, how to measure/clean each)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HOME = Path.home()

SAFE = "safe"       # reclaimable cache; the owning tool rebuilds it on demand
REVIEW = "review"   # could remove something still in active use; check before cleaning


@dataclass
class Category:
    id: str
    label: str
    risk: str
    measure: Callable[[], int]
    clean: Callable[[], None]


def _dir_size_bytes(path: Path) -> int:
    """Shell out to `du` rather than walking in Python: far faster on large caches."""
    try:
        output = subprocess.run(
            ["du", "-sk", str(path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout
        return int(output.split()[0]) * 1024
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError):
        return 0


def _parse_docker_size(text: str) -> int:
    """Parse docker's human sizes like '27.87GB' or '101.5MB' (decimal units, docker's own convention)."""
    match = re.match(r"([\d.]+)\s*([KMGT]?B)", text.strip())
    if not match:
        return 0
    value, unit = match.groups()
    multiplier = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}[unit]
    return int(float(value) * multiplier)


def _path_category(id: str, label: str, risk: str, paths: list[Path], clean_cmd: list[str] | None = None) -> Category:
    def measure() -> int:
        return sum(_dir_size_bytes(p) for p in paths if p.exists())

    def clean() -> None:
        if clean_cmd:
            subprocess.run(clean_cmd, capture_output=True, text=True, timeout=600)
            return
        for p in paths:
            if not p.exists():
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

    return Category(id, label, risk, measure, clean)


def _android_studio_version_key(name: str) -> tuple[int, int, int]:
    match = re.search(r"AndroidStudio(\d+)\.(\d+)(?:\.(\d+))?", name)
    if not match:
        return (0, 0, 0)
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch) if patch else 0)


def _android_studio_old_cache_paths() -> list[Path]:
    base = HOME / "Library/Caches/Google"
    if not base.exists():
        return []
    as_dirs = [p for p in base.iterdir() if p.is_dir() and p.name.startswith("AndroidStudio")]
    if len(as_dirs) <= 1:
        return []
    as_dirs.sort(key=lambda p: _android_studio_version_key(p.name))
    return as_dirs[:-1]  # keep the newest installed version


def _pnpm_store_path() -> Path | None:
    try:
        output = subprocess.run(
            ["pnpm", "store", "path"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        return Path(output) if output else None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _docker_category() -> Category:
    def measure() -> int:
        try:
            output = subprocess.run(
                ["docker", "system", "df", "--format", "{{.Reclaimable}}"],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            ).stdout
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return 0
        return sum(_parse_docker_size(line) for line in output.splitlines() if line.strip())

    def clean() -> None:
        subprocess.run(["docker", "system", "prune", "-f"], capture_output=True, text=True, timeout=600)

    return Category("docker-unused", "Docker 미사용 리소스 (중지된 컨테이너/네트워크/dangling 이미지/빌드 캐시)", REVIEW, measure, clean)


def get_categories() -> list[Category]:
    """Build the category list fresh each call so paths reflect the current machine state."""
    categories = [
        _path_category("npm-cache", "npm 캐시", SAFE, [HOME / ".npm"], ["npm", "cache", "clean", "--force"]),
        _path_category(
            "yarn-cache", "Yarn 캐시", SAFE, [HOME / "Library/Caches/Yarn"], ["yarn", "cache", "clean"]
        ),
        _path_category(
            "homebrew-cache",
            "Homebrew 캐시",
            SAFE,
            [HOME / "Library/Caches/Homebrew"],
            ["brew", "cleanup", "-s"],
        ),
        _path_category("pip-cache", "pip 캐시", SAFE, [HOME / "Library/Caches/pip"], ["pip", "cache", "purge"]),
        _path_category(
            "cocoapods-cache",
            "CocoaPods 캐시",
            SAFE,
            [HOME / "Library/Caches/CocoaPods"],
            ["pod", "cache", "clean", "--all"],
        ),
        _path_category(
            "xcode-derived-data",
            "Xcode DerivedData",
            SAFE,
            [HOME / "Library/Developer/Xcode/DerivedData"],
        ),
        _path_category(
            "android-studio-old-cache",
            "Android Studio 구버전 캐시",
            SAFE,
            _android_studio_old_cache_paths(),
        ),
        _docker_category(),
    ]

    pnpm_store = _pnpm_store_path()
    if pnpm_store:
        categories.append(
            _path_category("pnpm-store", "pnpm 스토어", SAFE, [pnpm_store], ["pnpm", "store", "prune"])
        )

    return categories


def select_categories(categories: list, ids: list[str]) -> list:
    if "all" in ids:
        return list(categories)
    wanted = set(ids)
    return [c for c in categories if c.id in wanted]
