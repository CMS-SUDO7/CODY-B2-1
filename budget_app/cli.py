from __future__ import annotations

import argparse
import functools
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeVar

from .models import BudgetAppError, Transaction, ValidationError, parse_positive_amount, validate_date
from .services import BudgetService

P = ParamSpec("P")
R = TypeVar("R")


def measure_time(func: Callable[P, R]) -> Callable[P, R]:
    """명령 실행 시간을 공통 형식으로 stderr에 기록한다."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            print(f"[실행 시간] {elapsed:.1f}ms", file=sys.stderr)

    return wrapper


def friendly_errors(func: Callable[P, int]) -> Callable[P, int]:
    """예상 가능한 오류를 스택트레이스 없이 종료 코드로 변환한다."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except BudgetAppError as exc:
            print(f"오류: {exc.message}", file=sys.stderr)
            if exc.hint:
                print(f"해결: {exc.hint}", file=sys.stderr)
            return 2
        except (OSError, UnicodeError) as exc:
            print(f"오류: 파일을 처리할 수 없습니다. ({exc})", file=sys.stderr)
            print("해결: 경로와 파일 권한, UTF-8 인코딩을 확인하세요.", file=sys.stderr)
            return 3
        except Exception as exc:
            print(f"오류: 처리 중 예상하지 못한 문제가 발생했습니다. ({exc})", file=sys.stderr)
            print("해결: 입력값과 data 폴더의 JSONL 파일 형식을 확인하세요.", file=sys.stderr)
            return 1

    return wrapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m budget_app",
        description="JSONL 파일 기반 콘솔 가계부",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="데이터 저장 폴더 (기본값: ./data, 명령어 앞에 지정)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="거래를 대화형으로 추가")
    add.set_defaults(handler=handle_add)

    listing = commands.add_parser("list", help="최신순 거래 목록")
    listing.add_argument("--limit", type=int, default=20, help="표시 건수 (기본값: 20)")
    listing.set_defaults(handler=handle_list)

    search = commands.add_parser("search", help="조건으로 거래 검색")
    search.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    search.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    search.add_argument("--category", help="카테고리")
    search.add_argument("--type", choices=["income", "expense"], help="거래 유형")
    search.add_argument("--q", help="메모 키워드")
    search.add_argument("--tag", help="태그")
    search.set_defaults(handler=handle_search)

    summary = commands.add_parser("summary", help="월별 요약")
    summary.add_argument("--month", required=True, help="대상 월 YYYY-MM")
    summary.add_argument("--top", type=int, default=5, help="지출 카테고리 순위 (기본값: 5)")
    summary.set_defaults(handler=handle_summary)

    budget = commands.add_parser("budget", help="월 예산 설정/조회")
    budget_commands = budget.add_subparsers(dest="budget_command", required=True)
    budget_set = budget_commands.add_parser("set", help="예산 설정")
    budget_set.add_argument("--month", required=True, help="대상 월 YYYY-MM")
    budget_set.add_argument("--amount", required=True, help="예산(양의 정수)")
    budget_set.set_defaults(handler=handle_budget_set)
    budget_get = budget_commands.add_parser("get", help="월 예산 조회")
    budget_get.add_argument("--month", required=True, help="대상 월 YYYY-MM")
    budget_get.set_defaults(handler=handle_budget_get)
    budget_list = budget_commands.add_parser("list", help="모든 예산 조회")
    budget_list.set_defaults(handler=handle_budget_list)

    category = commands.add_parser("category", help="카테고리 관리")
    category_commands = category.add_subparsers(dest="category_command", required=True)
    category_add = category_commands.add_parser("add", help="카테고리 추가")
    category_add.add_argument("name", nargs="?", help="이름(생략 시 대화형 입력)")
    category_add.set_defaults(handler=handle_category_add)
    category_list = category_commands.add_parser("list", help="카테고리 목록")
    category_list.set_defaults(handler=handle_category_list)
    category_remove = category_commands.add_parser("remove", help="카테고리 삭제")
    category_remove.add_argument("name", help="삭제할 카테고리")
    category_remove.set_defaults(handler=handle_category_remove)

    update = commands.add_parser("update", help="id 기반 옵션 방식 거래 수정")
    update.add_argument("--id", required=True, help="거래 id")
    update.add_argument("--date", help="날짜 YYYY-MM-DD")
    update.add_argument("--type", choices=["income", "expense"], help="거래 유형")
    update.add_argument("--category", help="카테고리")
    update.add_argument("--amount", help="금액(양의 정수)")
    update.add_argument("--memo", help="메모(빈 문자열로 삭제 가능)")
    update.add_argument("--tags", help="쉼표로 구분한 태그(빈 문자열로 삭제 가능)")
    update.set_defaults(handler=handle_update)

    delete = commands.add_parser("delete", help="거래 삭제")
    delete.add_argument("--id", required=True, help="거래 id")
    delete.set_defaults(handler=handle_delete)

    importer = commands.add_parser("import", help="CSV 거래 가져오기")
    importer.add_argument("--from", dest="source", type=Path, required=True, help="입력 CSV")
    importer.set_defaults(handler=handle_import)

    exporter = commands.add_parser("export", help="조건에 맞는 거래를 CSV로 내보내기")
    exporter.add_argument("--out", type=Path, required=True, help="출력 CSV")
    exporter.add_argument("--month", help="대상 월 YYYY-MM")
    exporter.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    exporter.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    exporter.set_defaults(handler=handle_export)
    return parser


