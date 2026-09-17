# 설정 관리 사용법

## 실행

프로젝트 루트에서 다음 명령으로 설정 검증과 Logger 초기화를 실행한다.

```powershell
.venv/Scripts/python.exe src/main.py
.venv/Scripts/python.exe src/main.py --config config/app.json
```

기본 파일은 `config/app.json`이다. `--config`의 상대 경로는 명령 실행 위치를,
파일 내부의 상대 경로는 설정 파일이 있는 디렉터리를 기준으로 해석한다.

## 설정 항목

| 항목 | 기본값 | 허용 값 / 의미 |
| --- | --- | --- |
| environment | development | development, test, production |
| logging.level | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| logging.directory | ../logs | 로그 디렉터리 |
| inventory.server_file | servers.txt | 다음 단계에서 읽을 서버 목록 파일 |
| ssh.timeout | 30 | 연결 제한 시간(초), 정수 1~300 |
| ssh.max_workers | 10 | 동시 작업 수, 정수 1~100 |

누락된 항목에는 기본값을 적용하지만 파일 자체가 없으면 오류로 처리한다.
알 수 없는 항목과 중복 키도 거부하여 설정 오타를 발견할 수 있도록 한다.
비밀번호·토큰·개인키 내용을 넣는 항목은 제공하지 않는다.
시간 제한과 작업 수의 범위는 현재 애플리케이션의 초기 정책이다.

## 시작 순서

1. `load_config()`가 UTF-8 JSON을 읽고 자료형·범위를 검사한다.
2. 변경 불가능한 `AppConfig` 객체로 검증 결과를 반환한다.
3. `LoggerManager.configure()`가 로그 수준과 디렉터리를 적용한다.
4. 시작 메시지를 기록하고 종료 시 핸들러를 정리한다.

종료 코드는 정상 0, 로그 초기화 실패 1, 설정 오류 2다.
실행 중 Logger 설정 변경은 거부하며, 변경하려면 먼저 `shutdown()`해야 한다.
기존 `get_logger()`만 사용하는 코드는 기존 INFO 기본값을 유지한다.

이번 단계는 설정과 시작 기반까지 구현했다. 서버 목록 파일의 존재·내용 확인과
실제 SSH 실행은 다음 단계에서 구현하며, 현재 실행은 서버에 접속하지 않는다.

## 검증

2026-09-17: 기존 Logger 회귀 검사와 설정·시작 통합 검사를 합쳐 **101 passed**.
파일 누락, JSON 오류, 중복 키, 잘못된 자료형·범위, 경로 기준,
지정된 로그 출력과 초기화 실패의 종료 코드를 검증했다.

```powershell
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
```
