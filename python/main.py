# main.py
import sys
from cli import run_cli

def main():
    try:
        # CLI 실행 (모든 로직은 여기서 시작됨)
        run_cli()
    except KeyboardInterrupt:
        # 프로그램 전체에서 발생하는 강제 종료를 여기서 한 번에 깔끔하게 처리
        print("\n\n🚫 프로그램이 사용자에 의해 종료되었습니다.")
        sys.exit(0)

if __name__ == "__main__":
    main()