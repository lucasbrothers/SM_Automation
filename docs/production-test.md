# CLIENT / SERVER / GUI 운영환경 테스트 설치 안내

이 패키지는 소스와 설치 스크립트다. 단독 EXE/MSI나 의존성을 포함한 오프라인 설치본은 아니다. 인터넷 가능한 설치 환경에서는 고정된 requirements를 내려받아 설치한다. 폐쇄망은 docs/offline-deployment.md를 따른다. 실제 검증은 로컬 Ubuntu WSL에서만 수행했다. 실제 RHEL/AIX/Windows CLIENT 검증은 아직 남아 있다.

## 구성과 파일

- CLIENT: 관리 대상 서버. 앱 에이전트 설치는 필요 없다. SSH/SFTP 서비스와 관리 계정을 준비한다. client-prerequisites.zip에는 준비 안내만 포함한다.
- SERVER: Linux 메인 서버. server-install.zip을 원하는 디렉터리에 풀고 deploy/install-server.sh를 실행한다. Python 3.11 이상과 venv/pip, SSH 클라이언트가 필요하다.
- GUI: Windows PC. gui-install.zip을 풀고 Python 3.14를 준비한다. deploy/install-gui.ps1 실행 후 deploy/start-gui.cmd로 실행한다.
- 통신: GUI→SERVER TCP 7443 / SERVER→CLIENT 지정 SSH 포트(기본 22). 파일 전송은 CLIENT↔SERVER 작업과 별도 GUI(Windows)↔SERVER 파일 탐색 창으로 구분한다.

## SERVER 설치·설정·실행

서비스를 실행할 Linux 계정으로 아래 명령을 수행한다. 설치 위치 예시는 /opt/SM_Automation이다.

```sh
cd /opt/SM_Automation
bash deploy/install-server.sh
.venv/bin/python scripts/provision_server.py --server-name 실제서버DNS --server-ip 실제서버IP
.venv/bin/python scripts/create_gui_account.py --id admin
```

프로비저닝은 최초 설치에서 한 번만 실행한다. 기존 키가 있으면 재생성하지 않는다. 계정 등록 도구에서 사용할 비밀번호를 직접 입력한다. 로컬 WSL에 설정한 기본 비밀번호는 배포 패키지에 포함되지 않는다.

config/app.local.json에서 environment를 production으로, ssh.user/port/privilege/key_file을 실제 CLIENT 관리 설정으로 수정한다. SERVER 파일 경로는 이 Linux 서비스 계정의 접근 권한을 따른다. CLIENT의 SSH 호스트 키를 별도 확인한 뒤 서비스 계정의 ~/.ssh/known_hosts에 등록한다. GUI의 SERVER 연결은 Linux OS 계정 대신 위에서 등록한 앱 ID를 사용한다.

```sh
.venv/bin/python scripts/run_server.py --config config/app.local.json
```

지속 실행은 deploy/sm-automation.service를 사용한다. 이 템플릿은 /opt/SM_Automation 및 smops 계정을 가정하므로 실제 설치 경로와 서비스 계정에 맞춰 편집한다. 프로비저닝·앱 계정 등록도 같은 서비스 계정으로 실행해야 한다.

```sh
sudo cp deploy/sm-automation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sm-automation
sudo systemctl status sm-automation
```

## GUI 설치·연결

SERVER에서 공개 ~/.config/sm-automation/ca.crt만 Windows로 전달한다. 인증서 선택 UI는 없지만 TLS 서버 검증은 유지되므로 외부 운영 SERVER의 공개 CA는 Windows 신뢰 저장소에 한 번 등록해야 한다. 사내 CA를 이미 신뢰하면 추가 등록은 필요 없다. master.key/API token/개인키를 옮기지 않는다.

