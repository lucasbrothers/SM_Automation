# WSL 개발 및 통합 테스트 진행 기록

2026-10-08. 후속 사용자 지시에 따라 테스트 보류를 해제하고 로컬 WSL Ubuntu만 대상으로 테스트했다.
Linux가 모든 실제 작업을 수행하며 Windows는 네이티브 GUI와 TLS 7443 통제만 담당한다.

## 현재 구성

- WSL Ubuntu 26.04.1, Python 3.14.4, systemd, root 서비스.
- Linux 배포 경로 `/opt/SM_Automation`, 가상환경 `.venv`.
- `sm-automation.service` 및 `ssh.socket` 활성화. 현재 WSL 주소 172.22.194.8(재시작 시 변경 가능).
- 테스트 대상은 암호화 목록의 `wsl-ubuntu`, 주소 127.0.0.1 한 대뿐이다.
- 대상 SSH는 root 공개키 인증이며 키는 loopback 접속으로 제한했다. root 비밀번호 로그인을 활성화하지 않았다.
- 비밀 자료는 Linux `/root/.config/sm-automation` 및 `/root/.ssh`에만 보관한다.
- DATA/BACKUP은 Linux 배포 디렉터리 아래 암호화 저장한다. Git에는 포함하지 않는다.

## 완료한 확인

- Linux 기존 회귀 테스트: 167 passed.
- Windows → Linux 검증 TLS 접속 및 잘못된 토큰 거부.
- 실제 SSH 연결 수집, 자원 모니터링, Linux 보안 감사 작업 완료.
- 백업 11개 아티팩트 정상 완료. 설정 tar의 sudoers/sudoers.d 포함 확인 및 계정별 chage 결과 미리보기 확인.
- 선택 설정 파일 부재 및 비어 있는 crontab을 실제 실패와 구분하도록 수정.
- Windows 네이티브 GUI의 서버 접속, 전체선택 해제/선택, 작업 요청, 결과 표 및 마인드맵 표시 확인.
- AIX 및 Windows 관리 대상은 실행하지 않았다. 복원·패치 적용·계정 변경도 아직 실행하지 않았다.

## 실행 및 재개

Windows 프로젝트 가상환경에 requirements-gui.txt를 설치한 뒤 다음을 실행한다.

```powershell
.venv/Scripts/python.exe scripts/run_wsl_desktop.py
.venv/Scripts/python.exe scripts/wsl_integration_check.py
.venv/Scripts/python.exe scripts/gui_wsl_check.py
```

GUI 실행 도구는 현재 WSL IP와 인증 자료를 읽어 메모리에만 유지한다. 공개 CA 임시 파일은 종료 시 제거한다.
WSL IP가 변경되면 서버 인증서 SAN도 맞춰 갱신해야 한다. 데이터 키를 새로 생성하면 기존 암호화 데이터를 읽을 수 없으므로 보존한다.

Linux 재검증:

```sh
cd /opt/SM_Automation
.venv/bin/python -m pytest -q -p no:cacheprovider
systemctl status sm-automation.service
```

처음 설치하는 승인된 WSL 환경에서는 runtime/dev 의존성과 openssh-server/net-tools를 준비한 후
root로 scripts/configure_wsl_lab.py를 실행한다. 이 도구는 로컬 실습용이며 일반 운영 서버 배포는 deployment.md를 따른다.
코드 동기화 시 DATA/BACKUP, 가상환경, 비밀 자료, config/app.local.json은 덮어쓰지 않는다.

## 남은 개발

- 중앙 GUI 계정 생성·변경·잠금·삭제와 변경 전 백업.
- 패치 및 보안 정책 적용 GUI, 정기 작업/취소.
- AIX/Windows 정책·수집 실환경 검증(현재 승인된 테스트 범위는 WSL뿐).
- 사용자별 권한, 전체 복원/대용량 전송, 키 순환 및 보존 정책.

자동화 sm-automation은 사용량을 먼저 확인하고 이 문서를 읽어 이어간다.
소진 시 진행 상태를 기록하고 다음 실행에서 재확인한다. 전체 승인 범위가 완료되기 전에는 자동화를 중지하지 않는다.
