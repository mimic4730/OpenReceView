# main.py
"""
OpenReceView のエントリポイント。

- src/ を import パスに追加
- PySide6 の QApplication を立ち上げて MainWindow を表示
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# ──────────────────────────────────────────────
# src ディレクトリを import パスに追加
# ──────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from openreceview.gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())