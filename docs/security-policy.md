# 보안 정책

실행 시 사용하는 보안 정책은 운영체제와 버전에 맞는 JSON 파일을 선택합니다.
RHEL 8은 `config/security-policy-rhel8.json`, RHEL 9는
`config/security-policy-rhel9.json`, AIX 7.1은
`config/security-policy-aix7.1.json`, Windows Server 2022는
`config/security-policy-windows2022.json`을 사용합니다. 정책 기준을 추가하거나
변경할 때는 이 문서가 아니라 해당 JSON 파일을 수정합니다.

아래 값은 현재 Linux 테스트 환경을 위한 권고 기준입니다. 고객사 승인이나
최종 운영 보안 기준을 대신하지 않습니다.

| JSON 파라미터 | 권고 설정값 | 설명 |
| --- | --- | --- |
| `allowed_sshd_settings.permitrootlogin` | `without-password`, `no` | SSH를 통한 root 직접 로그인을 제한합니다. `without-password`는 root 비밀번호 로그인을 막고 키 인증만 허용하며, `no`는 SSH root 로그인을 모두 차단합니다. |
| `allowed_sshd_settings.pubkeyauthentication` | `yes` | SSH 공개키 인증을 허용합니다. 운영 환경에서는 비밀번호보다 공개키 인증을 우선하는 데 사용합니다. |
| `allowed_sshd_config_modes` | `600` | `/etc/ssh/sshd_config`를 소유자만 읽고 쓸 수 있도록 제한합니다. 다른 사용자의 설정 변조를 방지합니다. |
| `required_root_accounts` | `root` | UID 0 권한을 가진 표준 root 계정이 존재해야 함을 검사합니다. |
| `forbidden_root_accounts` | `[]` | root 외에 UID 0 권한을 가진 비인가 계정을 등록합니다. 목록에 있는 계정이 발견되면 정책 위반입니다. |

## 추가 보안 기준

세부 기준은 다음 버전별 파일의 `security_controls` 아래에 저장합니다.

- [RHEL 8 정책](../config/security-policy-rhel8.json)
- [RHEL 9 정책](../config/security-policy-rhel9.json)
- [AIX 7.1 정책](../config/security-policy-aix7.1.json)
- [Windows Server 2022 정책](../config/security-policy-windows2022.json)

각 기준에는 적용 대상 플랫폼과 버전이 함께 기록됩니다.

| 구분 | 주요 권고 기준 |
| --- | --- |
| 서비스 | 고객사 기준에 따라 RHEL 8/9 `firewalld` stopped/disabled |
| SELinux | 고객사 기준에 따라 RHEL 8/9 `disabled` |
| 계정 정책 | `PASS_MAX_DAYS=90`, `PASS_MIN_DAYS=1`, `PASS_MIN_LEN=8`, `PASS_WARN_AGE=7`, `MAIL_DIR` 비활성화 |
| 로그인 배너 | `/etc/issue`, `/etc/issue.net`, `/etc/motd`에 승인 경고문 유지 |
| 서비스 엔트리 | `/etc/services` 주석 처리 대신 systemd 서비스/socket와 방화벽 규칙으로 관리 |
| sudo | wheel 권한 정책 활성화 |
| 파일 권한 | passwd, shadow, 로그, cron, PAM, SSH 관련 파일의 기준 권한 적용 |
| 계정 정리 | 불필요한 lp, games, operator, ftp 계정 및 그룹 제거 대상 관리 |
| 시간 설정 | RTC를 UTC 기준으로 사용 (`local_rtc=false`) |
| faillock | RHEL 8/9에서 deny `5`, unlock_time `600`, authselect `with-faillock` |
| SSSD | debug level `0`, 설정 파일 mode `600`, 소유자 `root:root` |

Windows Server 2022 권고 기준은 다음과 같습니다.

| 구분 | 주요 권고 기준 |
| --- | --- |
| Windows Firewall | Domain/Private/Public 프로파일 enabled, inbound 기본 차단 |
| Microsoft Defender | 실시간 감시, 행위 감시, 클라우드 보호, 자동 서명 업데이트 활성화 |
| UAC | UAC 활성화, 보안 데스크톱에서 관리자 동의/일반 사용자 자격 증명 요구 |
| 계정 정책 | 최소 8자, 최대 사용기간 90일, 최소 사용기간 1일, 이력 5개, 복잡성 활성화 |
| 계정 잠금 | 5회 실패 시 30분 잠금, 카운터 초기화 30분 |
| RDP | 기본 비활성화, 사용 시 NLA/TLS/High 암호화, 저장 자격 증명 차단 |
| SMB | SMBv1 및 NTLMv1 차단, SMB signing 양방향 요구, Guest 로그온 차단 |
| TLS | TLS 1.0/1.1 및 약한 cipher 차단, TLS 1.2 활성화 |
| 감사 정책 | 로그인, 계정 관리, 정책 변경, 권한 사용, 시스템 이벤트 성공/실패 감사 |
| PowerShell | Script Block/Module logging 및 transcription 활성화 |
| 이벤트 로그 | Security 256MB, Application/System 128MB 이상 및 중앙 전달 검토 |
| 로컬 계정 | Guest 비활성화, Administrator 별도 운영정책 적용, 미사용 계정 검토 후 제거 |
| 네트워크 | LLMNR 비활성화, 불필요한 NetBIOS 비활성화 |
| 시스템 보호 | 지원 시 Secure Boot, BitLocker, Credential Guard 활성화 |

