# 패치 파일과 ISO로 설치 테스트

06 Patches에서 Connection map의 Linux CLIENT 선택을 사용합니다. 관리자는 다음 세 경로로 파일을 준비할 수 있습니다.

* **GUI 파일 선택**: Windows의 `.deb` / `.rpm`을 선택합니다. 파일은 Linux SERVER의 `/srv/sm-automation/shared/patch-<ID>`로 업로드된 후 선택됩니다.
* **SERVER 파일 선택**: Linux SERVER 폴더를 조회하고 패키지 파일을 여러 개 선택합니다. 폴더를 더블 클릭하면 이동합니다. 경로 입력 칸에는 여러 절대 경로를 `|`로 구분하여 직접 입력할 수도 있습니다.
* **ISO 패키지 검색**: Windows GUI 또는 Linux SERVER의 ISO를 고릅니다. GUI ISO는 SERVER로 먼저 업로드합니다. SERVER에서 읽기 전용으로 마운트하고 파일명으로 검색한 다음 DEB/RPM을 여러 개 선택합니다.

파일이 선택되면 패키지명 입력보다 우선합니다. 파일 경로를 비우면 기존 저장소 패키지명 방식으로 돌아갑니다.

## 계획과 적용

1. 대상 CLIENT와 선택 파일을 확인하고 **Preview patch plan**을 누릅니다. 계획 단계에서는 설치하지 않습니다.
2. 결과에서 의존성, 신규 설치/변경 내역, 파일 경로와 SHA256을 확인합니다.
3. **Apply reviewed plan**을 누르면 대상 설정 백업 후 설치합니다. 백업이 불완전하면 설치하지 않습니다. 기존 계획의 1시간 유효 기간과 대상 일치 검사를 유지합니다.
4. 계획 후 파일 내용·패키지 상태·의존성 계획이 바뀌면 적용을 거부합니다. 입력을 수정한 경우에도 계획을 다시 만들어야 합니다.

DEB 파일 모드는 저장소 목록과 메타데이터를 격리하여 선택 파일만 사용합니다. 의존 패키지는 CLIENT에 이미 설치되어 있거나 함께 선택해야 합니다. 신규 설치/업그레이드를 지원하며 하위 버전과 제거는 거부합니다. DEB 원본의 신뢰성은 관리자가 확인해야 하며 SHA256은 계획 때 검토한 파일 내용의 일치를 확인합니다.

RPM 파일 모드는 CLIENT의 RPM 서명 검증과 의존성 시험을 통과한 파일을 `rpm -U`로 적용합니다. 신뢰된 서명 키가 CLIENT에 준비되어 있어야 하며 저장소에서 의존성을 내려받지 않습니다. RPM 실제 장비 통합 검증은 아직 수행하지 않았습니다.

자동 재부팅은 하지 않습니다. 패키지의 설치 스크립트가 서비스를 재시작할 수 있으며, 설정 백업은 패키지 버전의 자동 롤백이 아닙니다.

## ISO 범위

마운트는 SERVER에서 `loop,ro,nodev,nosuid,noexec`로 수행하며 관리자만 사용할 수 있습니다. 파일 검색은 한 번에 최대1000개, 최대10초/10만 항목으로 제한합니다. 결과가 잘리면 검색어를 좁히세요. GUI 업로드에 인위적인 파일 용량 제한은 없으며 SERVER/CLIENT의 여유 디스크 공간이 필요합니다.

선택 파일의 계획/적용이 끝날 때까지 마운트를 유지하세요. 같은 ISO를 다시 선택하면 기존 마운트로 접근할 수 있으며 **ISO 마운트 해제**로 분리합니다. SERVER 재부팅 뒤에는 다시 마운트해야 합니다. 업로드 원본은 자동 삭제하지 않습니다.

Ubuntu live ISO에는 전체 저장소가 들어 있지 않을 수 있습니다. 필요한 패키지가 없으면 DEB/RPM과 의존 파일을 별도로 준비하세요. Windows ISO의 EXE/MSI/MSU/CAB/WIM/ESD는 검색·조회할 수 있지만 Windows 설치/패치 변경은 지원하지 않습니다. 특히 WIM/ESD는 OS 이미지이므로 Linux 패키지처럼 설치하지 않습니다. 기존 Windows/AIX 패치 조회 전용 정책을 유지합니다.

## 로컬 검증 및 실습 파일 (2026-10-16)

승인된 Ubuntu CLIENT `192.168.250.2`에서 GUI 전송 프로토콜로 파일 업로드, ISO 읽기 전용 마운트/검색, 시험용 패키지1.0 설치 및 ISO의2.0으로 업그레이드, 하위 버전 차단, 검토 후 SHA256이 변경된 파일의 적용 차단을 검증했습니다. 실제 적용마다 사전 백업을 완료했습니다. 시험 패키지는 CLIENT에서 제거했습니다.

SERVER 실습 경로: `/srv/sm-automation/shared/patch-lab-5dfff076`.

* `sm-automation-patch-fixture-1.0.deb`: 시험용 신규 설치 파일
* `gui-upload/fixture-2.0.deb`: GUI 전송 경로로 업로드한 업그레이드 파일
* `packages.iso`: 위2.0 패키지를 포함한 시험 ISO

Windows 실습 파일: `D:/WSL/VM-Setup/package-test/fixture-2.0.deb`. 시험 패키지는 `/usr/share/sm-automation-patch-fixture/version`에 버전 문자열만 설치하며 서비스나 OS 설정을 변경하지 않습니다. 실습 후 CLIENT에서 `sudo dpkg --purge sm-automation-patch-fixture`로 정리할 수 있습니다.

상세 시험 결과는 로컬 `D:/WSL/VM-Setup/patch-file-acceptance.json`에 있습니다.
