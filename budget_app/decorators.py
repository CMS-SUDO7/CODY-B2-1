"""실행 시간 측정과 공통 예외 처리 데코레이터.

CLI 명령마다 반복될 수 있는 시간 측정과 예외 출력 코드를 데코레이터로
분리하여 실제 명령 함수는 가계부 기능에만 집중하게 한다.
"""

from __future__ import annotations

import functools
import sys
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .errors import BudgetAppError


P = ParamSpec("P")
R = TypeVar("R")


# 기능 1: 어떤 함수에도 붙일 수 있는 실행 시간 측정 데코레이터
def measure_time(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            # 명령이 실패하더라도 finally에서 실행 시간을 항상 출력한다.
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[실행 시간] {elapsed_ms:.3f} ms")

    return wrapper


# 기능 2: 예상 가능한 오류를 스택트레이스 없이 안내하는 공통 데코레이터
def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except BudgetAppError as exc:
            # 직접 정의한 오류에는 원인과 해결 힌트가 들어 있다.
            print(f"오류: {exc.message}", file=sys.stderr)
            print(f"해결 힌트: {exc.hint}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            # Ctrl+C 종료는 일반 입력 오류와 다른 표준 종료 코드로 구분한다.
            print("\n작업이 사용자에 의해 취소되었습니다.", file=sys.stderr)
            return 130
        except Exception:
            # 알 수 없는 내부 정보나 스택트레이스는 사용자 화면에 노출하지 않는다.
            print("오류: 예상하지 못한 문제가 발생했습니다.", file=sys.stderr)
            print("해결 힌트: 입력과 데이터 파일을 확인한 뒤 다시 시도하세요.", file=sys.stderr)
            return 2

    return wrapper
