"""CLI부터 JSONL 파일까지 연결하는 표준 라이브러리 통합 테스트."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BudgetAppIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_directory.name) / "data"

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def run_cli(self, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "budget_app",
                "--data-dir",
                str(self.data_dir),
                *arguments,
            ],
            cwd=PROJECT_ROOT,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_add_then_new_process_can_list_and_search(self) -> None:
        added = self.run_cli(
            "add",
            input_text="2026-08-10\nexpense\nfood\n12000\n점심\n회사,식사\n",
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("저장 성공: id=", added.stdout)

        # 별도 프로세스로 다시 실행해도 JSONL에 저장된 거래가 유지되어야 한다.
        listed = self.run_cli("list", "--limit", "1")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("12,000원", listed.stdout)
        self.assertIn("memo=점심", listed.stdout)

        searched = self.run_cli("search", "--category", "food", "--tag", "회사")
        self.assertEqual(searched.returncode, 0, searched.stderr)
        self.assertIn("총 1건", searched.stdout)

    def test_summary_prints_budget_warning(self) -> None:
        self.run_cli(
            "add",
            input_text="2026-08-10\nexpense\nfood\n12000\n점심\n\n",
        )
        budget = self.run_cli("budget", "set", "--month", "2026-08", "--amount", "10000")
        self.assertEqual(budget.returncode, 0, budget.stderr)

        summary = self.run_cli("summary", "--month", "2026-08")
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertIn("예산 사용률: 120.0%", summary.stdout)
        self.assertIn("경고: 월 예산을 초과했습니다!", summary.stdout)

    def test_invalid_csv_reports_all_rows_and_saves_nothing(self) -> None:
        # category list를 한 번 실행해 기본 저장 파일 3개를 만든다.
        self.run_cli("category", "list")
        csv_path = Path(self.temp_directory.name) / "invalid.csv"
        csv_path.write_text(
            "date,type,category,amount,memo,tags\n"
            "2026-08-01,expense,food,0,잘못된 금액,검증\n"
            "bad-date,income,salary,1000,잘못된 날짜,검증\n",
            encoding="utf-8",
        )

        imported = self.run_cli("import", "--from", str(csv_path))
        self.assertEqual(imported.returncode, 1)
        self.assertIn("CSV 검증 실패 (2건)", imported.stderr)
        self.assertIn("2번째 줄", imported.stderr)
        self.assertIn("3번째 줄", imported.stderr)

        transactions_path = self.data_dir / "transactions.jsonl"
        self.assertEqual(transactions_path.read_text(encoding="utf-8"), "")

    def test_missing_id_returns_nonzero_exit_code(self) -> None:
        deleted = self.run_cli("delete", "--id", "does-not-exist")
        self.assertEqual(deleted.returncode, 1)
        self.assertIn("거래를 찾을 수 없습니다", deleted.stderr)
        self.assertNotIn("Traceback", deleted.stderr)


if __name__ == "__main__":
    unittest.main()
