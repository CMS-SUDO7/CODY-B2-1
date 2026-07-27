from __future__ import annotations

import csv
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from .models import (
    Budget,
    ConflictError,
    NotFoundError,
    Transaction,
    ValidationError,
    parse_positive_amount,
    validate_date,
    validate_month,
)
from .repositories import BudgetStore, CategoryStore, TransactionRepository


class BudgetService:
    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.transactions = TransactionRepository(data_dir)
        self.categories = CategoryStore(data_dir)
        self.budgets = BudgetStore(data_dir)

    def _require_category(self, category: str) -> None:
        if not self.categories.contains(category):
            raise ValidationError(
                f"등록되지 않은 카테고리입니다: {category}",
                "category list로 확인하거나 category add로 먼저 등록하세요.",
            )

    def add_transaction(
        self,
        *,
        date: str,
        type: str,
        category: str,
        amount: str | int,
        memo: str = "",
        tags: list[str] | None = None,
    ) -> Transaction:
        self._require_category(category)
        transaction = Transaction(
            id=uuid.uuid4().hex,
            type=type,  # type: ignore[arg-type]
            date=validate_date(date),
            amount=parse_positive_amount(amount),
            category=category,
            memo=memo.strip(),
            tags=[tag.strip() for tag in (tags or []) if tag.strip()],
        )
        self.transactions.append(transaction)
        return transaction

    def list_transactions(self, limit: int) -> Iterator[Transaction]:
        if limit <= 0:
            raise ValidationError("--limit은 0보다 커야 합니다.")
        for index, transaction in enumerate(self.transactions.iter_latest()):
            if index >= limit:
                break
            yield transaction

    def search(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        type: str | None = None,
        query: str | None = None,
        tag: str | None = None,
    ) -> Iterator[Transaction]:
        if date_from:
            validate_date(date_from)
        if date_to:
            validate_date(date_to)
        if date_from and date_to and date_from > date_to:
            raise ValidationError("--from은 --to보다 늦을 수 없습니다.")
        if type and type not in ("income", "expense"):
            raise ValidationError("--type은 income 또는 expense여야 합니다.")
        lowered_query = query.casefold() if query else None
        for item in self.transactions.iter_latest():
            if date_from and item.date < date_from:
                continue
            if date_to and item.date > date_to:
                continue
            if category and item.category != category:
                continue
            if type and item.type != type:
                continue
            if lowered_query and lowered_query not in item.memo.casefold():
                continue
            if tag and tag not in item.tags:
                continue
            yield item

    def update_transaction(self, target_id: str, changes: dict[str, object]) -> Transaction:
        if "category" in changes:
            self._require_category(str(changes["category"]))
        if "date" in changes:
            changes["date"] = validate_date(str(changes["date"]))
        if "amount" in changes:
            changes["amount"] = parse_positive_amount(changes["amount"])  # type: ignore[arg-type]
        if "type" in changes and changes["type"] not in ("income", "expense"):
            raise ValidationError("--type은 income 또는 expense여야 합니다.")
        if "tags" in changes:
            changes["tags"] = [tag.strip() for tag in str(changes["tags"]).split(",") if tag.strip()]
        if not changes:
            raise ValidationError(
                "수정할 필드가 없습니다.",
                "--date, --type, --category, --amount, --memo, --tags 중 하나를 지정하세요.",
            )
        updated: Transaction | None = None

        def transform(item: Transaction) -> Transaction:
            nonlocal updated
            updated = replace(item, **changes)
            return updated

        if not self.transactions.rewrite(target_id, transform):
            raise NotFoundError(
                f"id={target_id} 거래가 없습니다.",
                "list 또는 search로 거래 id를 확인하세요.",
            )
        assert updated is not None
        return updated

    def delete_transaction(self, target_id: str) -> None:
        self.transactions.delete(target_id)

    def monthly_summary(self, month: str, top: int) -> dict[str, object]:
        validate_month(month)
        if top <= 0:
            raise ValidationError("--top은 0보다 커야 합니다.")
        income = expense = count = 0
        by_category: dict[str, int] = defaultdict(int)
        for item in self.transactions.iter_all():
            if item.date.startswith(month):
                count += 1
                if item.type == "income":
                    income += item.amount
                else:
                    expense += item.amount
                    by_category[item.category] += item.amount
        categories = sorted(by_category.items(), key=lambda pair: (-pair[1], pair[0]))[:top]
        return {
            "count": count,
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "categories": categories,
            "budget": self.budgets.get(month),
        }

    def set_budget(self, month: str, amount: str | int) -> Budget:
        budget = Budget(month=validate_month(month), amount=parse_positive_amount(amount))
        self.budgets.set(budget)
        return budget

    def remove_category(self, name: str) -> None:
        if self.transactions.exists_with_category(name):
            raise ConflictError(
                f"카테고리 '{name}'를 사용하는 거래가 있어 삭제할 수 없습니다.",
                "해당 거래의 카테고리를 먼저 update한 후 다시 삭제하세요.",
            )
        self.categories.remove(name)

    def import_csv(self, source: Path) -> tuple[int, int]:
        imported = skipped = 0
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"date", "type", "category", "amount"} <= set(reader.fieldnames):
                raise ValidationError(
                    "CSV 헤더에 필수 열이 없습니다.",
                    "date,type,category,amount,memo,tags 스키마를 사용하세요.",
                )
            for row_number, row in enumerate(reader, 2):
                try:
                    self.add_transaction(
                        date=row.get("date") or "",
                        type=row.get("type") or "",
                        category=row.get("category") or "",
                        amount=row.get("amount") or "",
                        memo=row.get("memo", ""),
                        tags=(row.get("tags") or "").split(","),
                    )
                    imported += 1
                except ValidationError:
                    skipped += 1
        return imported, skipped

    def export_csv(
        self,
        output: Path,
        *,
        month: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> int:
        if not month and not date_from and not date_to:
            raise ValidationError(
                "export에는 조회 조건이 필요합니다.",
                "--month 또는 --from/--to를 지정하세요.",
            )
        if month:
            validate_month(month)
            month_from, month_to = f"{month}-01", f"{month}-31"
            if date_from or date_to:
                raise ValidationError("--month와 --from/--to는 함께 사용할 수 없습니다.")
            date_from, date_to = month_from, month_to
        output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with output.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["date", "type", "category", "amount", "memo", "tags"]
            )
            writer.writeheader()
            for item in self.search(date_from=date_from, date_to=date_to):
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
        return count
