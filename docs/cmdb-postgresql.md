# PostgreSQL CMDB 운영

## 환경 분리

현재는 TEST1의 원격 PostgreSQL을 검증 대상으로 사용합니다. 운영 환경에서도
PostgreSQL은 Windows 컨트롤러 로컬에 설치합니다. 원격 TEST1은 개발 검증
대상으로만 유지합니다. 상세한
`listen_addresses`, `pg_hba.conf`, TLS, 방화벽 설정은
[원격 PostgreSQL 운영 서버 구성](postgresql-remote-setup.md)을 따릅니다.

```text
원격 검증 대상
host: 192.168.192.131
user: postgres
database: postgres

향후 로컬 운영 대상
host: localhost
port: 5432
database: sm_automation
user: sm_automation
```

비밀번호는 문서, JSON, 명령행 인자에 저장하지 않습니다. 원격 검증
스크립트가 숨김 입력으로 받거나 `SM_AUTOMATION_POSTGRES_PASSWORD` 환경변수로
받습니다.

## 원격 PostgreSQL 검증

읽기 전용 연결 확인:

```powershell
py -3 scripts/verify_remote_postgresql.py `
    --host 192.168.192.131 `
    --port 5432 `
    --user postgres `
    --database postgres
```

비밀번호를 입력하면 PostgreSQL 버전, 데이터베이스, 접속 사용자,
standby 여부를 출력합니다. 서버에 스키마를 생성해야 하는 승인을 받은
경우에만 다음 옵션을 추가합니다.

```powershell
py -3 scripts/verify_remote_postgresql.py `
    --host 192.168.192.131 `
    --user postgres `
    --database postgres `
    --apply-schema
```

## 로컬 PostgreSQL 재현

로컬 PostgreSQL과 `psql.exe`가 설치된 환경에서 실행합니다.

```powershell
.\scripts\setup_local_postgresql.ps1 `
    -PostgresHost localhost `
    -PostgresPort 5432 `
    -AdminUser postgres `
    -DatabaseName sm_automation `
    -ApplicationUser sm_automation
```

스크립트는 다음을 수행합니다.

1. PostgreSQL 관리자 연결 확인
2. `sm_automation_owner` NOLOGIN 소유자 역할 생성
3. `sm_automation` 제한된 LOGIN 애플리케이션 역할 생성
4. 애플리케이션 역할에 superuser, CREATEDB, CREATEROLE, replication 권한 부여 금지
5. `sm_automation` 데이터베이스 생성
6. `config/cmdb-schema.sql` 적용
7. 애플리케이션 역할에 필요한 database/schema/table/sequence 권한만 부여
8. 비밀번호 환경변수 정리

## 애플리케이션 연결

로컬 초기화 후 애플리케이션 접속 비밀번호를 런타임에 설정합니다.

```powershell
$env:SM_AUTOMATION_CMDB_PASSWORD = "<runtime-secret>"
```

`config/app.json`의 `cmdb.enabled`를 `true`로 바꾸고, `cmdb.host`와
`cmdb.database`를 로컬 환경에 맞춥니다. 운영에서는 `sslmode=verify-full`을
유지하고, 로컬 개발에서 TLS를 구성하지 않은 경우에만 별도 개발 설정에서
값을 조정합니다.

## 스키마

초기 스키마는 [config/cmdb-schema.sql](../config/cmdb-schema.sql)입니다.
자산, IP/DNS, OS, 담당자, 업무 서비스, 계정 관계, 보안 감사 결과,
중요 설정값을 저장합니다. 변경은 파괴적 SQL을 직접 실행하지 않고 승인된
migration으로 관리해야 합니다.
