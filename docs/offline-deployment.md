# Windows 오프라인 배포 및 설치

이 문서는 현재 Windows PC에 애플리케이션과 로컬 PostgreSQL을 설치하는
절차를 설명합니다.

## 패키지 구성

```text
src/sw/
  python-wheels/
    paramiko-*.whl
    psycopg-*.whl
    psycopg_binary-*.whl
    cffi-*.whl
    cryptography-*.whl
    invoke-*.whl
    ...
```

PostgreSQL은 현재 PC에 별도로 설치합니다. Python wheel은 현재 PC에서
미리 내려받아 `src/sw/python-wheels`에 넣습니다.

## 오프라인 패키지 준비

현재 PC에서 인터넷 연결이 가능한 동안 프로젝트 루트 기준으로 실행합니다.

```powershell
.\scripts\prepare_offline_python_packages.ps1
```

이 스크립트는 [requirements-runtime.txt](../requirements-runtime.txt)에
지정된 실행 의존성을 `src/sw/python-wheels`에 저장합니다. 개발용 pytest는
운영 배포에 포함하지 않습니다.

## 현재 PC 설치

현재 PC에서 wheel bundle을 확인하고 설치합니다.

```powershell
.\scripts\install_offline_bundle.ps1
```

PostgreSQL은 현재 PC에 공식 설치 프로그램으로 별도 설치하고 다음 값을 사용합니다.

- 설치 위치: 현재 PC의 승인된 로컬 경로
- 포트: `5432`
- 관리자 계정: `postgres`
- 관리자 비밀번호: 현재 PC의 로컬 보안 정책에 따라 설정
- 외부 접속: 비활성화

PostgreSQL은 외부에 공개하지 않고 localhost에서만 접속하도록 구성합니다.
`listen_addresses`를 localhost로 유지하고 현재 PC의 애플리케이션만 접속하게
합니다.

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

이 명령은 [CMDB 스키마](../config/cmdb-schema.sql)를 로컬 `sm_automation`
데이터베이스에 적용합니다. 현재 스키마에는 다음 테이블이 포함됩니다.

- `assets`, `network_endpoints`, `operating_systems`
- `owners`, `asset_owners`
- `business_services`, `asset_business_services`
- `account_inventory`, `asset_accounts`
- `security_audits`, `config_values`

스키마 적용 여부는 로컬 PostgreSQL에서 다음 명령으로 확인합니다.

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
    -h localhost -p 5432 -U postgres -d sm_automation `
    -c "\dt"
```

출력에 위 테이블들이 표시되면 로컬 CMDB 스키마가 생성된 상태입니다.

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
- 로그 prefix에 시간, PID, 사용자, DB, 클라이언트 주소 기록
- `public` 스키마의 PUBLIC 전체 권한 제거
- 운영 애플리케이션은 제한된 `sm_automation` 계정 사용

이 설정은 현재 PC에서 로컬 CMDB를 운영하기 위한 것입니다.

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

- PostgreSQL 설치 프로그램은 Windows x64용이므로 현재 PC가 x64 환경인지 확인합니다.
- PostgreSQL 설치 관리자에 비밀번호를 명령행 인자로 전달하지 않습니다.
- `src/sw/python-wheels`에 실제 wheel이 없으면 완전한 오프라인 Python 설치가
  불가능합니다.
- 운영 패키지에 `requirements-dev.txt`의 pytest 개발 도구를 포함하지 않습니다.
- PostgreSQL은 현재 PC의 localhost에서만 사용합니다.

## 현재 PC 설치 확인 항목

- PostgreSQL 서비스가 실행 중인지 확인합니다.
- `localhost:5432` TCP 연결을 확인합니다.
- `sm_automation` 데이터베이스와 `sm_automation` 계정으로 접속합니다.
- [CMDB 스키마](../config/cmdb-schema.sql)의 테이블 목록을 확인합니다.
- 애플리케이션 실행과 테스트를 현재 PC에서 수행합니다.
