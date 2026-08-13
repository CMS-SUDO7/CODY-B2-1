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

검증 실패 시 첫 오류에서 멈추지 않고 잘못된 행 번호와 원인을 모아서 출력합니다. 이를 통해 CSV를 여러 번 실행하며 한 줄씩 고칠 필요가 없습니다.

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

헤더는 이름으로 찾으므로 열 순서가 달라도 정상 처리됩니다. 추가 열은 무시하지만 `date`, `type`, `category`, `amount` 필수 헤더와 각 값의 검증 규칙은 반드시 지켜야 합니다. 코드에서는 외부 CSV 경계의 타입을 `CsvImportRow`, `CsvExportRow` `TypedDict`로 선언했습니다.

## 5. 프로젝트 및 모듈 구조

전체 제출 구조는 다음과 같습니다.

```text
budget_app_project/
├── README.md
├── budget_app/                 # 실제 가계부 애플리케이션 패키지
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── models.py
│   ├── services.py
│   ├── repositories.py
│   ├── decorators.py
│   └── errors.py
├── tests/
│   └── test_integration.py     # 재실행 유지·오류 처리 통합 테스트
└── benchmarks/
    └── streaming_100k.py       # 10만 건 스트리밍 측정 스크립트
```

`budget_app` 내부의 핵심 모듈 책임은 다음과 같습니다.

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

`tests`와 `benchmarks`는 실제 가계부가 실행될 때 불러오는 애플리케이션 모듈이 아닙니다. 각각 기능 검증과 성능 측정을 위한 보조 폴더이므로, 과제에서 요구한 7개 기능 모듈의 책임 분리에는 영향을 주지 않습니다.

| 보조 파일 | 책임 | 실행 명령 |
| --- | --- | --- |
| `tests/test_integration.py` | CLI부터 JSONL 저장까지 주요 시나리오 자동 검증 | `python -m unittest discover -s tests -v` |
| `benchmarks/streaming_100k.py` | 임시 거래 10만 건을 만들고 시간·메모리 측정 | `python benchmarks/streaming_100k.py` |

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

## 7. 실행 증거와 재실행 데이터 유지

다음은 Python 3.12.13 환경에서 실제 검증한 대표 흐름입니다. UUID와 실행 시간은 실행할 때마다 달라질 수 있습니다.

### 추가 후 목록·검색

```text
$ python -m budget_app add
등록된 카테고리: food, transport, housing, health, salary, etc
날짜 YYYY-MM-DD: 2026-08-10
타입 income/expense: expense
카테고리: food
금액: 12000
메모 (선택): 점심
태그 (선택, 쉼표 구분): 회사,식사
저장 성공: id=f3a2782f...(생략)

$ python -m budget_app list --limit 1
2026-08-10 | expense | 12,000원 | food | id=f3a2782f...(생략) memo=점심 tags=회사,식사
총 1건

$ python -m budget_app search --category food --tag 회사
2026-08-10 | expense | 12,000원 | food | id=f3a2782f...(생략) memo=점심 tags=회사,식사
총 1건
```

`add` 프로세스가 끝난 뒤 `list`를 **새 Python 프로세스로 다시 실행**해도 같은 거래가 출력되었습니다. 즉, 메모리에만 있던 값이 아니라 `data/transactions.jsonl`에서 다시 읽은 값입니다. 이때 다음 3개 파일도 존재합니다.

```text
data/categories.jsonl
data/transactions.jsonl
data/budgets.jsonl
```

### 예산 초과 출력

```text
$ python -m budget_app budget set --month 2026-08 --amount 10000
예산 저장 성공: 2026-08 = 10,000원

$ python -m budget_app summary --month 2026-08
[2026-08 요약] 거래 1건
총 수입: 0원
총 지출: 12,000원
잔액: -12,000원
지출 카테고리 TOP 3
  1. food: 12,000원
월 예산: 10,000원
예산 사용률: 120.0%
경고: 월 예산을 초과했습니다!
```

스케줄러가 주기적으로 알림을 보내는 기능은 미션 범위가 아닙니다. 요구사항에 맞게 사용자가 `summary`를 실행했을 때 즉시 사용률과 초과 경고를 표시합니다.

### 자동 통합 테스트

외부 라이브러리 없이 다음 명령으로 CLI부터 JSONL 저장까지 한 번에 검증할 수 있습니다.

```bash
python -m unittest discover -s tests -v
```

검증 항목은 다음과 같습니다.

- 추가 후 별도 프로세스에서 목록·검색 가능
- 설정 예산을 초과하면 summary 경고 출력
- 잘못된 CSV의 모든 오류 행 보고 및 0건 반영
- 없는 id 삭제 시 스택트레이스 없이 종료 코드 1 반환

## 8. 대표 오류와 CSV 실패 예시

### `ValidationError`: 잘못된 CSV 여러 행

예를 들어 금액이 0인 행과 날짜가 잘못된 행을 함께 import하면 다음처럼 한 번에 표시됩니다.

