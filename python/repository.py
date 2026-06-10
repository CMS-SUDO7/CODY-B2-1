import json
import os
import tempfile
from pathlib import Path
from typing import Generator, List, Any, Dict

class FileRepository:
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.transactions_file = self.data_dir / "transactions.jsonl"
        self.categories_file = self.data_dir / "categories.jsonl"
        self.budgets_file = self.data_dir / "budgets.jsonl"
        self._initialize_files()

    def _initialize_files(self):
        # 파일이 없으면 생성
        for file in [self.transactions_file, self.budgets_file]:
            if not file.exists():
                file.touch()
        
        # 카테고리가 비어있으면 기본 데이터 생성 (안 A)
        if not self.categories_file.exists() or self.categories_file.stat().st_size == 0:
            default_categories = ["food", "transport", "rent", "salary", "etc"]
            with open(self.categories_file, 'w', encoding='utf-8') as f:
                for c in default_categories:
                    f.write(json.dumps({"name": c}) + '\n')

    def append_record(self, file_path: Path, data: dict):
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data) + '\n')

    def _reverse_readline(self, file_path: Path) -> Generator[str, None, None]:
        """최신순 조회를 위한 파일 역순 읽기 제너레이터 (스트리밍)"""
        if not file_path.exists() or file_path.stat().st_size == 0:
            return
        
        with open(file_path, 'rb') as f:
            f.seek(0, 2)
            position = f.tell()
            buffer = b''
            while position > 0:
                read_size = min(1024, position)
                f.seek(position - read_size)
                chunk = f.read(read_size)
                buffer = chunk + buffer
                position -= read_size
                if b'\n' in buffer:
                    lines = buffer.split(b'\n')
                    buffer = lines[0]
                    for line in reversed(lines[1:]):
                        if line: yield line.decode('utf-8')
            if buffer:
                yield buffer.decode('utf-8')

    def get_all_transactions_desc(self) -> Generator[Dict[str, Any], None, None]:
        """거래 내역을 최신순으로 제너레이터 반환"""
        for line in self._reverse_readline(self.transactions_file):
            yield json.loads(line)

    def get_all_categories(self) -> List[str]:
        categories = []
        if self.categories_file.exists():
            with open(self.categories_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        categories.append(json.loads(line)["name"])
        return categories

    def get_budget(self, month: str) -> int:
        budget = 0
        if self.budgets_file.exists():
            with open(self.budgets_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data["month"] == month:
                            budget = data["amount"]
        return budget

    def atomic_rewrite_transactions(self, transactions: List[Dict[str, Any]]):
        """임시 파일을 활용한 원자적 업데이트"""
        fd, temp_path = tempfile.mkstemp(dir=self.data_dir, text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            for t in transactions:
                f.write(json.dumps(t) + '\n')
        os.replace(temp_path, self.transactions_file)

    def atomic_rewrite_categories(self, categories: List[str]):
        fd, temp_path = tempfile.mkstemp(dir=self.data_dir, text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            for c in categories:
                f.write(json.dumps({"name": c}) + '\n')
        os.replace(temp_path, self.categories_file)