PowerShell에서 압축을 푼 프로젝트 디렉터리로 이동한 뒤 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-gui.ps1 -PublicCA C:\배포자료\ca.crt
.\deploy\start-gui.cmd
```

Connect server에서 실제 SERVER IP 또는 DNS, 포트 7443, 등록한 앱 ID/비밀번호를 입력한다. 인증서의 이름/IP가 연결 주소와 일치해야 한다. Overview→Manage inventory에서 CLIENT hostname/IP/OS를 등록한다. Connection map에서 CLIENT 한 대를 선택하고 CLIENT login settings에서 SSH 계정·포트·비밀번호를 설정한다. 키 인증은 SERVER의 SSH 프로필을 준비한다.

## CLIENT 준비

Linux CLIENT는 OpenSSH 서버와 SFTP를 실행하고 관리 계정의 공개키 또는 비밀번호 SSH 인증을 준비한다. 연결 조회에는 ss/netstat, 설정 수집에는 각 OS의 명령과 파일 접근 권한이 필요하다. 자원·계정·보안·패치 변경은 현재 Linux를 지원하며 해당 관리 계정의 권한과 서버 프로필 privilege가 맞아야 한다. 모든 기능이 필요하면 승인된 권한으로 구성한다.

AIX는 SSH/SFTP 및 OS 수집 명령을 준비한다. Windows CLIENT는 OpenSSH 서버/SFTP 및 PowerShell을 준비한다. 두 환경의 수집 코드는 있으나 실환경 검증은 미완료다. 계정·패치 기능은 모든 OS에서 제공되는 것이 아니다. CLIENT에는 SM Automation Python 패키지를 설치하지 않는다.

## 첫 테스트 순서

1. GUI 로그인 후 목록 조회, CLIENT 한 대 선택.
2. Commands / Files에서 hostname 실행, 대상별 성공/실패·stdout/stderr 확인, CSV 저장.
3. Resources와 연결 조회, 계정 목록 조회, 설정 백업 및 미리보기.
4. 파일 전송: CLIENT/SERVER의 기존 부모 디렉터리와 새 대상 파일명을 사용해 8 MiB 이하 일반 파일을 왕복한다. 업로드 CLIENT→SERVER / 다운로드 SERVER→CLIENT. 기존 대상 덮어쓰기는 거부한다.
5. 계정 생성·SSH 정책 적용·패치 적용은 계획과 사전 백업을 확인한 후 해당 운영 테스트 대상에 실행한다.

TLS 오류는 CA 신뢰와 주소 일치, 로그인 오류는 앱 계정, SSH 오류는 CLIENT 계정/known_hosts/포트, 파일 오류는 양쪽 경로·권한을 확인한다. 기존 실행 중인 GUI는 닫고 최신 패키지로 다시 실행한다.


## 2026-10-13 설치·통합 검증 결과

- 현재 저장된 로컬 CLIENT 설정으로 Accounts 29개 조회, 09 root 명령, 명령 실패/상세 GUI 표시 및 CLIENT↔SERVER 왕복 통과.
- 별도 임시 계정으로 비밀번호 SSH, 최초 공개키 배포/중복 방지/키 로그인, sudo 비밀번호 root 실행 통과. su는 WSL 전용 mount namespace의 별도 shadow로 검증해 실제 root 비밀번호를 변경하지 않았다. 임시 계정·sudo 권한·개인키는 정리한다.
- SERVER ZIP을 임시 위치에 새 venv로 설치하고 프로비저닝·앱 계정 등록·검증 TLS 로그인 통과. WSL 인터넷이 차단돼 Windows에서 받은 Linux wheels로 오프라인 설치했다.
- GUI ZIP을 별도 위치에 풀고 install-gui.ps1로 새 runtime 설치 및 90% 시작 확인. CLIENT는 에이전트 설치 없이 SSH/SFTP 준비 방식이다.
- GUI↔SERVER 64 MiB 바이너리 왕복, 실제 /tmp 가시성, 기존 파일 보존, 실패·취소 임시 파일 정리 통과. 파일은 숨김 임시 파일로 전송 후 완성된 이름으로 게시한다. 취소는 현재 전송 조각 처리 후 적용한다. 통신 장애로 정리 요청도 실패하면 잔여 경로를 표시한다.
- 실제 RHEL/AIX/Windows CLIENT와 외부 운영 SERVER가 제공되지 않아 이 환경의 검증은 미완료다. 현재 승인은 로컬 WSL에 한정한다.
- 폴더 재귀 전송, 중단 파일 재개, 앱 계정별 권한 분리는 후속 개발 후보이며 이번 운영 준비 검증 완료와 구분한다.

재검증 도구: scripts/wsl_acceptance.py(WSL root), scripts/wsl_install_check.py(WSL), scripts/wsl_gui_file_check.py(Windows), scripts/wsl_tools_check.py(Windows). 검증 도구는 설치 패키지에 포함하지 않으며 실제 CLIENT 목록이나 접속 비밀번호를 변경하지 않는다.
