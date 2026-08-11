"""사용자에게 안전하게 보여 줄 애플리케이션 오류.

기능별 오류를 같은 부모 클래스로 묶어 두면 CLI에서 한 번에 처리하면서도
사용자에게는 오류 원인과 해결 방법을 구분해 보여 줄 수 있다.
"""


class BudgetAppError(Exception):
    """예상 가능한 모든 업무/입력 오류의 부모 클래스."""

    def __init__(self, message: str, hint: str = "입력값을 확인해 주세요.") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# 날짜·금액·타입처럼 사용자가 입력한 값이 규칙에 맞지 않을 때 사용한다.
class ValidationError(BudgetAppError):
    """입력값 또는 저장 데이터 형식 오류."""


# 검색한 거래, 카테고리, 예산이 존재하지 않을 때 사용한다.
class NotFoundError(BudgetAppError):
    """요청한 데이터가 존재하지 않을 때의 오류."""


# 사용 중인 카테고리 삭제처럼 현재 상태와 충돌하는 요청에 사용한다.
class ConflictError(BudgetAppError):
    """현재 데이터 상태 때문에 작업할 수 없을 때의 오류."""


# JSONL·CSV 파일을 읽거나 안전하게 저장하지 못했을 때 사용한다.
class StorageError(BudgetAppError):
    """파일 읽기/쓰기 오류."""
