"""
Main application entry point for the TinySA Ultra Spectrum Analyzer.

Initializes the PySide6 QApplication, sets high-DPI scaling, shows a splash
screen while the real work happens, and launches MainWindow.
"""

import os
import sys
import traceback

# High-DPI hints must be set before QApplication is constructed.
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

# Add the root project path to sys.path so `gui`, `styles` and `utils` resolve
# whether we are run from source or from a PyInstaller bundle.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402

from gui.splash_screen import TinySASplashScreen  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402


def main():
    """Application entry point with a splash screen and app icon."""
    app = QApplication(sys.argv)
    app.setApplicationName("TinySA Ultra Spectrum Analyzer Pro Suite")
    app.setOrganizationName("TinySA Community & Antigravity Labs")

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    splash = TinySASplashScreen(icon_path=icon_path)
    splash.show()

    # The splash used to advance through fixed time.sleep() calls totalling
    # ~1.6 s, which is a deliberately unresponsive window. Progress is now tied
    # to real construction work, and device probing happens on the acquisition
    # thread after the window is up.
    splash.set_progress(20, "Loading graphics subsystem...")
    app.processEvents()

    try:
        splash.set_progress(55, "Building spectrum and waterfall engine...")
        app.processEvents()

        window = MainWindow()
        if os.path.exists(icon_path):
            window.setWindowIcon(QIcon(icon_path))

        splash.set_progress(100, "Ready - detecting hardware...")
        app.processEvents()
    except Exception:
        splash.close()
        detail = traceback.format_exc()
        print(detail, file=sys.stderr)
        QMessageBox.critical(
            None,
            "TinySA Ultra Suite - Startup Failed",
            f"The application could not start:\n\n{detail}",
        )
        return 1

    window.show()
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