def _prompt_until(prompt: str, validator: Callable[[str], object]) -> str:
    while True:
        value = input(prompt).strip()
        try:
            validator(value)
            return value
        except ValidationError as exc:
            print(f"입력 오류: {exc.message}")
            if exc.hint:
                print(f"힌트: {exc.hint}")


def _validate_type(value: str) -> None:
    if value not in ("income", "expense"):
        raise ValidationError("type은 income 또는 expense여야 합니다.")


def _print_transaction(item: Transaction) -> None:
    tags = f" #{' #'.join(item.tags)}" if item.tags else ""
    memo = f" | {item.memo}" if item.memo else ""
    print(
        f"{item.date} | {item.type:7} | {item.category:12} | "
        f"{item.amount:>12,}원 | {item.id}{memo}{tags}"
    )


def _print_stream(items: object) -> None:
    found = False
    for item in items:  # type: ignore[union-attr]
        found = True
        _print_transaction(item)
    if not found:
        print("조건에 맞는 거래가 없습니다.")


def handle_add(args: argparse.Namespace, service: BudgetService) -> None:
    print("거래 정보를 입력하세요.")
    date = _prompt_until("날짜 (YYYY-MM-DD): ", validate_date)
    type_value = _prompt_until("타입 (income/expense): ", _validate_type)
    while True:
        category = input("카테고리: ").strip()
        if service.categories.contains(category):
            break
        print("입력 오류: 등록되지 않은 카테고리입니다.")
        print("등록된 카테고리:", ", ".join(service.categories.iter_all()))
    amount = _prompt_until("금액 (양의 정수): ", parse_positive_amount)
    memo = input("메모 (선택): ").strip()
    tags = [tag.strip() for tag in input("태그 (쉼표 구분, 선택): ").split(",") if tag.strip()]
    transaction = service.add_transaction(
        date=date,
        type=type_value,
        category=category,
        amount=amount,
        memo=memo,
        tags=tags,
    )
    print(f"저장했습니다. id={transaction.id}")


def handle_list(args: argparse.Namespace, service: BudgetService) -> None:
    _print_stream(service.list_transactions(args.limit))


def handle_search(args: argparse.Namespace, service: BudgetService) -> None:
    _print_stream(
        service.search(
            date_from=args.date_from,
            date_to=args.date_to,
            category=args.category,
            type=args.type,
            query=args.q,
            tag=args.tag,
        )
    )


