from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal


class BudgetAppError(Exception):
    """사용자에게 원인과 해결 방법을 보여줄 수 있는 오류."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ValidationError(BudgetAppError):
    pass


class NotFoundError(BudgetAppError):
    pass


class ConflictError(BudgetAppError):
    pass

TransactionType = Literal["income", "expense"]


def validate_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"날짜 형식이 올바르지 않습니다: {value}",
            "YYYY-MM-DD 형식으로 입력하세요.",
        ) from exc
    if parsed.isoformat() != value:
        raise ValidationError("날짜 형식이 올바르지 않습니다.", "YYYY-MM-DD 형식으로 입력하세요.")
    return value


def validate_month(value: str) -> str:
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"월 형식이 올바르지 않습니다: {value}",
            "YYYY-MM 형식으로 입력하세요.",
        ) from exc
    if parsed.strftime("%Y-%m") != value:
        raise ValidationError("월 형식이 올바르지 않습니다.", "YYYY-MM 형식으로 입력하세요.")
    return value


def parse_positive_amount(value: str | int) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("금액은 정수여야 합니다.", "0보다 큰 정수를 입력하세요.") from exc
    if amount <= 0:
        raise ValidationError("금액은 0보다 커야 합니다.", "양의 정수를 입력하세요.")
    return amount


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    type: TransactionType
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValidationError("거래 id가 비어 있습니다.")
        if self.type not in ("income", "expense"):
            raise ValidationError(
                f"허용되지 않은 거래 유형입니다: {self.type}",
                "income 또는 expense를 사용하세요.",
            )
        validate_date(self.date)
        parse_positive_amount(self.amount)
        if not self.category.strip():
            raise ValidationError("카테고리가 비어 있습니다.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Transaction:
        return cls(
            id=str(value["id"]),
            type=value["type"],
            date=str(value["date"]),
            amount=parse_positive_amount(value["amount"]),
            category=str(value["category"]),
            memo=str(value.get("memo", "")),
            tags=[str(tag) for tag in value.get("tags", [])],
        )


@dataclass(frozen=True, slots=True)
class Budget:
    month: str
    amount: int

    def __post_init__(self) -> None:
        validate_month(self.month)
        parse_positive_amount(self.amount)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
