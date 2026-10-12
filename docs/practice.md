# 로컬 WSL 실습

프로젝트 루트의 `실습-GUI.cmd`를 더블클릭한다. 기존 Windows `.venv`와 구성된 WSL Ubuntu가 필요하다. 현재 WSL 주소와 인증 자료는 실행 도구가 읽으므로 직접 입력하지 않는다.

1. Connection map에서 `wsl-ubuntu`를 선택하고 연결을 수집해 표와 마인드맵을 확인한다.
2. Resources에서 자원을 조회하고 자동 갱신을 확인한다.
3. Accounts에서 계정 목록을 조회한다.
4. Backups에서 선택한 로컬 대상의 백업을 실행하고 완료 후 설정 파일 목록과 명령 결과를 미리 본다.
5. Activity에서 작업 결과를 확인한다. 연결 해제 후 재접속하면 저장된 이력을 다시 조회할 수 있다.
6. Patches에서 업데이트를 조회하고 버전 선택 후 계획을 검토한다. 적용은 실제 패키지를 변경한다.
7. Schedules에서 읽기 수집/백업 예약을 만들어 보고, 필요 없는 예약은 일시정지 또는 삭제한다.

계정 생성·변경·삭제와 SSH 정책 적용은 실제 WSL을 변경하므로 해당 실습이 필요할 때 실행한다. 계정 삭제는 홈을 보존한다. 테스트 대상은 로컬 WSL 한 대로 제한한다.

DATA와 BACKUP은 WSL `/opt/SM_Automation` 아래에 암호화 저장된다. 키를 삭제하거나 새로 생성하지 않는다. 비밀번호·키·토큰을 안내서나 Git에 복사하지 않는다.

화면만 미리 보려면 PowerShell에서 `./scripts/start_desktop.ps1 -Demo`를 실행한다. 데모 데이터는 실제 서버 결과가 아니다.


## 추가 실습

- Accounts의 `1. Target servers` → `2. Account details` → `3. Review and run` 순서로 진행한다. 탭 아래 분할선을 드래그해 목록 높이를 조절한다.
- 상단 `Zoom`을 60–140%로 조절한다. 작은 창에서는 작업 영역을 스크롤한다.
- 상단 `Save query results`로 현재 화면에 로드된 조회 결과를 CSV 저장한다. 결과 팝업의 `Save results CSV`도 사용할 수 있다. 엑셀에서 CSV를 열 수 있다.
- `09 Commands / Files`에서 선택 CLIENT를 확인하고 `hostname` 같은 명령을 실행한다. Activity에서 작업을 더블클릭해 stdout/stderr/exit_code를 조회·저장한다.
- 파일 업로드는 CLIENT→SERVER, 다운로드는 SERVER→CLIENT다. SERVER는 Linux 메인 서버이고 GUI콘솔은 Windows다. 양쪽의 절대 경로를 입력하고 CLIENT 한 대를 선택한다. 부모 디렉터리는 미리 존재해야 하며 대상 파일은 새 이름이어야 한다. 파일은 8 MiB 이하 일반 파일로 제한된다.

- 명령 실행 결과는 Commands / Files의 대상별 결과 표에 표시된다. 행을 선택하면 상세 출력이 보이며 Download detailed results CSV로 저장한다.
- Connection map에서 CLIENT 한 대를 선택한 뒤 왼쪽 CLIENT login settings를 연다. SSH 계정·포트 및 비밀번호 인증을 설정해 저장한다. 기존 비밀번호가 있으면 빈 칸으로 저장해 유지할 수 있다. 비밀번호 인증을 해제하면 저장 비밀번호를 지우고 기존 SSH 키/프로필을 사용한다. 실제 실행 권한은 해당 CLIENT 계정과 기존 프로필을 따른다.

- 실습 실행 시 SERVER IP·Port·ID·Password를 입력한다. 로컬 WSL 주소와 기본 admin ID는 자동으로 채운다. 비밀번호는 대화에서 지정한 값을 직접 입력한다. 인증서 파일 선택은 필요 없다. 왼쪽 SERVER GUI account에서 GUI 전용 계정을 추가하거나 비밀번호를 변경할 수 있다. CLIENT SSH 계정과는 별개다.

- Overview의 Download clients Excel / Import CSV / Excel로 .xlsx 목록을 저장·가져온다. 열은 hostname, ip, os, profile이다. 가져오기는 기존 목록을 교체한다. Manage inventory에서 개별 입력도 가능하다.
- 최초 키 배포는 CLIENT login settings에 기존 계정의 유효한 비밀번호를 설정한 뒤 CLIENT를 선택하고 Deploy SERVER public key를 실행한다. 결과는 Activity에서 확인한다. 성공 후 비밀번호 인증을 해제하면 키 인증을 사용한다. 공개키만 CLIENT로 전달하며 개인키는 SERVER에 남는다.
