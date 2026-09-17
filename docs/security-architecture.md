# 보안 정책 권고 아키텍처

## 목적

SM_Automation은 운영체제와 버전에 따라 보안 기준과 실행 방법이 다르므로,
정책 파일과 플랫폼별 처리 모듈을 분리합니다.

## 정책 파일 구조

```text
config/
  security-policy-rhel8.json
  security-policy-rhel9.json
  security-policy-aix7.1.json
  security-policy-windows2022.json
  security-policy-postgresql.json
```

정책 파일은 기준값과 적용 조건만 보유합니다. SSH 명령, PowerShell 명령,
AIX 명령은 정책 파일에 직접 넣지 않고 플랫폼 어댑터가 관리합니다.

## 배포 모델

SM_Automation은 중앙 관리용 **컨트롤러**에 설치합니다. 현재 개발 환경은
Windows이며, 향후 고객사 운영 패키지도 Windows Server 또는 Windows 관리용
PC에 설치할 수 있도록 Python 표준 라이브러리와 Windows 호환 패키지를
기본으로 사용합니다.

```text
Windows Controller
  ├─ Linux/RHEL 대상: Paramiko SSH
  ├─ AIX 대상: Paramiko SSH 및 AIX 전용 어댑터
  ├─ Windows 대상: WinRM/PowerShell 어댑터
  └─ CMDB: 원격 또는 로컬 PostgreSQL
```

컨트롤러 운영체제와 관리 대상 운영체제는 서로 다를 수 있습니다. 따라서
Windows에서 실행된다고 Linux 명령을 로컬에서 실행하지 않으며, 원격 대상에
접속한 뒤 대상 OS 전용 명령을 실행합니다.

## 처리 흐름

```mermaid
flowchart LR
    I[Inventory] --> D[OS/Version Detection]
    D --> S[Policy Selection]
    S --> C[Read-only Collection]
    C --> E[Compliance Evaluation]
    E --> P[Remediation Plan]
    P --> A{Approved?}
    A -- No --> R[Report Only]
    A -- Yes --> B[Backup]
    B --> X[Platform Apply Adapter]
    X --> V[Validate]
    V -- Pass --> O[Reload or Restart]
    V -- Fail --> RB[Rollback]
```

## 계층별 책임

| 계층 | 책임 | 현재 상태 |
| --- | --- | --- |
| Inventory | hostname, IP, OS 목록 검증 | 구현 완료 |
| SSH Engine | Linux/AIX SSH 접속 및 원격 명령 | 신뢰된 호스트 키 검증 및 예외 처리 구현 |
| WinRM Adapter | Windows Server 원격 접속 | 정책 파일만 준비 |
| Policy Registry | OS/버전별 JSON 선택 | 파일 기준 운영 |
| Collector | 서버의 실제 설정과 상태 수집 | SSH 기본/보안 일부 구현 |
| Evaluator | 실제값과 정책값 비교 | SSH 기준 구현, 나머지는 `not_evaluated` |
| Remediation Plan | 변경 대상과 현재/권고값 생성 | 구현 완료 |
| Apply Adapter | 백업, 변경, 검증, reload | 단일 Linux 설정 파일의 SSH 옵션, 서버 단위 적용 |
| Rollback | 검증 실패 시 원상복구 | 쓰기·검증·reload·재접속 실패 시 원본 복구 시도 |
| Monitoring | 자원 메트릭 수집 | 보류, node-exporter 예정 |
| CMDB Repository | PostgreSQL 자산/관계/감사 데이터 저장 | 아키텍처 및 스키마 추가 |

## 현재 구현 범위

- Windows 컨트롤러에서 Linux/RHEL 원격 SSH 수집, 평가, 계획 실행을 검증했습니다.
- AIX와 Windows 대상은 정책 파일과 설계 기준을 준비했으며, 전용 실행 어댑터는
  추가 구현이 필요합니다.
- Windows 로컬 PostgreSQL 재현은 PowerShell 스크립트로 제공합니다.
- Linux/AIX 대상의 원격 PostgreSQL 접속은 네트워크와 PostgreSQL 서버 정책이
  허용된 경우에만 동작합니다.

## 플랫폼별 적용 원칙

### RHEL 8/9

- `firewalld`와 SELinux 기준은 고객사 승인값을 사용합니다.
- `authselect` 관리 파일은 직접 편집하지 않습니다.
- `faillock`, `pwquality`, SSSD는 실제 사용 여부를 먼저 확인합니다.
- systemd 서비스와 socket은 `/etc/services` 편집으로 대체하지 않습니다.

### AIX 7.1

- `/etc/security/user`, `/etc/security/passwd`, `/etc/inetd.conf` 등 AIX
  고유 경로를 사용합니다.
- `systemctl`, `authselect`, `faillock`, SELinux, SSSD 명령은 사용하지
  않습니다.
- 계정 제거와 네트워크 필터 변경은 애플리케이션 의존성을 검토합니다.

### Windows Server 2022

- PowerShell/WinRM 기반 수집 및 적용 어댑터를 별도로 구현합니다.
- Windows Firewall, Defender, UAC, RDP, SMB, TLS, 감사 정책을 Windows
  정책 파일 기준으로 평가합니다.
