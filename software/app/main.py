"""Phase 1 application entry point."""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("滤光片疵病检测软件")
    app.setApplicationVersion("1.0.0")
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        def check():
            if not window.isVisible():
                app.exit(1)
                return
            if "--screenshot" in sys.argv:
                from pathlib import Path
                dest = Path(sys.argv[sys.argv.index("--screenshot") + 1])
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(dest)):
                    app.exit(2)
                    return
            app.exit(0)
        QTimer.singleShot(800, check)
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
