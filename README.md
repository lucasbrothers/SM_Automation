# SM_Automation

Enterprise System Management Automation

## Development Setup

- [다른 PC에서 개발 이어가기](docs/pc-handoff.md)
- [설정 관리 사용법](docs/configuration.md)
- [SSH 및 보안 정책 사용법](docs/ssh-connection-options.md)
- [보안 정책 기준표](docs/security-policy.md)
- [보안 정책 권고 아키텍처](docs/security-architecture.md)
- [PostgreSQL CMDB 운영](docs/cmdb-postgresql.md)
- [원격 PostgreSQL 운영 서버 구성](docs/postgresql-remote-setup.md)
- [Windows 오프라인 배포 및 설치](docs/offline-deployment.md)
- Python 3.14.7, dependencies pinned in `requirements-dev.txt`.

운영 패키지는 Windows 컨트롤러 배포를 기준으로 설계하며, Linux/RHEL과 AIX는
SSH 원격 어댑터, Windows 대상은 향후 WinRM/PowerShell 어댑터로 관리합니다.

## Design Context

- [중앙 OS 관리 시스템 설계 — 프로젝트 인계](docs/central-os-design-context.md)
- [기존 대화 기록 (78개 항목)](docs/imported-central-os-conversation.md)

## Project Goal

Centralized management platform for Linux, AIX and Windows.

Features

- Security Management
- Account Management
- Patch Management
- Backup
- Monitoring
- Grafana
- Prometheus
- REST API


SM_Automation
│
├── src
│
├── config
│
├── tests
│
├── logs
│
├── reports
│
└── docs