Windows 정책은 Linux 명령이나 AIX 경로를 사용하지 않습니다. Windows
적용 모듈은 향후 PowerShell/WinRM 기반으로 별도 구현해야 합니다.

`authselect`, `faillock`, `sssd`, SELinux, systemd 서비스 항목은 RHEL 8/9
기준입니다. `firewalld=disabled`, `SELinux=disabled`는 일반적인 보안 권고와
다를 수 있지만 현재 고객사 승인 기준으로 반영했습니다. `/etc/security/passwd`,
`/etc/dfs/dfstab`, `/etc/sulog` 등 AIX 전용 경로는 RHEL 정책에서 제외했습니다.
AIX와 Windows는 동일 명령을 그대로 적용하지 않고 별도 정책 파일과 플랫폼별
적용 모듈로 분리합니다.

RHEL 8/9 공통 기준이라도 `system-auth` 같은 authselect 관리 파일은 직접
수정하지 않고 authselect 프로파일을 통해 변경해야 합니다. SSSD 설정은
실제로 SSSD를 사용하는 서버에서만 적용합니다.

## 설정 적용 순서

1. D25950의 SSH 키 기반 접속을 확인합니다.
2. `inventory_ssh_check.py --check-root`로 root 전환을 확인합니다.
3. `security_audit.py`로 현재 설정을 수집합니다.
4. 해당 OS/버전 정책 파일과 비교해 정책 위반을 확인합니다.
5. 고객사 승인 후에만 SSH 설정을 변경합니다.

## Evaluate

```powershell
py -3 scripts/security_compliance.py `
    --audit-report reports/security-audit.json `
    --policy-file config/security-policy-rhel9.json `
    --report-file reports/security-compliance.json
```

종료 코드:

- `0`: 모든 inventory 대상이 정책을 준수합니다.
- `1`: 하나 이상의 정책 위반이 발견되었습니다.
- `2`: 입력 파일 또는 결과 처리 오류입니다.

정책 평가기는 읽기 전용이며 SSH 설정이나 계정을 변경하지 않습니다. 설정을
변경하는 조치 작업은 별도 승인과 rollback 계획 후에 구현해야 합니다.

## 변경 계획 생성

정책 위반을 실제 서버에 적용하기 전에 서버별 변경 계획을 생성합니다.
이 명령은 원격 서버를 변경하지 않습니다.

```powershell
py -3 scripts/security_remediation_plan.py `
    --audit-report reports/security-audit.json `
    --policy-file config/security-policy-rhel9.json `
    --report-file reports/security-remediation-plan.json
```

생성된 계획에는 현재값, 권고값, 변경 대상 파라미터가 기록됩니다. 실제
적용 기능은 고객사 승인, 변경 전 백업, 설정 검증, rollback 절차를 확정한
후 별도 구현합니다.

## 승인된 변경 적용

변경 계획을 검토하고 승인한 후에만 `--apply`를 사용합니다. 기본 실행은
dry-run이며 원격 서버를 변경하지 않습니다.

```powershell
py -3 scripts/security_apply.py `
    --plan-file reports/security-remediation-plan.json `
    --inventory config/servers.test.txt `
    --user D25950 `
    --key-file C:/Users/seong/.ssh/id_rsa `
    --apply
```

적용 시 대상 서버의 `/etc/ssh/sshd_config`를 시간표시 백업으로 저장하고,
`sshd -t` 설정 검증을 통과한 경우에만 SSH 데몬을 reload합니다. 검증 실패
시 기존 설정을 복원합니다. 적용 후에는 `inventory_ssh_check.py
--check-root`와 `security_audit.py`를 다시 실행해야 합니다.

## AIX 7.1 평가

AIX는 RHEL 명령을 사용하지 않고 AIX 전용 정책 파일을 선택합니다.

```powershell
py -3 scripts/security_compliance.py `
    --audit-report reports/security-audit-aix7.1.json `
    --policy-file config/security-policy-aix7.1.json `
    --report-file reports/security-compliance-aix7.1.json
```

AIX 7.1에서는 `/etc/security/user`의 비밀번호 정책, `/etc/inetd.conf`,
`/etc/security/passwd`, `/var/adm` 로그 경로를 사용합니다. `systemctl`,
`authselect`, `faillock`, `sssd`, SELinux 명령은 AIX 7.1 기준에 포함하지
않습니다.

## Windows Server 2022 평가

Windows용 감사 수집기가 추가되면 다음 정책 파일을 사용합니다.

```powershell
py -3 scripts/security_compliance.py `
    --audit-report reports/security-audit-windows2022.json `
    --policy-file config/security-policy-windows2022.json `
    --report-file reports/security-compliance-windows2022.json
```
