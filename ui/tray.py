"""
tray.py — System tray icon and menu for PostureGuard.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from core.engine import State

if TYPE_CHECKING:
    from core.engine import PostureEngine
    from audio.player import AudioPlayer


# --------------------------------------------------------------------------
# Icon generator (draws a colored circle — no image files needed)
# --------------------------------------------------------------------------

def _make_icon(color: str, size: int = 32) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    margin = 2
    p.drawEllipse(margin, margin, size - 2*margin, size - 2*margin)
    p.end()
    return QIcon(pix)


_ICONS: dict = {}  # populated lazily after QApplication is created

def _ensure_icons():
    if not _ICONS:
        _ICONS[State.IDLE]        = _make_icon("#555555")
        _ICONS[State.TRACKING]    = _make_icon("#2ecc71")
        _ICONS[State.GRACE]       = _make_icon("#f39c12")
        _ICONS[State.BAD_POSTURE] = _make_icon("#e74c3c")
        _ICONS[State.AWAY]        = _make_icon("#3498db")
        _ICONS[State.PAUSED]      = _make_icon("#95a5a6")

_TOOLTIPS = {
    State.IDLE:        "PostureGuard — остановлен",
    State.TRACKING:    "PostureGuard — осанка ✅",
    State.GRACE:       "PostureGuard — осанка ⚠️",
    State.BAD_POSTURE: "PostureGuard — ПЛОХАЯ ОСАНКА 🔴",
    State.AWAY:        "PostureGuard — не в кадре 💤",
    State.PAUSED:      "PostureGuard — пауза ⏸",
}


# --------------------------------------------------------------------------
# Signal bridge (cross-thread safe)
# --------------------------------------------------------------------------

class _Bridge(QObject):
    state_changed  = pyqtSignal(object)   # State
    alarm_started  = pyqtSignal()
    alarm_stopped  = pyqtSignal()


class TrayApp:
    """
    Owns the QSystemTrayIcon and coordinates the engine + audio player.
    Must be created on the main Qt thread.
    """

    def __init__(self, engine: "PostureEngine", audio: "AudioPlayer"):
        self.engine = engine
        self.audio  = audio
        self._bridge = _Bridge()

        # Connect bridge signals (always on main thread)
        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.alarm_started.connect(self._on_alarm_started)
        self._bridge.alarm_stopped.connect(self._on_alarm_stopped)

        # Wire engine callbacks (may fire from any thread)
        engine.on_state_change = lambda s: self._bridge.state_changed.emit(s)
        engine.on_alarm_start  = lambda:   self._bridge.alarm_started.emit()
        engine.on_alarm_stop   = lambda:   self._bridge.alarm_stopped.emit()

        # Build tray
        _ensure_icons()
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_ICONS[State.IDLE])
        self._tray.setToolTip("PostureGuard")
        self._tray.activated.connect(self._on_tray_activated)
        self._main_window = None  # set by main.py after MainWindow is created

        self._build_menu()
        self._tray.show()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background:#121224; color:#ddd; border:1px solid #2a2a4a; }"
            "QMenu::item:selected { background:#1e3a5f; }"
            "QMenu::separator { height:1px; background:#2a2a4a; margin:4px 0; }"
        )

        # Open main window
        open_action = QAction("🖥  Открыть окно", menu)
        open_action.triggered.connect(self._cmd_open_window)
        menu.addAction(open_action)
        menu.addSeparator()

        # Status header (non-clickable)
        self._status_action = QAction("PostureGuard", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        # Start / Stop / Pause
        self._start_action = QAction("▶  Начать отслеживание", menu)
        self._start_action.triggered.connect(self._cmd_start)
        menu.addAction(self._start_action)

        self._pause_action = QAction("⏸  Пауза", menu)
        self._pause_action.triggered.connect(self._cmd_pause)
        self._pause_action.setEnabled(False)
        menu.addAction(self._pause_action)

        self._stop_action = QAction("⏹  Остановить", menu)
        self._stop_action.triggered.connect(self._cmd_stop)
        self._stop_action.setEnabled(False)
        menu.addAction(self._stop_action)

        menu.addSeparator()

        cal_action = QAction("📷  Калибровка", menu)
        cal_action.triggered.connect(self._cmd_calibrate)
        menu.addAction(cal_action)

        settings_action = QAction("⚙️  Настройки", menu)
        settings_action.triggered.connect(self._cmd_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("✖  Выход", menu)
        quit_action.triggered.connect(self._cmd_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

    # ------------------------------------------------------------------
    # Tray commands
    # ------------------------------------------------------------------

    def _cmd_open_window(self):
        if self._main_window:
            self._main_window.show()
            self._main_window.raise_()
            self._main_window.activateWindow()

    def _cmd_start(self):
        if self.engine.state == State.PAUSED:
            self.engine.resume()
        else:
            self.engine.start()
        self._start_action.setEnabled(False)
        self._pause_action.setEnabled(True)
        self._stop_action.setEnabled(True)

    def _cmd_pause(self):
        if self.engine.state == State.PAUSED:
            self.engine.resume()
            self._pause_action.setText("⏸  Пауза")
        else:
            self.engine.pause()
            self._pause_action.setText("▶  Продолжить")

    def _cmd_stop(self):
        self.engine.stop()
        self._start_action.setEnabled(True)
        self._pause_action.setEnabled(False)
        self._pause_action.setText("⏸  Пауза")
        self._stop_action.setEnabled(False)

    def _cmd_calibrate(self):
        from ui.calibration_window import CalibrationWindow
        dlg = CalibrationWindow(self.engine)
        dlg.exec()

    def _cmd_settings(self):
        from ui.settings import SettingsWindow
        dlg = SettingsWindow(on_config_changed=self._on_config_changed)
        dlg.exec()

    def _cmd_quit(self):
        self.engine.stop()
        self.audio.cleanup()
        QApplication.quit()

    def _on_config_changed(self, cfg: dict):
        self.engine.reload_config(cfg)
        # Update audio sound path
        if cfg.get("use_default_sound", True):
            self.audio.set_sound(None)
        else:
            self.audio.set_sound(cfg.get("sound_file"))

    # ------------------------------------------------------------------
    # Engine event handlers (main thread via signals)
    # ------------------------------------------------------------------

    def _on_state_changed(self, state: State):
        self._tray.setIcon(_ICONS.get(state, _ICONS[State.IDLE]))
        self._tray.setToolTip(_TOOLTIPS.get(state, "PostureGuard"))
        self._status_action.setText(_TOOLTIPS.get(state, "PostureGuard"))

    def _on_alarm_started(self):
        from core.engine import State
        if self.engine.state == State.PAUSED:
            return
        self.audio.play()
        self._tray.showMessage(
            "PostureGuard",
            "⚠️  Исправьте осанку! Выпрямите спину и шею.",
            QSystemTrayIcon.MessageIcon.Warning,
            3000,
        )

    def _on_alarm_stopped(self):
        self.audio.stop()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._cmd_open_window()
