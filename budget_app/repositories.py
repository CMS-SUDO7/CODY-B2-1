"""JSONL 스트리밍 읽기, 쓰기 및 원자적 파일 교체."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from .errors import NotFoundError, StorageError, ValidationError
from .models import Budget, Transaction


# categories.jsonl이 비어 있을 때 자동으로 생성할 기본 카테고리
DEFAULT_CATEGORIES = ("food", "transport", "housing", "health", "salary", "etc")


# JSONL 저장소 공통 기능: 파일 준비, 한 줄씩 읽기, 추가, 원자적 교체
class JsonlRepository:
    def __init__(self, path: Path) -> None:
        # 최초 실행에서도 별도 초기화 명령 없이 폴더와 파일을 사용할 수 있게 한다.
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _iter_dicts(self) -> Iterator[dict[str, Any]]:
        # yield를 사용하므로 파일 전체가 아니라 현재 한 줄만 메모리에 유지한다.
        try:
            with self.path.open("r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise StorageError(
                            f"{self.path.name} {line_number}번째 줄의 JSON이 손상되었습니다.",
                            "해당 줄을 백업한 뒤 JSON 형식을 수정하세요.",
                        ) from exc
                    if not isinstance(data, dict):
                        raise StorageError(
                            f"{self.path.name} {line_number}번째 줄이 객체가 아닙니다.",
                            "각 줄을 JSON 객체 형태로 저장하세요.",
                        )
                    yield data
        except OSError as exc:
            raise StorageError(
                f"파일을 읽을 수 없습니다: {self.path}",
                "경로와 파일 권한을 확인하세요.",
            ) from exc

    def _append_dict(self, data: dict[str, Any]) -> None:
        # add처럼 기존 데이터를 바꿀 필요가 없는 작업은 파일 끝에 한 줄을 추가한다.
        try:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(data, ensure_ascii=False) + "\n")
                # 운영체제 버퍼까지 밀어 데이터 유실 가능성을 낮춘다.
                file.flush()
                os.fsync(file.fileno())
        except OSError as exc:
            raise StorageError(
                f"파일에 저장할 수 없습니다: {self.path}",
                "저장 폴더의 경로, 권한, 남은 용량을 확인하세요.",
            ) from exc

    def _atomic_write_dicts(self, items: Iterator[dict[str, Any]]) -> None:
        # update/delete는 원본 대신 임시 파일을 완성한 후 한 번에 교체한다.
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp:
                temp_name = temp.name
                for item in items:
                    temp.write(json.dumps(item, ensure_ascii=False) + "\n")
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, self.path)
            # 파일 교체 정보도 디스크에 반영되도록 폴더를 동기화한다.
            self._sync_directory()
        except OSError as exc:
            self._remove_temp_file(temp_name)
            raise StorageError(
                f"파일을 안전하게 교체하지 못했습니다: {self.path}",
                "저장 폴더의 권한과 남은 용량을 확인하세요.",
            ) from exc
        except BaseException:
            # 검증 실패나 Ctrl+C가 발생해도 완성되지 않은 임시 파일을 남기지 않는다.
            self._remove_temp_file(temp_name)
            raise

    @staticmethod
    def _remove_temp_file(temp_name: str | None) -> None:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass

    def _sync_directory(self) -> None:
        # 일부 운영체제에서는 지원되지 않을 수 있으므로 실패해도 본 작업은 유지한다.
        try:
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)


# 거래 저장소: 거래 추가·조회·수정·삭제와 최신순 스트리밍 담당
class TransactionRepository(JsonlRepository):
    def iter_all(self) -> Iterator[Transaction]:
        # summary나 카테고리 사용 여부 확인처럼 전체 순회가 필요한 기능에서 사용한다.
        for data in self._iter_dicts():
            yield Transaction.from_dict(data)

    def iter_latest(self) -> Iterator[Transaction]:
        """파일을 통째로 올리지 않고 뒤에서부터 한 줄씩 읽는다."""
        for line_number, line in self._iter_lines_reverse():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise StorageError(
                    f"{self.path.name}의 역순 {line_number}번째 데이터가 손상되었습니다.",
                    "transactions.jsonl의 JSON 형식을 확인하세요.",
                ) from exc
            if not isinstance(data, dict):
                raise StorageError(
                    f"{self.path.name}에 객체가 아닌 데이터가 있습니다.",
                    "각 줄을 JSON 객체 형태로 저장하세요.",
                )
            yield Transaction.from_dict(data)

    def _iter_lines_reverse(self, chunk_size: int = 8192) -> Iterator[tuple[int, str]]:
        # 파일 끝에서 일정 크기만큼 나눠 읽어 최근 등록 거래부터 반환한다.
        try:
            with self.path.open("rb") as file:
                file.seek(0, os.SEEK_END)
                position = file.tell()
                buffer = b""
                reverse_number = 0
                while position > 0:
                    read_size = min(chunk_size, position)
                    position -= read_size
                    file.seek(position)
                    buffer = file.read(read_size) + buffer
                    lines = buffer.split(b"\n")
                    buffer = lines[0]
                    for raw_line in reversed(lines[1:]):
                        if raw_line:
                            reverse_number += 1
                            yield reverse_number, raw_line.decode("utf-8")
                if buffer:
                    reverse_number += 1
                    yield reverse_number, buffer.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise StorageError(
                f"파일을 역순으로 읽을 수 없습니다: {self.path}",
                "파일이 UTF-8인지와 읽기 권한을 확인하세요.",
            ) from exc

    def append(self, transaction: Transaction) -> None:
        self._append_dict(transaction.to_dict())

    def append_many(self, transactions: Sequence[Transaction]) -> None:
        # import 데이터는 기존 거래와 합친 임시 파일을 완성한 뒤 한 번에 반영한다.
        def combined() -> Iterator[dict[str, Any]]:
            yield from self._iter_dicts()
            for transaction in transactions:
                yield transaction.to_dict()

        self._atomic_write_dicts(combined())

    def find(self, transaction_id: str) -> Transaction | None:
        return next((item for item in self.iter_all() if item.id == transaction_id), None)

    def update(self, transaction_id: str, transform: Callable[[Transaction], Transaction]) -> Transaction:
        updated: Transaction | None = None

        # 대상 id만 새 객체로 바꾸고 나머지는 그대로 임시 파일에 기록한다.
        def changed_items() -> Iterator[dict[str, Any]]:
            nonlocal updated
            for item in self.iter_all():
                if item.id == transaction_id:
                    updated = transform(item)
                    yield updated.to_dict()
                else:
                    yield item.to_dict()

        self._atomic_write_dicts(changed_items())
        if updated is None:
            raise NotFoundError(
                f"거래를 찾을 수 없습니다: {transaction_id}",
                "list 명령으로 id를 확인하세요.",
            )
        return updated

    def delete(self, transaction_id: str) -> None:
        found = False

        # 삭제할 id를 제외한 모든 거래를 임시 파일에 기록한다.
        def remaining() -> Iterator[dict[str, Any]]:
            nonlocal found
            for item in self.iter_all():
                if item.id == transaction_id:
                    found = True
                    continue
                yield item.to_dict()

        self._atomic_write_dicts(remaining())
        if not found:
            raise NotFoundError(
                f"거래를 찾을 수 없습니다: {transaction_id}",
                "list 명령으로 id를 확인하세요.",
            )


# 카테고리 저장소: 문자열 카테고리를 별도 JSONL 파일로 관리
class CategoryRepository(JsonlRepository):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        # 안 A 정책: 파일이 비어 있으면 기본 카테고리를 자동 생성한다.
        if self.path.stat().st_size == 0:
            self._atomic_write_dicts({"name": name} for name in DEFAULT_CATEGORIES)

    def iter_names(self) -> Iterator[str]:
        for data in self._iter_dicts():
            name = str(data.get("name", "")).strip()
            if not name:
                raise ValidationError(
                    "카테고리 파일에 빈 이름이 있습니다.",
                    "categories.jsonl의 name 값을 확인하세요.",
                )
            yield name

    def exists(self, name: str) -> bool:
        return any(current == name for current in self.iter_names())

    def add(self, name: str) -> None:
        normalized = name.strip()
        if not normalized:
            raise ValidationError("카테고리 이름이 비어 있습니다.", "이름을 입력하세요.")
        if self.exists(normalized):
            raise ValidationError(
                f"이미 존재하는 카테고리입니다: {normalized}",
                "category list로 목록을 확인하세요.",
            )
        self._append_dict({"name": normalized})

    def remove(self, name: str) -> None:
        found = False

        # 카테고리 삭제 역시 임시 파일과 원자적 교체 방식을 사용한다.
        def remaining() -> Iterator[dict[str, Any]]:
            nonlocal found
            for current in self.iter_names():
                if current == name:
                    found = True
                    continue
                yield {"name": current}

        self._atomic_write_dicts(remaining())
        if not found:
            raise NotFoundError(
                f"카테고리를 찾을 수 없습니다: {name}",
                "category list로 이름을 확인하세요.",
            )


# 예산 저장소: 월별 예산 조회와 같은 월의 예산 갱신 담당
class BudgetRepository(JsonlRepository):
    def iter_all(self) -> Iterator[Budget]:
        for data in self._iter_dicts():
            yield Budget.from_dict(data)

    def get(self, month: str) -> Budget | None:
        return next((budget for budget in self.iter_all() if budget.month == month), None)

    def set(self, budget: Budget) -> None:
        replaced = False

        # 같은 월이 있으면 교체하고, 없으면 파일 마지막에 새 예산을 추가한다.
        def budgets() -> Iterator[dict[str, Any]]:
            nonlocal replaced
            for current in self.iter_all():
                if current.month == budget.month:
                    replaced = True
                    yield budget.to_dict()
                else:
                    yield current.to_dict()
            if not replaced:
                yield budget.to_dict()

        self._atomic_write_dicts(budgets())
