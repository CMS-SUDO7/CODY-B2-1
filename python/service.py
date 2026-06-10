import csv
import sys
from functools import wraps
from datetime import datetime
from collections import defaultdict
from typing import Optional, List
from models import Transaction, Budget, Category
from repository import FileRepository

# [데코레이터] 공통 예외 처리기
def service_error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            print(f"\n❌ [입력 오류] {e}\n💡 힌트: 입력 값을 다시 확인해 주세요.")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"\n❌ [파일 오류] {e}\n💡 힌트: 데이터 디렉토리 설정 및 파일 존재 여부를 확인하세요.")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ [시스템 오류] 처리 중 문제가 발생했습니다: {e}")
            sys.exit(1)
    return wrapper

class BudgetService:
    def __init__(self, data_dir: str = "./data"):
        self.repo = FileRepository(data_dir)

    def _validate_date(self, date_str: str):
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")

    @service_error_handler
    def add_transaction(self, type: str, date: str, amount: int, category: str, memo: str, tags: str):
        self._validate_date(date)
        if type not in ['income', 'expense']:
            raise ValueError("type은 'income' 또는 'expense'만 가능합니다.")
        if amount <= 0:
            raise ValueError("금액은 양수여야 합니다.")
        if category not in self.repo.get_all_categories():
            raise ValueError(f"'{category}'는 존재하지 않는 카테고리입니다. 먼저 추가해주세요.")

        tx = Transaction.create(type, date, amount, category, memo, tags)
        self.repo.append_record(self.repo.transactions_file, tx.__dict__)
        print(f"✅ 거래가 성공적으로 저장되었습니다. (ID: {tx.id})")

    @service_error_handler
    def list_transactions(self, limit: int = 10):
        print(f"--- 최근 거래 목록 (최대 {limit}건) ---")
        count = 0
        for tx in self.repo.get_all_transactions_desc():
            if count >= limit: break
            print(f"[{tx['id']}] {tx['date']} | {tx['type'].upper():7} | {tx['category']:10} | {tx['amount']:,}원 | {tx.get('memo', '')} {tx.get('tags', [])}")
            count += 1
        if count == 0:
            print("데이터가 없습니다.")

    @service_error_handler
    def search_transactions(self, from_date: Optional[str], to_date: Optional[str], category: Optional[str], type_: Optional[str], q: Optional[str], tag: Optional[str]):
        print(f"--- 검색 결과 ---")
        count = 0
        for tx in self.repo.get_all_transactions_desc():
            if from_date and tx['date'] < from_date: continue
            if to_date and tx['date'] > to_date: continue
            if category and tx['category'] != category: continue
            if type_ and tx['type'] != type_: continue
            if q and q.lower() not in tx.get('memo', '').lower(): continue
            if tag and tag not in tx.get('tags', []): continue
            
            print(f"[{tx['id']}] {tx['date']} | {tx['type'].upper():7} | {tx['category']:10} | {tx['amount']:,}원 | {tx.get('memo', '')}")
            count += 1
        if count == 0:
            print("조건에 맞는 결과가 없습니다.")

    @service_error_handler
    def get_summary(self, month: str, top_n: int = 3):
        income = 0
        expense = 0
        cat_expenses = defaultdict(int)
        
        has_data = False
        for tx in self.repo.get_all_transactions_desc():
            if tx['date'].startswith(month):
                has_data = True
                if tx['type'] == 'income':
                    income += tx['amount']
                else:
                    expense += tx['amount']
                    cat_expenses[tx['category']] += tx['amount']

        if not has_data:
            print(f"⚠️ {month}의 데이터가 없습니다.")
            return

        print(f"📊 {month} 요약 정보")
        print(f"- 총 수입: {income:,}원")
        print(f"- 총 지출: {expense:,}원")
        print(f"- 잔여액 : {income - expense:,}원\n")

        budget = self.repo.get_budget(month)
        if budget > 0:
            usage = (expense / budget) * 100
            print(f"💰 예산 현황: {expense:,} / {budget:,} ({usage:.1f}%)")
            if usage > 100:
                print("🚨 경고: 예산을 초과했습니다!")
            print("")

        print(f"🏆 지출 카테고리 TOP {top_n}")
        sorted_cats = sorted(cat_expenses.items(), key=lambda x: x[1], reverse=True)
        for i, (cat, amt) in enumerate(sorted_cats[:top_n], 1):
            print(f"  {i}. {cat}: {amt:,}원")

    @service_error_handler
    def set_budget(self, month: str, amount: int):
        if amount < 0: raise ValueError("예산은 0 이상이어야 합니다.")
        self.repo.append_record(self.repo.budgets_file, {"month": month, "amount": amount})
        print(f"✅ {month}월 예산이 {amount:,}원으로 설정되었습니다.")

    @service_error_handler
    def manage_category(self, action: str, name: str = None):
        cats = self.repo.get_all_categories()
        if action == "list":
            print(f"📁 카테고리 목록: {', '.join(cats)}")
        elif action == "add":
            if name in cats: raise ValueError("이미 존재하는 카테고리입니다.")
            self.repo.append_record(self.repo.categories_file, {"name": name})
            print(f"✅ 카테고리 '{name}' 추가 완료.")
        elif action == "remove":
            if name not in cats: raise ValueError("존재하지 않는 카테고리입니다.")
            # 사용 중인지 검증 (전체 탐색 필요)
            for line in open(self.repo.transactions_file, 'r', encoding='utf-8'):
                if json.loads(line).get('category') == name:
                    raise ValueError("해당 카테고리를 사용하는 거래 내역이 존재하여 삭제할 수 없습니다.")
            cats.remove(name)
            self.repo.atomic_rewrite_categories(cats)
            print(f"✅ 카테고리 '{name}' 삭제 완료.")

    @service_error_handler
    def update_transaction(self, tx_id: str, **kwargs):
        # 전체 읽기 후 원자적 교체
        transactions = []
        found = False
        with open(self.repo.transactions_file, 'r', encoding='utf-8') as f:
            for line in f:
                tx = json.loads(line)
                if tx['id'] == tx_id:
                    found = True
                    for k, v in kwargs.items():
                        if v is not None: tx[k] = v
                transactions.append(tx)
        
        if not found: raise ValueError(f"ID '{tx_id}'를 찾을 수 없습니다.")
        self.repo.atomic_rewrite_transactions(transactions)
        print("✅ 거래 내역이 성공적으로 수정되었습니다.")

    @service_error_handler
    def delete_transaction(self, tx_id: str):
        transactions = []
        found = False
        with open(self.repo.transactions_file, 'r', encoding='utf-8') as f:
            for line in f:
                tx = json.loads(line)
                if tx['id'] == tx_id:
                    found = True
                    continue # 삭제 대상 제외
                transactions.append(tx)
        
        if not found: raise ValueError(f"ID '{tx_id}'를 찾을 수 없습니다.")
        self.repo.atomic_rewrite_transactions(transactions)
        print("✅ 거래 내역이 성공적으로 삭제되었습니다.")

    @service_error_handler
    def export_csv(self, out_path: str, month: str = None, from_date: str = None, to_date: str = None):
        if not month and not (from_date and to_date):
            raise ValueError("--month 또는 --from/--to 조건을 지정해야 합니다.")
        
        with open(out_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['date', 'type', 'category', 'amount', 'memo', 'tags']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            count = 0
            # 제너레이터로 읽어오며 조건 필터링
            for tx in self.repo.get_all_transactions_desc():
                if month and not tx['date'].startswith(month): continue
                if from_date and tx['date'] < from_date: continue
                if to_date and tx['date'] > to_date: continue
                
                writer.writerow({
                    'date': tx['date'], 'type': tx['type'], 'category': tx['category'],
                    'amount': tx['amount'], 'memo': tx.get('memo', ''), 'tags': ",".join(tx.get('tags', []))
                })
                count += 1
        print(f"✅ {count}건의 데이터가 {out_path}로 내보내졌습니다.")

    @service_error_handler
    def import_csv(self, from_path: str):
        count = 0
        with open(from_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                tx = Transaction.create(
                    type=row['type'], date=row['date'], amount=int(row['amount']),
                    category=row['category'], memo=row.get('memo', ''), tags=row.get('tags', '')
                )
                self.repo.append_record(self.repo.transactions_file, tx.__dict__)
                count += 1
        print(f"✅ {count}건의 데이터 일괄 등록 완료.")