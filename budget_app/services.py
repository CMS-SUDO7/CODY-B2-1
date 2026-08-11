"""검색, 요약, 예산, 카테고리, CSV 입출력 업무 규칙."""

from __future__ import annotations

import csv
import os
import tempfile
import uuid
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .errors import ConflictError, NotFoundError, StorageError, ValidationError
from .models import Budget, Transaction, normalize_tags, validate_date, validate_month, validate_type
from .repositories import BudgetRepository, CategoryRepository, TransactionRepository


# import/export에서 공통으로 사용하는 고정 CSV 열 순서
CSV_FIELDS = ["date", "type", "category", "amount", "memo", "tags"]


# 거래 업무 기능: add, list, search, update, delete 규칙을 한곳에서 처리
class TransactionService:
    def __init__(self, transactions: TransactionRepository, categories: CategoryRepository) -> None:
        self.transactions = transactions
        self.categories = categories

    def _require_category(self, category: str) -> str:
        # 거래에는 categories.jsonl에 등록된 카테고리만 사용할 수 있다.
        normalized = category.strip()
        if not self.categories.exists(normalized):
            raise ValidationError(
                f"등록되지 않은 카테고리입니다: {normalized}",
                "category list로 확인하거나 category add로 먼저 등록하세요.",
            )
        return normalized

    def create(
        self,
        *,
        date: str,
        type: str,
        category: str,
        amount: int | str,
        memo: str = "",
        tags: list[str] | str | None = None,
    ) -> Transaction:
        # uuid4로 중복 가능성이 매우 낮은 거래 id를 생성한다.
        transaction = Transaction(
            id=uuid.uuid4().hex,
            date=date,
            type=type,
            category=self._require_category(category),
            amount=amount,  # type: ignore[arg-type]
            memo=memo,
            tags=normalize_tags(tags),
        )
        self.transactions.append(transaction)
        return transaction

    def list_latest(self, limit: int) -> Iterator[Transaction]:
        if limit <= 0:
            raise ValidationError("--limit은 1 이상이어야 합니다.", "양수 정수를 입력하세요.")
        # 저장소의 역순 제너레이터에서 필요한 개수까지만 소비한다.
        for index, transaction in enumerate(self.transactions.iter_latest()):
            if index >= limit:
                break
            yield transaction

    def search(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        category: str | None = None,
        type: str | None = None,
        query: str | None = None,
        tag: str | None = None,
        month: str | None = None,
    ) -> Iterator[Transaction]:
        # 파일을 읽기 전에 검색 조건 자체가 올바른지 먼저 검증한다.
        if from_date:
            validate_date(from_date)
        if to_date:
            validate_date(to_date)
        if from_date and to_date and from_date > to_date:
            raise ValidationError(
                "--from 날짜가 --to 날짜보다 늦습니다.",
                "검색 기간의 시작일과 종료일을 바르게 입력하세요.",
            )
        if type:
            type = validate_type(type)
        if category:
            category = self._require_category(category)
        if month:
            validate_month(month)
        keyword = query.casefold() if query else None

        # 조건에 맞는 거래만 yield하므로 검색 결과도 스트리밍된다.
        for item in self.transactions.iter_latest():
            if from_date and item.date < from_date:
                continue
            if to_date and item.date > to_date:
                continue
            if category and item.category != category:
                continue
            if type and item.type != type:
                continue
            if keyword and keyword not in item.memo.casefold():
                continue
            if tag and tag not in item.tags:
                continue
            if month and not item.date.startswith(f"{month}-"):
                continue
            yield item

    def update(self, transaction_id: str, **changes: Any) -> Transaction:
        # CLI에서 실제로 전달된 옵션만 changes에 들어오므로 지정한 필드만 바뀐다.
        if not changes:
            raise ValidationError(
                "수정할 필드가 없습니다.",
                "--date, --type, --category, --amount, --memo, --tags 중 하나 이상 입력하세요.",
            )
        if "category" in changes:
            changes["category"] = self._require_category(changes["category"])
        if "tags" in changes:
            changes["tags"] = normalize_tags(changes["tags"])
        return self.transactions.update(transaction_id, lambda old: old.updated(**changes))

    def delete(self, transaction_id: str) -> None:
        self.transactions.delete(transaction_id)


# 예산 업무 기능: 월 예산을 검증해 저장하고 없는 예산을 구분해서 처리
class BudgetService:
    def __init__(self, budgets: BudgetRepository) -> None:
        self.budgets = budgets

    def set(self, month: str, amount: int | str) -> Budget:
        budget = Budget(month=month, amount=amount)  # type: ignore[arg-type]
        self.budgets.set(budget)
        return budget

    def get(self, month: str) -> Budget:
        validate_month(month)
        budget = self.budgets.get(month)
        if budget is None:
            raise NotFoundError(
                f"{month}에 설정된 예산이 없습니다.",
                "budget set으로 월 예산을 먼저 설정하세요.",
            )
        return budget


# 카테고리 업무 기능: 목록·추가·삭제 및 사용 중 삭제 방지 규칙
class CategoryService:
    def __init__(self, categories: CategoryRepository, transactions: TransactionRepository) -> None:
        self.categories = categories
        self.transactions = transactions

    def list(self) -> Iterator[str]:
        yield from self.categories.iter_names()

    def add(self, name: str) -> None:
        self.categories.add(name)

    def remove(self, name: str) -> None:
        # 거래가 참조하는 카테고리를 지우면 데이터 의미가 깨지므로 삭제를 막는다.
        if any(item.category == name for item in self.transactions.iter_all()):
            raise ConflictError(
                f"사용 중인 카테고리는 삭제할 수 없습니다: {name}",
                "해당 거래의 카테고리를 update로 변경한 뒤 다시 시도하세요.",
            )
        self.categories.remove(name)


