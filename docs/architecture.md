# Linux 메인 서버 / Windows GUI 아키텍처

기준일: 2026-10-08. 이번 사용자 결정이 이전 설계 및 인계 문서보다 우선한다.

## 역할

| 구성요소 | 역할 | 하지 않는 일 |
| --- | --- | --- |
| Windows GUI | 목록 편집, 대상 선택, 작업 요청, 마인드맵 및 결과 표시 | 대상 SSH 접속, 수집·백업 실행, 운영 데이터 파일 저장 |
| Linux 메인 서버 | 모든 SSH 작업, 작업 큐, 수집, 백업, 암호화, 이력 저장 | 웹 UI 제공 |
| 관리 대상 | Linux/RHEL, AIX, Windows OpenSSH | GUI나 별도 관리 에이전트 설치 |

Windows와 Linux는 **전용 TLS/TCP 7443 포트**로 통신한다. SSH 터널과 HTTP를 사용하지 않는다.
Linux와 관리 대상의 통신만 SSH(기본 22)다. Windows 대상도 OpenSSH를 사용한다.

## 구성

- `src/desktop`: PySide6 네이티브 GUI, 인증서 검증 TLS 클라이언트
- `src/shared/protocol.py`: 4바이트 길이 + UTF-8 JSON 메시지, 최대 16 MiB
- `src/server`: TLS 서버, 서버 목록, 최대 2개 동시 작업, 작업당 SSH 병렬 실행
- `src/storage`: Fernet 인증 암호화 및 원자적 파일 교체
- `src/monitoring/connections.py`: OS별 netstat 호출 및 ESTABLISHED 연결 파싱
- `src/backup`: OS별 파일 및 명령 스냅샷 수집
- `src/engine`: Linux 메인 서버에서 대상 SSH 수행

## 요청 흐름

1. Windows가 Linux 인증서를 검증하고 접근 토큰과 요청을 보낸다.
2. Linux는 서버 목록에서 대상을 확인하고 작업 ID를 반환한다.
3. Linux의 작업 큐가 SSH로 수집하며 서버별 결과를 암호화 저장한다.
4. GUI가 약 3초마다 진행 상황을 읽고, 완료된 결과를 메모리에서 표시한다.
5. GUI를 닫아도 Linux 작업은 계속된다. 재접속하여 Activity에서 결과를 다시 볼 수 있다.

전용 포트는 관리망에서 GUI 호스트만 접근하도록 배치한다. TLS 인증서/호스트 검증을
끄는 옵션은 없다. 접근 토큰은 현재 운영자 공통 토큰이며 개별 사용자/RBAC는 후속 범위다.
작업 실행 API는 미리 정한 종류만 허용하며 임의 쉘 명령 API를 제공하지 않는다.

## 저장 모델

PostgreSQL 코드·스키마·의존성을 제거했다. 기존 DB 데이터 자동 변환은 구현하지 않았다.

- DATA: `inventory.json.enc`, `jobs/<id>.json.enc`
- BACKUP: `<날짜>/<hostname>/<run-id>/configuration_files.tar.enc`, 명령 결과와 메타데이터
- 키: Linux 서비스 계정의 `~/.config/sm-automation/master.key`
- TLS 및 API 토큰: 별도 secrets 디렉터리. Windows에는 CA 공개 인증서와 접근 토큰만 전달

작업/파일 내용은 암호화하며, 날짜·hostname·파일명 및 Fernet 생성 시각은 숨기지 않는다.
서버 설정과 공개 보안 정책 파일은 비밀정보를 넣지 않는 JSON이다.
Windows GUI는 결과와 토큰을 메모리에서만 사용하고 저장 기능은 제공하지 않는다.
Linux 대상 SSH 비밀번호를 쓸 경우 서비스 환경변수 `SM_AUTOMATION_SSH_PASSWORD`로 제공한다.

## 재시작 및 범위

서버가 재시작하면 마지막 100개 작업을 읽고 미완료 작업을 interrupted로 기록한다.
자동 재실행하지 않는다. 부분 백업은 남으므로 확인 후 새 작업으로 재시도한다.
작업 취소·스케줄러·보존기간 정리·사용자별 권한·키 순환 UI는 후속 구현 범위다.

연결 맵은 netstat의 특정 시점 관측치이며 패킷 분석/연결 방향 판정 기능이 아니다.
서버당 5,000개 연결을 반환하고 초과는 표시한다. 맵은 서버당 25개 peer까지 표시하며
검색과 하단 표로 나머지를 확인한다. IPv4/IPv6 실환경 파싱은 다음 PC에서 확인한다.

기존 보안 정책 평가·설정 변경 엔진은 유지하되 이번 GUI는 읽기 전용 보안 감사만 연결한다.
Linux 계정 조회/생성/정보 변경/비밀번호 잠금/삭제 GUI와 변경 전 백업을 구현했다. Debian/Ubuntu 패치 조회·버전 지정 계획·백업 후 적용 GUI도 구현했다. 다른 OS 패치, 자동 복원, 전체 정책 적용 GUI는 후속 범위다.
