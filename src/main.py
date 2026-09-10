"""
SM_Automation Entry Point
"""

from pathlib import Path


def main() -> None:
    """
    Main Function
    """
    project_root = Path(__file__).resolve().parent.parent

    print("=" * 50)
    print("SM_Automation")
    print("=" * 50)
    print(f"Project Root : {project_root}")
    print("Application Started.")
    print("=" * 50)


if __name__ == "__main__":
    main()