```text
$ python -m budget_app import --from invalid.csv
오류: CSV 검증 실패 (2건)
- 2번째 줄: 금액은 0보다 커야 합니다: 0
- 3번째 줄: 날짜 형식이 올바르지 않습니다: bad-date
해결 힌트: 표시된 행을 수정하세요. 오류가 하나라도 있으면 파일 전체를 반영하지 않습니다.
```

이 경우 정상인 행이 섞여 있어도 `transactions.jsonl`에는 **아무 행도 추가되지 않습니다**. 다른 대표 실패는 다음과 같습니다.

| 잘못된 CSV | 처리 결과 |
| --- | --- |
| 헤더 없음 | `CSV 헤더가 없습니다.` |
| `amount` 필수 열 없음 | `CSV 필수 열이 없습니다: amount` |
| UTF-8이 아닌 인코딩 | `CSV 파일이 UTF-8 형식이 아닙니다.` |
| 등록되지 않은 카테고리 | 해당 행 번호와 카테고리 오류를 요약 |
| 열 순서만 다름 | 헤더 이름으로 읽으므로 정상 처리 |

### `NotFoundError`: 없는 거래 id

```text
$ python -m budget_app delete --id does-not-exist
오류: 거래를 찾을 수 없습니다: does-not-exist
해결 힌트: list 명령으로 id를 확인하세요.

$ echo $?
1
```

## 9. 모듈 간 인터페이스와 객체 생성 흐름

주요 공개 함수와 클래스의 입출력 계약은 다음과 같습니다.

| 모듈 | 공개 인터페이스 | 입력 → 출력/역할 |
| --- | --- | --- |
| `models.py` | `Transaction(...)` | 원시 필드 → 검증된 거래 객체 |
| `models.py` | `Budget(...)` | 월·금액 → 검증된 예산 객체 |
| `repositories.py` | `TransactionRepository.iter_latest()` | JSONL → `Iterator[Transaction]` |
| `repositories.py` | `append/update/delete()` | 거래 또는 id → 영구 파일 반영 |
| `services.py` | `TransactionService.create()` | 사용자 값 → 저장된 `Transaction` |
| `services.py` | `TransactionService.search()` | 선택 검색 조건 → `Iterator[Transaction]` |
| `services.py` | `SummaryService.monthly()` | `YYYY-MM`, TOP N → 요약 사전 또는 `None` |
| `services.py` | `CsvService.import_csv()` | CSV 경로 → 반영 건수 `int` |
| `services.py` | `CsvImportRow`/`CsvExportRow` | CSV 행의 키·값 타입 계약 |
| `cli.py` | `main()` | 명령행 인자 → 종료 코드 `int` |
| `decorators.py` | `handle_errors`/`measure_time` | 실행 함수 → 공통 처리된 실행 함수 |

거래 생성 흐름은 다음과 같습니다.

```text
cli.execute()
  → TransactionService.create()
    → CategoryRepository.exists()로 카테고리 확인
    → Transaction(...) 생성 시 날짜·타입·금액 검증
    → TransactionRepository.append()로 JSONL 저장
  → CLI가 생성된 id 출력
```

예산은 `BudgetService.set()`에서 `Budget(...)` 객체를 만든 뒤 `BudgetRepository.set()`으로 저장합니다. 파일에서 읽을 때도 `Transaction.from_dict()`와 `Budget.from_dict()`가 같은 모델 생성자를 사용하므로 입력 경로에 따라 검증이 달라지지 않습니다.

타입 힌트는 실행 시 자동 검증 장치가 아니라 함수의 계약입니다. 예를 들어 `create(..., amount: int | str) -> Transaction`은 문자열 입력도 받지만 반환 시점에는 검증된 거래 객체라는 뜻입니다. 실제 실행 검증은 `validate_amount()`가 담당하고, 타입 힌트는 VSCode 자동완성·정적 검사·협업 시 이해를 돕습니다.

## 10. JSONL을 선택한 이유

가계부의 내부 저장은 JSONL, 외부 교환은 CSV로 역할을 나눴습니다.

| 비교 항목 | JSONL | CSV |
| --- | --- | --- |
| 한 건 추가 | 파일 끝에 JSON 한 줄 append가 간단함 | 한 행 append가 가능함 |
| 구조 표현 | `tags`를 JSON 배열로 자연스럽게 저장 | 배열을 쉼표 문자열로 다시 인코딩해야 함 |
| 자료형 | 숫자·문자열·배열 구분 유지 | 모든 값이 기본적으로 문자열 |
| 스트리밍 | 한 줄씩 독립적으로 파싱 가능 | 한 행씩 스트리밍 가능 |
| 사람이 표로 보기 | CSV보다 불편함 | 스프레드시트에서 보기 쉬움 |
| 검색 성능 | 별도 인덱스가 없으면 O(N) | 별도 인덱스가 없으면 O(N) |
| 스키마 변경 | 선택 필드를 추가하기 비교적 쉬움 | 헤더와 모든 행의 열 규칙 관리 필요 |

이 프로그램은 태그 목록과 명확한 숫자 타입을 안전하게 보존하면서 거래 한 건을 빠르게 추가해야 하므로 내부 형식으로 JSONL을 선택했습니다. 반면 사용자가 Excel 등에서 편집하거나 다른 프로그램과 교환할 때는 CSV가 편하므로 import/export 형식으로 사용합니다.