def handle_summary(args: argparse.Namespace, service: BudgetService) -> None:
    result = service.monthly_summary(args.month, args.top)
    if result["count"] == 0:
        print(f"{args.month}: 데이터 없음")
        budget = result["budget"]
        if budget:
            print(f"설정 예산: {budget.amount:,}원")
            print("예산 사용률: 0.0%")
            print(f"남은 예산: {budget.amount:,}원")
        return
    print(f"[{args.month} 월별 요약]")
    print(f"총 수입: {result['income']:,}원")
    print(f"총 지출: {result['expense']:,}원")
    print(f"잔액:    {result['balance']:,}원")
    categories = result["categories"]
    print(f"카테고리별 지출 TOP {args.top}:")
    if categories:
        for rank, (category, amount) in enumerate(categories, 1):
            print(f"  {rank}. {category}: {amount:,}원")
    else:
        print("  지출 없음")
    budget = result["budget"]
    if budget:
        usage = result["expense"] / budget.amount * 100
        print(f"예산: {budget.amount:,}원 / 사용률: {usage:.1f}%")
        if result["expense"] > budget.amount:
            print(f"[경고] 예산을 {result['expense'] - budget.amount:,}원 초과했습니다!")
        else:
            print(f"남은 예산: {budget.amount - result['expense']:,}원")


def handle_budget_set(args: argparse.Namespace, service: BudgetService) -> None:
    budget = service.set_budget(args.month, args.amount)
    print(f"{budget.month} 예산을 {budget.amount:,}원으로 저장했습니다.")


def handle_budget_get(args: argparse.Namespace, service: BudgetService) -> None:
    from .models import validate_month

    validate_month(args.month)
    budget = service.budgets.get(args.month)
    if budget:
        print(f"{budget.month}: {budget.amount:,}원")
    else:
        print(f"{args.month}: 설정된 예산이 없습니다.")


def handle_budget_list(args: argparse.Namespace, service: BudgetService) -> None:
    budgets = list(service.budgets.iter_all())
    if not budgets:
        print("설정된 예산이 없습니다.")
    for budget in budgets:
        print(f"{budget.month}: {budget.amount:,}원")


def handle_category_add(args: argparse.Namespace, service: BudgetService) -> None:
    name = (args.name or input("새 카테고리 이름: ")).strip()
    if not name:
        raise ValidationError("카테고리 이름은 비어 있을 수 없습니다.")
    service.categories.add(name)
    print(f"카테고리 '{name}'를 추가했습니다.")


def handle_category_list(args: argparse.Namespace, service: BudgetService) -> None:
    print("등록된 카테고리:")
    for category in service.categories.iter_all():
        print(f"- {category}")


def handle_category_remove(args: argparse.Namespace, service: BudgetService) -> None:
    service.remove_category(args.name)
    print(f"카테고리 '{args.name}'를 삭제했습니다.")


def handle_update(args: argparse.Namespace, service: BudgetService) -> None:
    changes = {
        key: value
        for key, value in {
            "date": args.date,
            "type": args.type,
            "category": args.category,
            "amount": args.amount,
            "memo": args.memo,
            "tags": args.tags,
        }.items()
        if value is not None
    }
    transaction = service.update_transaction(args.id, changes)
    print(f"거래를 수정했습니다. id={transaction.id}")


def handle_delete(args: argparse.Namespace, service: BudgetService) -> None:
    service.delete_transaction(args.id)
    print(f"거래를 삭제했습니다. id={args.id}")


def handle_import(args: argparse.Namespace, service: BudgetService) -> None:
    imported, skipped = service.import_csv(args.source)
    print(f"가져오기 완료: 성공 {imported}건, 건너뜀 {skipped}건")


def handle_export(args: argparse.Namespace, service: BudgetService) -> None:
    count = service.export_csv(
        args.out,
        month=args.month,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    print(f"내보내기 완료: {count}건 → {args.out}")


@friendly_errors
@measure_time
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = BudgetService(args.data_dir)
    args.handler(args, service)
    return 0
