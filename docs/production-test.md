# CLIENT / SERVER / GUI 운영환경 테스트 설치 안내

이 패키지는 소스와 설치 스크립트다. 단독 EXE/MSI나 의존성을 포함한 오프라인 설치본은 아니다. 인터넷 가능한 설치 환경에서는 고정된 requirements를 내려받아 설치한다. 폐쇄망은 docs/offline-deployment.md를 따른다. 실제 검증은 로컬 Ubuntu WSL에서만 수행했다. 실제 RHEL/AIX/Windows CLIENT 검증은 아직 남아 있다.

## 구성과 파일

- CLIENT: 관리 대상 서버. Linux/AIX는 SSH/SFTP와 관리 계정을 준비한다. Windows는 Windows CLIENT 자동 연결 설치 EXE를 권장하며 IP/포트만 입력한다. client-prerequisites.zip에는 준비 안내만 포함한다.
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

AIX는 SSH/SFTP 및 OS 수집 명령을 준비한다. 기존 Windows SSH 모드는 OpenSSH 서버/SFTP 및 PowerShell을 준비한다. 새 Windows agent 모드는 문서 아래의 자동 연결 설치 안내를 따른다. 두 환경의 수집 코드는 있으나 실환경 검증은 미완료다. 계정·패치 기능은 모든 OS에서 제공되는 것이 아니다. CLIENT에는 SM Automation Python 패키지를 설치하지 않는다.

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
- 당시 후속 후보였던 폴더 전송·재개·역할별 권한은 아래 2026-10-14 구현 내용을 따른다.

재검증 도구: scripts/wsl_acceptance.py(WSL root), scripts/wsl_install_check.py(WSL), scripts/wsl_gui_file_check.py(Windows), scripts/wsl_tools_check.py(Windows). 검증 도구는 설치 패키지에 포함하지 않으며 실제 CLIENT 목록이나 접속 비밀번호를 변경하지 않는다.


## 2026-10-14 폴더 전송·재개·권한

09 → GUI ↔ SERVER 파일 전송에서 파일과 폴더를 선택해 버튼 또는 드래그앤드롭으로 전송한다. 하위 폴더·빈 폴더·빈 파일을 포함하며, 링크/Windows junction/특수 파일은 따라가지 않고 중단 상태를 표시한다. 서로 다른 기존 파일은 덮어쓰지 않는다. 이미 전송된 파일의 크기와 SHA256이 같으면 유지하고 다음 파일로 진행한다. Windows에서 지원하지 않는 파일명은 오류로 표시한다.

Pause는 현재 조각 처리 후 중단하고, Resume은 원본·부분 파일의 SHA256 일치를 검사해 이어 전송한다. 같은 SERVER IP/포트/ID로 다시 접속하면 GUI 재시작 후에도 Resume할 수 있다. 원본이 변경됐거나 부분 파일이 다르면 재개하지 않는다. Cancel transfer와 Discard paused transfer는 임시 파일/재개 기록을 정리한다. 네트워크 오류로 정리가 실패하면 기록을 보존해 다시 정리할 수 있다. 한 GUI 계정/접속 주소당 미완료 전송 묶음 하나를 유지하며, 재개하거나 폐기한 뒤 새 전송을 시작한다. 폴더 전체를 한 번에 게시하는 방식은 아니므로 완료된 파일·빈 폴더는 중단 후에도 남는다.

재개 기록은 Windows LOCALAPPDATA/SM_Automation/transfers에 경로·진행 상태만 저장한다. 로그인 비밀번호나 키는 기록하지 않는다. 같은 계정으로 GUI 창을 여러 개 띄워 동시에 파일 전송하지 않는다.

관리자는 SERVER GUI account에서 계정 목록과 Role을 지정한다. 기존 계정의 Password를 비우면 비밀번호를 유지하며 권한만 바꾼다. 마지막 관리자를 일반 사용자로 변경할 수 없다. 기존 계정은 이전 권한을 유지하도록 관리자 역할로 호환한다.

