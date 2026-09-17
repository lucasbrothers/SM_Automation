# 원격 PostgreSQL 운영 서버 구성

운영 환경에서는 PostgreSQL을 Windows 컨트롤러에 설치하지 않고 별도 Linux
서버에 설치합니다.

```text
Windows SM_Automation Controller
        |
        | TLS / TCP 5432
        v
RHEL 8/9 PostgreSQL CMDB Server
        |
        +-- sm_automation database
        +-- sm_automation_owner (NOLOGIN)
        +-- sm_automation (LOGIN, restricted)
```

## 1. PostgreSQL 서버에서 설정 파일 확인

PostgreSQL 서버의 `postgres` 계정으로 실행합니다.

```bash
sudo -u postgres psql -d postgres -c "SHOW config_file;"
sudo -u postgres psql -d postgres -c "SHOW hba_file;"
sudo -u postgres psql -d postgres -c "SHOW data_directory;"
```

배포판과 PostgreSQL 버전에 따라 경로가 다를 수 있으므로 경로를 임의로
가정하지 않습니다.

## 2. listen_addresses 설정

`postgresql.conf`에서 모든 인터페이스가 아니라 PostgreSQL 서버의 사설
관리 IP만 지정합니다.

```ini
listen_addresses = '10.10.10.20'
port = 5432
password_encryption = 'scram-sha-256'
```

설정 파일 위치는 1단계의 `SHOW config_file` 결과를 사용합니다.

```bash
sudo systemctl restart postgresql
sudo ss -lntp | grep 5432
```

다음처럼 `0.0.0.0:5432`에 무조건 바인딩하는 설정은 피합니다.

```ini
listen_addresses = '*'
```

## 3. 원격 인증 설정

`pg_hba.conf`에는 관리 컨트롤러의 실제 사설 IP 또는 승인된 관리망만
허용합니다. 예를 들어 컨트롤러가 `10.10.10.50`인 경우:

```conf
hostssl  sm_automation  sm_automation  10.10.10.50/32  scram-sha-256
```

초기 연결 확인을 위해 임시로 넓은 대역을 허용하지 않습니다.
다음 설정은 운영 기준으로 사용하지 않습니다.

```conf
host    all    all    0.0.0.0/0    trust
host    all    all    0.0.0.0/0    md5
```

설정 반영:

```bash
sudo systemctl reload postgresql
sudo -u postgres psql -d postgres -c "SELECT pg_reload_conf();"
```

## 4. TLS 설정

애플리케이션은 기본적으로 `sslmode=verify-full`을 사용합니다. 따라서
PostgreSQL 서버 인증서의 SAN에 CMDB DNS 이름이 있어야 합니다.

```ini
ssl = on
ssl_min_protocol_version = 'TLSv1.2'
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

인증서와 개인키 권한 예시:

```bash
sudo chown postgres:postgres server.crt server.key
sudo chmod 600 server.key
sudo chmod 644 server.crt
```

운영 연결은 IP보다 DNS 이름을 사용합니다.

```text
cmdb-db.example.internal
```

Windows 컨트롤러에는 신뢰할 CA 인증서를 배포하고, 애플리케이션 설정은
다음처럼 지정합니다.

```json
{
  "cmdb": {
    "enabled": true,
    "host": "cmdb-db.example.internal",
    "port": 5432,
    "database": "sm_automation",
    "user": "sm_automation",
    "password_env": "SM_AUTOMATION_CMDB_PASSWORD",
    "sslmode": "verify-full"
  }
}
```

## 5. 역할과 데이터베이스 생성

DB 관리자 계정으로 실행합니다. 애플리케이션 역할에는 superuser,
CREATEDB, CREATEROLE 권한을 부여하지 않습니다.

```sql
CREATE ROLE sm_automation_owner NOLOGIN;
CREATE ROLE sm_automation LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE sm_automation PASSWORD '<runtime-secret>';
CREATE DATABASE sm_automation OWNER sm_automation_owner;
```

비밀번호를 SQL 파일, 저장소, 명령 이력에 남기지 않습니다. 실제 운영에서는
Secret Manager 또는 안전한 관리자 세션에서 설정합니다.

스키마 적용:

```bash
psql "host=localhost dbname=sm_automation user=postgres sslmode=peer" \
  -v ON_ERROR_STOP=1 \
  -f /path/to/SM_Automation/config/cmdb-schema.sql
```

스키마 적용 후 애플리케이션 계정에는 필요한 권한만 부여합니다.

```sql
GRANT CONNECT ON DATABASE sm_automation TO sm_automation;
GRANT USAGE ON SCHEMA public TO sm_automation;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sm_automation;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sm_automation;
```

## 6. 방화벽과 네트워크 확인

PostgreSQL 서버와 네트워크 방화벽에서 Windows 컨트롤러 IP만 TCP 5432에
접근하도록 허용합니다. firewalld 사용 환경의 예시는 다음과 같습니다.

```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.10.10.50/32" port port="5432" protocol="tcp" accept'
sudo firewall-cmd --reload
```

고객사 기준으로 firewalld가 비활성화된 환경이면 네트워크 방화벽/ACL에서
동일한 제한을 적용해야 합니다. PostgreSQL을 인터넷에 직접 노출하지
않습니다.

## 7. 연결 확인 순서

Windows 컨트롤러에서 먼저 포트만 확인합니다.

```powershell
Test-NetConnection cmdb-db.example.internal -Port 5432
```

그 다음 비밀번호를 환경변수로 설정하고 원격 검증을 실행합니다.

```powershell
$env:SM_AUTOMATION_POSTGRES_PASSWORD = "<runtime-secret>"
py -3 scripts/verify_remote_postgresql.py `
    --host cmdb-db.example.internal `
    --database postgres `
    --user postgres `
    --sslmode verify-full
Remove-Item Env:SM_AUTOMATION_POSTGRES_PASSWORD
```

애플리케이션 연결 비밀번호는 별도로 설정합니다.

```powershell
$env:SM_AUTOMATION_CMDB_PASSWORD = "<runtime-secret>"
```

## 현재 TEST1 접속 실패 점검

현재 `192.168.192.131:5432`가 접근되지 않는 경우 PostgreSQL 서버에서
다음을 순서대로 확인합니다.

```bash
sudo ss -lntp | grep 5432
sudo -u postgres psql -d postgres -c "SHOW listen_addresses;"
sudo -u postgres psql -d postgres -c "SHOW hba_file;"
sudo journalctl -u postgresql --since "30 minutes ago" --no-pager
```

- `ss` 결과가 없으면 PostgreSQL이 외부 주소에 listen하지 않는 상태입니다.
- `127.0.0.1:5432`만 보이면 `listen_addresses`를 수정해야 합니다.
- 사설 IP가 보이지만 연결되지 않으면 방화벽 또는 네트워크 ACL을 확인합니다.
- 연결은 되지만 인증 실패하면 `pg_hba.conf`와 계정 인증 방식을 확인합니다.
