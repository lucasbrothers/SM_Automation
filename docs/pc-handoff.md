# 다른 PC에서 개발 이어가기

기준: 2026-10-08 아키텍처 변경. 이 문서가 2026-09-17 인계보다 우선한다.
저장소: https://github.com/lucasbrothers/SM_Automation / 브랜치: master

## 이번에 변경한 방향

1. Linux가 메인 서버이며 모든 실제 업무를 수행한다.
2. Windows는 네이티브 GUI/통제만 담당하고 전용 TLS/TCP 7443으로 연결한다(SSH 터널 아님).
3. 관리 대상 접속은 SSH를 유지한다. Windows 대상도 OpenSSH를 사용한다.
4. PostgreSQL을 제거하고 DATA/BACKUP의 내용을 암호화한다.
5. 체크박스·전체선택 + netstat ESTABLISHED 마인드맵, 전체 대상 OS별 백업을 추가했다.
6. 후속 사용자 지시로 로컬 WSL Ubuntu 통합 테스트를 승인받았다. 결과와 재개 방법은 docs/wsl-progress.md를 따른다.

## 인계 자료

- README.md: 진입점
- docs/deployment.md: Linux 서비스와 Windows GUI 실행
- docs/configuration.md: 경로·키·포트·SSH 설정
- docs/architecture.md: 책임 분리·저장·통신·현재 범위
- docs/backups.md: 파일/명령 수집 범위와 복호화
- docs/images/: 실제 GUI 코드로 만든 예시 목업
- deploy/sm-automation.service: systemd 템플릿

## 새 PC 준비

```sh
git clone https://github.com/lucasbrothers/SM_Automation.git
cd SM_Automation
git switch master
```

이미 저장소가 있다면 로컬 변경을 보존한 뒤 `git pull --ff-only origin master`로 갱신한다.
가상환경은 복사하지 않는다. Linux 서버는 requirements-runtime.txt,
Windows GUI는 requirements-gui.txt를 사용한다. 이번 GUI 렌더링 환경은 Windows / Python 3.14.7 / PySide6 6.11.2다.
로컬 WSL Ubuntu에서 root Linux 서비스를 실행하고 Windows GUI 연동을 확인했다. 폐쇄망 패키지는 대상 OS·Python과 일치하도록 별도 준비한다.

새 설치는 deployment.md대로 Linux에서 키와 인증서를 생성한다.
기존 DATA/BACKUP을 이어받는 경우 원래 master.key가 반드시 필요하다.
Git에는 실제 키·토큰·운영 CSV·DATA·BACKUP·가상환경이 포함되지 않는다.
기존 PostgreSQL의 운영 데이터를 파일로 변환하는 마이그레이션은 별도 작업이다.
DB 소프트웨어를 이 PC에서 제거하거나 DB 데이터를 삭제하지는 않았다.

## 다음 PC에서 최소 확인할 항목

로컬 WSL에서는 1~4의 핵심 경로를 확인했다. 다른 PC에서는 다음 기능의 정상 여부 위주로 재확인한다.

1. Linux 서비스를 시작하고 Windows가 TLS 7443으로 인증·접속하는지.
2. GUI에서 서버 목록을 저장하고 Linux DATA의 파일이 암호화되는지.
3. 서버 1대 선택/전체선택 후 netstat 연결이 맵과 표에 표시되는지.
4. Linux 1대의 sudoers/sudoers.d, 계정별 chage 결과와 manifest를 읽을 수 있는지.
5. AIX 및 Windows OpenSSH 대상에서 OS별 명령과 인코딩/권한이 맞는지.
6. GUI 종료 후 Linux 작업이 계속되고 재접속하여 이력을 읽을 수 있는지.

기존 pytest를 원하면 requirements-dev.txt 설치 후 실행하되 이번 기능의 충분한 검증으로
간주하지 않는다. 기존 설정 테스트의 PostgreSQL 기대값만 새 설정에 맞춰 수정했고 새 대규모
테스트는 추가하지 않았다. 이전 101 passed 기록은 이전 코드 기준이다.

## 현재 구현의 한계 / 이어서 할 작업

- 최신 사용자 지시로 Red Hat Enterprise Linux를 명시적으로 지원 범위에 추가했다. RHEL은 Linux 공통 기능과 RPM/DNF 캐시 업데이트 조회·버전 고정 계획·백업 후 로컬 서명 RPM 적용 경로를 사용한다. 실제 RHEL 검증은 아직 필요하다. 외부 대상 테스트는 승인되지 않았고 현재 테스트는 로컬 Ubuntu WSL만 사용한다.

- 서버별 SSH 프로필을 추가했다. Linux의 보호된 ssh-profiles.json에 계정/키/포트를 정의하고 GUI/CSV에는 profile 이름만 지정한다. 다른 PC에서 실제 연결을 확인한다.
- AIX/Windows 실환경 netstat 및 파일/명령 수집 조정.
- Linux 계정 GUI와 변경 전 암호화 백업을 구현하고 WSL에서 확인했다. Debian/Ubuntu 및 RHEL 패치 조회·계획·백업 후 적용 경로를 연결했다. SSH 설정 파일 권한 600 및 인증 정책 계획/적용을 추가했다. 전역 Include 적용·실패 복구를 WSL에서 확인했다. 조건부 Match 및 AIX/Windows 계정·패치는 후속 범위다. RHEL 적용 실환경 검증은 별도로 필요하다.
- API는 공통 운영자 토큰 방식. 예약 수집/백업과 대기 대상 취소를 구현했다. 사용자별 로그인·역할 및 실행 중 원격 명령 강제 취소는 후속 범위.
- 수집 결과는 서버당 5,000 연결, 그래프는 서버당 25 peer로 제한. 대용량 최적화는 후속 범위.
- 백업 전체 복원과 대용량 스트리밍, 키 순환, 보존기간 정리 기능은 후속 범위.
- 기존 직접 실행 스크립트는 과거 호환 도구이며 새 GUI의 운영 경로가 아니다. 새 기능은 run_server.py를 통해 사용한다.
- Linux 계정 공개키 등록을 추가했다. 개인키는 받지 않으며 등록 전 authorized_keys 상태도 암호화 백업한다. Python 3가 필요하고 실제 검증은 로컬 WSL만 수행했다.
- SSH 설정 적용은 sudo 프로필 또는 direct root를 지원한다. direct root의 적용·재접속·복구·임시 정리에는 sudo가 필요하지 않다. WSL에서 적용 및 실패 복구를 확인했다.
- Red Hat 인증 설정 백업에 SSSD·Kerberos·sudo 전역 설정을 포함했다. 없는 선택 경로는 경고로 남긴다. 실제 RHEL 수집은 후속 확인이 필요하다.

## 다음 작업자에게 전달할 문장

> docs/pc-handoff.md와 docs/architecture.md를 먼저 읽으세요. Linux 메인 서버,
> Windows 네이티브 GUI, 전용 TLS 포트, 대상 SSH, 암호화 DATA/BACKUP 구조를 유지하세요.
> 후속 지시로 WSL root 통합 테스트를 진행했습니다. docs/wsl-progress.md에서 결과를 확인하고
> 서버별 SSH 프로필과 OS별 수집 문제를 보완하세요. 한국어로 단계별 3줄 이내로 설명하고
> 코드 식별자·주석·docstring은 영어로 작성하세요.
