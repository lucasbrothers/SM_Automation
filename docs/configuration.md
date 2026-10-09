# 설정과 암호화 저장

2026-10-08 변경: PostgreSQL 설정을 제거하고 Linux 메인 서버 설정을 추가했다.
`config/app.json`을 `config/app.local.json`으로 복사해 사용한다. local 파일은 Git 제외다.

| 항목 | 기본값 | 의미 |
| --- | --- | --- |
| storage.data_directory | ./DATA | 암호화 목록·작업 결과 |
| storage.backup_directory | ./BACKUP | 암호화 백업 |
| storage.key_file | ~/.config/sm-automation/master.key | 외부 보관 암호화 키 |
| server.host | 0.0.0.0 | Linux 수신 주소 |
| server.port | 7443 | Windows GUI 전용 TLS/TCP 포트 |
| server.tls_cert / tls_key | ~/.config/sm-automation/server.crt / server.key | 서버 인증서/개인키 |
| server.token_file | ~/.config/sm-automation/api.token | GUI 접근 토큰 |
| ssh.user | D25950 | Linux가 대상에 접속하는 계정 |
| ssh.port | 22 | 대상 SSH 포트 |
| ssh.key_file | null | Linux상의 키 경로, 없으면 SSH agent/기본 키 사용 |
| ssh.timeout | 30 | 연결/일반 명령 제한 시간 |
| ssh.max_workers | 10 | 작업당 병렬 대상 수 |
| ssh.privilege | sudo | Unix 백업 권한 전환: sudo / direct / su |
| backup.timeout | 180 | 백업 명령별 시간 제한(초) |
| backup.max_capture_mb | 64 | 명령별 메모리 캡처 상한(MiB) |

DATA/BACKUP 및 server/ssh 경로의 상대값은 **프로젝트 루트** 기준으로 해석한다.
`~`는 Linux 서비스 계정 홈이다. 기존 logging/inventory 경로는 설정 파일 디렉터리 기준이다.
절대 경로를 지정해 별도 볼륨으로 옮길 수 있다. 기존 파일을 새 경로로 자동 이동하지 않는다.
`inventory.server_file`은 기존 CLI 호환 설정이며 서버의 실제 목록은 DATA의 암호화 파일이다.
CSV는 GUI 가져오기 또는 `scripts/import_inventory.py`로 명시적으로 등록한다.
가져오기는 기존 목록 전체를 교체한다. 필수 열은 `hostname,ip,os`이며 `profile`은 선택이다. UTF-8(BOM 포함)을 사용하고 헤더 대소문자·앞뒤 공백은 허용한다. 중복 열·빈 필수 값·잘못된 행은 저장 전에 거부한다.
Windows에서는 GUI의 Import CSV를 사용한다. 직접 가져오기 스크립트는 Linux 메인 서버에서 실행한다.

Fernet으로 내용 암호화와 변조 검출을 수행한다. 암호화 키는 DATA/BACKUP 밖에 둬야 한다.
키가 없거나 잘못되면 읽기를 중단하며 새 키를 자동 생성하지 않는다.
암호화 파일과 **원래 master.key를 함께 보존**해야 다른 Linux 서버에서 내용을 읽을 수 있다.
키·토큰은 POSIX에서 0600 권한으로 보관한다. 평문 중간파일은 생성하지 않는다.

`sudo`: 대상에서 `sudo -n sh -c ...`를 실행한다. 비밀번호 프롬프트 없는 승인된 sudo 권한 필요.
`direct`: 이미 필요한 읽기 권한을 갖춘 로그인 계정으로 실행한다.
`su`: `su - root -c ...`이며 비대화형 전환이 사전 허용된 대상만 지원한다.
대화형 root 비밀번호 입력은 지원하지 않으며, 실패 시 작업 실패/부분 완료로 표시한다.

Windows의 SSH 세션은 필요한 권한을 가진 관리 계정을 사용해야 한다.
SSH 계정/포트/키의 기본값은 전역 설정이며 OS별 계정이 다른 환경에서는
아래 서버별 접속 프로필을 사용한다.

## 서버별 SSH 프로필

Linux의 `~/.config/sm-automation/ssh-profiles.json`에 접속 프로필을 둘 수 있다.
파일이 없으면 app 설정의 전역 접속값을 사용한다. 예시는 `config/ssh-profiles.example.json`이다.
이 파일은 Linux 서비스 계정이 읽을 수 있는 0600 권한으로 보관한다.
프로필의 `key_file`은 **Linux 절대 경로 또는 ~ 경로**를 사용한다.
비밀번호가 필요하면 `password_env`에 Linux 환경변수 이름만 지정한다.
GUI에는 프로필 이름만 입력하며 키/비밀번호는 전송하지 않는다.

CSV 선택 열 `profile` 또는 Manage inventory의 SSH profile에 `unix-admin`,
`windows-admin` 등을 지정한다. 비워 두면 `default`(전역 설정)다.
프로필 파일 변경 후 Linux 서비스를 재시작하면 반영된다.
프로필을 읽을 때 사용자·포트·권한 방식·키 경로·환경변수 이름을 검사한다. 포트는 숫자로 1~65535를 지정하고 키는 Linux 절대 또는 `~/` 경로를 사용한다. `password` 같은 지원하지 않는 필드는 거부하며 비밀번호 값은 파일에 넣지 않는다.
추가 권한 전환 `sudo-su`는 `sudo -n su - root -c ...`를 사용한다.
