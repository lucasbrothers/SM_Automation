"""Launch the native console connected to this user's local WSL lab."""
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from desktop.client import ConnectionSettings, ServerClient
from desktop.main import Console, STYLE, ConnectDialog
from desktop.theme import light_palette


def main():
    def read(path):
        return subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "cat", path], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    address = subprocess.check_output(["wsl", "-d", "Ubuntu", "-u", "root", "--", "hostname", "-I"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).split()[0]
    with tempfile.TemporaryDirectory(prefix="sm-wsl-gui-") as directory:
        ca = Path(directory) / "ca.crt"; ca.write_bytes(read("/root/.config/sm-automation/ca.crt"))
        app = QApplication(sys.argv)
        for name in ("segoeui.ttf", "segoeuib.ttf", "malgun.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
        app.setFont(QFont("Segoe UI", 10)); app.setStyle("Fusion"); app.setPalette(light_palette()); app.setStyleSheet(STYLE)
        window = Console()
        dialog = ConnectDialog(window); dialog.host.setText(address); dialog.login_id.setText("admin")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return 0
        window.show()
        window.connect_to(ServerClient(dialog.settings()))
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