- Linux SSH 명령이나 AIX 파일 경로를 재사용하지 않습니다.

## 적용 승인 게이트

1. 정책 파일과 고객사 기준을 승인합니다.
2. 읽기 전용 감사 결과를 생성합니다.
3. 준수 평가와 변경 계획을 검토합니다.
4. 변경 대상, 영향, 백업 위치, rollback 방법을 확인합니다.
5. 승인된 대상에 한해 플랫폼 적용 어댑터를 실행합니다.
6. 설정 검증과 재접속을 수행합니다.
7. 결과 보고서를 저장합니다.

현재 구현은 이 흐름 중 수집, 평가, 계획, 일부 SSH 적용까지 제공합니다.
RHEL 전체 기준 적용과 Windows/AIX 실행 어댑터는 별도 단계로 확장합니다.

## PostgreSQL CMDB 보안

- CMDB 연결은 전용 애플리케이션 계정과 `sslmode=verify-full`을 사용합니다.
- 애플리케이션 계정에는 superuser, CREATEDB, CREATEROLE 권한을 부여하지
  않습니다.
- 원격 접근은 사설 관리망과 허용된 클라이언트만 허용합니다.
- `pg_hba.conf`는 deny-by-default와 `scram-sha-256`을 기준으로 합니다.
- 비밀번호는 저장소와 JSON에 저장하지 않고 환경변수 또는 Secret Manager를
  사용합니다.
- 초기 스키마는 [config/cmdb-schema.sql](../config/cmdb-schema.sql)이며,
  변경은 승인된 migration으로 관리합니다.
- 원격 TEST1 PostgreSQL은 검증과 초기 스키마 적용 대상이며, 향후 로컬
  PostgreSQL은 [scripts/setup_local_postgresql.ps1](../scripts/setup_local_postgresql.ps1)로
  동일한 DB/역할/스키마 구성을 재현합니다.
- PostgreSQL 보안 기준은
  [config/security-policy-postgresql.json](../config/security-policy-postgresql.json)에
  저장합니다.

## 검토 후 반영한 실행 보호 절차

- SSH는 실행 계정의 `~/.ssh/known_hosts`를 읽고 미등록·변경된 호스트 키를 거부합니다.
  공개키 배포를 포함한 모든 SSH 작업 전에 관리자가 별도 경로로 서버 지문을 확인해야 합니다.
- 인벤토리 hostname은 대소문자를 구분하지 않고 유일해야 합니다. 계획의 hostname과 IP가
  현재 인벤토리와 일치하는지 전체 계획을 먼저 검사합니다.
- 감사 실패 또는 필수 SSH 관측값 누락은 `blocked` 계획으로 기록하며 변경 작업을 만들지
  않습니다. 적용 직전 `sshd -T` 현재값이 계획의 `current`와 다르면 변경하지 않습니다.
- 평가 결과의 `evaluated_checks`는 실제 검사 범위, `unevaluated_controls`는 구현되지 않은
  범위입니다. Windows/AIX 평가기와 `security_controls`는 미구현이므로 전체 준수로 판정하지
  않습니다. SSH 변경 계획의 `no_changes`는 SSH 변경이 없다는 뜻이며 전체 정책 준수가 아닙니다.
- 적용은 Linux/systemd의 `/etc/ssh/sshd_config` 단일 파일만 지원합니다. 활성 `Include` 또는
  `Match`가 있는 파일과 심볼릭 링크는 변경을 거부합니다. 일반적인 RHEL의 include 구성도
  이 제한에 해당할 수 있으며, 자동 적용을 위해 해당 구문을 삭제해서는 안 됩니다.
- 서버별 모든 옵션을 하나의 변경으로 묶고 `mktemp`로 고유 백업 디렉터리를 만듭니다.
  원본은 `/etc/ssh/.sm_automation.<고유값>/sshd_config`에 보존합니다. 설정 구문 및
  유효값을 검사하고 reload 후 다시 확인한 뒤 새 SSH 연결과 `sudo -n true`를 검증합니다.
- 변경 중 실패하면 원본 복구와 reload를 시도합니다. 재접속 실패 시 기존 세션으로 복구하며,
  설정 해시가 달라졌으면 다른 변경을 덮어쓰지 않고 수동 복구 필요 상태를 보고합니다.
- `/etc/ssh/.sm_automation.lock` 디렉터리로 동시 변경을 막습니다. 강제 종료 후 잠금이
  남으면 실행 중인 작업과 설정·백업 상태를 확인한 후 관리자가 잠금을 해제해야 합니다.
- 적용 보고서는 기본 `reports/security-apply.json`에 서버별로 저장합니다. 백업은 자동 삭제하지
  않습니다. 호스트 전체 배치는 성공 또는 실패로 집계하며 미실행 옵션을 성공으로 세지 않습니다.

SSH 및 DB의 실제 운영 연결 시험은 별도로 수행해야 합니다. 컨트롤러나 네트워크가 끊겨 기존
세션까지 잃으면 자동 복구를 보장할 수 없으므로 콘솔 접근과 보고된 원본 백업을 복구 수단으로
유지합니다. Windows/AIX 실행 어댑터, Include/Match 전용 적용기, 전체 보안 기준 평가 및 CMDB
업무 데이터 저장은 후속 구현 범위입니다.
