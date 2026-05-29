"""
main.py — PostureGuard entry point.
Works both as a Python script and as a PyInstaller EXE.
"""
import os
import sys

# Resource path helper — works in both dev and PyInstaller one-file EXE
def resource_path(relative: str) -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

# Config lives next to the EXE / script (user-writable, NOT inside _MEIPASS)
def user_data_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

os.environ['POSTURE_GUARD_DATA_DIR'] = user_data_dir()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Generate alert sound if missing
# ---------------------------------------------------------------------------
ALERT_PATH = os.path.join(user_data_dir(), "assets", "alert.wav")
if not os.path.isfile(ALERT_PATH):
    bundled = resource_path(os.path.join("assets", "alert.wav"))
    if os.path.isfile(bundled):
        import shutil
        os.makedirs(os.path.dirname(ALERT_PATH), exist_ok=True)
        shutil.copy2(bundled, ALERT_PATH)
    else:
        from generate_alert import generate_buzzer
        generate_buzzer(ALERT_PATH)

# ---------------------------------------------------------------------------
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QPixmap, QPainter


def _make_app_icon() -> QIcon:
    """Build app icon from the ICO (preferred on Windows) or SVG meditation figure."""
    # .ico contains 16/32/48/64/128/256px — Windows uses correct size automatically
    ico_path = resource_path(os.path.join("assets", "app_icon.ico"))
    if os.path.isfile(ico_path):
        return QIcon(ico_path)
    svg_path = resource_path(os.path.join("assets", "app_icon.svg"))
    if os.path.isfile(svg_path):
        return QIcon(svg_path)
    # Fallback: render inline SVG
    svg_data = b"""<svg width="256" height="256" viewBox="0 0 256 256" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="256" height="256" rx="56" fill="#1e293b"/>
  <g transform="translate(32,32) scale(8)">
    <path fill="#3b82f6" d="M12 8C13.1046 8 14 7.10457 14 6C14 4.89543 13.1046 4 12 4C10.8954 4 10 4.89543 10 6C10 7.10457 10.8954 8 12 8Z"/>
    <path fill="#3b82f6" d="M21 16V14C18.76 14 16.84 13.04 15.4 11.32L14.06 9.72C13.874 9.49447 13.6403 9.31295 13.3757 9.18846C13.1112 9.06397 12.8224 8.99961 12.53 9H11.48C10.89 9 10.33 9.26 9.95 9.72L8.61 11.32C7.16 13.04 5.24 14 3 14V16C5.77 16 8.19 14.83 10 12.75V15L6.12 16.55C5.45 16.82 5 17.48 5 18.21C5 19.2 5.8 20 6.79 20H9V19.5C9 18.837 9.26339 18.2011 9.73223 17.7322C10.2011 17.2634 10.837 17 11.5 17H14.5C14.78 17 15 17.22 15 17.5C15 17.78 14.78 18 14.5 18H11.5C10.67 18 10 18.67 10 19.5V20H17.21C18.2 20 19 19.2 19 18.21C19 17.48 18.55 16.82 17.88 16.55L14 15V12.75C15.81 14.83 18.23 16 21 16Z"/>
  </g>
</svg>"""
    from PyQt6.QtCore import QByteArray
    renderer = QSvgRenderer(QByteArray(svg_data))
    pix = QPixmap(256, 256)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from core.calibration import load_calibration, load_config
from core.engine import PostureEngine
from audio.player import AudioPlayer
from ui.tray import TrayApp
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("PostureGuard")
    app_icon = _make_app_icon()
    app.setWindowIcon(app_icon)

    cfg = load_config()

    audio = AudioPlayer()
    sound_file = cfg.get("sound_file") if not cfg.get("use_default_sound", True) else None
    audio.set_sound(sound_file)
    audio.set_volume(cfg.get("volume", 0.8))

    engine = PostureEngine(config=cfg)
    tray   = TrayApp(engine=engine, audio=audio)

    cal = load_calibration()
    if cal is None:
        from ui.calibration_window import CalibrationWindow
        engine.start()
        dlg = CalibrationWindow(engine)
        dlg.exec()
    else:
        engine.set_calibration(cal)
        engine.start()

    window = MainWindow(engine=engine, audio=audio, tray=tray)
    tray._main_window = window
    tray._tray.activated.connect(
        lambda reason: window.show() or window.raise_()
        if reason.value == 2 else None
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
