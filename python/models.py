import uuid
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Transaction:
    id: str
    type: str  # 'income' or 'expense'
    date: str  # YYYY-MM-DD
    amount: int
    category: str
    memo: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @classmethod
    def create(cls, type: str, date: str, amount: int, category: str, memo: str = "", tags: str = "") -> 'Transaction':
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        return cls(
            id=uuid.uuid4().hex[:8],
            type=type,
            date=date,
            amount=amount,
            category=category,
            memo=memo if memo else None,
            tags=tag_list
        )

@dataclass
class Category:
    name: str

@dataclass
class Budget:
    month: str  # YYYY-MM
    amount: int