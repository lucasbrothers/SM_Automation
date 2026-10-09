# Linux 서버와 Windows GUI 배포

2026-10-08 개발 초안. 이 문서는 다음 PC에서 실행하기 위한 절차이며, 이번 PC에서
Linux 서비스 설치나 실서버 접속을 수행했다는 의미가 아니다.

## 1. Linux 메인 서버

Python 3.14 환경을 준비한다. Linux 배포판별 패키지 가용성은 대상 PC에서 확인한다.
아래는 프로젝트 디렉터리에서 실행한다.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
cp config/app.json config/app.local.json
.venv/bin/python scripts/provision_server.py --server-name sm-main.example.internal --server-ip 192.0.2.10
```

server-name/server-ip에는 Windows GUI가 실제 연결할 이름과 주소를 넣는다.
프로비저닝은 CA·서버 인증서·암호화 키·접근 토큰을 서비스 계정 홈에 만든다.
이미 키가 있으면 덮어쓰지 않는다. 이 스크립트는 비밀번호나 토큰 내용을 출력하지 않는다.
사내 CA를 사용하는 경우 사내 인증서로 `server.tls_cert`/`server.tls_key`를 지정한다.

`config/app.local.json`에서 DATA/BACKUP 경로, 대상 SSH 계정과 키를 지정한다.
Linux 서비스 계정의 known_hosts에 **확인된 대상 호스트 키**를 등록한다.
자동으로 호스트 키를 신뢰하도록 설정하지 않는다.

서버 목록을 작성해 암호화 저장한다.

```sh
.venv/bin/python scripts/import_inventory.py /secure/path/servers.csv --config config/app.local.json
.venv/bin/python scripts/run_server.py --config config/app.local.json
```

CSV 형식은 `hostname,ip,os`다. `config/servers.example.csv`에는 문서용 주소만 있다.
서버의 실제 목록은 암호화 파일에 저장하므로 원본 CSV 보관 여부는 운영 정책에 따른다.

Linux 방화벽/관리망에서는 Windows GUI 호스트 → Linux TCP 7443을 허용한다.
Linux → 관리 대상 TCP 22도 필요하다. 웹 서버나 SSH 터널은 필요하지 않다.

## 2. Windows GUI

Windows Python 3.14와 프로젝트 파일을 준비한다. GUI 환경에 SSH/DB 패키지는 필요 없다.

```powershell
py -3.14 -m venv .venv-gui
.venv-gui/Scripts/python.exe -m pip install -r requirements-gui.txt
.venv-gui/Scripts/python.exe scripts/run_desktop.py
```

1. Linux에서 생성한 공개 `ca.crt`를 Windows로 전달한다.
2. API 토큰은 승인된 별도 전달 수단으로 운영자에게 제공한다.
3. GUI의 **Connect server**에서 Linux 주소, 7443, CA 파일, 토큰을 입력한다.
4. Overview에서 목록을 관리하거나 CSV를 가져온다(기존 목록 교체).
5. Connection map에서 서버 체크박스/Select all → Collect connections를 누른다.
6. Backups의 Back up ALL servers는 전체 목록을, Back up selected는 선택 대상을 실행한다.
7. Activity 또는 Backups에서 행을 더블클릭하면 결과/백업 경로를 확인한다.

Windows에는 `master.key`, 대상 SSH 개인키, 대상 SSH 비밀번호를 옮기지 않는다.
GUI 연결 해제 시 메모리의 운영 데이터와 토큰 참조를 비우며 디스크에 저장하지 않는다.

## 3. systemd (선택)

`deploy/sm-automation.service`는 `/opt/SM_Automation`과 서비스 계정 `smops`를 가정한
템플릿이다. 해당 계정·경로를 운영 환경에 맞게 준비한 뒤 배치한다.
프로비저닝도 **서비스 계정으로** 수행하여 홈 디렉터리의 키 경로가 일치해야 한다.
서비스 계정은 DATA/BACKUP에 쓸 수 있고 키/인증서/known_hosts를 읽을 수 있어야 한다.

```sh
sudo cp deploy/sm-automation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sm-automation
sudo systemctl status sm-automation
```

필요한 경우 `SM_AUTOMATION_SSH_PASSWORD`는 보호된 `/etc/sm-automation/runtime.env`에서
제공한다. 비밀번호는 저장소 또는 앱 설정 JSON에 넣지 않는다.

## 4. GUI 목업

```powershell
.venv-gui/Scripts/python.exe scripts/run_desktop.py --demo
.venv-gui/Scripts/python.exe scripts/run_desktop.py --mockup docs/images/desktop-connection-map.png
.venv-gui/Scripts/python.exe scripts/run_desktop.py --page backups --mockup docs/images/desktop-backups.png
.venv-gui/Scripts/python.exe scripts/run_desktop.py --page resources --mockup docs/images/desktop-resources.png
.venv-gui/Scripts/python.exe scripts/run_desktop.py --page security --mockup docs/images/desktop-security-plan.png
```

데모 모드는 실제 서버 접속과 작업 실행을 하지 않는다. PNG는 예시 데이터를 사용한다.

### 혼합 OS 환경의 접속 프로필

Linux에서 `config/ssh-profiles.example.json`을
`~/.config/sm-automation/ssh-profiles.json`으로 복사하고 사용자·키·포트를 수정한다.
파일 권한을 0600으로 지정하고 서비스를 시작한다.
GUI의 Manage inventory에서 각 서버에 프로필 이름을 지정한다.
프로필 없는 서버는 app.local.json의 전역 SSH 설정을 따른다.
Windows는 프로필 이름만 선택하며 실제 SSH 인증정보를 보관하지 않는다.
