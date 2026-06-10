import argparse
import sys
from service import BudgetService

def run_cli():
    parser = argparse.ArgumentParser(description="작은 서비스: 콘솔 가계부")
    parser.add_argument("--data-dir", default="./data", help="데이터 저장 폴더 지정")
    
    # title을 추가하면 help 화면이 예쁘게 나옵니다.
    subparsers = parser.add_subparsers(dest="command", required=True, title="사용 가능한 명령어")

    # 1. ADD
    subparsers.add_parser("add", help="거래 추가 (대화형)")
    
    # 2. LIST
    list_parser = subparsers.add_parser("list", help="거래 목록 조회")
    list_parser.add_argument("--limit", type=int, default=10, help="출력 개수 (기본 10)")

    # 3. SEARCH
    search_parser = subparsers.add_parser("search", help="거래 검색")
    search_parser.add_argument("--from", dest="from_date", help="시작일 (YYYY-MM-DD)")
    search_parser.add_argument("--to", dest="to_date", help="종료일 (YYYY-MM-DD)")
    search_parser.add_argument("--category", help="카테고리명")
    search_parser.add_argument("--type", help="income 또는 expense")
    search_parser.add_argument("--q", help="메모 키워드 검색")
    search_parser.add_argument("--tag", help="태그 검색")

    # 4. SUMMARY
    summary_parser = subparsers.add_parser("summary", help="월별 요약")
    summary_parser.add_argument("--month", required=True, help="YYYY-MM")
    summary_parser.add_argument("--top", type=int, default=3, help="카테고리 TOP N")

    # 5. BUDGET
    budget_parser = subparsers.add_parser("budget", help="예산 관리")
    budget_parser.add_argument("action", choices=["set"])
    budget_parser.add_argument("--month", required=True, help="YYYY-MM")
    budget_parser.add_argument("--amount", type=int, required=True, help="예산 금액")

    # 6. CATEGORY
    cat_parser = subparsers.add_parser("category", help="카테고리 관리")
    cat_parser.add_argument("action", choices=["add", "list", "remove"])
    cat_parser.add_argument("--name", help="카테고리 이름 (add/remove 시 필수)")

    # 7. UPDATE
    update_parser = subparsers.add_parser("update", help="거래 수정 (옵션 기반)")
    update_parser.add_argument("--id", required=True, help="수정할 거래 ID")
    update_parser.add_argument("--type", choices=["income", "expense"])
    update_parser.add_argument("--date", help="YYYY-MM-DD")
    update_parser.add_argument("--amount", type=int)
    update_parser.add_argument("--category")
    update_parser.add_argument("--memo")

    # 8. DELETE
    delete_parser = subparsers.add_parser("delete", help="거래 삭제")
    delete_parser.add_argument("--id", required=True, help="삭제할 거래 ID")

    # 9. IMPORT / EXPORT
    import_parser = subparsers.add_parser("import", help="CSV 데이터 가져오기")
    import_parser.add_argument("--from", dest="from_csv", required=True, help="CSV 파일 경로")

    export_parser = subparsers.add_parser("export", help="CSV 데이터 내보내기")
    export_parser.add_argument("--out", required=True, help="저장할 CSV 파일 경로")
    export_parser.add_argument("--month", help="YYYY-MM")
    export_parser.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    export_parser.add_argument("--to", dest="to_date", help="YYYY-MM-DD")

    args = parser.parse_args()
    service = BudgetService(data_dir=args.data_dir)

    # 명령어 라우팅
    if args.command == "add":
        print("📝 거래 내역 추가를 시작합니다.")
        date = input("날짜 (YYYY-MM-DD): ").strip()
        type_ = input("타입 (income/expense): ").strip()
        category = input("카테고리: ").strip()
        amount = int(input("금액: ").strip())
        memo = input("메모 (선택): ").strip()
        tags = input("태그 (선택, 쉼표 구분): ").strip()
        service.add_transaction(type_, date, amount, category, memo, tags)
        
    elif args.command == "list":
        service.list_transactions(limit=args.limit)
        
    elif args.command == "search":
        service.search_transactions(args.from_date, args.to_date, args.category, args.type, args.q, args.tag)
        
    elif args.command == "summary":
        service.get_summary(args.month, args.top)
        
    elif args.command == "budget":
        if args.action == "set":
            service.set_budget(args.month, args.amount)
            
    elif args.command == "category":
        if args.action in ["add", "remove"] and not args.name:
            print("❌ 카테고리 추가/삭제 시 --name 옵션이 필요합니다.", file=sys.stderr)
            sys.exit(1)
        service.manage_category(args.action, args.name)
        
    elif args.command == "update":
        # 입력된 옵션만 필터링하여 전달
        updates = {k: v for k, v in vars(args).items() if k not in ['command', 'data_dir', 'id'] and v is not None}
        service.update_transaction(args.id, **updates)
        
    elif args.command == "delete":
        service.delete_transaction(args.id)
        
    elif args.command == "import":
        service.import_csv(args.from_csv)
        
    elif args.command == "export":
        service.export_csv(args.out, args.month, args.from_date, args.to_date)