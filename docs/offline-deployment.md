# 오프라인 설치 패키지

Linux 서버와 Windows GUI의 패키지를 **각 대상과 같은 OS/CPU/Python 환경**에서 별도로 준비한다.
이전 Windows 컨트롤러용 wheel 모음은 Linux 서버에 사용할 수 없다.
PostgreSQL은 설치하지 않는다. Python 런타임 설치 파일은 별도 반입한다.

## Linux 메인 서버용 (온라인 Linux 준비 PC)

```sh
python3.14 scripts/prepare_offline_packages.py --role server
```

wheelhouse/server 폴더와 프로젝트를 고객사 Linux로 옮긴 뒤:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse/server -r requirements-runtime.txt
```

## Windows GUI용 (온라인 Windows 준비 PC)

```powershell
py -3.14 scripts/prepare_offline_packages.py --role gui
```

wheelhouse/gui 폴더와 프로젝트를 Windows GUI 서버로 옮긴 뒤:

```powershell
py -3.14 -m venv .venv-gui
.venv-gui/Scripts/python.exe -m pip install --no-index --find-links wheelhouse/gui -r requirements-gui.txt
```

설치 후 [deployment.md](deployment.md)의 Linux 키/인증서 준비 및 GUI 연결 순서를 따른다.
PySide6 wheel에는 네이티브 Qt 구성요소가 포함되며 용량이 크므로 반입 용량을 확보한다.
Linux 패키지의 최소 glibc/OpenSSL/Python 호환성은 실제 준비 PC에서 확인해야 한다.
Windows wheel을 Linux에 설치하지 않는다. wheelhouse는 Git에 넣지 않고 별도 배포한다.
현재 저장소의 src/sw/python-wheels는 과거 Windows 개발용 파일이며 새 배포 기준이 아니다.
