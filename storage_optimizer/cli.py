"""CLI entry point.

`scan`  — measure every category, print a table, save the report, and fire a
          macOS notification with the total reclaimable size. Read-only.
`clean` — read the last scan's report and delete only the categories the
          user selects (by id, "all", or via --interactive).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from storage_optimizer import notifier
from storage_optimizer.cleaner import run_clean
from storage_optimizer.formatting import human_size
from storage_optimizer.scanner import get_categories, select_categories

REPORT_PATH = Path.home() / ".personal-automations" / "storage_scan_latest.json"


def _scan() -> list[dict]:
    categories = get_categories()
    report = [
        {"id": c.id, "label": c.label, "risk": c.risk, "size_bytes": c.measure()}
        for c in categories
    ]
    report.sort(key=lambda r: r["size_bytes"], reverse=True)
    return report


def cmd_scan(args: argparse.Namespace) -> int:
    report = _scan()
    total = sum(r["size_bytes"] for r in report)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps({"generated_at": datetime.now().isoformat(), "categories": report}, ensure_ascii=False, indent=2)
    )

    print(f"{'ID':<28} {'위험도':<8} {'용량':>10}  라벨")
    for r in report:
        print(f"{r['id']:<28} {r['risk']:<8} {human_size(r['size_bytes']):>10}  {r['label']}")
    print(f"\n총 회수 가능 용량: {human_size(total)}")

    notifier.notify("스토리지 스캔 완료", f"회수 가능 용량 {human_size(total)} — 'clean --interactive'로 선택 삭제")
    return 0


def _load_report() -> list[dict]:
    if not REPORT_PATH.exists():
        print("저장된 스캔 결과가 없습니다. 먼저 `scan`을 실행하세요.", file=sys.stderr)
        sys.exit(1)
    return json.loads(REPORT_PATH.read_text())["categories"]


def _prompt_ids(report: list[dict]) -> list[str]:
    print("삭제할 항목 번호를 쉼표로 구분해 입력하세요 (전체: all, 취소: 빈 입력):\n")
    for i, r in enumerate(report, start=1):
        print(f"  {i}. [{r['risk']}] {r['label']} — {human_size(r['size_bytes'])}")
    choice = input("\n> ").strip()
    if not choice:
        return []
    if choice.lower() == "all":
        return [r["id"] for r in report]
    ids = []
    for token in choice.split(","):
        token = token.strip()
        if not token.isdigit() or not (1 <= int(token) <= len(report)):
            print(f"무시된 입력: {token!r}", file=sys.stderr)
            continue
        ids.append(report[int(token) - 1]["id"])
    return ids


def cmd_clean(args: argparse.Namespace) -> int:
    report = _load_report()
    ids = _prompt_ids(report) if args.interactive else args.ids
    if not ids:
        print("선택된 항목이 없습니다. 종료합니다.")
        return 0

    categories = select_categories(get_categories(), ids)
    if not categories:
        print("선택한 id와 일치하는 카테고리가 없습니다.", file=sys.stderr)
        return 1

    results = run_clean(categories, dry_run=args.dry_run)
    label = "(dry-run) 예상" if args.dry_run else "정리 완료"
    total_freed = 0
    for r in results:
        print(f"{label}: {r.label} — {human_size(r.freed_bytes)}")
        total_freed += r.freed_bytes
    print(f"\n총 {'예상 ' if args.dry_run else ''}회수 용량: {human_size(total_freed)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="storage_optimizer")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("scan", help="용량을 스캔하고 리포트를 저장/알림")
    scan_parser.set_defaults(func=cmd_scan)

    clean_parser = sub.add_parser("clean", help="마지막 스캔 결과 중 선택한 항목만 삭제")
    clean_parser.add_argument("ids", nargs="*", help="삭제할 카테고리 id들 (또는 all)")
    clean_parser.add_argument("--interactive", action="store_true", help="체크리스트로 선택")
    clean_parser.add_argument("--dry-run", action="store_true", help="삭제 없이 예상 용량만 출력")
    clean_parser.set_defaults(func=cmd_clean)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
