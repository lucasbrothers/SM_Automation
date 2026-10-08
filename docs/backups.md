# OS별 백업

백업은 **Linux 메인 서버**에서 실행하며 GUI에는 진행 상황과 파일 경로만 반환한다.
Back up ALL servers는 현재 암호화 목록의 모든 대상을, Back up selected는 선택 대상을 처리한다.

## 저장 구조

```text
BACKUP/
  2026-10-08/
    hostname/
      run-id/
        configuration_files.tar.enc       # Unix archive
        configuration_files.json.enc      # Windows base64 file collection
        configuration_files.metadata.json.enc
        account_expiry_chage.txt.enc       # Linux account-by-account output
        account_sudo_privileges.txt.enc
        system.txt.enc
        network.txt.enc
        ...
        manifest.json.enc
```

날짜는 Linux 메인 서버의 로컬 날짜다. 같은 날 다시 실행해도 run-id가 달라 덮어쓰지 않는다.
각 명령 결과와 stderr/종료 코드/수집 시간은 별도 암호화 파일로 보존한다.
manifest는 각 단계 후 갱신하여 중단 직전까지 완료한 항목을 남긴다.

## 주요 수집 범위

| OS | 설정 파일 | 명령 결과 |
| --- | --- | --- |
| Linux | passwd/group/shadow/gshadow, sudoers 및 sudoers.d 전체, SSH, PAM, security, login.defs, fstab, hosts, DNS, sysctl, cron, systemd, network, audit, rsyslog, logrotate | 계정별 chage -l 및 sudo -l -U, uname/os-release, getent, df/lsblk/mount, ip/netstat, services, packages, sysctl, crontab |
| AIX | passwd/group, /etc/security, sudoers 및 sudoers.d(/opt/freeware 포함), SSH, filesystems, inittab, environment, rc.net/rc.tcpip, inetd, DNS, cron | lsuser/lsgroup, 계정 만료 속성, 계정별 sudo 권한, oslevel/prtconf, lsvg/lspv, lssrc, lslpp/emgr, no/vmo/ioo/schedo |
| Windows | ProgramData/ssh, hosts, GroupPolicy, Tasks | 로컬 계정/그룹 및 net user 만료정보, 서비스, 예약작업, 네트워크, 디스크, 패치, 방화벽, auditpol, 정책 레지스트리 조회 |

`chage`는 Linux 명령이다. AIX는 `lsuser`, Windows는 `net user`로 대응한다.
Windows는 OpenSSH와 PowerShell, 필요한 관리자 권한이 준비되어 있어야 한다.
이 백업은 주요 OS 설정/운영 정보 스냅샷이다. 디스크 이미지·애플리케이션 DB·전체 레지스트리
하이브·AD 전체 백업을 대체하지 않는다. 필요 경로/명령은 `src/backup/profiles.py`에서 확장한다.

## 결과 해석

- completed: 해당 단계가 종료 코드 0이고 stderr가 없음
- partial: 결과 파일은 있으나 명령 실패 또는 경고가 포함됨(없는 선택 경로도 포함)
- failed: 연결/권한/시간/크기 등으로 해당 항목을 저장하지 못함

Unix 설정 파일은 tar 스트림을 받아 즉시 암호화한다. 원격/로컬 평문 임시파일을 만들지 않는다.
명령별 기본 캡처 상한은 64 MiB이며 Windows 파일 수집은 원본 합계 32 MiB를 제한한다.
상한 초과는 성공으로 취급하지 않는다. 대규모 폴더를 위한 청크 스트리밍은 후속 범위다.
메모리 사용량을 고려해 `ssh.max_workers`와 `backup.max_capture_mb`를 조정한다.
대상 설정이 백업 도중 바뀔 수 있으므로 원자적인 파일시스템 스냅샷은 아니다.

## Linux에서 복호화해 확인

```sh
.venv/bin/python scripts/decrypt_artifact.py '2026-10-08/web-prod-01/RUN_ID/manifest.json.enc' --output /secure/export/manifest.json --config config/app.local.json
.venv/bin/python scripts/decrypt_artifact.py '2026-10-08/web-prod-01/RUN_ID/configuration_files.tar.enc' --output /secure/export/configuration.tar --config config/app.local.json
```

출력 디렉터리는 먼저 준비한다. 기존 파일은 덮어쓰지 않는다. 출력은 명시적 평문 내보내기이므로
읽기 권한을 제한한다. tar는 별도 임시 디렉터리에서 확인하고 시스템 루트에 바로 풀지 않는다.
자동 복원/덮어쓰기 기능은 이번 범위에 포함하지 않았다.

백업 결과 화면은 서버/파일별 트리와 텍스트 미리보기를 제공한다.
미리보기는 Linux가 복호화하여 최대 64 KiB를 반환하고 Windows는 메모리에서만 표시한다.
설정 tar 아카이브는 GUI에서 풀지 않고 Linux의 명시적 내보내기 도구를 사용한다.
