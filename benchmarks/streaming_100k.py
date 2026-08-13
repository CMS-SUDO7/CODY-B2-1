"""10만 건 JSONL에서 스트리밍 시간과 Python 최대 메모리를 재는 스크립트."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

# 파일을 직접 실행해도 형제 폴더인 budget_app 패키지를 찾을 수 있게 한다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from budget_app.repositories import CategoryRepository, TransactionRepository
from budget_app.services import TransactionService


RECORD_COUNT = 100_000
T = TypeVar("T")


def measure(operation: Callable[[], T]) -> tuple[T, float, float]:
    tracemalloc.start()
    started = time.perf_counter()
    result = operation()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak / 1024 / 1024


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        root = Path(temp_directory)
        transaction_path = root / "transactions.jsonl"
        with transaction_path.open("w", encoding="utf-8") as file:
            for index in range(RECORD_COUNT):
                row = {
                    "id": f"bench-{index:06d}",
                    "type": "expense",
                    "date": "2026-08-01",
                    "amount": index + 1,
                    "category": "food",
                    "memo": "benchmark",
                    "tags": ["large"],
                }
                file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

        repository = TransactionRepository(transaction_path)
        categories = CategoryRepository(root / "categories.jsonl")
        service = TransactionService(repository, categories)

        latest, list_seconds, list_peak = measure(lambda: list(service.list_latest(20)))
        found, search_seconds, search_peak = measure(
            lambda: sum(1 for _ in service.search(query="없는키워드"))
        )

        print(f"레코드: {RECORD_COUNT:,}건")
        print(f"파일 크기: {transaction_path.stat().st_size / 1024 / 1024:.2f} MiB")
        print(f"list 20: {len(latest)}건, {list_seconds:.4f}초, 최대 {list_peak:.3f} MiB")
        print(f"전체 검색: {found}건, {search_seconds:.4f}초, 최대 {search_peak:.3f} MiB")


if __name__ == "__main__":
    main()