# 요약 업무 기능: 월 수입·지출·잔액·카테고리 순위·예산 사용률 계산
class SummaryService:
    def __init__(self, transactions: TransactionRepository, budgets: BudgetRepository) -> None:
        self.transactions = transactions
        self.budgets = budgets

    def monthly(self, month: str, top: int) -> dict[str, Any] | None:
        validate_month(month)
        if top <= 0:
            raise ValidationError("--top은 1 이상이어야 합니다.", "양수 정수를 입력하세요.")

        income = 0
        expense = 0
        count = 0
        category_expenses: dict[str, int] = defaultdict(int)
        # 거래를 한 건씩 읽으면서 합계만 누적하므로 전체 목록을 저장하지 않는다.
        for item in self.transactions.iter_all():
            if not item.date.startswith(f"{month}-"):
                continue
            count += 1
            if item.type == "income":
                income += item.amount
            else:
                expense += item.amount
                category_expenses[item.category] += item.amount
        if count == 0:
            return None

        # 금액은 내림차순, 금액이 같으면 카테고리 이름순으로 정렬한다.
        ranked = sorted(category_expenses.items(), key=lambda pair: (-pair[1], pair[0]))[:top]
        budget = self.budgets.get(month)
        return {
            "month": month,
            "count": count,
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "top_categories": ranked,
            "budget": budget.amount if budget else None,
            "usage_rate": (expense / budget.amount * 100) if budget else None,
            "over_budget": expense > budget.amount if budget else False,
        }


# CSV 업무 기능: 전체 검증 후 가져오기와 조건별 원자적 내보내기
class CsvService:
    def __init__(self, transaction_service: TransactionService) -> None:
        self.transaction_service = transaction_service

    def import_csv(self, source: Path) -> int:
        if not source.is_file():
            raise NotFoundError(
                f"CSV 파일을 찾을 수 없습니다: {source}",
                "--from 경로를 확인하세요.",
            )
        # 일부 행만 저장되는 일을 막기 위해 모든 행을 먼저 검증해 준비한다.
        prepared: list[Transaction] = []
        try:
            with source.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if reader.fieldnames is None:
                    raise ValidationError("CSV 헤더가 없습니다.", "README의 CSV 스키마를 확인하세요.")
                missing = [field for field in CSV_FIELDS[:4] if field not in reader.fieldnames]
                if missing:
                    raise ValidationError(
                        f"CSV 필수 열이 없습니다: {', '.join(missing)}",
                        "date,type,category,amount 헤더를 포함하세요.",
                    )
                for row_number, row in enumerate(reader, start=2):
                    try:
                        prepared.append(
                            Transaction(
                                id=uuid.uuid4().hex,
                                date=row.get("date", ""),
                                type=row.get("type", ""),
                                category=self.transaction_service._require_category(row.get("category", "")),
                                amount=row.get("amount", ""),  # type: ignore[arg-type]
                                memo=row.get("memo", ""),
                                tags=normalize_tags(row.get("tags", "")),
                            )
                        )
                    except ValidationError as exc:
                        raise ValidationError(
                            f"CSV {row_number}번째 줄 오류: {exc.message}",
                            exc.hint,
                        ) from exc
        except UnicodeDecodeError as exc:
            raise ValidationError(
                "CSV 파일이 UTF-8 형식이 아닙니다.",
                "파일을 UTF-8로 저장한 뒤 다시 시도하세요.",
            ) from exc
        except OSError as exc:
            raise StorageError(
                f"CSV 파일을 읽을 수 없습니다: {source}",
                "경로와 읽기 권한을 확인하세요.",
            ) from exc

        # 전 행이 유효할 때만 기존 JSONL과 합쳐 원자적으로 반영한다.
        self.transaction_service.transactions.append_many(prepared)
        return len(prepared)

    def export_csv(
        self,
        output: Path,
        *,
        month: str | None,
        from_date: str | None,
        to_date: str | None,
    ) -> int:
        # 실수로 전체 데이터를 내보내지 않도록 기간 조건을 필수로 한다.
        if not month and not (from_date or to_date):
            raise ValidationError(
                "export에는 기간 조건이 필요합니다.",
                "--month 또는 --from/--to를 하나 이상 입력하세요.",
            )
        if month and (from_date or to_date):
            raise ValidationError(
                "--month와 --from/--to를 함께 사용할 수 없습니다.",
                "월 조건 또는 날짜 범위 중 하나만 선택하세요.",
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        count = 0
        try:
            # CSV도 임시 파일을 완성한 뒤 os.replace로 교체한다.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp:
                temp_name = temp.name
                writer = csv.DictWriter(temp, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for item in self.transaction_service.search(
                    month=month,
                    from_date=from_date,
                    to_date=to_date,
                ):
                    writer.writerow(
                        {
                            "date": item.date,
                            "type": item.type,
                            "category": item.category,
                            "amount": item.amount,
                            "memo": item.memo,
                            "tags": ",".join(item.tags),
                        }
                    )
                    count += 1
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, output)
        except OSError as exc:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise StorageError(
                f"CSV 파일을 저장할 수 없습니다: {output}",
                "출력 경로의 권한과 남은 용량을 확인하세요.",
            ) from exc
        return count
