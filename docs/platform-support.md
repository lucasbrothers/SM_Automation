# Windows · Linux · AIX 통합 관리

CLIENT는 관리 대상 OS 장비, SERVER는 작업·예약·암호화 보관을 담당하는 Linux 중앙 서버, GUI는 Windows 관리 콘솔입니다. 중앙 SERVER의 OS와 관리 대상 OS는 별개입니다.

| 기능 | Windows CLIENT agent | Linux CLIENT SSH | AIX CLIENT SSH |
|---|---|---|---|
| 목록·장비록·CSV·작업 이력 | 지원 | 지원 | 지원 |
| TCP 연결·캐시 지도 | 지원 | 지원 | 지원 |
| CI 수집 | 지원 | 지원 | 지원 |
| 원격 명령 | PowerShell / SYSTEM | 셸 / root 전환 | 셸 / 지정 계정 |
| 파일 전송 | 지원, 현재 8 MiB | 지원 | 지원 |
| 설정 백업·비교 | agent 1.1 지원 | 지원 | 지원 |
| 05 계정 | 로컬 계정 조회만 | 조회·변경 | 계정·그룹·잠금·만료 조회 전용 |
| 06 패치 | 설치된 KB 조회만 | 조회·계획·적용, 배포판별 조건 | OS 수준·설치 파일셋·임시 수정 조회 전용 |
| 08 자원 | CPU·물리 메모리·시스템 디스크·가동시간 조회 | 지원 | 부하·메모리·루트 디스크·가동시간 조회 |
| Linux 보안 정책 | 전용 메뉴 미지원 | 지원 | 전용 메뉴 미지원 |

Windows 패치 목록은 Get-HotFix/CBS에 기록된 설치 KB입니다. 미설치 업데이트, 모든 앱·드라이버를 조사하는 목록은 아닙니다. 계정 암호나 해시는 수집하지 않습니다. Windows를 포함한 계정 변경/패치 계획·적용 요청은 전체 작업 접수 전에 거부합니다.

Windows 에이전트는 GUI에서 실행한 명령을 PowerShell로 해석합니다. Linux 셸 명령을 그대로 Windows에 보내면 실패할 수 있습니다. Windows 명령은 SYSTEM 권한으로 실행됩니다.

작업이 없을 때는 CLIENT가 SERVER 응답을 최대 15초 기다리고, 작업 등록 시 바로 응답합니다. 에이전트는 이후 짧은 간격으로 재접속합니다. 이전 설치 파일의 CLIENT는 30~35초 주기이므로 새 설치 파일로 갱신해야 합니다. 오프라인, 장시간 명령, 동시 작업 한도에 의한 대기는 별도입니다.

검증 범위: 승인된 현재 Windows PC와 로컬 WSL. AIX·RHEL 실장비 검증은 미실행이며 지원 경로 구현과 실장비 검증 완료는 구분합니다.


## AIX 05·06·08 조회

05: `lsuser -f`의 명시된 비밀이 아닌 속성만 수집합니다. UID·기본/보조 그룹·홈·셸·설명·잠금·만료를 표시합니다. Enabled는 account_locked의 반대값으로, 다른 로그인 제한까지 합산한 로그인 가능 판정이 아닙니다. Expires는 AIX 원본 형식(0=만료 없음)입니다. 계정 변경은 차단합니다.

06: `oslevel -s`, `lslpp -lc`, `emgr -l`을 사용합니다. 동일 파일셋이 /usr·/etc 저장소별로 보이면 Source로 구분합니다. 현재 설치 상태 조회이며 미설치 업데이트/APAR 누락 판정은 아닙니다. emgr 권한 오류는 부분 성공과 경고로 보존합니다. 설치·제거·commit·재부팅은 수행하지 않습니다. Windows/AIX 포함 변경 작업은 Linux 대상에도 실행하기 전에 전체 거부합니다.

08: `uptime`, `vmstat -v`, `df -Pk /`를 사용합니다. vmstat의 memory/free pages(4 KiB)를 MiB로 환산하며 사용량은 전체-무료(파일 캐시 포함)입니다. Linux available이나 프로세스 메모리 합계와 같지 않습니다. Load는 CPU 사용률이 아닙니다. SSH 로그인 계정에 각 명령 조회 권한이 필요하고 부족하면 오류를 그대로 보고합니다. GUI 자동 조회·장비록·예약·이력·정렬·CSV를 기존 경로로 이용합니다.

각 원격 명령은 60초/4 MiB로 제한하며 CLIENT에 Python이나 패키지를 설치하지 않습니다. 검증은 AIX 형식 고정 응답과 WSL에서 이루어졌으며 실제 AIX 7.x 장비 검증은 별도로 필요합니다.

IBM 명령 참고: [lsuser](https://www.ibm.com/docs/en/aix/7.2.0?topic=l-lsuser-command), [lslpp](https://www.ibm.com/docs/en/aix/7.2.0?topic=l-lslpp-command), [vmstat](https://www.ibm.com/docs/en/aix/7.2.0?topic=v-vmstat-command).


## Windows 08 Resources

기존 Windows 에이전트의 명령 통로로 고정된 읽기 전용 PowerShell/CIM 조회를 수행합니다. 재설치·추가 패키지·성능 카운터 설정 변경은 필요 없습니다. Windows OpenSSH 경로도 같은 수집기를 사용합니다.

CPU는 Win32_PerfFormattedData_PerfOS_Processor의 _Total PercentProcessorTime이며 Linux/AIX의 1·5·15분 Load와 구분합니다. 물리 메모리는 Win32_OperatingSystem의 TotalVisibleMemorySize-FreePhysicalMemory(KiB→MiB)입니다. 시스템 드라이브는 OS SystemDrive를 사용하므로 C:로 고정하지 않습니다. 가동시간은 OS 시각-LastBootUpTime이며 누적 시간·분·초로 표시합니다. 누락/비정상 지표는 0으로 채우지 않고 실패로 보고합니다.

표 정렬·CSV·장비록·SERVER 예약 및 GUI 120초 자동 조회는 기존 monitoring 경로를 사용합니다. 정렬 활성 상태에서 메모리/디스크 막대가 다른 호스트로 붙는 문제도 방지했습니다. 실행 중인 Windows PC의 에이전트를 통해 자원 조회와 암호화 작업 이력 반환을 실제 검증했습니다.

Microsoft 참고: [OS 물리 메모리·부팅 시각](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-operatingsystem), [WMI 성능 조회](https://learn.microsoft.com/en-us/windows/win32/wmisdk/wmi-tasks--performance-monitoring).