| 역할 | 허용 작업 |
| --- | --- |
| admin | root 명령, CLIENT/앱 계정·접속 설정, 전체 파일·정책·패치 관리 |
| operator | 연결·자원·계정 목록 조회, 저장 명령 편집, 공유폴더 업로드·다운로드·폴더 생성 |
| viewer | 연결·자원 및 허용된 결과 조회, 공유폴더 목록·다운로드 |

운영자/조회자의 파일 접근은 /srv/sm-automation/shared 내부로 제한하며, root 명령과 관리자 작업 결과·SERVER 비밀 파일 접근은 서버에서 거부한다. 공유폴더는 공용 공간이며 사용자별 개인 폴더 격리 기능은 아니다. API 토큰은 호환용 관리자 자격이므로 일반 사용자에게 배포하지 않는다.

운영 서버에서는 서비스 계정에 맞춰 공유폴더를 먼저 준비한다(아래 smops를 실제 서비스 계정으로 변경).

```sh
sudo install -d -o smops -g smops -m 0700 /srv/sm-automation/shared
```

검증: 로컬 WSL 폴더 왕복·GUI 재시작에 해당하는 기록 재로드 후 업로드/다운로드 재개·원본 변경 거부·기존 파일 보존 통과. 실제 Windows↔WSL TLS에서 폴더/빈 항목 및 재개 SHA256 검증, 실제 operator/viewer 로그인 후 관리자·root 명령·비밀 파일·관리자 작업 결과 접근 차단 통과. scripts/wsl_followup_check.py로 재검증한다.


## 2026-10-14 Cron 예약 및 패치 안내

07에서 예약 방식을 한 번/일정 간격 또는 Crontab으로 선택한다. Cron은 분(0–59), 시(0–23), 일(1–31), 월(1–12), 요일(0–7, 일요일 0/7) 다섯 칸을 사용한다. *, 목록(0,30), 범위(1-5), 간격(*/15)을 지원하며 영문 요일/월 이름·L/W/#/@별칭은 지원하지 않는다. 예: `0 9 * * 1-5`는 평일 09:00, `30 2 1 * *`는 매월 1일 02:30이다. 시간대 기본값은 Asia/Seoul이며 UTC 등 IANA 이름을 지정할 수 있다. 일과 요일이 모두 제한되면 둘 중 하나가 맞는 날짜에 실행한다. */15는 매시간 0/15/30/45분이며 생성 시각부터 15분 간격이라는 뜻이 아니다.

예약은 Linux DATA/schedules.json.enc에 암호화 저장되고 SERVER 내부 스케줄러가 실행한다. OS crontab 파일을 직접 편집하지 않는다. Windows GUI 종료와 무관하며 SERVER 서비스가 꺼져 있으면 실행할 수 없다. 재시작 후 놓친 시각은 한 번 처리하고 다음 미래 시각을 계산한다. 실행 중인 동일 작업이나 서버 작업 한도가 있으면 기다린다. 일시정지한 cron 예약 재개는 다음 미래 시각부터 시작한다. 불확실한 실행 중단/저장 이력 복구 문제가 있으면 자동 재실행 대신 예약을 중지해 검토하도록 기존 보호를 유지한다. DST 없는 시각은 건너뛰고 두 번 나타나는 시각은 각각 예약 시각으로 처리한다.

예약 대상 작업은 연결 수집·자원 조회·보안 점검·백업이다. 명령 또는 패치 자동 적용 예약은 제공하지 않는다.

06 패치 화면 상단에 단계 안내와 '패치 동작·지원 범위 자세히 보기'를 추가했다. 업데이트 조회는 기존 메타데이터를 읽으며 갱신·설치를 수행하지 않는다. 입력 칸에 패키지명 또는 패키지명=버전을 공백 구분해 넣고 계획을 생성한다. 계획은 설치가 아닌 시뮬레이션이다. 성공한 계획은 1시간 이내 같은 대상·상태로만 적용하며 사전 설정 백업, 고정 버전·의존성 검증 후 설치한다. 자동 재부팅/전체 시스템 롤백은 없고, 패키지 자체의 서비스 재시작 가능성 때문에 유지보수 시간이 필요하다. Debian/Ubuntu APT와 준비된 서명 RPM 기반 RHEL DNF를 지원하며 실제 RHEL 검증은 남아 있다.

