# Windows 오프라인 배포 및 설치

운영 패키지는 Windows 컨트롤러에 배포하며, PostgreSQL은 원격 Linux 서버가
아니라 같은 Windows 컨트롤러의 로컬 PostgreSQL을 사용합니다.

## 패키지 구성

```text
src/sw/
  postgresql-18.6-3-windows-x64.exe
  python-wheels/
    paramiko-*.whl
    psycopg-*.whl
    psycopg_binary-*.whl
    cffi-*.whl
    cryptography-*.whl
    invoke-*.whl
    ...
```

현재 저장소에는 PostgreSQL 설치 파일이 포함되어 있습니다. Python wheel은
인터넷이 가능한 준비 PC에서 미리 내려받아 `src/sw/python-wheels`에 넣어야
완전한 오프라인 설치가 됩니다.

## 오프라인 패키지 준비

인터넷이 가능한 준비 PC에서 프로젝트 루트 기준으로 실행합니다.

```powershell
.\scripts\prepare_offline_python_packages.ps1
```

이 스크립트는 [requirements-runtime.txt](../requirements-runtime.txt)에
지정된 실행 의존성을 `src/sw/python-wheels`에 저장합니다. 개발용 pytest는
운영 배포에 포함하지 않습니다.

## 운영 PC 설치

패키지를 운영 Windows PC로 반입한 후 설치 파일 존재 여부와 wheel bundle을
확인합니다.

```powershell
.\scripts\install_offline_bundle.ps1
```

PostgreSQL을 설치하려면 다음처럼 실행합니다.

```powershell
.\scripts\install_offline_bundle.ps1 -InstallPostgreSQL
```

PostgreSQL 설치 프로그램 화면에서 다음 값을 사용합니다.

- 설치 위치: 고객사 승인 로컬 경로
- 포트: `5432`
- 관리자 계정: `postgres`
- 관리자 비밀번호: 고객사 Secret 정책에 따라 설정
- 외부 원격 접속: 비활성화

설치 프로그램에 포함된 PostgreSQL은 외부에 공개하지 않고 localhost에서만
접속하도록 구성합니다. `listen_addresses`를 localhost로 유지하고 로컬
애플리케이션만 접속하게 합니다.

## CMDB 초기화

PostgreSQL 설치가 끝난 뒤 관리자 비밀번호와 애플리케이션 비밀번호를 각각
숨김 입력해 실행합니다.

```powershell
.\scripts\setup_local_postgresql.ps1 `
    -PostgresHost localhost `
    -PostgresPort 5432 `
    -AdminUser postgres `
    -DatabaseName sm_automation `
    -ApplicationUser sm_automation
```

## 로컬 PostgreSQL 권장 보안 설정

설치 및 CMDB 초기화 후 다음 스크립트를 실행합니다. 비밀번호는 숨김 입력되고
스크립트가 종료되면 환경변수에서 제거됩니다.

```powershell
.\scripts\harden_local_postgresql.ps1 `
    -PsqlPath "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
    -DatabaseName sm_automation `
    -RestartService
```

적용 기준:

- `listen_addresses=localhost`: 외부 PostgreSQL 접속 차단
- `password_encryption=scram-sha-256`
- 연결/해제, checkpoint, lock wait 로그 활성화
- 로그 prefix에 시간, PID, 사용자, DB, 원격 주소 기록
- `public` 스키마의 PUBLIC 전체 권한 제거
- 운영 애플리케이션은 제한된 `sm_automation` 계정 사용

이 설정은 로컬 CMDB 운영 모델에 맞춘 것입니다. PostgreSQL을 별도 원격
Linux 서버에 다시 배치할 때는 [원격 PostgreSQL 운영 서버 구성](postgresql-remote-setup.md)의
TLS, `pg_hba.conf`, 관리망 방화벽 절차를 사용합니다.

`-RestartService`는 Windows 서비스 제어 권한이 필요합니다. 권한 부족으로
재시작이 실패하면 관리자 권한 PowerShell에서 다음을 실행합니다.

```powershell
Restart-Service postgresql-x64-18
```

재시작 후 `Test-NetConnection localhost -Port 5432`와 CMDB 연결 테스트를
다시 실행합니다.

이후 [config/app.local.json](../config/app.local.json)을 사용합니다.

```powershell
py -3 src/main.py --config config/app.local.json
```

애플리케이션 접속 비밀번호는 저장하지 않고 런타임 환경변수로 제공합니다.

```powershell
$env:SM_AUTOMATION_CMDB_PASSWORD = "<runtime-secret>"
```

## 설치 확인

```powershell
Test-NetConnection localhost -Port 5432
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d postgres -c "SELECT version(), current_user;"
py -3 -c "import paramiko, psycopg; print('runtime packages: OK')"
```

설치 파일과 wheel의 무결성 확인을 위해 배포 전 SHA256 목록을 생성하고,
반입 후 다시 비교하는 것을 권장합니다.

```powershell
Get-ChildItem src/sw -Recurse -File | Get-FileHash -Algorithm SHA256
```

## 주의사항

- PostgreSQL 설치 파일은 Windows x64용이므로 x64 운영 PC에서 사용합니다.
- PostgreSQL 설치 관리자에 비밀번호를 명령행 인자로 전달하지 않습니다.
- `src/sw/python-wheels`에 실제 wheel이 없으면 완전한 오프라인 Python 설치가
  불가능합니다.
- 운영 패키지에 `requirements-dev.txt`의 pytest 개발 도구를 포함하지 않습니다.
- PostgreSQL localhost 구성은 원격 PostgreSQL 서버와 분리된 운영 모델입니다.

## 현재 로컬 설치 검증 결과

- PostgreSQL 서비스: `postgresql-x64-18`, `RUNNING`
- PostgreSQL 버전: `18.6`
- `localhost:5432`: TCP 연결 성공
- CMDB database: `sm_automation`
- 애플리케이션 계정: `sm_automation`
- 애플리케이션 연결: 성공
- 보안 SQL: 적용 성공
- 전체 테스트: `130 passed`
