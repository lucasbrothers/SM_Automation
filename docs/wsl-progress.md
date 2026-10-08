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

- Linux 기존 회귀 테스트: 195 passed (계정·패치·예약 검증 포함).
- Windows → Linux 검증 TLS 접속 및 잘못된 토큰 거부.
- 실제 SSH 연결 수집, 자원 모니터링, Linux 보안 감사 작업 완료.
- 백업 11개 아티팩트 정상 완료. 설정 tar의 sudoers/sudoers.d 포함 확인 및 계정별 chage 결과 미리보기 확인.
- 선택 설정 파일 부재 및 비어 있는 crontab을 실제 실패와 구분하도록 수정.
- Windows 네이티브 GUI의 서버 접속, 전체선택 해제/선택, 작업 요청, 결과 표 및 마인드맵 표시 확인.
- AIX 및 Windows 관리 대상은 실행하지 않았다. 전체 복원 및 실제 버전 업그레이드는 아직 실행하지 않았다. 계정 변경과 동일 버전 패치 적용 경로는 아래 기록을 따른다.

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

- 계정 관리 후속: 그룹 변경, 비밀번호/키 프로비저닝, AIX/Windows 지원.
- 패치 후속: RPM/AIX/Windows 지원, 폐쇄망 패키지 업로드 및 메타데이터 갱신. 보안 정책 적용 GUI. 예약/취소 후속: 달력 기반 반복 및 실행 중 명령 단위 취소.
- AIX/Windows 정책·수집 실환경 검증(현재 승인된 테스트 범위는 WSL뿐).
- 사용자별 권한, 전체 복원/대용량 전송, 키 순환 및 보존 정책.

자동화 sm-automation은 사용량을 먼저 확인하고 이 문서를 읽어 이어간다.
소진 시 진행 상태를 기록하고 다음 실행에서 재확인한다. 전체 승인 범위가 완료되기 전에는 자동화를 중지하지 않는다.

## 2026-10-08 계정 관리 추가

Accounts 페이지에서 Linux 계정 조회/생성/SR·이름 변경/비밀번호 로그인 잠금·해제/삭제를 요청한다.
대상은 Connection map 선택을 따른다. comment는 SR-날짜-이름이며 UID 선택, 기존 GID 선택이 가능하다.
UID 미지정 시 대상 useradd 정책에 따라 할당한다. 새 계정은 비밀번호 미설정 상태다.
변경 전 전체 백업이 완료되어야 실행한다. 같은 IP의 계정 변경은 백업부터 순차 처리한다.
SSH 관리 계정과 UID 1000 미만/65534 시스템 계정 변경을 거부한다. 삭제는 홈을 보존한다.
비밀번호 잠금은 SSH 공개키 접속을 막지 않는다. 해제는 기존 비밀번호 해시가 있는 잠긴 계정만 가능하다.
실패한 변경의 결과에도 선행 백업 위치를 보존한다. Activity에서 결과를 확인한다.

실제 WSL 임시 계정 생성/변경/잠금/조회/삭제 및 비밀번호 미설정 잠금 해제 거부를 확인했다.
테스트 계정은 삭제했고 /home/smtest_1791463632 홈은 삭제 정책대로 보존했다.
Windows GUI가 Accounts 작업을 제출하고 실제 계정 목록을 표시하는 것을 확인했다.
재확인 도구: scripts/wsl_account_check.py (WSL 한 대에만 임시 계정을 만들고 마지막에 삭제).
목업: docs/images/desktop-accounts.png (합성 예시, 실제 사용자 정보 아님).
Linux apt 패치 GUI를 추가했다. 정기 작업/취소를 추가했다. 다음 구현 우선순위는 보안 정책 적용과 계정 관리 보완이다.

## 2026-10-08 패치 관리 추가

