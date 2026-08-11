"""거래와 예산 데이터 구조 및 기본 검증."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from .errors import ValidationError


# 거래 타입은 수입과 지출 두 값만 허용한다.
ALLOWED_TYPES = {"income", "expense"}


# 입력 검증 기능: 실제 달력에 존재하는 YYYY-MM-DD인지 확인한다.
def validate_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"날짜 형식이 올바르지 않습니다: {value}",
            "YYYY-MM-DD 형식으로 입력하세요. 예: 2026-08-10",
        ) from exc
    return value


# 입력 검증 기능: 월별 요약과 예산에 쓰는 YYYY-MM 형식을 확인한다.
def validate_month(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"월 형식이 올바르지 않습니다: {value}",
            "YYYY-MM 형식으로 입력하세요. 예: 2026-08",
        ) from exc
    return value


# 입력 검증 기능: 금액을 정수로 변환하고 양수인지 확인한다.
def validate_amount(value: int | str) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"금액은 정수여야 합니다: {value}",
            "0보다 큰 정수를 입력하세요.",
        ) from exc
    if amount <= 0:
        raise ValidationError(
            f"금액은 0보다 커야 합니다: {amount}",
            "양수 정수를 입력하세요.",
        )
    return amount


# 입력 검증 기능: 대소문자를 정리한 뒤 income/expense만 통과시킨다.
def validate_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in ALLOWED_TYPES:
        raise ValidationError(
            f"허용되지 않은 거래 타입입니다: {value}",
            "income 또는 expense를 입력하세요.",
        )
    return normalized


# 태그 처리 기능: 문자열 또는 목록을 받아 공백·빈 값·중복을 제거한다.
def normalize_tags(value: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if value is None:
        return []
    raw_tags = value.split(",") if isinstance(value, str) else value
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        tag = str(item).strip()
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


# 거래 데이터 모델: 한 건의 거래가 반드시 가져야 할 필드와 규칙을 정의한다.
@dataclass(slots=True)
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # 객체가 생성되는 모든 경로(add, update, import, JSONL 읽기)에 같은 검증을 적용한다.
        self.id = str(self.id).strip()
        if not self.id:
            raise ValidationError("거래 id가 비어 있습니다.", "유일한 id를 지정하세요.")
        self.type = validate_type(self.type)
        self.date = validate_date(self.date)
        self.amount = validate_amount(self.amount)
        self.category = str(self.category).strip()
        if not self.category:
            raise ValidationError("카테고리가 비어 있습니다.", "등록된 카테고리를 입력하세요.")
        self.memo = str(self.memo).strip()
        self.tags = normalize_tags(self.tags)

    def to_dict(self) -> dict[str, Any]:
        # JSONL에 저장 가능한 기본 자료형으로 변환한다.
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date,
            "amount": self.amount,
            "category": self.category,
            "memo": self.memo,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        # JSONL 한 줄을 Transaction 객체로 복원한다.
        try:
            return cls(
                id=data["id"],
                type=data["type"],
                date=data["date"],
                amount=data["amount"],
                category=data["category"],
                memo=data.get("memo", ""),
                tags=data.get("tags", []),
            )
        except KeyError as exc:
            raise ValidationError(
                f"거래 데이터에 필수 필드가 없습니다: {exc.args[0]}",
                "transactions.jsonl 파일 형식을 확인하세요.",
            ) from exc

    def updated(self, **changes: Any) -> Transaction:
        # 기존 객체를 직접 바꾸지 않고, 변경 사항이 반영된 새 객체를 만든다.
        return replace(self, **changes)


# 예산 데이터 모델: 월과 양수 금액의 조합을 검증한다.
@dataclass(slots=True)
class Budget:
    month: str
    amount: int

    def __post_init__(self) -> None:
        # 예산도 생성과 파일 복원 시 동일한 검증 규칙을 거친다.
        self.month = validate_month(self.month)
        self.amount = validate_amount(self.amount)

    def to_dict(self) -> dict[str, Any]:
        return {"month": self.month, "amount": self.amount}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Budget:
        try:
            return cls(month=data["month"], amount=data["amount"])
        except KeyError as exc:
            raise ValidationError(
                f"예산 데이터에 필수 필드가 없습니다: {exc.args[0]}",
                "budgets.jsonl 파일 형식을 확인하세요.",
            ) from exc
