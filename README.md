# Budget Console

파일 손상과 메모리 사용을 고려해 설계한 Python 콘솔 가계부입니다. 거래 추가·목록·검색·월별 요약·예산·카테고리·수정·삭제·CSV 가져오기/내보내기를 지원합니다.

## 요구 환경과 실행

- Python 3.10 이상
- 표준 라이브러리만 사용
- 별도 `pip install`이 필요한 외부 패키지 없음

프로젝트 폴더에서 바로 실행합니다.

```bash
python -m budget_app --help
python -m budget_app <command> --help
```

기본 저장 폴더는 현재 위치의 `./data`입니다. 다른 위치는 **명령어 앞에** 전역 옵션으로 지정합니다.

```bash
python -m budget_app --data-dir ./my-data list --limit 10
```

첫 실행 때 폴더와 세 파일이 자동 생성되며, 카테고리가 비어 있으면 `food`, `transport`, `rent`, `salary`, `health`, `leisure`, `other`가 자동 등록됩니다.

## 주요 명령

```bash
# 대화형 거래 추가
python -m budget_app add

# 최신 20건 / 최신 5건
python -m budget_app list
python -m budget_app list --limit 5

# 복합 검색(지정한 조건은 AND로 결합)
python -m budget_app search --from 2026-07-01 --to 2026-07-31
python -m budget_app search --category food --type expense --q 점심 --tag 회사

# 월 요약과 지출 카테고리 TOP 3
python -m budget_app summary --month 2026-07 --top 3

# 예산 설정/조회
python -m budget_app budget set --month 2026-07 --amount 1000000
python -m budget_app budget get --month 2026-07
python -m budget_app budget list

# 카테고리 관리
python -m budget_app category add education
python -m budget_app category list
python -m budget_app category remove education

# 옵션 기반 수정(지정한 필드만 변경)
python -m budget_app update --id <id> --amount 15000 --memo "팀 점심"
python -m budget_app update --id <id> --tags "회사,식사"

# 삭제
python -m budget_app delete --id <id>

# CSV 가져오기/내보내기
python -m budget_app import --from ./input.csv
python -m budget_app export --out ./july.csv --month 2026-07
python -m budget_app export --out ./period.csv --from 2026-07-01 --to 2026-07-15
```

모든 하위 명령은 `--help`를 제공합니다. 정상 종료 코드는 `0`, 입력·도메인 오류는 `2`, 파일 오류는 `3`, 사용자 중단(`Ctrl+C`)은 `130`입니다. 오류에는 스택트레이스 대신 원인과 해결 힌트를 출력합니다.

## 저장 위치와 형식

`--data-dir` 아래에 최소 세 파일을 분리해 영구 저장합니다.

| 파일 | 형식 | 역할 |
| --- | --- | --- |
| `transactions.jsonl` | UTF-8 JSONL | 거래(한 줄에 JSON 객체 하나) |
| `categories.jsonl` | UTF-8 JSONL | 카테고리 |
| `budgets.jsonl` | UTF-8 JSONL | 월별 예산 |

거래 예시:

```json
{"id":"8c...","type":"expense","date":"2026-07-10","amount":12000,"category":"food","memo":"점심","tags":["회사"]}
```

`list`와 `search`는 제너레이터로 거래를 한 건씩 내보냅니다. 최신순 조회는 파일 끝에서부터 블록 단위로 읽으므로 전체 파일을 리스트로 만들지 않습니다. `summary`도 순방향 스트리밍 집계를 사용합니다. 수정·삭제는 같은 폴더의 임시 파일에 완전한 결과를 기록하고 `fsync`한 뒤 원본과 원자적으로 교체합니다.

## 입력 규칙

- 날짜: 실제 존재하는 날짜의 `YYYY-MM-DD`
- 월: `YYYY-MM`
- 타입: `income` 또는 `expense`
- 금액: 0보다 큰 정수
- 카테고리: 사전에 등록된 값
- 태그: 대화형/수정/CSV에서 쉼표로 구분

`add`는 잘못된 날짜·타입·금액·카테고리를 다시 입력받습니다. `update`는 **옵션 방식으로 고정**되어 있으며 없는 id는 오류로 처리합니다. 사용 중인 카테고리는 삭제할 수 없고, 해당 거래를 먼저 다른 카테고리로 수정해야 합니다.

## import/export CSV 스키마

UTF-8, 헤더 포함 CSV입니다. Excel 호환성을 위해 내보내기는 UTF-8 BOM을 포함하며 가져오기는 BOM 유무를 모두 처리합니다.

| column | required | 설명 |
| --- | --- | --- |
| `date` | Y | `YYYY-MM-DD` |
| `type` | Y | `income` / `expense` |
| `category` | Y | 등록된 카테고리 |
| `amount` | Y | 양수 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표 구분 문자열(CSV 규칙에 따라 필드 인용) |

가져오기에서 유효한 행은 즉시 영구 저장되며, 잘못된 행은 건너뛰고 성공/건너뜀 건수를 출력합니다. 새 거래 id는 가져올 때 생성됩니다. 내보내기는 `--month` 또는 `--from`/`--to` 조건이 반드시 필요하며 `--month`와 기간 조건은 함께 쓸 수 없습니다.

## 구조

```text
budget_app/
├── cli.py           # argparse, 대화형 입력, 출력, 데코레이터
├── models.py        # 데이터 모델, 검증, 도메인 오류
├── repositories.py  # JSONL 스트리밍, 원자적 저장
└── services.py      # 검색, 요약, 예산, CSV 업무 규칙
```

`cli.py`의 `friendly_errors`, `measure_time` 데코레이터가 공통 예외 처리와 실행 시간 측정을 분리합니다. 공개 함수와 주요 데이터 구조에는 타입 힌트를 적용했습니다.
