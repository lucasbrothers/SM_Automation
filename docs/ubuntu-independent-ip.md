# Ubuntu SERVER / CLIENT 독립 IP 실습

2026-10-16 실제 접속과 관리 작업 검증 완료.

| 역할 | 환경 | IP | 접속 |
|---|---|---|---|
| SERVER | WSL Ubuntu / Ubuntu26.04 | 172.22.194.8 | GUI TCP7443 |
| CLIENT | Hyper-V Ubuntu-Client / Ubuntu24.04.5 LTS | 192.168.250.2 | SSH TCP22 |
| 게이트웨이 | Windows SM-Test-Private | 192.168.250.1 | 내부망 |

WSL 배포판 둘은 네트워크를 공유하므로 CLIENT를 별도 Hyper-V VM으로 구성했다. 기존 WSL Ubuntu-Client는 삭제하지 않고 중지하여 보존했다. SERVER의 WSL 주소는 Windows 재부팅 후 바뀔 수 있으며 GUI 실행기가 현재 주소를 읽는다.

## 실행

1. Hyper-V 관리자에서 Ubuntu-Client가 실행 중인지 확인한다. 꺼져 있으면 시작한다.
2. 프로젝트의 `.venv/Scripts/pythonw.exe`로 `scripts/run_wsl_desktop.py`를 실행하고 기존 SM Automation 전용 계정으로 로그인한다.
3. 장비 목록의 ubuntu-client를 선택한다. 주소192.168.250.2, OS Ubuntu24.04, SSH 프로필 ubuntu-client-vm이 적용되어 있다.
4. 05 Accounts에서 계정 조회, 08 Resources에서 자원 조회, 09 Commands / Files에서 명령/전송을 실습한다.
5. 명령 `id -u; hostname`의 결과가 `0`, `ubuntu-client`이면 CLIENT의 root 권한으로 실행된 것이다.
6. CLIENT ↔ SERVER 전송 경로는 양쪽 Linux 파일시스템이다. Windows GUI ↔ SERVER 전송은 별도 창을 사용한다.

CLIENT 접속 계정 D25950은 SERVER 공개키로 로그인하며 sudo가 설정되어 있다. 개인키/로그인 비밀은 문서나 설치 소스에 포함하지 않는다.

## 검증 결과와 제한

계정/자원/CI/root 명령/패치 조회/연결 지도/백업/양방향 전송/백업 비교 총10개 작업 성공. 백업12개 항목 성공. 전송된 파일은 내용과 SHA256을 대조했고 시험 파일을 정리했다. 최초 netstat 누락은 net-tools 설치로 해결했다.

Linux에서 외부 Ubuntu 저장소 직접 접속은 실패하며 Windows에서는 다운로드된다. 패치 조회는 기존 메타데이터 기준이고 실제 업데이트 설치는 검증하지 않았다. 외부 저장소 연결은 추가 네트워크 점검이 필요하다. 로컬 SERVER–CLIENT 통신과 독립 IP는 검증 완료했다.

VM 사양: 2 CPU, 시작2GiB/동적1~3GiB, 디스크30GiB. 로컬 준비 파일은 D:/WSL/VM-Setup, 디스크는 D:/WSL/Ubuntu-Client-VM에 있다. 재프로비저닝 스크립트는 deploy/provision-ubuntu-client-vm.ps1이며 현재 실행 중인 VM을 다시 만들 필요는 없다.
