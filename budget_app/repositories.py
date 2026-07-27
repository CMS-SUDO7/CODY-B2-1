from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .models import Budget, ConflictError, NotFoundError, Transaction

DEFAULT_CATEGORIES = ("food", "transport", "rent", "salary", "health", "leisure", "other")


def _write_json_line(stream: Any, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def reverse_lines(path: Path, chunk_size: int = 8192) -> Iterator[str]:
    """UTF-8 텍스트 파일을 마지막 줄부터 메모리 제한적으로 읽는다."""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        position = stream.tell()
        buffer = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            stream.seek(position)
            buffer = stream.read(read_size) + buffer
            lines = buffer.split(b"\n")
            buffer = lines[0]
            for line in reversed(lines[1:]):
                if line:
                    yield line.decode("utf-8").removesuffix("\r")
        if buffer:
            yield buffer.decode("utf-8").removesuffix("\r")


class TransactionRepository:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "transactions.jsonl"
        self.path.touch(exist_ok=True)

    def append(self, transaction: Transaction) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            _write_json_line(stream, transaction.to_dict())
            stream.flush()
            os.fsync(stream.fileno())

    def iter_all(self) -> Iterator[Transaction]:
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    try:
                        yield Transaction.from_dict(json.loads(line))
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise ConflictError(
                            f"거래 파일 {line_number}번째 줄이 손상되었습니다.",
                            "해당 줄의 JSON 형식과 필수 필드를 확인하세요.",
                        ) from exc

    def iter_latest(self) -> Iterator[Transaction]:
        for line in reverse_lines(self.path):
            try:
                yield Transaction.from_dict(json.loads(line))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConflictError(
                    "거래 파일에 손상된 줄이 있습니다.",
                    "transactions.jsonl의 JSON 형식을 확인하세요.",
                ) from exc

    def exists_with_category(self, category: str) -> bool:
        return any(item.category == category for item in self.iter_all())

    def rewrite(
        self,
        target_id: str,
        transform: Callable[[Transaction], Transaction | None],
    ) -> bool:
        found = False
        fd, temporary_name = tempfile.mkstemp(
            prefix=".transactions-", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
                for transaction in self.iter_all():
                    if transaction.id == target_id:
                        found = True
                        replacement = transform(transaction)
                        if replacement is not None:
                            _write_json_line(output, replacement.to_dict())
                    else:
                        _write_json_line(output, transaction.to_dict())
                output.flush()
                os.fsync(output.fileno())
            if found:
                os.replace(temporary, self.path)
            else:
                temporary.unlink(missing_ok=True)
            return found
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def delete(self, target_id: str) -> None:
        if not self.rewrite(target_id, lambda _: None):
            raise NotFoundError(
                f"id={target_id} 거래가 없습니다.",
                "list 또는 search로 거래 id를 확인하세요.",
            )


class CategoryStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "categories.jsonl"
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", encoding="utf-8", newline="\n") as stream:
                for name in DEFAULT_CATEGORIES:
                    _write_json_line(stream, {"name": name})

    def iter_all(self) -> Iterator[str]:
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    value = json.loads(line)
                    yield str(value["name"])

    def contains(self, name: str) -> bool:
        return any(item == name for item in self.iter_all())

    def add(self, name: str) -> None:
        if self.contains(name):
            raise ConflictError(f"이미 존재하는 카테고리입니다: {name}")
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            _write_json_line(stream, {"name": name})

    def remove(self, name: str) -> None:
        categories = list(self.iter_all())
        if name not in categories:
            raise NotFoundError(f"존재하지 않는 카테고리입니다: {name}")
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                for category in categories:
                    if category != name:
                        _write_json_line(stream, {"name": category})
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


class BudgetStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "budgets.jsonl"
        self.path.touch(exist_ok=True)

    def iter_all(self) -> Iterator[Budget]:
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    value = json.loads(line)
                    yield Budget(month=str(value["month"]), amount=int(value["amount"]))

    def get(self, month: str) -> Budget | None:
        return next((item for item in self.iter_all() if item.month == month), None)

    def set(self, budget: Budget) -> None:
        values = {item.month: item for item in self.iter_all()}
        values[budget.month] = budget
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                for month in sorted(values):
                    _write_json_line(stream, values[month].to_dict())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
