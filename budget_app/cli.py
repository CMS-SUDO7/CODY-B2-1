"""명령어 해석, 대화형 입력, 화면 출력."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from typing import TypeVar

from .decorators import handle_errors, measure_time
from .errors import ValidationError
from .models import Transaction, normalize_tags, validate_amount, validate_date, validate_type
from .repositories import BudgetRepository, CategoryRepository, TransactionRepository
from .services import BudgetService, CategoryService, CsvService, SummaryService, TransactionService


T = TypeVar("T")


# CLI 구성 기능: 최상위 명령과 각 명령에서 사용할 --옵션을 정의한다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m budget_app", description="JSONL 기반 콘솔 가계부")
    # 모든 명령에서 공통으로 사용하는 저장 폴더 옵션
    parser.add_argument("--data-dir", default="./data", help="저장 폴더 (기본값: ./data)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add는 과제 조건에 맞게 옵션 없이 대화형으로 입력받는다.
    subparsers.add_parser("add", help="거래를 대화형으로 추가")

    # list 명령: 출력할 최대 거래 수를 지정한다.
    list_parser = subparsers.add_parser("list", help="최근 등록 거래 목록")
    list_parser.add_argument("--limit", type=int, default=20, help="최대 출력 건수 (기본값: 20)")

    # search 명령: 입력된 조건만 조합하여 필터링한다.
    search = subparsers.add_parser("search", help="조건에 맞는 거래 검색")
    search.add_argument("--from", dest="from_date", help="시작일 YYYY-MM-DD")
    search.add_argument("--to", dest="to_date", help="종료일 YYYY-MM-DD")
    search.add_argument("--category", help="카테고리")
    search.add_argument("--type", choices=("income", "expense"), help="거래 타입")
    search.add_argument("--q", help="메모 키워드")
    search.add_argument("--tag", help="태그")

    # summary 명령: 대상 월과 카테고리 상위 출력 개수를 받는다.
    summary = subparsers.add_parser("summary", help="월별 요약")
    summary.add_argument("--month", required=True, help="대상 월 YYYY-MM")
    summary.add_argument("--top", type=int, default=3, help="지출 카테고리 상위 N개")

    # budget 명령은 set/get 하위 명령으로 나눈다.
    budget = subparsers.add_parser("budget", help="월 예산 설정/조회")
    budget_sub = budget.add_subparsers(dest="budget_command", required=True)
    budget_set = budget_sub.add_parser("set", help="월 예산 설정")
    budget_set.add_argument("--month", required=True, help="대상 월 YYYY-MM")
    budget_set.add_argument("--amount", required=True, help="양수 정수 금액")
    budget_get = budget_sub.add_parser("get", help="월 예산 조회")
    budget_get.add_argument("--month", required=True, help="대상 월 YYYY-MM")

    # category 명령은 list/add/remove 하위 명령으로 나눈다.
    category = subparsers.add_parser("category", help="카테고리 관리")
    category_sub = category.add_subparsers(dest="category_command", required=True)
    category_sub.add_parser("list", help="카테고리 목록")
    category_add = category_sub.add_parser("add", help="카테고리 추가")
    category_add.add_argument("--name", help="이름 (생략하면 대화형 입력)")
    category_remove = category_sub.add_parser("remove", help="카테고리 삭제")
    category_remove.add_argument("--name", help="이름 (생략하면 대화형 입력)")

    # update는 대화형이 아닌 옵션 방식으로 고정하며, 입력한 필드만 수정한다.
    update = subparsers.add_parser("update", help="id 기반 옵션 방식 거래 수정")
    update.add_argument("--id", required=True, help="거래 id")
    update.add_argument("--date", help="YYYY-MM-DD")
    update.add_argument("--type", choices=("income", "expense"))
    update.add_argument("--category")
    update.add_argument("--amount")
    update.add_argument("--memo", help="빈 문자열을 주면 메모 삭제")
    update.add_argument("--tags", help="쉼표 구분, 빈 문자열을 주면 전체 삭제")

    # delete는 거래를 정확히 지정할 수 있도록 id를 필수로 받는다.
    delete = subparsers.add_parser("delete", help="id 기반 거래 삭제")
    delete.add_argument("--id", required=True, help="거래 id")

    # import/export 명령: 입력 파일과 출력 조건을 옵션으로 받는다.
    import_parser = subparsers.add_parser("import", help="CSV 거래 가져오기")
    import_parser.add_argument("--from", dest="from_path", required=True, help="입력 CSV 경로")

    export = subparsers.add_parser("export", help="조건에 맞는 거래를 CSV로 내보내기")
    export.add_argument("--out", required=True, help="출력 CSV 경로")
    export.add_argument("--month", help="대상 월 YYYY-MM")
    export.add_argument("--from", dest="from_date", help="시작일 YYYY-MM-DD")
    export.add_argument("--to", dest="to_date", help="종료일 YYYY-MM-DD")
    return parser


# 대화형 입력 기능: 잘못 입력하면 오류를 보여 주고 같은 항목을 다시 받는다.
def prompt_until(prompt: str, validator: Callable[[str], T], default: str | None = None) -> T:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        try:
            return validator(value)
        except ValidationError as exc:
            print(f"입력 오류: {exc.message}")
            print(f"힌트: {exc.hint}")


# 빈 문자열을 허용하지 않는 카테고리 이름 등에 사용하는 검증 함수
def require_text(value: str) -> str:
    if not value.strip():
        raise ValidationError("값이 비어 있습니다.", "한 글자 이상 입력하세요.")
    return value.strip()


# 거래 한 건을 목록과 검색에서 공통으로 사용할 한 줄 문자열로 만든다.
def format_transaction(item: Transaction) -> str:
    tags = f" tags={','.join(item.tags)}" if item.tags else ""
    memo = f" memo={item.memo}" if item.memo else ""
    return (
        f"{item.date} | {item.type:<7} | {item.amount:>12,}원 | "
        f"{item.category} | id={item.id}{memo}{tags}"
    )


# 제너레이터에서 거래를 한 건씩 받아 출력하고 최종 건수를 표시한다.
def print_transactions(items: Iterable[Transaction]) -> int:
    count = 0
    for item in items:
        print(format_transaction(item))
        count += 1
    if count == 0:
        print("조건에 맞는 거래가 없습니다.")
    else:
        print(f"총 {count}건")
    return count


# 모든 실제 명령에 공통 예외 처리와 실행 시간 측정을 적용한다.
@handle_errors
@measure_time
def execute(args: argparse.Namespace) -> int:
    # 기능별로 분리된 저장소와 서비스를 조립한다.
    data_dir = Path(args.data_dir).expanduser()
    transactions = TransactionRepository(data_dir / "transactions.jsonl")
    categories = CategoryRepository(data_dir / "categories.jsonl")
    budgets = BudgetRepository(data_dir / "budgets.jsonl")

    transaction_service = TransactionService(transactions, categories)
    category_service = CategoryService(categories, transactions)
    budget_service = BudgetService(budgets)
    summary_service = SummaryService(transactions, budgets)
    csv_service = CsvService(transaction_service)

    # add 기능: 등록된 카테고리를 안내하고 거래 정보를 순서대로 입력받는다.
    if args.command == "add":
        available = list(category_service.list())
        print(f"등록된 카테고리: {', '.join(available)}")
        transaction = transaction_service.create(
            date=prompt_until("날짜 YYYY-MM-DD", validate_date, date.today().isoformat()),
            type=prompt_until("타입 income/expense", validate_type),
            category=prompt_until(
                "카테고리",
                lambda value: value if value in available else (_ for _ in ()).throw(
                    ValidationError(
                        f"등록되지 않은 카테고리입니다: {value}",
                        "위 목록 중 하나를 입력하세요.",
                    )
                ),
            ),
            amount=prompt_until("금액", validate_amount),
            memo=input("메모 (선택): ").strip(),
            tags=normalize_tags(input("태그 (선택, 쉼표 구분): ")),
        )
        print(f"저장 성공: id={transaction.id}")
        return 0

    # list 기능: 최근 등록 거래부터 --limit 개수만 출력한다.
    if args.command == "list":
        print_transactions(transaction_service.list_latest(args.limit))
        return 0

    # search 기능: 사용자가 지정한 검색 조건을 서비스에 전달한다.
    if args.command == "search":
        print_transactions(
            transaction_service.search(
                from_date=args.from_date,
                to_date=args.to_date,
                category=args.category,
                type=args.type,
                query=args.q,
                tag=args.tag,
            )
        )
        return 0

    # summary 기능: 월 합계, 카테고리 순위, 예산 정보를 보기 좋게 출력한다.
    if args.command == "summary":
        result = summary_service.monthly(args.month, args.top)
        if result is None:
            print(f"{args.month}: 데이터 없음")
            return 0
        print(f"[{args.month} 요약] 거래 {result['count']}건")
        print(f"총 수입: {result['income']:,}원")
        print(f"총 지출: {result['expense']:,}원")
        print(f"잔액: {result['balance']:,}원")
        print(f"지출 카테고리 TOP {args.top}")
        if result["top_categories"]:
            for rank, (name, amount) in enumerate(result["top_categories"], start=1):
                print(f"  {rank}. {name}: {amount:,}원")
        else:
            print("  지출 없음")
        if result["budget"] is not None:
            print(f"월 예산: {result['budget']:,}원")
            print(f"예산 사용률: {result['usage_rate']:.1f}%")
            if result["over_budget"]:
                print("경고: 월 예산을 초과했습니다!")
        return 0

    # budget 기능: 하위 명령에 따라 월 예산을 저장하거나 조회한다.
    if args.command == "budget":
        if args.budget_command == "set":
            budget = budget_service.set(args.month, args.amount)
            print(f"예산 저장 성공: {budget.month} = {budget.amount:,}원")
        else:
            budget = budget_service.get(args.month)
            print(f"{budget.month} 예산: {budget.amount:,}원")
        return 0

    # category 기능: 목록·추가·삭제 흐름을 하나의 명령 그룹으로 처리한다.
    if args.command == "category":
        if args.category_command == "list":
            for name in category_service.list():
                print(f"- {name}")
        elif args.category_command == "add":
            name = args.name or prompt_until("추가할 카테고리", require_text)
            category_service.add(name)
            print(f"카테고리 추가 성공: {name}")
        else:
            name = args.name or prompt_until("삭제할 카테고리", require_text)
            category_service.remove(name)
            print(f"카테고리 삭제 성공: {name}")
        return 0

    # update 기능: 값이 전달된 옵션만 골라 서비스에 넘긴다.
    if args.command == "update":
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
        updated = transaction_service.update(args.id, **changes)
        print(f"수정 성공: {format_transaction(updated)}")
        return 0

    # delete 기능: id에 해당하는 거래를 안전한 파일 재작성 방식으로 삭제한다.
    if args.command == "delete":
        transaction_service.delete(args.id)
        print(f"삭제 성공: id={args.id}")
        return 0

    # import 기능: CSV 전체 검증 및 반영 결과 건수를 출력한다.
    if args.command == "import":
        count = csv_service.import_csv(Path(args.from_path).expanduser())
        print(f"가져오기 완료: {count}건")
        return 0

    # export 기능: 월 또는 날짜 범위에 맞는 거래를 CSV로 저장한다.
    if args.command == "export":
        count = csv_service.export_csv(
            Path(args.out).expanduser(),
            month=args.month,
            from_date=args.from_date,
            to_date=args.to_date,
        )
        print(f"내보내기 완료: {count}건 -> {args.out}")
        return 0


# argparse로 명령행을 해석한 후 공통 실행 함수에 전달한다.
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return execute(args)


if __name__ == "__main__":
    sys.exit(main())
