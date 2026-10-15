# Windows CLIENT 실기 검증 — 2026-10-15

사용자가 승인한 현재 Windows PC와 로컬 WSL Ubuntu SERVER에서 실제 실행했다. CLIENT를 설치 파일로 1.0.0에서 1.1.0으로 업데이트했으며 기존 장비 등록을 유지했다.

| 검증 항목 | 결과 |
|---|---|
| 서비스 설치/업데이트 | SMAutomationAgent 실행 중, LocalSystem, 자동(지연 시작). 설치된 실행 파일의 SHA256이 검증한 빌드와 일치 |
| CI 수집 | 실제 hostname·OS·CPU·메모리·SMT 수집 성공 |
| PowerShell | SYSTEM 실행 및 결과 반환 성공 |
| 명령 실패 보고 | 의도한 종료 코드 7을 대상별 failed로 정확히 보고 |
| TCP 연결 | 실제 연결 수집·SERVER 저장 캐시 조회 성공 |
| CLIENT → SERVER | 목적지 실제 파일 및 원본 바이트/SHA256 일치 |
| SERVER → CLIENT | Windows 목적지 실제 파일 및 바이트/SHA256 일치 |
| Windows 백업 | 11개 항목 completed, Linux 암호화 저장 및 복호화 후 크기/내용 검증. 설정 JSON에 실제 파일 존재 확인 |
| 설정 비교 | 현재 PC 설정 파일 245개 비교, 변경 0건 |
| 장비록 | Windows CLIENT를 포함한 임시 장비록 단위 연결 수집 성공 |
| 저장 명령어 | 저장·조회 및 시험 후 정리 성공 |
| SERVER 예약 | 40초 뒤 예약 실행과 Windows 결과 반환 성공. 중간 heartbeat로 예약이 무효화되지 않음 |
| Linux 백업/비교 | 로컬 WSL 대상 12개 백업 항목과 설정 비교 모두 completed. 실행 중인 SERVER 작업 이력에도 새 성공 기록 저장 |

Windows 백업 재검증 소요 시간은 약 118초, 설정 비교 약 1초였다. 현재 PC의 도구 초기화·조회 시간이며 다른 장비/부하에서의 성능을 보장하지 않는다.

## 발견 후 수정한 문제

- Windows 1.0.0 에이전트는 백업 처리가 없어 실패했다. 1.1.0에 항목별 수집을 추가했다.
- Linux는 일반 로그인 계정으로 보호된 파일/계정 진단을 읽어 partial이었다. 비밀번호를 표준 입력으로 전달하는 sudo 및 선택적 su 전환과 UID 0 확인을 적용했다. tar 바이너리도 그대로 보존한다.
- PowerShell 모듈 준비 진행 메시지가 CLIXML stderr로 출력돼 exit 0도 partial이었다. 프로필의 진행 표시를 줄이고, 완전한 진행 메시지만 들어 있는 XML을 오류 판정에서 제외한다. 원본은 암호화 메타데이터에 보존하며 실제 오류/혼합 XML/잘못된 XML은 제외하지 않는다.
- 백업 항목 사이의 30초 유휴 대기를 짧은 서버 작업 전달 대기로 줄였다. 대기 중 전역 장비 잠금은 해제한다.
- 예약 대상 비교에서 heartbeat 시각/온라인 상태를 제외하고 주소·OS·프로필·장비 ID 등 실제 대상 정보를 검사한다.

전체 Windows 회귀 검증 512 passed / 29 skipped, WSL 백업/권한/비교/예약 관련 56 passed. 컴파일된 바이너리와 독립 WSL TLS 간 서명/백업 항목/철회 통신 시험도 통과했다.

시험용 장비록·예약·저장 명령은 삭제했다. 백업/작업 이력은 검토할 수 있도록 남겼고, 테스트 파일은 저장소의 Git 제외 logs 폴더에만 있다. 비밀번호·개인키·토큰을 이 문서나 Git/설치 패키지에 포함하지 않는다.

## 확인 범위