## 11. 제너레이터, 10만 건 측정과 병목 분석

`iter_all()`과 `iter_latest()`는 목록을 만들어 반환하지 않고 `yield`로 한 건씩 반환합니다. 호출자는 현재 거래 한 건만 처리한 뒤 다음 거래를 요청하므로 파일 크기에 비례해 전체 객체 목록을 메모리에 쌓지 않습니다.

재현 명령:

```bash
python benchmarks/streaming_100k.py
```

2026-08-12, Python 3.12.13 환경에서 100,000건(12.20 MiB)을 측정한 결과입니다. 파일 생성 시간은 제외했고, 메모리는 표준 라이브러리 `tracemalloc`이 관측한 Python 할당 최대값입니다. 운영체제와 디스크에 따라 시간은 달라질 수 있습니다.

| 작업 | 처리 범위 | 시간 | Python 최대 메모리 |
| --- | ---: | ---: | ---: |
| `list --limit 20` 상당 | 최신 20건 | 0.0010초 | 0.028 MiB |
| 없는 키워드 전체 검색 | 100,000건 전부 | 2.3420초 | 0.036 MiB |

결과에서 제너레이터 덕분에 전체 검색도 Python 메모리는 거의 일정하지만, 검색 시간은 레코드 수에 비례합니다. 예상 병목과 개선 우선순위는 다음과 같습니다.

1. **파일 I/O와 JSON 파싱**: search·summary는 모든 행을 읽고 JSON을 파싱하므로 O(N)입니다. 가장 먼저 월별 파일 분할(`transactions-2026-08.jsonl`)이나 월/날짜별 보조 인덱스를 고려합니다.
2. **update/delete 전체 재작성**: 안전한 원자적 교체를 위해 파일 전체를 다시 씁니다. 수정이 매우 잦아지면 월별 파일 분할로 재작성 범위를 줄이는 것이 우선입니다.
3. **import 준비 목록의 메모리**: 부분 반영 방지를 위해 import 대상 전체를 검증 후 보관합니다. 매우 큰 CSV에서는 검증된 행을 임시 JSONL에 스트리밍하고 검증 완료 후 병합하는 2단계 방식으로 바꿀 수 있습니다.
4. **데이터베이스 전환**: 수십만~수백만 건에서 복합 검색과 수정이 빈번해지면 표준 라이브러리 `sqlite3`로 인덱스를 두는 것이 직접 만든 인덱스보다 안전합니다. 다만 이 과제는 파일 기반 JSONL/CSV가 필수이므로 현재 구현에는 적용하지 않았습니다.
5. **병렬 처리**: 단일 JSONL 디스크 읽기에서는 병렬화가 오히려 순서 관리와 디스크 경합을 늘릴 수 있어 우선순위가 낮습니다. 먼저 분할·인덱싱으로 읽는 데이터 양 자체를 줄이는 편이 효과적입니다.

## 12. 요구 범위와 추가 제안에 대한 판단

다음 항목은 현재 미션 요구를 이미 만족하거나 범위를 넘기 때문에 기능으로 추가하지 않았습니다.

| 제안 | 판단 |
| --- | --- |
| 카테고리 삭제 시 자동 대체 | 미션은 “삭제 차단 또는 대체 요구” 중 하나를 허용합니다. 현재는 데이터가 뜻하지 않게 바뀌지 않는 차단 방식을 선택했고, 사용자가 `update` 후 삭제하도록 안내합니다. |
| 예산 스케줄 알림 | 미션은 summary 실행 시 사용률과 초과 경고를 요구합니다. 백그라운드 스케줄러·OS 알림은 콘솔 가계부 범위를 넘습니다. |
| 파일 로깅 데코레이터 | 데코레이터 1개 이상 요구에 대해 예외 처리와 실행 시간 측정 2개를 실제 적용했습니다. 개인 금융 명령을 별도 로그에 중복 저장하는 기능은 개인정보와 파일 관리 범위를 늘려 제외했습니다. |
| 자동 백업 플래그 | `os.replace()` 전까지 원본 파일이 유지되므로 쓰기 중 실패에는 원자성이 보장됩니다. 과제 필수 기능이 아닌 버전 백업은 구현하지 않았습니다. 중요한 실데이터 작업 전에는 `data` 폴더를 복사해 수동 백업할 수 있습니다. |
| CSV 열 순서 오류 | `csv.DictReader`는 헤더 이름으로 값을 찾기 때문에 순서가 달라도 오류가 아닙니다. 대신 필수 헤더 누락·빈 값·형식 오류를 검증합니다. |

원자적 교체는 “새 파일 작성 실패 시 기존 파일 보존”을 해결하지만, 사용자가 정상 명령으로 잘못 수정한 내용을 과거 버전으로 되돌리는 기능은 아닙니다. 복구 이력까지 필요해지는 운영 환경에서는 타임스탬프 백업이나 SQLite 트랜잭션을 별도 요구사항으로 설계해야 합니다.
