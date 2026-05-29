"""
calibration_window.py — camera preview with MediaPipe skeleton overlay
and a "Fix Pose" button. Fully bilingual (ru/en).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import cv2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QFont
from PyQt6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QFrame,
)

if TYPE_CHECKING:
    from core.engine import PostureEngine

C_BG      = "#202124"
C_SURFACE = "#292a2d"
C_BORDER  = "#3c4043"
C_HOVER   = "#4d5156"
C_MUTED   = "#5f6368"
C_TEXT    = "#e8eaed"
C_SUBTEXT = "#9ca3af"
C_BLUE    = "#8ab4f8"
C_GREEN   = "#4ade80"
C_GREEN_B = "#22c55e"
C_RED     = "#ef4444"
C_YELLOW  = "#fbbf24"

_CAL_TR = {
    "title":        {"ru": "Калибровка осанки",            "en": "Posture Calibration"},
    "win_title":    {"ru": "Калибровка осанки — PostureGuard", "en": "Posture Calibration — PostureGuard"},
    "instr_title":  {"ru": "<b>Инструкция:</b>",           "en": "<b>Instructions:</b>"},
    "instr_body":   {
        "ru": ("Сядьте прямо, смотрите в камеру.<br>"
               "Камера должна быть на уровне глаз, плечи в кадре.<br>"
               "Когда поза идеальная — нажмите «Зафиксировать позу»."),
        "en": ("Sit up straight and look at the camera.<br>"
               "The camera should be at eye level with both shoulders visible.<br>"
               "When your posture is correct — press «Fix Pose»."),
    },
    "guide":        {
        "ru": "Камера на уровне глаз   |   Видно оба плеча   |   Хорошее освещение",
        "en": "Camera at eye level   |   Both shoulders visible   |   Good lighting",
    },
    "waiting":      {"ru": "Ожидание данных от камеры…",      "en": "Waiting for camera data…"},
    "no_signal":    {"ru": "Нет сигнала от камеры…",          "en": "No camera signal…"},
    "no_face":      {"ru": "Лицо не обнаружено — проверьте камеру и освещение",
                     "en": "Face not detected — check camera and lighting"},
    "no_shoulders": {"ru": "Плечи не видны — отодвиньтесь немного от камеры",
                     "en": "Shoulders not visible — move back a little"},
    "countdown":    {"ru": "Фиксирую позу через {n} сек…",   "en": "Saving pose in {n} sec…"},
    "ready":        {"ru": "Поза обнаружена. Нажмите «Зафиксировать позу»",
                     "en": "Pose detected. Press «Fix Pose»"},
    "no_pose":      {"ru": "Поза не обнаружена — убедитесь что лицо и плечи видны",
                     "en": "Pose not detected — make sure face and shoulders are visible"},
    "saved":        {"ru": "Поза сохранена!",                 "en": "Pose saved!"},
    "failed":       {"ru": "Не удалось получить данные. Попробуйте ещё раз.",
                     "en": "Could not capture data. Please try again."},
    "fix_btn":      {"ru": "Зафиксировать позу",              "en": "Fix Pose"},
    "recal_btn":    {"ru": "Перекалибровать",                 "en": "Recalibrate"},
    "close_btn":    {"ru": "Закрыть",                         "en": "Close"},
    "finish_btn":   {"ru": "Завершить",                        "en": "Finish"},
}


def _ct(key: str, **kwargs) -> str:
    """Translate calibration string using current app language."""
    try:
        from ui.main_window import _LANG
        lang = _LANG
    except Exception:
        lang = "en"
    d = _CAL_TR.get(key, {})
    text = d.get(lang, d.get("ru", key))
    if kwargs:
        text = text.format(**kwargs)
    return text


class CalibrationWindow(QDialog):
    def __init__(self, engine: "PostureEngine", parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle(_ct("win_title"))
        self.setMinimumSize(700, 580)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {C_BG};
                color: {C_TEXT};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 13px;
            }}
            QLabel {{ background: transparent; }}
            QPushButton {{
                border-radius: 6px; font-size: 13px;
                padding: 0 20px; min-height: 40px;
            }}
            QScrollBar:vertical {{
                background: {C_SURFACE}; width: 6px; border-radius: 3px;
            }}
        """)
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_frame)
        self._timer.start(33)  # ~30 fps

        self._countdown       = 0
        self._countdown_start = 0.0

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 16)

        title = QLabel(_ct("title"))
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C_TEXT};")
        layout.addWidget(title)

        instr_card = QFrame()
        instr_card.setStyleSheet(f"background:{C_SURFACE}; border-radius:8px;")
        instr_layout = QVBoxLayout(instr_card)
        instr_layout.setContentsMargins(14, 10, 14, 10)
        instr_layout.setSpacing(4)

        instr = QLabel(
            _ct("instr_title") + " " + _ct("instr_body")
        )
        instr.setWordWrap(True)
        instr.setTextFormat(Qt.TextFormat.RichText)
        instr.setStyleSheet(f"color:{C_TEXT}; font-size:13px;")
        instr_layout.addWidget(instr)

        guide = QLabel(_ct("guide"))
        guide.setAlignment(Qt.AlignmentFlag.AlignCenter)
        guide.setStyleSheet(f"color:{C_SUBTEXT}; font-size:11px; margin-top:4px;")
        instr_layout.addWidget(guide)
        layout.addWidget(instr_card)

        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(640, 400)
        self._video_label.setStyleSheet(
            f"background:#000000; border:1px solid {C_BORDER}; border-radius:10px;"
        )
        self._video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._video_label)

        self._status_label = QLabel(_ct("waiting"))
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(f"color:{C_SUBTEXT}; font-size:12px;")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._fix_btn = QPushButton(_ct("fix_btn"))
        self._fix_btn.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:#202124;"
            f"border-radius:6px;font-size:14px;font-weight:bold;}}"
            f"QPushButton:hover{{background:#a8c8ff;}}"
            f"QPushButton:disabled{{background:{C_BORDER};color:{C_MUTED};}}"
        )
        self._fix_btn.clicked.connect(self._on_fix_clicked)
        btn_row.addWidget(self._fix_btn)

        self._close_btn = QPushButton(_ct("close_btn"))
        self._close_btn.setStyleSheet(
            f"QPushButton{{background:{C_SURFACE};color:{C_SUBTEXT};"
            f"border:1px solid {C_BORDER};}}"
            f"QPushButton:hover{{background:{C_BORDER};color:{C_TEXT};}}"
        )
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)

        layout.addLayout(btn_row)

    def _refresh_frame(self):
        frame = self.engine.latest_frame
        if frame is None or frame.overlay_image is None:
            self._set_status(_ct("no_signal"), "warning")
            return

        if not frame.face_visible:
            self._set_status(_ct("no_face"), "warning")
        elif not frame.shoulders_visible:
            self._set_status(_ct("no_shoulders"), "warning")
        else:
            if self._countdown > 0:
                elapsed   = time.time() - self._countdown_start
                remaining = max(0, self._countdown - int(elapsed))
                if remaining == 0:
                    self._do_calibrate()
                else:
                    self._set_status(_ct("countdown", n=remaining), "ok")
            else:
                self._set_status(_ct("ready"), "ok")

        img_bgr = frame.overlay_image
        h, w = img_bgr.shape[:2]
        rgb   = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        q_img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img).scaled(
            self._video_label.width(), self._video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(pixmap)

    def _set_status(self, text: str, level: str = "ok"):
        color = {"ok": C_GREEN, "warning": C_YELLOW, "error": C_RED}.get(level, C_SUBTEXT)
        self._status_label.setStyleSheet(
            f"color:{color}; font-size:12px; font-weight:bold;"
        )
        self._status_label.setText(text)

    def _on_fix_clicked(self):
        frame = self.engine.latest_frame
        if frame is None or not frame.face_visible or not frame.shoulders_visible:
            self._set_status(_ct("no_pose"), "error")
            return
        self._countdown       = 3
        self._countdown_start = time.time()
        self._fix_btn.setEnabled(False)

    def _do_calibrate(self):
        from core.calibration import calibrate_from_frame, calibrate_from_buffer, save_calibration

        cal = calibrate_from_buffer(getattr(self.engine, '_buffer', None))
        if cal is None:
            frame = self.engine.latest_frame
            if frame:
                cal = calibrate_from_frame(frame)

        if cal is None:
            self._set_status(_ct("failed"), "error")
            self._fix_btn.setEnabled(True)
            self._countdown = 0
            return

        self.engine.set_calibration(cal)
        save_calibration(cal)

        self._countdown = 0
        self._set_status(
            f"{_ct('saved')}  "
            f"H={cal.head_shoulder_dist:.3f}  "
            f"R={cal.shoulder_eye_ratio:.2f}  "
            f"θ={cal.shoulder_tilt_deg:.1f}°",
            "ok",
        )
        self._fix_btn.setText(_ct("recal_btn"))
        self._fix_btn.setEnabled(True)
        self._close_btn.setText(_ct("finish_btn"))

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