현재 Windows PC와 로컬 WSL 한정 실기 검증이다. PC 재부팅/에이전트 제거는 실행하지 않았다. 자동 시작 설정은 Windows 서비스/레지스트리에서 확인했다. 외부 Windows/AIX/RHEL 및 실제 1,000대 부하 시험은 별도다. Windows agent의 전용 계정 변경·패치·보안 감사·08 자원 모니터링은 아직 지원하지 않으며 성공 항목에 포함하지 않았다. 백업은 설정·진단 자료로 전체 디스크 이미지/복구 기능이 아니다.


## 2026-10-15 Windows 계정/패치 조회 및 통합 OS 표시

05는 Windows 로컬 계정 6개(SID·그룹·활성 상태 등), 06은 설치 KB 5개(설치일·설명)를 현재 PC의 기존 1.1 에이전트로 실제 조회했다. Windows 계정 생성/삭제 및 패치 계획/적용은 SERVER에서 거부됨을 실기 확인했다. Linux 기능을 유지하며 Windows 혼합 대상 변경도 작업 접수 전에 전체 거부한다. CSV는 새 속성을 포함하고 표 정렬을 유지한다. 도메인 계정 및 미설치 Windows Update/전체 앱·드라이버 조회는 범위 밖이다.

Windows 명령 작업은 실제 이력에서 completed였으며 기존 CLIENT의 30~35초 고정 sleep이 대기 원인이었다. 새 CLIENT는 wait_for_task 플래그로 최대 15초 SERVER 대기를 요청하고 작업 등록 condition 알림에 즉시 깨어난다. SERVER 잠금을 대기 중 해제하고 기존 CLIENT 호환을 유지한다. 작업 이력 Details에 전달 상태를 표시한다. signed TLS 독립 바이너리 시험 및 큐 알림 동시성 검증 통과. 현재 PC의 UAC 설치가 취소되어 새 바이너리 서비스 교체는 미완료이며 실제 설치 서비스의 대기 시간 개선은 아직 검증하지 못했다. 갱신 파일 release/SM-Windows-Client-Setup.exe 준비.

제품 설명을 Windows·Linux·AIX 통합 관리로 정리하고 docs/platform-support.md에 기능별 구현/제약/실장비 검증 범위를 명시했다. AIX 계정/패치 전용 메뉴 및 자원/보안 전 기능을 새로 구현했다는 의미는 아니다. 실제 검증은 승인된 현재 Windows PC와 WSL에 한정한다. 자동화 일시정지와 사용자 results.csv 미추적 유지.

최종 검증: Windows 전체 526 passed / 29 skipped, 최종 상태 표시/지원 안내 관련 47 passed / 2 skipped, WSL 계정·패치·agent 관련 27 passed. 역할별 설치 ZIP 갱신 및 로컬 SERVER 재시작 적용 완료. UAC 취소로 현재 Windows 서비스 바이너리 갱신은 사용자 관리자 실행 필요.


## 2026-10-15 Windows 08 Resources 지원

Windows 기존 agent 명령 통로와 OpenSSH 경로에 고정 CIM 자원 조회를 연결했다. _Total CPU 사용률, OS 가시 물리 메모리(KiB→MiB), OS SystemDrive 논리 디스크, OS 현재 시각-LastBootUpTime을 수집한다. GUI는 Windows CPU %와 Linux/AIX Load를 구분하고 가동시간은 누적 시간·분·초로 표시한다. 누락·범위 초과·비유한 지표는 실패 처리한다. 데이터/표 구조는 기존 monitoring을 사용하여 장비록·예약·CSV·정렬·자동 조회를 유지한다. 정렬 시 메모리/디스크 막대와 호스트 대응도 함께 보존했다.

현재 PC는 기존 hostname 대신 -agent- 식별자 접미사를 가진 등록 이름으로 online이었다. 사용자의 장비 목록을 변경하지 않고 해당 유일한 등록 대상으로 실행해 Windows CPU·물리 메모리·시스템 드라이브·가동시간 및 작업 이력 반환을 실제 검증했다. 에이전트 설치/교체·권한 설정 변경은 수행하지 않았다. AIX/RHEL 실장비 시험 미실행, 자동화 일시정지 및 사용자 results.csv 미추적 유지.

검증: Windows 전체 556 passed / 29 skipped, WSL 자원 수집 관련 12 passed, 승인된 현재 Windows PC agent 실제 08 조회 PASS. 로컬 SERVER 적용 및 역할별 설치 ZIP 갱신 완료.