Cron 형식 참고: https://man7.org/linux/man-pages/man5/crontab.5.html


## 2026-10-14 장비록·예약 목록/변경

상단 실행 대상에서 개별 장비 선택 또는 장비록을 지정한다. '장비록 관리'에서 이름·설명·구성원을 생성/수정/삭제하며 같은 장비가 여러 장비록에 포함될 수 있다. 장비록은 Linux DATA/equipment-books.json.enc에 암호화 저장한다. 변경 권한은 관리자이며 운영자/조회자는 목록을 사용할 수 있다.

장비록을 선택하면 계정·패치·원격 명령·수집·자원·백업·공개키 배포 등 CLIENT 작업의 대상이 장비록 구성원이 된다. 구성원 체크는 장비록 관리에서 바꾸며, 단일 CLIENT 접속 설정은 개별 장비로 지정한다. CLIENT→SERVER 다중 파일 업로드는 충돌 방지를 위해 SERVER 경로에 {hostname}을 포함한다. SERVER→CLIENT는 동일 SERVER 파일을 여러 CLIENT로 전송할 수 있다. GUI↔SERVER 파일 창은 CLIENT 작업과 별개다.

07은 '예약 목록'과 '예약 등록' 탭으로 구분한다. 목록은 다음 실행·작업·대상 장비록/CLIENT·반복 조건과 시간대·최근 제출 시각·최근 결과·예약 상태를 표시하며 CSV 저장을 지원한다. '선택 예약 변경'은 기존 ID를 유지하면서 작업·시각·Cron·반복·사용 여부를 수정한다. 대상을 바꾸려면 상단 실행 대상을 선택하고 '현재 Connection map 선택으로 교체'를 체크한다. 실행 중인 예약은 작업 종료 후 변경할 수 있다. 장비록 삭제/구성원 변경 또는 장비 주소/OS 변경이 감지되면 자동 예약을 중지하며, 대상을 다시 검토해 예약을 수정해야 한다.

## 백업 ↔ 현재 설정 비교와 엑셀

03에서 기준 백업 행을 선택하고 상단 실행 대상을 장비록으로 지정한 뒤 '선택 백업 ↔ 현재 설정 비교'를 실행한다. 기준 백업은 보존하며 현재 설정도 변경하지 않는다. 비교 범위는 원래 설정 파일 보관 범위이며 실시간 명령 출력과 파일 수정 시각은 제외한다. Unix는 파일 내용 SHA256·권한·소유자·링크를 비교하고 Windows 파일 JSON은 내용으로 비교한다. AIX/Windows 실제 검증은 남아 있다.

비교 창 상단에 대상/변경 장비/변경 파일/실패/미완료 수를 표시한다. 장비별 결과에서 장비를 선택하면 해당 장비의 변경 파일과 상세 차이를 읽는다. 추가는 녹색, 삭제는 주황색, 변경은 노란색으로 구분한다. 기준 백업에 장비가 없거나 주소/OS가 다르거나 설정 수집이 불완전하면 그 장비는 실패로 표시하며 '동일'로 판정하지 않는다.

'장비록 비교 엑셀 다운로드'는 장비록 요약·장비별 결과·변경 파일·상세 차이 4개 시트를 생성한다. 전체 장비록의 변경 파일을 포함하며 헤더 고정·필터·색상 구분을 적용한다. 비밀번호·토큰·개인키로 식별되는 행/파일 내용은 표시하지 않는다. 파일 크기/상세 차이에는 표시 한도가 있으며 큰 파일/바이너리는 SHA256으로 변경을 판정한다. 상세 차이 전체 표시 한도에 걸리면 생략을 명시한다. 파일명·SHA256·변경 여부는 계속 보고한다. 비교 결과는 BACKUP/comparisons에 암호화 저장하며 Activity에서 다시 조회한다.

