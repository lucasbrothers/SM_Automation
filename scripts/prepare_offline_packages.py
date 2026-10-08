"""Prepare wheels on a machine matching the destination OS and Python."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["server", "gui"], required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    requirement = root / ("requirements-runtime.txt" if args.role == "server" else "requirements-gui.txt")
    destination = args.destination or root / "wheelhouse" / args.role
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--dest", str(destination),
                    "-r", str(requirement)], check=True)


if __name__ == "__main__":
    main()
