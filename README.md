# 콘솔 가계부 (`budget_app`)

Python 표준 라이브러리만 사용하는 JSONL 기반 콘솔 가계부입니다. Python 3.10 이상에서 동작하며 거래·카테고리·예산을 서로 다른 파일에 영구 저장합니다.

## 1. 실행 방법

프로젝트 루트(`README.md`와 `budget_app` 폴더가 있는 위치)에서 실행합니다.

```bash
python -m budget_app --help
python -m budget_app <command> --help
```

저장 폴더의 기본값은 `./data`입니다. 다른 폴더를 사용하려면 **명령어 앞에** 전역 옵션을 둡니다.

```bash
python -m budget_app --data-dir ./my_data list --limit 10
```

최초 실행 시 저장 폴더와 JSONL 파일 3개가 자동 생성됩니다. `categories.jsonl`이 비어 있으면 `food`, `transport`, `housing`, `health`, `salary`, `etc` 기본 카테고리를 자동 생성합니다.

## 2. 주요 명령

### 거래 추가: 대화형 방식

```bash
python -m budget_app add
```

날짜, 타입, 카테고리, 금액, 메모, 태그를 순서대로 입력합니다. 날짜에서 Enter를 누르면 오늘 날짜가 적용됩니다. 저장되면 생성된 UUID 기반 `id`를 출력합니다.

### 최근 거래 목록

```bash
python -m budget_app list
python -m budget_app list --limit 5
```

“최신순”은 최근 등록 순서를 의미합니다. `transactions.jsonl`을 파일 뒤에서부터 읽는 제너레이터를 사용하므로 목록 조회를 위해 파일 전체를 메모리에 올리지 않습니다.

### 거래 검색

```bash
python -m budget_app search --from 2026-08-01 --to 2026-08-31
python -m budget_app search --category food --type expense
python -m budget_app search --q 점심 --tag 회사
```

검색 조건은 함께 사용할 수 있고 결과는 최근 등록 순서로 표시됩니다. 검색도 역순 제너레이터를 사용합니다.

### 월별 요약

```bash
python -m budget_app summary --month 2026-08
python -m budget_app summary --month 2026-08 --top 5
```

총수입, 총지출, 잔액, 지출 카테고리 TOP N을 출력합니다. 설정된 월 예산이 있으면 사용률과 초과 경고도 표시합니다. 거래가 없는 달에는 `데이터 없음`을 출력합니다.

### 예산 설정/조회

```bash
python -m budget_app budget set --month 2026-08 --amount 1000000
python -m budget_app budget get --month 2026-08
```

### 카테고리 관리

```bash
python -m budget_app category list
python -m budget_app category add --name education
python -m budget_app category remove --name education
```

`--name`을 생략하면 대화형으로 이름을 입력합니다. 거래에서 사용 중인 카테고리는 삭제할 수 없습니다. 먼저 해당 거래를 `update`로 다른 카테고리로 바꿔야 합니다.

### 거래 수정: 옵션 방식으로 고정

```bash
python -m budget_app update --id <거래-id> --amount 15000
python -m budget_app update --id <거래-id> --category food --memo "팀 점심" --tags "회사,식사"
python -m budget_app update --id <거래-id> --memo "" --tags ""
```

`update`는 대화형이 아닌 옵션 방식입니다. 지정한 필드만 변경합니다. 빈 `--memo`와 빈 `--tags`는 기존 값을 지웁니다. 수정할 옵션이 하나도 없거나 id가 없으면 오류 종료합니다.

### 거래 삭제

```bash
python -m budget_app delete --id <거래-id>
```

존재하지 않는 id는 원인과 해결 힌트를 출력하고 종료 코드 1로 끝납니다.

### CSV 가져오기

```bash
python -m budget_app import --from ./sample.csv
```

CSV 전체 행을 먼저 검증합니다. 한 행이라도 잘못되면 어느 거래도 반영하지 않습니다. 모든 행이 유효할 때만 기존 거래와 합쳐 원자적으로 저장합니다. CSV 카테고리는 먼저 등록되어 있어야 합니다.

### CSV 내보내기

```bash
python -m budget_app export --out ./august.csv --month 2026-08
python -m budget_app export --out ./range.csv --from 2026-08-01 --to 2026-08-15
```

`--month` 또는 `--from`/`--to` 날짜 조건이 반드시 필요합니다. 월 조건과 날짜 범위 조건은 함께 사용할 수 없습니다. 출력 CSV도 임시 파일을 완성한 뒤 원자적으로 교체합니다.

## 3. 저장 파일 위치와 형식

기본 저장 구조:

```text
./data/
├── transactions.jsonl
├── categories.jsonl
└── budgets.jsonl
```

JSONL은 한 줄에 JSON 객체 하나를 기록합니다. 모두 UTF-8입니다.

`transactions.jsonl` 예시:

```json
{"id":"3c17...","type":"expense","date":"2026-08-10","amount":12000,"category":"food","memo":"점심","tags":["회사","식사"]}
```

`categories.jsonl` 예시:

```json
{"name":"food"}
```

`budgets.jsonl` 예시:

```json
{"month":"2026-08","amount":1000000}
```

거래 수정·삭제, 예산 갱신, 카테고리 삭제는 같은 폴더의 임시 파일에 먼저 기록하고 `os.replace()`로 원자적으로 교체합니다. 쓰기 직전에 `flush()`와 `fsync()`도 실행합니다.

## 4. import/export CSV 스키마

공통 규칙: UTF-8, 첫 줄 헤더 포함. Excel이 만든 UTF-8 BOM 파일도 import할 수 있습니다.

| column | required | 설명 |
| --- | --- | --- |
| `date` | Y | `YYYY-MM-DD` |
| `type` | Y | `income` 또는 `expense` |
| `category` | Y | 이미 등록된 카테고리 |
| `amount` | Y | 0보다 큰 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표(`,`) 구분 문자열 |

예시:

```csv
date,type,category,amount,memo,tags
2026-08-01,income,salary,3000000,월급,"급여,정기"
2026-08-02,expense,food,12000,점심,"회사,식사"
```

## 5. 모듈 구조

| 파일 | 책임 |
| --- | --- |
| `cli.py` | 명령 파싱, 대화형 입력, 화면 출력 |
| `models.py` | `Transaction`, `Budget` dataclass와 기본 검증 |
| `services.py` | 검색, 요약, 예산 계산, 카테고리 규칙, CSV 처리 |
| `repositories.py` | JSONL 제너레이터, 영구 저장, 원자적 교체 |
| `decorators.py` | 실행 시간 측정, 공통 예외 처리 |
| `errors.py` | 사용자용 오류 계층 |
| `__main__.py` | `python -m budget_app` 진입점 |

`__init__.py`는 Python 패키지 표시와 버전 정보만 포함합니다.

## 6. 검증과 종료 코드

- 날짜: 실제 존재하는 `YYYY-MM-DD`
- 타입: `income` 또는 `expense`
- 금액: 0보다 큰 정수
- 카테고리: 등록된 이름만 허용
- 스택트레이스 대신 `오류 원인`과 `해결 힌트` 출력
- 정상 종료: `0`
- 예상 가능한 입력/업무 오류: `1`
- 예상하지 못한 오류: `2`
- Ctrl+C 취소: `130`
- argparse 사용법 오류: `2`

종료 코드 확인 예시:

```bash
python -m budget_app delete --id does-not-exist
echo $?
```

모든 실제 명령에는 실행 시간 측정과 공통 예외 처리 데코레이터가 적용됩니다. 각 명령과 하위 명령은 `--help`로 사용법을 확인할 수 있습니다.