## CLIENT 1,000대 기준 부하 완화

- 새 설치의 ssh.max_workers 기본값은 5다. 이는 작업당이 아닌 SERVER 전체 동시 접속 상한으로도 적용한다. 기존 운영 설정은 유지한다(현재 WSL 2). 백업/비교 및 변경 전 백업의 무거운 처리는 전체 1건으로 제한한다.
- 50대 초과 작업은 기본 60초에 걸쳐 연결 시작을 분산한다. 실제 완료 시간은 장비 응답/동시 실행 제한에 따라 더 길 수 있다. API options.spread_seconds(0–3600)로 명시할 수 있다. 예약도 같은 실행 경로를 사용하며 동일 예약의 이전 작업이 끝나지 않으면 겹쳐 실행하지 않는다.
- GUI 작업 목록은 유휴 시 15초/작업 중 3초, 자원 자동 조회는 120초다. 자원 상세는 선택 대상만 받으며 결과 페이지는 최대 50장비 단위다.
- 큰 장비별 수집 결과는 별도 암호화 파일로 저장하고 작업 이력에는 참조를 기록한다. 처리된 Future 참조를 해제해 모든 결과를 작업 종료까지 중복 보관하지 않는다. 백업 비교는 요약부터 받고 선택 장비 상세만 읽는다. 엑셀 생성도 행 단위 기록/임시 스풀을 사용한다.
- 파일은 SHA256 비교 후 변경된 내용에 대해서만 텍스트 차이를 계산한다. 비교 보고서 상세 읽기는 한 번에 1개이고, 최대 2개의 결과를 30초 캐시한다. 로그인 검증은 성공한 비밀번호의 비가역 HMAC만 최대 128개/60초 캐시하고 매번 계정 레코드를 확인하므로 비밀번호·권한 변경은 즉시 반영한다.
- 실제 1,000대 동시 부하 시험은 수행하지 않았다. 1,000대 목록·장비록 처리는 단위 검증했고, 동시 실행 제한과 실제 로컬 WSL 2대 별칭의 작업/비교를 검증했다. 운영 환경에서 장비록별 시간대를 나누고 CPU·메모리·디스크를 측정해 동시 접속 수를 조정한다.

검증 도구 scripts/wsl_books_comparison_check.py는 임시 독립 SERVER 저장소/TLS 포트와 로컬 WSL 별칭 2개를 사용한다. 실제 운영 인벤토리/장비록/예약은 바꾸지 않으며 비교용 cron 주석 파일은 종료 시 정리한다.

## CI 자산 관리

GUI **10 CI / 자산**에서 장비록·선택 CLIENT의 OS/하드웨어/자원을 수집하고, 고객사·운영상태·서비스 등급·담당자·서비스명 등 자산 정보를 개별 또는 일괄 편집할 수 있습니다. 저장된 조회 전체를 CSV/Excel로 내려받습니다. 사용 순서·플랫폼별 수집 제한·권한·저장 위치는 [CI 자산 관리](ci-dashboard.md)를 확인하세요.

## Windows CLIENT 자동 연결 설치

Windows는 이제 별도 Python/SSH/WinRM 설치 대신 **Windows CLIENT 설치 / 상태**에서 만든 설치 EXE를 사용할 수 있습니다. 설치 시 SERVER IP와 포트만 입력하면 장비별 인증으로 SERVER에 자동 등록됩니다. 기존 Linux/AIX SSH 방식은 유지합니다. 설치·등록 허용 범위·오프라인/제거 상태·관리 목록 삭제·지원 기능과 검증 제한은 [Windows CLIENT 에이전트 안내](windows-client-agent.md)를 확인하세요.