Patches 페이지: Query updates → 설치된 패키지 입력 → Preview patch plan → 결과 검토 → Apply reviewed plan.
현재 Debian/Ubuntu apt 대상만 지원한다. 조회는 기존 메타데이터를 사용하고 자동 apt update를 하지 않는다.
계획은 패키지 이름 또는 이름=버전을 최대 50개 입력받는다. 설치된 패키지만 선택하며 의존성 변경도 apt 모의 실행 결과에 표시한다.
서버가 보관한 완료 계획만 적용하며 대상 목록/주소/프로필이 같아야 한다. 계획 유효기간은 1시간이다.
Windows가 임의 명령이나 설치 버전을 전달하여 계획을 우회할 수 없다.
적용 전 전체 암호화 백업을 만들고 apt 모의 실행을 재확인한다. 패키지 상태가 바뀌면 새 계획을 요구한다.
apt --no-remove/--only-upgrade를 사용하며 기존 설정 파일을 유지한다. 자동 재부팅하지 않고 필요 여부만 결과에 표시한다.
서비스는 같은 대상의 계정 변경과 패치 적용을 순차 처리한다. 실패 시에도 선행 백업 위치는 결과에 남는다.
패키지 스크립트는 서비스를 재시작할 수 있다. 설정 백업은 패키지 바이너리의 자동 롤백 기능이 아니다.

실제 확인: WSL net-tools의 설치된 버전으로 모의 실행(변경 0개), 암호화 선행 백업, 적용 요청 완료 및 버전 유지.
실제 업그레이드/서비스 재시작/재부팅/복원은 테스트하지 않았다. 다른 PC에서는 유지보수 시간에 별도 확인한다.
검증 도구 scripts/wsl_patch_check.py는 이 동일 버전 경로만 실행한다.
GUI 이벤트 검증에서 실제 업데이트 조회와 버전 지정 계획 표시 및 적용 버튼 활성화를 확인했다.
목업 docs/images/desktop-patches.png는 합성 데이터다.

## 2026-10-08 예약 및 취소 추가

Schedules 페이지에서 백업/연결 수집/자원 수집/보안 감사의 미래 실행 시각과 반복 간격을 지정한다.
계정 변경·패치 적용은 자동 예약하지 않는다. GUI 시각은 해당 Windows PC의 로컬 시간이며 서버에는 시간대 포함 ISO 시각으로 전달한다.
반복 0분은 한 번만 실행하며 최소 반복은 1분이다. Linux DATA/schedules.json.enc에 암호화 저장한다.
GUI를 종료해도 Linux 스케줄러가 실행한다. Linux가 꺼져 있던 동안의 누락을 연속 재생하지 않고 재가동 후 한 번만 실행한다.
이전 예약 작업이 실행 중이거나 서버 동시 작업 한도(2개)에 도달하면 기다린다. 같은 예약 작업을 중복 실행하지 않는다.
대상 주소/OS/프로필이 변경되면 자동 중지하고 새 예약을 요구한다. 재시작 시 제출 여부가 불확실한 예약도 자동 재시도하지 않는다.
일시정지/삭제는 미래 실행을 막는다. 만료된 예약은 새 미래 시각으로 다시 만들어야 한다.
저장소 오류로 스케줄러가 중단되면 status API의 scheduler_running이 false가 된다. 원인을 복구한 뒤 서비스를 재시작한다.

Activity에서 선택 작업의 Cancel pending targets를 누르면 대기 대상을 취소한다.
시작된 원격 명령은 강제 종료하지 않고 완료 결과를 보존한다. 계정/패치 변경은 선행 백업 뒤에도 취소 여부를 확인한다.
최종 작업 상태 cancelled와 개별 대상 결과를 함께 읽어야 하며 취소는 이미 수행한 변경의 자동 복원이 아니다.

실제 WSL 예약 연결 수집 완료, 예약 암호화 저장, Linux 서비스 재시작 후 일시정지 상태 유지,
재개/일시정지, 백업 취소를 확인했다. 테스트용 예약은 마지막에 삭제했다.
검증 도구 scripts/wsl_schedule_check.py는 로컬 WSL만 사용하고 Linux 서비스를 한 번 재시작한다.
GUI 예약 목록 로딩을 확인했고 docs/images/desktop-schedules.png 합성 목업을 추가했다.
