# 다른 PC에서 개발 이어가기

## 저장한 환경

- 기준일: 2026-09-17
- 저장소: https://github.com/lucasbrothers/SM_Automation
- 브랜치: `master`
- 검증 환경: Windows, PowerShell, Python 3.14.7
- 개발 패키지: `requirements-dev.txt`에 현재 설치 버전을 고정했다.
- 애플리케이션 실행 의존성: Python 표준 라이브러리만 사용한다.

`.python-version`은 기준 버전 기록이며 Python을 자동 설치하지 않는다.
다른 운영체제에서는 명령을 조정해야 하며 아직 실행 검증하지 않았다.
가상환경은 PC별 절대 경로를 포함하므로 `.venv`를 복사하지 말고 새로 만든다.

## 새 Windows PC 준비

Git과 Python 3.14.7을 설치한다. PowerShell에서 `py -3.14 --version`이
`Python 3.14.7`인지 확인하고 다음 명령을 실행한다.

```powershell
git clone https://github.com/lucasbrothers/SM_Automation.git
cd SM_Automation
git switch master
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
.venv/Scripts/python.exe src/main.py
```

기대 결과는 **101개 테스트 통과**, 프로그램 종료 코드 0,
`logs/sm_automation.log`에 `Application initialized` 기록이다.
가상환경 활성화 없이 직접 실행하므로 PowerShell 실행 정책을 바꿀 필요가 없다.
이미 저장소가 있다면 미커밋 작업을 먼저 보존하고 `git pull --ff-only origin master`로 받는다.

패키지 설치는 인터넷 접근이 필요하다. 오프라인 PC로 이동할 경우 동일한
Windows/Python 환경의 온라인 PC에서 wheel 파일도 준비한다.

```powershell
.venv/Scripts/python.exe -m pip download -r requirements-dev.txt -d wheelhouse
```

`wheelhouse` 폴더를 별도로 옮기고 새 PC에서 다음 명령으로 설치한다.

```powershell
.venv/Scripts/python.exe -m pip install --no-index --find-links wheelhouse -r requirements-dev.txt
```

wheel 파일과 Python/Git 설치 파일은 이번 저장소에 포함하지 않았다.

## IDE 및 설정

- VS Code에서 저장소 폴더를 열고 Python 인터프리터로 `.venv/Scripts/python.exe`를 선택한다.
- pytest 설정은 저장소의 `pytest.ini`를 사용한다.
- 기본 설정은 `config/app.json`, 상세 설명은 [configuration.md](configuration.md)에 있다.
- PC별 설정은 `config/app.local.json`으로 복사하여 수정하고
  `.venv/Scripts/python.exe src/main.py --config config/app.local.json`으로 실행한다.
- 실행 로그, 캐시, 가상환경, 로컬 설정, 실제 서버 목록은 Git에 포함하지 않는다.

## 완료 상태와 다음 작업

1. Logger 구현과 보안·동시 초기화·복구·회전 검증 완료.
2. JSON 설정 읽기·검증과 Logger 설정 연결 완료.
3. `main.py`의 설정 검증 및 시작/종료 처리 완료.
4. 전체 테스트 101개 통과.

다음 작업은 **서버 목록 로더**다. `AppConfig.server_file`을 입력으로 사용하여
hostname/IP 형식을 결정하고, IP 유효성·중복·잘못된 행·파일 오류를 검증한다.
현재 서버 목록 파일은 없으며 아직 읽거나 SSH 접속을 수행하지 않는다.
그다음 SSH 연결·명령 실행 엔진을 구현한다.

새 PC에서 에이전트에게 아래 내용을 전달하면 된다.

> docs/pc-handoff.md와 docs/configuration.md를 읽고 현재 테스트를 확인한 뒤,
> 다음 단계인 서버 목록 로더를 구현해 주세요. 한국어로 진행 상황을 설명하고,
> 코드의 이름·주석·docstring은 영어로 작성해 주세요.

이 문서는 프로젝트 작업 맥락을 저장한다. IDE 탭, 대화 세션,
플러그인·계정 인증 정보는 새 PC에서 별도로 설정해야 한다.
