"""
main_window.py — PostureGuard main window.

Faithfully implements the web App.tsx design:
  - Lucide SVG icons rendered via QSvgRenderer (same icons as web)
  - Sidebar slides out to the RIGHT with QPropertyAnimation
  - Smooth hover via CSS transition + QTimer-based opacity animation on icon buttons
  - All colours, spacing, typography from App.tsx
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QObject,
    QPropertyAnimation, QEasingCurve,
    QByteArray, QRectF, QPoint,
)
from PyQt6.QtGui import (
    QImage, QPixmap, QColor, QPainter, QFont, QPen,
    QIcon,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QSlider,
    QSizePolicy, QFrame, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QSpinBox, QLineEdit, QFileDialog,
    QStackedWidget, QScrollArea, QMenu,
)

from core.engine import State
from core.calibration import load_config, save_config
from core.session_tracker import SessionTracker, load_records, StreakRecord

if TYPE_CHECKING:
    from core.engine import PostureEngine
    from audio.player import AudioPlayer
    from ui.tray import TrayApp


# ═══════════════════════════════════════════════════════════════════════════
# Palette — exact match to App.tsx
# ═══════════════════════════════════════════════════════════════════════════
C_BG       = "#202124"
C_SURFACE  = "#292a2d"
C_BORDER   = "#3c4043"
C_HOVER    = "#4d5156"
C_MUTED    = "#5f6368"
C_TEXT     = "#e8eaed"
C_SUBTEXT  = "#9ca3af"
C_BLUE     = "#8ab4f8"
C_GREEN    = "#4ade80"
C_GREEN_B  = "#22c55e"
C_YELLOW   = "#fbbf24"
C_RED      = "#ef4444"
C_RED_BTN  = "#dc2626"
C_RED_HOV  = "#b91c1c"

_STRICTNESS_KEYS   = ["soft", "medium", "hard"]
_STRICTNESS_LABELS = {"soft": "Light", "medium": "Medium", "hard": "Hard"}
_STRICTNESS_COLORS = {"soft": "#16a34a", "medium": "#d97706", "hard": "#dc2626"}
_STRICTNESS_DISPLAY = {
    "soft":   ("", {"ru": "Мягкий",  "en": "Light"}),
    "medium": ("", {"ru": "Средний", "en": "Medium"}),
    "hard":   ("", {"ru": "Строгий", "en": "Hard"}),
}

# ── Language ────────────────────────────────────────────────────────────────
def _detect_system_lang() -> str:
    """Return 'ru' if system locale is Russian, otherwise 'en'."""
    import locale
    loc = locale.getdefaultlocale()[0] or ""
    return "ru" if loc.startswith("ru") else "en"

_LANG = "en"   # will be overwritten from config or system locale at startup

TR = {
    # State labels
    "state_idle":        {"ru": "Остановлен",           "en": "Stopped"},
    "state_tracking":    {"ru": "Отслеживание активно", "en": "Tracking active"},
    "state_grace":       {"ru": "Осанка ухудшается",    "en": "Posture worsening"},
    "state_bad":         {"ru": "ПЛОХАЯ ОСАНКА",        "en": "BAD POSTURE"},
    "state_away":        {"ru": "Не за компьютером",    "en": "Away from desk"},
    "state_paused":      {"ru": "Пауза",                "en": "Paused"},
    # Streak
    "streak_good":       {"ru": "без предупреждений",   "en": "no warnings"},
    "streak_broken":     {"ru": "серия прервана",       "en": "streak broken"},
    # Stats panel
    "tab_stats":         {"ru": "  Статистика",         "en": "  Statistics"},
    "tab_settings":      {"ru": "  Настройки",          "en": "  Settings"},
    "card_streak":       {"ru": "Текущая серия",        "en": "Current streak"},
    "card_today":        {"ru": "Сегодня",              "en": "Today"},
    "card_warnings":     {"ru": "Предупреждения",       "en": "Warnings"},
    "card_week":         {"ru": "Недельная статистика", "en": "Weekly stats"},
    "today_time":        {"ru": "Время тренировки",     "en": "Training time"},
    "today_posture":     {"ru": "Правильная осанка",    "en": "Good posture"},
    "week_avg":          {"ru": "Ср. время в день",     "en": "Avg. per day"},
    "week_quality":      {"ru": "Качество осанки",      "en": "Posture quality"},
    "week_streak":       {"ru": "Дней подряд",          "en": "Days in a row"},
    "warn_poses":        {"ru": "напоминаний о позе",   "en": "posture reminders"},
    "warn_critical":     {"ru": "критических предупреждения", "en": "critical warnings"},
    "leaderboard_btn":   {"ru": "  Статистика",   "en": "  Statistics"},
    # Settings panel
    "card_strictness":   {"ru": "Уровень строгости",    "en": "Strictness level"},
    "strict_mode":       {"ru": "Режим:",               "en": "Mode:"},
    "strict_timeout":    {"ru": "Таймаут (сек):",       "en": "Timeout (sec):"},
    "card_sound":        {"ru": "Звук",                 "en": "Sound"},
    "sound_builtin":     {"ru": "Встроенный звук (зуммер)", "en": "Built-in sound (buzzer)"},
    "sound_volume":      {"ru": "Громкость:",           "en": "Volume:"},
    "sound_file":        {"ru": "Файл звука:",          "en": "Sound file:"},
    "sound_none":        {"ru": "Не выбран",            "en": "Not selected"},
    "card_grace":        {"ru": "Грейс-периоды",        "en": "Grace periods"},
    "grace_tea":         {"ru": "Чай/телефон (сек):",   "en": "Tea/phone (sec):"},
    "grace_keyboard":    {"ru": "Клавиатура (сек):",    "en": "Keyboard (sec):"},
    "grace_away":        {"ru": "Away — нет в кадре (сек):", "en": "Away — out of frame (sec):"},
    "card_tracking":     {"ru": "Что отслеживать",      "en": "What to track"},
    "track_neck":        {"ru": "Следить за шеей (наклон головы)", "en": "Track neck (head tilt)"},
    "track_back":        {"ru": "Следить за спиной (плечи)",       "en": "Track back (shoulders)"},
    "card_language":     {"ru": "Язык / Language",      "en": "Language / Язык"},
    # Header / bottom bar
    "app_title":         {"ru": "Тренировка осанки",    "en": "Posture Guard"},
    "about_btn":         {"ru": "О программе",          "en": "About"},
    "hide_panel":        {"ru": "Скрыть/показать панель","en": "Hide/show panel"},
    "cam_init":          {"ru": "Инициализация камеры…","en": "Initialising camera…"},
    "cam_off":           {"ru": "Камера выключена",     "en": "Camera off"},
    "btn_sound_off":     {"ru": "Выключить звук",       "en": "Mute sound"},
    "btn_sound_on":      {"ru": "Включить звук",        "en": "Unmute sound"},
    "btn_cam_off":       {"ru": "Выключить камеру",     "en": "Turn off camera"},
    "btn_cam_on":        {"ru": "Включить камеру",      "en": "Turn on camera"},
    "btn_settings":      {"ru": "Настройки",            "en": "Settings"},
    "btn_pause":         {"ru": "Пауза",                "en": "Pause"},
    "btn_resume":        {"ru": "Продолжить",           "en": "Resume"},
    "btn_calibrate":     {"ru": "Калибровка",           "en": "Calibration"},
    "btn_stats":         {"ru": "Статистика",           "en": "Statistics"},
    "btn_about_info":    {"ru": "О программе",          "en": "About"},
    "card_reset":        {"ru": "Сбросить статистику",  "en": "Reset Statistics"},
    "reset_btn":         {"ru": "Сбросить статистику",  "en": "Reset Statistics"},
    "reset_confirm_title": {"ru": "Подтверждение",      "en": "Confirm"},
    "reset_confirm_msg": {"ru": "Вы уверены, что хотите сбросить всю статистику?\nЭто действие нельзя отменить.",
                          "en": "Are you sure you want to reset all statistics?\nThis action cannot be undone."},
    "reset_yes":         {"ru": "Да, сбросить",         "en": "Yes, reset"},
    "reset_no":          {"ru": "Отмена",                "en": "Cancel"},
    "btn_tray":          {"ru": "Свернуть в трей",      "en": "Minimise to tray"},
    "about_text":        {
        "ru": "PostureGuard — приложение для контроля осанки\n\nИспользует MediaPipe для отслеживания положения головы и плеч.",
        "en": "PostureGuard — posture monitoring application\n\nUses MediaPipe to track head and shoulder position.",
    },
    "about_title":       {"ru": "О программе",         "en": "About"},
    "open_file":         {"ru": "Выберите звуковой файл", "en": "Select audio file"},
    # Leaderboard columns
    "lb_col_date":       {"ru": "Дата",                 "en": "Date"},
    "lb_col_time":       {"ru": "Время (от – до)",      "en": "Time (from – to)"},
    "lb_col_dur":        {"ru": "Длительность",         "en": "Duration"},
}

def t(key: str) -> str:
    """Return translated string for current language."""
    return TR[key].get(_LANG, TR[key]["ru"])


def set_lang(lang: str):
    global _LANG
    _LANG = lang


_STATE_CFG = {
    State.IDLE:        {"label": "state_idle",     "dot": "#6b7280"},
    State.TRACKING:    {"label": "state_tracking", "dot": C_GREEN_B},
    State.GRACE:       {"label": "state_grace",    "dot": "#f59e0b"},
    State.BAD_POSTURE: {"label": "state_bad",      "dot": C_RED},
    State.AWAY:        {"label": "state_away",     "dot": "#3b82f6"},
    State.PAUSED:      {"label": "state_paused",   "dot": "#9ca3af"},
}

SIDEBAR_W   = 300   # px
ANIM_MS     = 280   # sidebar animation duration


# ═══════════════════════════════════════════════════════════════════════════
# Lucide SVG icon paths  (stroke icons, viewBox 0 0 24 24)
# ═══════════════════════════════════════════════════════════════════════════
def _svg(path_d: str, extra: str = "") -> str:
    """Wrap a Lucide path in a valid SVG string (stroke icon)."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="white" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{extra}<path d="{path_d}"/>'
        '</svg>'
    )

def _svg_multi(*parts: str) -> str:
    """Multiple path/element strings (supports mixed stroke+fill)."""
    body = "".join(parts)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="white" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{body}'
        '</svg>'
    )

def _svg_filled(*parts: str) -> str:
    """Fill-only SVG (Google Material style — no stroke)."""
    body = "".join(parts)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'{body}'
        '</svg>'
    )

# Exact Lucide icon SVGs used in App.tsx
ICONS: dict[str, str] = {
    # Volume2
    "volume2": _svg_multi(
        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>',
        '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>',
        '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    ),
    # VolumeX
    "volumex": _svg_multi(
        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>',
        '<line x1="23" y1="9" x2="17" y2="15"/>',
        '<line x1="17" y1="9" x2="23" y2="15"/>',
    ),
    # Video
    "video": _svg_multi(
        '<polygon points="23 7 16 12 23 17 23 7"/>',
        '<rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>',
    ),
    # VideoOff
    "videooff": _svg_multi(
        '<path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5.66 0H14a2 2 0 0 1 2 2v3.34"/>',
        '<polygon points="23 7 16 12 23 17 23 7"/>',
        '<line x1="1" y1="1" x2="23" y2="23"/>',
    ),
    # Settings (gear)
    "settings": _svg_multi(
        '<circle cx="12" cy="12" r="3"/>',
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    ),
    # Pause — Google Material "pause" (two solid bars)
    "pause": _svg_filled(
        '<rect x="5" y="3" width="4" height="18" rx="1" fill="white"/>',
        '<rect x="15" y="3" width="4" height="18" rx="1" fill="white"/>',
    ),
    # Play — Google Material "play_arrow" (solid triangle)
    "play": _svg_filled(
        '<polygon points="6,3 20,12 6,21" fill="white"/>',
    ),
    # ScanFace
    "scanface": _svg_multi(
        '<path d="M3 7V5a2 2 0 0 1 2-2h2"/>',
        '<path d="M17 3h2a2 2 0 0 1 2 2v2"/>',
        '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/>',
        '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/>',
        '<path d="M8 14s1.5 2 4 2 4-2 4-2"/>',
        '<path d="M9 9h.01"/>',
        '<path d="M15 9h.01"/>',
    ),
    # Info
    "info": _svg_multi(
        '<circle cx="12" cy="12" r="10"/>',
        '<line x1="12" y1="16" x2="12" y2="12"/>',
        '<line x1="12" y1="8" x2="12.01" y2="8"/>',
    ),
    # Activity (header logo)
    "activity": _svg('<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'),
    # ChevronLeft
    "chevronleft": _svg('<polyline points="15 18 9 12 15 6"/>'),
    # ChevronRight
    "chevronright": _svg('<polyline points="9 18 15 12 9 6"/>'),
    # BarChart3
    "barchart3": _svg_multi(
        '<path d="M3 3v18h18"/>',
        '<path d="M18 17V9"/>',
        '<path d="M13 17V5"/>',
        '<path d="M8 17v-3"/>',
    ),
    # FolderOpen
    "folderopen": _svg_multi(
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
        '<polyline points="16 13 12 17 8 13"/>',
        '<line x1="12" y1="17" x2="12" y2="9"/>',
    ),
    # MinimizeToTray — use "minimize-2" / arrow-down-to-line style
    "tray": _svg_multi(
        '<path d="M4 14h16"/>',
        '<path d="M4 20h16"/>',
        '<polyline points="8 10 12 14 16 10"/>',
        '<path d="M12 4v10"/>',
    ),
    # Trophy
    "trophy": _svg_multi(
        '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/>',
        '<path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>',
        '<path d="M4 22h16"/>',
        '<path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/>',
        '<path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/>',
        '<path d="M18 2H6v7a6 6 0 0 0 12 0V2z"/>',
    ),
    # X (close)
    "x": _svg_multi(
        '<line x1="18" y1="6" x2="6" y2="18"/>',
        '<line x1="6" y1="6" x2="18" y2="18"/>',
    ),
    # Google Material "delete" — trash can
    "delete": _svg_filled(
        '<path fill="white" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>',
    ),
    "meditation": _svg_filled(
        '<path fill="white" d="M12 8C13.1046 8 14 7.10457 14 6C14 4.89543 13.1046 4 12 4C10.8954 4 10 4.89543 10 6C10 7.10457 10.8954 8 12 8Z"/>',
        '<path fill="white" d="M21 16V14C18.76 14 16.84 13.04 15.4 11.32L14.06 9.72C13.874 9.49447 13.6403 9.31295 13.3757 9.18846C13.1112 9.06397 12.8224 8.99961 12.53 9H11.48C10.89 9 10.33 9.26 9.95 9.72L8.61 11.32C7.16 13.04 5.24 14 3 14V16C5.77 16 8.19 14.83 10 12.75V15L6.12 16.55C5.45 16.82 5 17.48 5 18.21C5 19.2 5.8 20 6.79 20H9V19.5C9 18.837 9.26339 18.2011 9.73223 17.7322C10.2011 17.2634 10.837 17 11.5 17H14.5C14.78 17 15 17.22 15 17.5C15 17.78 14.78 18 14.5 18H11.5C10.67 18 10 18.67 10 19.5V20H17.21C18.2 20 19 19.2 19 18.21C19 17.48 18.55 16.82 17.88 16.55L14 15V12.75C15.81 14.83 18.23 16 21 16Z"/>',
    ),
}


def make_icon(svg_key: str, size: int = 20, color: str = "white") -> QIcon:
    """Render a SVG icon to a QIcon. Handles both stroke (Lucide) and fill (Material) icons."""
    svg_str = ICONS.get(svg_key, ICONS["x"])
    svg_str = svg_str.replace('stroke="white"', f'stroke="{color}"')
    svg_str = svg_str.replace('fill="white"',   f'fill="{color}"')
    renderer = QSvgRenderer(QByteArray(svg_str.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


def make_pixmap(svg_key: str, size: int = 20, color: str = "white") -> QPixmap:
    svg_str = ICONS.get(svg_key, ICONS["x"])
    svg_str = svg_str.replace('stroke="white"', f'stroke="{color}"')
    svg_str = svg_str.replace('fill="white"',   f'fill="{color}"')
    renderer = QSvgRenderer(QByteArray(svg_str.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


class RoundedVideoLabel(QLabel):
    """QLabel that clips its pixmap to rounded corners."""
    RADIUS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#000000;")
        self._pixmap: QPixmap | None = None

    def setPixmap(self, pm: QPixmap):  # type: ignore[override]
        self._pixmap = pm
        self.update()

    def clear(self):
        self._pixmap = None
        self.update()

    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainterPath
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Clip to rounded rect
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.RADIUS, self.RADIUS)
        painter.setClipPath(path)

        # Fill background
        painter.fillRect(self.rect(), QColor("#000000"))

        if self._pixmap and not self._pixmap.isNull():
            # Center the pixmap
            x = (self.width()  - self._pixmap.width())  // 2
            y = (self.height() - self._pixmap.height()) // 2
            painter.drawPixmap(x, y, self._pixmap)

        painter.end()



class _Bridge(QObject):
    state_changed = pyqtSignal(object)


# ═══════════════════════════════════════════════════════════════════════════
# IconButton — round button with Lucide SVG icon + smooth hover animation
# ═══════════════════════════════════════════════════════════════════════════
class IconButton(QPushButton):
    """
    Round button with a Lucide SVG icon.
    Icon is painted directly in paintEvent — immune to stylesheet resets.
    Hover background fades in/out via QTimer-driven colour interpolation.
    """
    _STEPS   = 8
    _STEP_MS = 18   # ~144fps feel

    def __init__(self, svg_key: str, tooltip: str = "",
                 bg: str = C_BORDER, hover_bg: str = C_HOVER,
                 size: int = 48, icon_size: int = 20,
                 icon_color: str = "white",
                 parent=None):
        super().__init__(parent)
        self._svg_key    = svg_key
        self._icon_color = icon_color
        self._icon_size  = icon_size
        self._bg         = QColor(bg)
        self._hover_bg   = QColor(hover_bg)
        self._cur_bg     = QColor(bg)
        self._btn_size   = size
        self._hovered    = False
        self._step       = 0
        self._pixmap_cache: QPixmap | None = None

        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        # No icon via Qt — we paint it ourselves
        self.setText("")
        self._refresh_cache()
        self._apply_style()

        self._timer = QTimer(self)
        self._timer.setInterval(self._STEP_MS)
        self._timer.timeout.connect(self._animate_step)

    def _refresh_cache(self):
        """Rebuild cached icon pixmap."""
        self._pixmap_cache = make_pixmap(self._svg_key, self._icon_size, self._icon_color)

    def _apply_style(self):
        r = self._btn_size // 2
        hex_col = self._cur_bg.name()
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background:{hex_col}; border-radius:{r}px;"
            f"  border:none; padding:0;"
            f"}}"
        )

    def paintEvent(self, event):
        # Let Qt draw the background (via stylesheet)
        super().paintEvent(event)
        # Draw our icon on top
        if self._pixmap_cache and not self._pixmap_cache.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            x = (self.width()  - self._icon_size) // 2
            y = (self.height() - self._icon_size) // 2
            painter.drawPixmap(x, y, self._icon_size, self._icon_size, self._pixmap_cache)
            painter.end()

    def _lerp_color(self, a: QColor, b: QColor, t: float) -> QColor:
        return QColor(
            int(a.red()   + (b.red()   - a.red())   * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue()  + (b.blue()  - a.blue())  * t),
        )

    def _animate_step(self):
        self._step = min(self._step + 1, self._STEPS)
        t = self._step / self._STEPS
        if self._hovered:
            self._cur_bg = self._lerp_color(self._bg, self._hover_bg, t)
        else:
            self._cur_bg = self._lerp_color(self._hover_bg, self._bg, t)
        self._apply_style()
        if self._step >= self._STEPS:
            self._timer.stop()

    def enterEvent(self, event):
        self._hovered = True
        self._step = self._STEPS - self._step
        self._timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._step = self._STEPS - self._step
        self._timer.start()
        super().leaveEvent(event)

    def set_svg(self, svg_key: str):
        self._svg_key = svg_key
        self._refresh_cache()
        self.update()

    def set_bg(self, bg: str):
        self._bg = QColor(bg)
        self._hover_bg = QColor(bg).lighter(130)
        self._cur_bg = QColor(bg)
        self._apply_style()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(self._btn_size, self._btn_size)


# ═══════════════════════════════════════════════════════════════════════════
# Pulsing status dot
# ═══════════════════════════════════════════════════════════════════════════
class VolumePopup(QFrame):
    """
    Volume slider that pops up above the sound button on hover.
    Plain child QFrame — no separate window to avoid Windows crashes.
    """
    def __init__(self, anchor: QWidget, get_vol, set_vol, parent: QWidget):
        super().__init__(parent)
        self._anchor  = anchor
        self._get_vol = get_vol
        self._set_vol = set_vol

        self.setFixedSize(44, 120)
        self.setStyleSheet(
            f"QFrame {{ background:{C_SURFACE}; border-radius:10px;"
            f"border:1px solid {C_BORDER}; }}"
        )
        self.hide()

        cl = QVBoxLayout(self)
        cl.setContentsMargins(0, 10, 0, 10)
        cl.setSpacing(6)

        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(0, 100)
        self._slider.setValue(100 - int(get_vol() * 100))
        self._slider.setFixedHeight(100)
        self._slider.setInvertedAppearance(True)
        self._slider.setStyleSheet(f"""
            QSlider {{ background: transparent; border: none; }}
            QSlider::groove:vertical {{
                background: {C_BORDER}; width: 4px; border-radius: 2px;
            }}
            QSlider::sub-page:vertical {{
                background: {C_BORDER}; width: 4px; border-radius: 2px;
            }}
            QSlider::add-page:vertical {{
                background: {C_BLUE}; width: 4px; border-radius: 2px;
            }}
            QSlider::handle:vertical {{
                background: {C_BLUE}; width: 14px; height: 14px;
                margin: 0 -5px; border-radius: 7px; border: none;
            }}
            QSlider::handle:vertical:hover {{ background: #a8c8ff; }}
        """)
        self._slider.valueChanged.connect(self._on_slider)
        cl.addWidget(self._slider, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(250)
        self._hide_timer.timeout.connect(self._maybe_hide)

        anchor.installEventFilter(self)

    def _on_slider(self, value: int):
        # setInvertedAppearance(True): value=0 when handle is at top (max visual).
        # Invert so top position → volume 100.
        self._set_vol(100 - value)

    def sync(self):
        self._slider.blockSignals(True)
        # Invert: store inverted value so handle sits at correct visual position.
        self._slider.setValue(100 - int(self._get_vol() * 100))
        self._slider.blockSignals(False)

    def _reposition(self):
        anchor_pos = self._anchor.mapTo(self.parentWidget(), QPoint(0, 0))
        x = anchor_pos.x() + (self._anchor.width() - self.width()) // 2
        y = anchor_pos.y() - self.height() - 6
        self.move(x, y)

    def show_popup(self):
        self.sync()
        self._reposition()
        self.raise_()
        self.show()

    def _maybe_hide(self):
        if not self._anchor.underMouse() and not self.underMouse():
            self.hide()

    def eventFilter(self, obj, event):
        if obj is self._anchor:
            t = event.type()
            if t == event.Type.Enter:
                self._hide_timer.stop()
                self.show_popup()
            elif t == event.Type.Leave:
                self._hide_timer.start()
        return False

    def enterEvent(self, event):
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_timer.start()
        super().leaveEvent(event)

    @staticmethod
    def attach(anchor: QWidget, get_vol, set_vol, parent: QWidget) -> "VolumePopup":
        return VolumePopup(anchor, get_vol, set_vol, parent)


class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = C_GREEN_B
        self._phase = 0.0
        t = QTimer(self); t.timeout.connect(self._tick); t.start(50)

    def set_color(self, c: str): self._color = c

    def _tick(self):
        self._phase += 0.1
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = 0.55 + 0.45 * math.sin(self._phase) ** 2
        c = QColor(self._color); c.setAlphaF(alpha)
        p.setBrush(c); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(self.rect())


# ═══════════════════════════════════════════════════════════════════════════
# Animated checkbox — white checkmark, smooth bg transition like IconButton
# ═══════════════════════════════════════════════════════════════════════════
class AnimatedCheckBox(QCheckBox):
    """
    QCheckBox that draws a crisp white checkmark when checked,
    and smoothly fades the indicator background (same easing as IconButton).
    """
    _STEPS   = 8
    _STEP_MS = 18

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._anim_step   = 0
        self._anim_target = 0
        self._timer = QTimer(self)
        self._timer.setInterval(self._STEP_MS)
        self._timer.timeout.connect(self._anim_tick)
        self.toggled.connect(self._on_toggled)
        self._anim_step = self._STEPS if self.isChecked() else 0
        self._anim_target = self._anim_step
        self.setStyleSheet(
            f"QCheckBox {{ color:{C_SUBTEXT}; font-size:13px; spacing:8px; }}"
        )

    def _on_toggled(self, checked: bool):
        self._anim_target = self._STEPS if checked else 0
        self._timer.start()

    def _anim_tick(self):
        if self._anim_step < self._anim_target:
            self._anim_step = min(self._anim_step + 1, self._anim_target)
        elif self._anim_step > self._anim_target:
            self._anim_step = max(self._anim_step - 1, self._anim_target)
        self.update()
        if self._anim_step == self._anim_target:
            self._timer.stop()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainterPath
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ind_size = 16
        ind_x = 0
        ind_y = (self.height() - ind_size) // 2
        t = self._anim_step / self._STEPS

        bg_off = QColor(C_BORDER)
        bg_on  = QColor(C_BLUE)
        hover  = self.underMouse()

        def lerp_color(a: QColor, b: QColor, frac: float) -> QColor:
            return QColor(
                int(a.red()   + (b.red()   - a.red())   * frac),
                int(a.green() + (b.green() - a.green()) * frac),
                int(a.blue()  + (b.blue()  - a.blue())  * frac),
            )

        if t < 0.001:
            bg     = QColor(C_HOVER) if hover else QColor(C_BORDER)
            border = QColor(C_BLUE)  if hover else QColor(C_MUTED)
        elif t > 0.999:
            bg     = QColor("#6fa3f7") if hover else QColor(C_BLUE)
            border = bg
        else:
            bg     = lerp_color(bg_off, bg_on, t)
            border = bg

        rect = QRectF(ind_x + 0.5, ind_y + 0.5, ind_size - 1, ind_size - 1)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 4, 4)

        if t > 0.01:
            opacity = min(t * 1.5, 1.0)
            pen = QPen(QColor(255, 255, 255, int(255 * opacity)), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(ind_x + 3,   ind_y + 8)
            path.lineTo(ind_x + 6.5, ind_y + 11.5)
            path.lineTo(ind_x + 13,  ind_y + 4.5)
            painter.drawPath(path)

        text_x = ind_size + 8
        text_rect = self.rect().adjusted(text_x, 0, 0, 0)
        painter.setPen(QPen(QColor(C_TEXT)))
        painter.setFont(self.font())
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text()
        )
        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
# Animated sidebar (slides right to hide, slides left to show)
# ═══════════════════════════════════════════════════════════════════════════
class AnimatedSidebar(QWidget):
    def __init__(self, target_width: int, parent=None):
        super().__init__(parent)
        self._w = target_width
        self._open = True
        self.setFixedWidth(target_width)

        # Animate both min and max width so the layout reflows naturally
        self._a_min = QPropertyAnimation(self, b"minimumWidth")
        self._a_max = QPropertyAnimation(self, b"maximumWidth")
        for a in (self._a_min, self._a_max):
            a.setDuration(ANIM_MS)
            a.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def is_open(self) -> bool: return self._open

    def show_panel(self):
        if self._open: return
        self._open = True
        self._run(0, self._w)

    def hide_panel(self):
        if not self._open: return
        self._open = False
        self._run(self.width(), 0)

    def toggle(self):
        self.hide_panel() if self._open else self.show_panel()

    def _run(self, start: int, end: int):
        for a in (self._a_min, self._a_max):
            a.stop(); a.setStartValue(start); a.setEndValue(end); a.start()


# ═══════════════════════════════════════════════════════════════════════════
# Streak timer
# ═══════════════════════════════════════════════════════════════════════════
class StreakDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#000000; border-radius:10px;")
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 16); v.setSpacing(6)

        self._lbl = QLabel("00:00.00")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont("Consolas", 32, QFont.Weight.Bold)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self._lbl.setFont(f)
        self._lbl.setStyleSheet(f"color:{C_GREEN}; background:transparent; letter-spacing:2px;")
        v.addWidget(self._lbl)

        self._sub = QLabel(t("streak_good"))
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setStyleSheet(f"color:{C_SUBTEXT}; font-size:12px; background:transparent;")
        v.addWidget(self._sub)

    def update_time(self, sec: float, running: bool, grace: bool = False):
        t_val = int(sec * 100); cs = t_val % 100; s = (t_val // 100) % 60
        m = (t_val // 6000) % 60; h = t_val // 360000
        text = f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}" if h else f"{m:02d}:{s:02d}.{cs:02d}"
        col = C_GREEN if running else ("#f59e0b" if grace else "#6b7280")
        self._lbl.setText(text)
        self._lbl.setStyleSheet(f"color:{col}; background:transparent; letter-spacing:2px;")
        self._sub.setText(t("streak_good") if running else t("streak_broken"))


# ═══════════════════════════════════════════════════════════════════════════
# Progress bar row
# ═══════════════════════════════════════════════════════════════════════════
class ProgressRow(QWidget):
    def __init__(self, label, value_text, value_color, pct, fill_color, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._pct = pct; self._fill_color = fill_color
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,4); v.setSpacing(5)
        row = QHBoxLayout()
        l = QLabel(label); l.setStyleSheet(f"color:{C_SUBTEXT}; font-size:12px;")
        r = QLabel(value_text); r.setStyleSheet(f"color:{value_color}; font-size:12px; font-weight:bold;")
        row.addWidget(l); row.addStretch(); row.addWidget(r)
        v.addLayout(row)
        self._bg = QFrame(); self._bg.setFixedHeight(6)
        self._bg.setStyleSheet(f"background:{C_BORDER}; border-radius:3px;")
        self._fill = QFrame(self._bg); self._fill.setFixedHeight(6)
        self._fill.setStyleSheet(f"background:{fill_color}; border-radius:3px;")
        v.addWidget(self._bg)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fill.setFixedWidth(max(int(self._bg.width() * self._pct), 0))


# ═══════════════════════════════════════════════════════════════════════════
# Leaderboard
# ═══════════════════════════════════════════════════════════════════════════
class LeaderboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:none; background:{C_BG}; }}
            QTabBar::tab {{
                background:{C_SURFACE}; color:{C_SUBTEXT};
                padding:6px 14px; font-size:11px;
                border:1px solid {C_BORDER}; border-bottom:none;
                border-radius:4px 4px 0 0; margin-right:2px;
            }}
            QTabBar::tab:selected {{ background:{C_BG}; color:{C_BLUE}; }}
            QTabBar::tab:hover    {{ color:{C_TEXT}; }}
        """)
        self._tables: dict[str, QTableWidget] = {}
        for key in _STRICTNESS_KEYS:
            _, name_d = _STRICTNESS_DISPLAY[key]
            name = name_d.get(_LANG, name_d["ru"])
            tbl = self._make_table(); self._tables[key] = tbl
            self._tabs.addTab(tbl, name)
        layout.addWidget(self._tabs)

    def _make_table(self):
        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(["#", t("lb_col_date"), t("lb_col_time"), t("lb_col_dur")])
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setStyleSheet(f"""
            QTableWidget {{ background:{C_BG}; color:{C_TEXT}; font-size:12px; border:none;
                            alternate-background-color:{C_SURFACE}; }}
            QHeaderView::section {{ background:{C_SURFACE}; color:{C_SUBTEXT};
                font-size:11px; font-weight:bold; padding:5px 8px; border:none;
                border-bottom:1px solid {C_BORDER}; }}
            QTableWidget::item:selected {{ background:#1a3a5a; color:white; }}
        """)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        return tbl

    def reload(self):
        records = load_records()
        by_s: dict[str, list] = {k: [] for k in _STRICTNESS_KEYS}
        for r in records:
            if r.strictness in by_s: by_s[r.strictness].append(r)
        for key, recs in by_s.items():
            recs.sort(key=lambda r: r.duration_sec, reverse=True)
            tbl = self._tables[key]; tbl.setRowCount(0)
            for pos, rec in enumerate(recs, 1):
                tbl.insertRow(tbl.rowCount()); row = tbl.rowCount()-1
                medal = {1:"🥇",2:"🥈",3:"🥉"}.get(pos, str(pos))
                for col, val in enumerate([medal, rec.date,
                        f"{rec.time_from} – {rec.time_to}", rec.duration_fmt()]):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col == 3:
                        item.setFont(QFont("Consolas", 12))
                        if pos == 1: item.setForeground(QColor("#f1c40f"))
                        elif pos <= 3: item.setForeground(QColor("#95a5a6"))
                    tbl.setItem(row, col, item)

    def switch_to_strictness(self, key: str):
        idx = _STRICTNESS_KEYS.index(key) if key in _STRICTNESS_KEYS else 1
        self._tabs.setCurrentIndex(idx)


# ═══════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):

    def __init__(self, engine: "PostureEngine", audio: "AudioPlayer",
                 tray: "TrayApp", parent=None):
        super().__init__(parent)
        self.engine = engine; self.audio = audio; self.tray = tray

        self.setWindowTitle("PostureGuard")
        self.setMinimumSize(900, 660)
        self.resize(1140, 740)

        self._bridge = _Bridge()
        self._bridge.state_changed.connect(self._on_state_changed)

        cfg = load_config()
        set_lang(cfg.get("language") or _detect_system_lang())
        self._tracker = SessionTracker(
            strictness=cfg.get("strictness", "medium"),
            on_streak_update=lambda _: None,
            on_record_saved=self._on_record_saved,
        )
        engine.on_state_change = lambda s: (
            self._bridge.state_changed.emit(s),
            self._tracker.on_state_change(s),
        )
        self._sound_on = True; self._cam_on = True
        self._warning_count = 0
        self._critical_count = 0
        self._session_start_time  = __import__('time').monotonic()
        self._session_active_sec  = 0.0   # wall time minus paused intervals
        self._good_posture_sec    = 0.0   # accumulated good-posture seconds today
        self._last_tick_time      = __import__('time').monotonic()
        self._setup_ui(cfg)

        # Wire engine warning callback
        engine.on_warning = self._on_warning

        # Notify tracker of initial state so the streak timer starts immediately
        # if the engine is already in TRACKING/GRACE at window open time.
        self._tracker.on_state_change(engine.state)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(50)

    # ──────────────────────────────────────────────────────────────────
    # Global stylesheet
    # ──────────────────────────────────────────────────────────────────
    def _setup_ui(self, cfg: dict):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background:{C_BG}; color:{C_TEXT};
                font-family:"Segoe UI",Arial,sans-serif;
            }}
            QLabel {{ background:transparent; }}
            QLineEdit {{
                background:{C_BORDER}; color:{C_TEXT};
                border:1px solid {C_MUTED}; border-radius:4px; padding:4px 8px;
            }}
            QSpinBox {{
                background:{C_BORDER}; color:{C_TEXT};
                border:1px solid {C_MUTED}; border-radius:4px;
                padding:3px 8px; min-width:70px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width:0; border:none;
            }}
            QCheckBox {{ color:{C_SUBTEXT}; font-size:13px; }}
            QCheckBox::indicator {{
                width:16px; height:16px;
                background:{C_BORDER}; border:1px solid {C_MUTED}; border-radius:4px;
            }}
            QCheckBox::indicator:checked {{
                background:{C_BLUE}; border:1px solid {C_BLUE};
            }}
            QCheckBox::indicator:hover {{
                border:1px solid {C_BLUE};
            }}
            QCheckBox::indicator:checked:hover {{
                background:#6fa3f7; border:1px solid #6fa3f7;
            }}
            QSlider::groove:horizontal {{
                height:4px; background:{C_BORDER}; border-radius:2px;
            }}
            QSlider::handle:horizontal {{
                background:{C_BLUE}; width:14px; height:14px;
                margin:-5px 0; border-radius:7px;
            }}
            QSlider::sub-page:horizontal {{
                background:{C_BLUE}; border-radius:2px;
            }}
            QScrollArea {{ border:none; }}
            QScrollBar:vertical {{
                background:{C_SURFACE}; width:6px; border-radius:3px;
            }}
            QScrollBar::handle:vertical {{
                background:{C_MUTED}; border-radius:3px; min-height:20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height:0;
            }}
        """)

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Content row
        content = QWidget(); content.setStyleSheet(f"background:{C_BG};")
        cl = QHBoxLayout(content); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        cl.addWidget(self._build_camera_area(), stretch=3)

        # Chevron toggle — sits right on the border between cam and sidebar
        self._chevron_btn = self._make_chevron()
        cl.addWidget(self._chevron_btn)

        # Sidebar
        self._sidebar = AnimatedSidebar(SIDEBAR_W)
        self._sidebar.setStyleSheet(
            f"background:{C_SURFACE}; border-left:1px solid {C_BORDER};")
        sb = QVBoxLayout(self._sidebar)
        sb.setContentsMargins(0,0,0,0); sb.setSpacing(0)
        sb.addWidget(self._build_tab_bar())
        self._sidebar_stack = QStackedWidget()
        self._sidebar_stack.addWidget(self._build_stats_panel())
        self._sidebar_stack.addWidget(self._build_settings_panel(cfg))
        sb.addWidget(self._sidebar_stack, stretch=1)
        cl.addWidget(self._sidebar)

        root.addWidget(content, stretch=1)
        root.addWidget(self._build_bottom_bar())

    # ──────────────────────────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        h = QWidget(); h.setFixedHeight(64)
        h.setStyleSheet(f"background:{C_BG}; border-bottom:1px solid {C_BORDER};")
        hl = QHBoxLayout(h); hl.setContentsMargins(24,0,24,0)

        # Meditation icon (Google-style) + title
        icon_lbl = QLabel()
        icon_lbl.setPixmap(make_pixmap("meditation", 22, C_BLUE))
        icon_lbl.setFixedSize(24, 24)

        self._header_title = QLabel(t("app_title"))
        self._header_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Medium))
        self._header_title.setStyleSheet("color:white;")

        left = QHBoxLayout(); left.setSpacing(10)
        left.addWidget(icon_lbl); left.addWidget(self._header_title)
        hl.addLayout(left); hl.addStretch()

        self._about_btn = QPushButton(t("about_btn"))
        self._about_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C_SUBTEXT};"
            f"font-size:13px;padding:6px 12px;border:none;border-radius:8px;}}"
            f"QPushButton:hover{{background:{C_BORDER};color:white;}}")
        self._about_btn.clicked.connect(self._show_about)

        hl.addWidget(self._about_btn)
        return h

    # ──────────────────────────────────────────────────────────────────
    # Camera area
    # ──────────────────────────────────────────────────────────────────
    def _build_camera_area(self) -> QWidget:
        area = QWidget(); area.setStyleSheet(f"background:{C_BG};")
        v = QVBoxLayout(area); v.setContentsMargins(24,16,0,16)

        # Container with rounded corners — video fills this completely
        self._cam_container = QWidget()
        self._cam_container.setStyleSheet(
            "background:#000000; border-radius:12px;")
        self._cam_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._cam_container.setMinimumSize(500, 360)

        cam_layout = QVBoxLayout(self._cam_container)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        cam_layout.setSpacing(0)

        # Stack: page0=live video, page1=loading, page2=cam-off
        self._video_stack = QStackedWidget()
        self._video_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Page 0 — live video
        self._video_label = RoundedVideoLabel()
        self._video_stack.addWidget(self._video_label)

        # Page 1 — loading placeholder (camera initialising)
        cam_loading_page = QWidget()
        cam_loading_page.setStyleSheet("background:#000000; border-radius:12px;")
        loading_layout = QVBoxLayout(cam_loading_page)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_icon = QLabel()
        loading_icon.setPixmap(make_pixmap("video", 64, C_MUTED))
        loading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_lbl = QLabel(t("cam_init"))
        self._loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_lbl.setStyleSheet(f"color:{C_SUBTEXT}; font-size:15px; background:transparent;")
        loading_layout.addWidget(loading_icon)
        loading_layout.addWidget(self._loading_lbl)
        self._video_stack.addWidget(cam_loading_page)

        # Page 2 — camera-off placeholder
        cam_off_page = QWidget()
        cam_off_page.setStyleSheet("background:#000000; border-radius:12px;")
        off_layout = QVBoxLayout(cam_off_page)
        off_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_off_icon = QLabel()
        cam_off_icon.setPixmap(make_pixmap("videooff", 64, C_MUTED))
        cam_off_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_off_lbl = QLabel(t("cam_off"))
        cam_off_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_off_lbl.setStyleSheet(f"color:{C_SUBTEXT}; font-size:15px; background:transparent;")
        off_layout.addWidget(cam_off_icon)
        off_layout.addWidget(cam_off_lbl)
        self._video_stack.addWidget(cam_off_page)

        # Start on loading page; switch to live once first frame arrives
        self._video_stack.setCurrentIndex(1)
        self._cam_initialized = False

        cam_layout.addWidget(self._video_stack)
        v.addWidget(self._cam_container)
        return area

    # ──────────────────────────────────────────────────────────────────
    # Chevron toggle button  (ChevronLeft / ChevronRight from Lucide)
    # ──────────────────────────────────────────────────────────────────
    def _make_chevron(self) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(16, 56)
        btn.setToolTip(t("hide_panel"))
        self._chevron_open = True
        self._update_chevron_icon(btn, True)
        btn.clicked.connect(self._toggle_sidebar)
        return btn

    def _update_chevron_icon(self, btn: QPushButton, open_: bool):
        key = "chevronright" if open_ else "chevronleft"
        btn.setIcon(make_icon(key, 12, C_SUBTEXT))
        btn.setIconSize(btn.sizeHint())
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background:{C_SURFACE}; border:none;"
            f"  border-left:1px solid {C_BORDER};"
            f"  border-top-left-radius:6px; border-bottom-left-radius:6px;"
            f"  padding:0;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{C_BORDER};"
            f"}}"
        )

    # ──────────────────────────────────────────────────────────────────
    # Sidebar tab bar
    # ──────────────────────────────────────────────────────────────────
    def _build_tab_bar(self) -> QWidget:
        bar = QWidget(); bar.setFixedHeight(48)
        bar.setStyleSheet(f"background:{C_SURFACE}; border-bottom:1px solid {C_BORDER};")
        h = QHBoxLayout(bar); h.setContentsMargins(0,0,0,0); h.setSpacing(0)

        self._tab_stats    = self._tab_btn("stats_icon", t("tab_stats"),    True)
        self._tab_settings = self._tab_btn("settings",   t("tab_settings"), False)

        # Inline BarChart3 icon into stats tab label via pixmap
        self._tab_stats.setIcon(make_icon("barchart3", 14, C_BLUE))
        self._tab_settings.setIcon(make_icon("settings", 14, C_SUBTEXT))

        self._tab_stats.clicked.connect(lambda: self._switch_tab(0))
        self._tab_settings.clicked.connect(lambda: self._switch_tab(1))
        h.addWidget(self._tab_stats); h.addWidget(self._tab_settings)
        return bar

    def _tab_btn(self, _icon: str, text: str, active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True); btn.setChecked(active)
        btn.setFixedHeight(48)
        btn.setIconSize(btn.sizeHint())
        self._apply_tab_style(btn, active)
        return btn

    @staticmethod
    def _apply_tab_style(btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet(
                f"QPushButton {{background:transparent; color:{C_BLUE}; font-size:13px;"
                f" padding:0 16px; border:none; border-bottom:2px solid {C_BLUE};"
                f" border-radius:0;}}"
                f"QPushButton:hover {{background:transparent;}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{background:transparent; color:{C_SUBTEXT}; font-size:13px;"
                f" padding:0 16px; border:none; border-bottom:2px solid transparent;"
                f" border-radius:0;}}"
                f"QPushButton:hover {{color:{C_TEXT}; background:transparent;}}"
            )

    def _switch_tab(self, idx: int):
        self._sidebar_stack.setCurrentIndex(idx)
        self._apply_tab_style(self._tab_stats, idx == 0)
        self._apply_tab_style(self._tab_settings, idx == 1)
        self._tab_stats.setChecked(idx == 0)
        self._tab_settings.setChecked(idx == 1)
        # Update tab icons colour
        self._tab_stats.setIcon(
            make_icon("barchart3", 14, C_BLUE if idx == 0 else C_SUBTEXT))
        self._tab_settings.setIcon(
            make_icon("settings", 14, C_BLUE if idx == 1 else C_SUBTEXT))
        if not self._sidebar.is_open():
            self._sidebar.show_panel()
            self._chevron_open = True
            self._update_chevron_icon(self._chevron_btn, True)

    # ──────────────────────────────────────────────────────────────────
    # Sidebar toggle
    # ──────────────────────────────────────────────────────────────────
    def _toggle_sidebar(self):
        self._sidebar.toggle()
        self._chevron_open = self._sidebar.is_open()
        self._update_chevron_icon(self._chevron_btn, self._chevron_open)

    def _toggle_or_open_tab(self, tab_idx: int):
        """Open sidebar to tab_idx; if already open on that tab — close it."""
        already_open = self._sidebar.is_open()
        current_tab = self._sidebar_stack.currentIndex()
        if already_open and current_tab == tab_idx:
            self._sidebar.hide_panel()
            self._chevron_open = False
            self._update_chevron_icon(self._chevron_btn, False)
        else:
            self._sidebar.show_panel()
            self._chevron_open = True
            self._update_chevron_icon(self._chevron_btn, True)
            self._switch_tab(tab_idx)

    # ──────────────────────────────────────────────────────────────────
    # Stats panel
    # ──────────────────────────────────────────────────────────────────
    def _build_stats_panel(self) -> QWidget:
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"background:{C_SURFACE}; border:none;")
        w = QWidget(); w.setStyleSheet(f"background:{C_SURFACE};")
        v = QVBoxLayout(w); v.setContentsMargins(12,12,18,12); v.setSpacing(10)

        c = self._card(t("card_streak"))
        self._streak_display = StreakDisplay()
        c.layout().addWidget(self._streak_display); v.addWidget(c)

        c = self._card(t("card_today"))
        self._today_time_row  = ProgressRow(t("today_time"), "0м",  "white", 0.0, C_BLUE)
        self._today_posture_row = ProgressRow(t("today_posture"), "—", C_GREEN, 0.0, C_GREEN_B)
        c.layout().addWidget(self._today_time_row)
        c.layout().addWidget(self._today_posture_row)
        v.addWidget(c)

        c = self._card(t("card_warnings"))
        self._warn_lbl = QLabel()
        self._warn_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._crit_lbl = QLabel()
        self._crit_lbl.setTextFormat(Qt.TextFormat.RichText)
        c.layout().addWidget(self._warn_lbl)
        c.layout().addWidget(self._crit_lbl)
        self._refresh_warning_labels()
        v.addWidget(c)

        c = self._card(t("card_week"))
        self._week_labels: dict[str, QLabel] = {}
        for key, display in [("week_avg", t("week_avg")), ("week_quality", t("week_quality")), ("week_streak", t("week_streak"))]:
            row = QHBoxLayout()
            l = QLabel(display); l.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;")
            r = QLabel("—"); r.setStyleSheet(f"color:{C_TEXT};font-size:12px;font-weight:bold;")
            row.addWidget(l); row.addStretch(); row.addWidget(r)
            c.layout().addLayout(row)
            self._week_labels[key] = r
        v.addWidget(c)

        # Trophy button — opens leaderboard window
        trophy_btn = QPushButton()
        trophy_btn.setIcon(make_icon("trophy", 18, C_YELLOW))
        trophy_btn.setIconSize(trophy_btn.sizeHint())
        from PyQt6.QtCore import QSize
        trophy_btn.setIconSize(QSize(18, 18))
        trophy_btn.setText(t("leaderboard_btn"))
        trophy_btn.setMinimumHeight(40)
        trophy_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG};color:{C_TEXT};border:1px solid {C_BORDER};"
            f"border-radius:8px;font-size:13px;text-align:left;padding:0 14px;}}"
            f"QPushButton:hover{{background:{C_BORDER};color:white;}}"
        )
        trophy_btn.clicked.connect(self._open_leaderboard)
        v.addWidget(trophy_btn)

        v.addStretch(); scroll.setWidget(w); return scroll

    # ──────────────────────────────────────────────────────────────────
    # Settings panel
    # ──────────────────────────────────────────────────────────────────
    def _build_settings_panel(self, cfg: dict) -> QWidget:
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"background:{C_SURFACE}; border:none;")
        w = QWidget(); w.setStyleSheet(f"background:{C_SURFACE};")
        v = QVBoxLayout(w); v.setContentsMargins(12,12,18,12); v.setSpacing(10)

        # ── Strictness ──────────────────────────────────────────
        c = self._card(t("card_strictness"))
        lbl = QLabel(t("strict_mode")); lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;")
        c.layout().addWidget(lbl)
        row = QHBoxLayout(); row.setSpacing(6); row.setContentsMargins(0,0,0,0)
        self._strict_btns: dict[str, QPushButton] = {}
        for key, label in _STRICTNESS_LABELS.items():
            btn = QPushButton(label); btn.setCheckable(True)
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _, k=key: self._on_strictness_btn(k))
            self._strict_btns[key] = btn; row.addWidget(btn)
        c.layout().addLayout(row)
        self._set_strictness_buttons(cfg.get("strictness","medium"))
        lbl2 = QLabel(t("strict_timeout"))
        lbl2.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;margin-top:4px;")
        c.layout().addWidget(lbl2)
        self._timeout_spin = QSpinBox(); self._timeout_spin.setRange(1,120)
        self._timeout_spin.setValue(cfg.get("medium_timeout_sec",10))
        self._timeout_spin.valueChanged.connect(self._auto_save)
        c.layout().addWidget(self._timeout_spin); v.addWidget(c)

        # ── Sound ───────────────────────────────────────────────
        c = self._card(t("card_sound"))
        self._use_default_cb = AnimatedCheckBox(t("sound_builtin"))
        self._use_default_cb.setChecked(cfg.get("use_default_sound",True))
        self._use_default_cb.toggled.connect(self._on_default_sound_toggle)
        c.layout().addWidget(self._use_default_cb)
        lbl = QLabel(t("sound_volume")); lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;margin-top:4px;")
        c.layout().addWidget(lbl)
        vol_row = QHBoxLayout(); vol_row.setSpacing(8)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0,100); self._vol_slider.setValue(int(cfg.get("volume",0.8)*100))
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        self._vol_slider.sliderReleased.connect(self._save_volume_cfg)
        self._vol_val_lbl = QLabel(f"{int(cfg.get('volume',0.8)*100)}%")
        self._vol_val_lbl.setFixedWidth(36)
        self._vol_val_lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;")
        vol_row.addWidget(self._vol_slider); vol_row.addWidget(self._vol_val_lbl)
        c.layout().addLayout(vol_row)
        lbl = QLabel(t("sound_file")); lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;margin-top:4px;")
        c.layout().addWidget(lbl)
        file_row = QHBoxLayout(); file_row.setSpacing(6)
        self._sound_path_edit = QLineEdit()
        self._sound_path_edit.setPlaceholderText(t("sound_none"))
        self._sound_path_edit.setText(cfg.get("sound_file") or "")
        self._sound_path_edit.setEnabled(not cfg.get("use_default_sound",True))
        self._sound_path_edit.editingFinished.connect(self._auto_save)
        browse_btn = QPushButton()
        browse_btn.setIcon(make_icon("folderopen", 16))
        browse_btn.setIconSize(browse_btn.sizeHint())
        browse_btn.setFixedSize(34,34)
        browse_btn.setStyleSheet(
            f"QPushButton{{background:{C_BORDER};border-radius:6px;border:none;}}"
            f"QPushButton:hover{{background:{C_HOVER};}}")
        browse_btn.clicked.connect(self._browse_sound)
        file_row.addWidget(self._sound_path_edit); file_row.addWidget(browse_btn)
        c.layout().addLayout(file_row); v.addWidget(c)

        # ── Grace periods ────────────────────────────────────────
        c = self._card(t("card_grace"))
        self._grace_spins: dict[str, QSpinBox] = {}
        for key, label, default in [
            ("grace_period_sec",         t("grace_tea"),      30),
            ("keyboard_grace_sec",        t("grace_keyboard"), 10),
            ("away_absence_timeout_sec",  t("grace_away"),      5),
        ]:
            gr = QHBoxLayout(); gr.setSpacing(8)
            lbl = QLabel(label); lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;")
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spin = QSpinBox(); spin.setRange(1,120); spin.setValue(cfg.get(key,default))
            spin.setFixedWidth(72)
            spin.valueChanged.connect(self._auto_save)
            self._grace_spins[key] = spin
            gr.addWidget(lbl); gr.addWidget(spin)
            c.layout().addLayout(gr)
        v.addWidget(c)

        # ── Tracking toggles ─────────────────────────────────────
        c = self._card(t("card_tracking"))
        self._track_neck_cb = AnimatedCheckBox(t("track_neck"))
        self._track_back_cb = AnimatedCheckBox(t("track_back"))
        self._track_neck_cb.setChecked(cfg.get("track_neck",True))
        self._track_back_cb.setChecked(cfg.get("track_back",True))
        self._track_neck_cb.toggled.connect(self._auto_save)
        self._track_back_cb.toggled.connect(self._auto_save)
        c.layout().addWidget(self._track_neck_cb); c.layout().addWidget(self._track_back_cb)
        v.addWidget(c)

        # ── Language ─────────────────────────────────────────────
        c = self._card(t("card_language"))
        lang_row = QHBoxLayout(); lang_row.setSpacing(8)
        lang_lbl = QLabel(t("card_language"))
        lang_lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:12px;")
        self._lang_btn = QPushButton(_LANG.upper())
        self._lang_btn.setFixedSize(48, 32)
        self._lang_btn.setStyleSheet(
            f"QPushButton{{background:{C_BORDER};color:{C_TEXT};"
            f"font-size:12px;font-weight:bold;border:none;border-radius:6px;}}"
            f"QPushButton:hover{{background:{C_HOVER};color:white;}}")
        self._lang_btn.clicked.connect(self._show_lang_menu)
        lang_row.addWidget(lang_lbl); lang_row.addStretch(); lang_row.addWidget(self._lang_btn)
        c.layout().addLayout(lang_row)
        v.addWidget(c)

        # ── Reset Statistics ─────────────────────────────────────
        c = self._card("")
        reset_row = QHBoxLayout(); reset_row.setSpacing(10); reset_row.setContentsMargins(0,0,0,0)
        reset_lbl = QLabel(t("reset_btn"))
        reset_lbl.setStyleSheet(f"color:{C_SUBTEXT}; font-size:13px;")
        reset_icon_btn = QPushButton()
        reset_icon_btn.setIcon(make_icon("delete", 18, "#fca5a5"))
        reset_icon_btn.setIconSize(__import__('PyQt6.QtCore', fromlist=['QSize']).QSize(18, 18))
        reset_icon_btn.setFixedSize(34, 34)
        reset_icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_icon_btn.setToolTip(t("reset_btn"))
        reset_icon_btn.setStyleSheet(
            f"QPushButton{{background:{C_RED_BTN};border:none;border-radius:8px;}}"
            f"QPushButton:hover{{background:{C_RED_HOV};}}"
            f"QPushButton:pressed{{background:#991b1b;}}"
        )
        reset_icon_btn.clicked.connect(self._confirm_reset_stats)
        reset_row.addWidget(reset_lbl); reset_row.addStretch(); reset_row.addWidget(reset_icon_btn)
        c.layout().addLayout(reset_row)
        v.addWidget(c)

        v.addStretch(); scroll.setWidget(w); return scroll

    # ──────────────────────────────────────────────────────────────────
    # Card helper
    # ──────────────────────────────────────────────────────────────────
    def _card(self, title: str) -> QWidget:
        c = QWidget()
        c.setStyleSheet(
            f"QWidget{{background:{C_BG};border-radius:10px;}}"
            f"QLabel{{background:transparent;}}"
        )
        v = QVBoxLayout(c); v.setContentsMargins(16,14,16,14); v.setSpacing(8)
        if title:
            h = QLabel(title); h.setStyleSheet("color:white;font-size:13px;font-weight:bold;")
            v.addWidget(h)
        return c

    # ──────────────────────────────────────────────────────────────────
    # Bottom bar  — exact icon order from App.tsx
    # ──────────────────────────────────────────────────────────────────
    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget(); bar.setFixedHeight(80)
        bar.setStyleSheet(f"background:{C_BG}; border-top:1px solid {C_BORDER};")
        bl = QHBoxLayout(bar); bl.setContentsMargins(24,0,24,0); bl.setSpacing(0)

        # Left — pulsing dot + label
        self._status_dot = StatusDot()
        self._session_lbl = QLabel(t("state_tracking"))
        self._session_lbl.setFixedWidth(180)
        self._session_lbl.setStyleSheet(f"color:{C_SUBTEXT};font-size:13px;margin-left:8px;")

        left_w = QWidget(); left_w.setFixedWidth(220)
        left_l = QHBoxLayout(left_w); left_l.setContentsMargins(0,0,0,0); left_l.setSpacing(0)
        left_l.addWidget(self._status_dot); left_l.addWidget(self._session_lbl); left_l.addStretch()
        bl.addWidget(left_w)

        # Center controls  (Volume2/VolumeX · Video/VideoOff · Settings · | · Pause/Play)
        center = QHBoxLayout(); center.setSpacing(8)

        self._sound_btn = IconButton("volume2", t("btn_sound_off"))
        self._sound_btn.clicked.connect(self._toggle_sound)
        center.addWidget(self._sound_btn)
        # Volume popup — appears on hover above the sound button
        self._vol_popup = VolumePopup.attach(
            self._sound_btn,
            get_vol=lambda: self.audio.get_volume(),
            set_vol=self._set_volume_from_popup,
            parent=self,
        )

        self._cam_btn = IconButton("video", t("btn_cam_off"))
        self._cam_btn.clicked.connect(self._toggle_camera)
        center.addWidget(self._cam_btn)

        self._settings_btn = IconButton("settings", t("btn_settings"))
        self._settings_btn.clicked.connect(lambda: self._toggle_or_open_tab(1))
        center.addWidget(self._settings_btn)

        self._stats_btn = IconButton("barchart3", t("btn_stats"))
        self._stats_btn.clicked.connect(lambda: self._toggle_or_open_tab(0))
        center.addWidget(self._stats_btn)

        div = QFrame(); div.setFixedSize(1,32)
        div.setStyleSheet(f"background:{C_BORDER};")
        center.addWidget(div)

        self._pause_btn = IconButton("pause", t("btn_pause"), bg=C_RED_BTN, hover_bg=C_RED_HOV)
        self._pause_btn.clicked.connect(self._toggle_pause)
        center.addWidget(self._pause_btn)
        # Reflect current engine state immediately
        self._on_state_changed(self.engine.state)

        # Shift center group 10px to the left: left stretch gets +10px, right gets -10px
        bl.addStretch(1)
        bl.addSpacing(10)
        bl.addLayout(center)
        bl.addStretch(1)

        # Right  (ScanFace · Info · tray)
        right = QHBoxLayout(); right.setSpacing(8)

        self._cal_btn = IconButton("scanface", t("btn_calibrate"))
        self._cal_btn.clicked.connect(self._open_calibration)
        right.addWidget(self._cal_btn)

        self._info_btn = IconButton("info", t("btn_about_info"))
        self._info_btn.clicked.connect(self._show_about)
        right.addWidget(self._info_btn)

        self._tray_btn = IconButton("tray", t("btn_tray"))
        self._tray_btn.clicked.connect(self.hide)
        right.addWidget(self._tray_btn)

        right_w = QWidget(); right_w.setFixedWidth(220)
        right_wl = QHBoxLayout(right_w); right_wl.setContentsMargins(0,0,0,0); right_wl.setSpacing(0)
        right_wl.addStretch(); right_wl.addLayout(right)
        bl.addWidget(right_w); return bar

    # ──────────────────────────────────────────────────────────────────
    # Tick / frame
    # ──────────────────────────────────────────────────────────────────
    def _tick(self):
        import time as _time
        now = _time.monotonic()
        dt  = now - self._last_tick_time
        self._last_tick_time = now

        self._refresh_frame()
        elapsed = self._tracker.tick()
        running = self.engine.state == State.TRACKING
        grace   = self.engine.state == State.GRACE
        self._streak_display.update_time(elapsed, running, grace)

        # Only count active (non-paused) time toward the session
        paused = self.engine.state == State.PAUSED
        if not paused:
            self._session_active_sec += dt

        # Accumulate good-posture time
        if running:
            self._good_posture_sec += dt

        # Update today stats every tick
        self._refresh_today_stats(self._session_active_sec)

    def _refresh_today_stats(self, session_sec: float):
        """Update today + weekly stats cards from session data and records."""
        # ── Today ──────────────────────────────────────────────────────
        def fmt_dur(s: float) -> str:
            s = int(s)
            h, m = s // 3600, (s % 3600) // 60
            sec  = s % 60
            if _LANG == "en":
                if h:
                    return f"{h}h {m}m"
                if m:
                    return f"{m}m {sec}s"
                return f"{sec}s"
            else:
                if h:
                    return f"{h}ч {m}м"
                if m:
                    return f"{m}м {sec}с"
                return f"{sec}с"

        today_pct = (self._good_posture_sec / session_sec) if session_sec > 1 else 0.0
        today_pct = min(today_pct, 1.0)

        self._today_time_row._fill.setFixedWidth(
            max(int(self._today_time_row._bg.width() * min(session_sec / 7200, 1.0)), 0))
        # update label via internal layout child
        lbl_time = self._today_time_row.layout().itemAt(0).layout().itemAt(0).widget()
        lbl_val  = self._today_time_row.layout().itemAt(0).layout().itemAt(2).widget()
        lbl_val.setText(fmt_dur(session_sec))

        posture_lbl = self._today_posture_row.layout().itemAt(0).layout().itemAt(2).widget()
        posture_lbl.setText(f"{int(today_pct * 100)}%")
        self._today_posture_row._pct = today_pct
        self._today_posture_row._fill.setFixedWidth(
            max(int(self._today_posture_row._bg.width() * today_pct), 0))

        # ── Weekly (from saved records) ─────────────────────────────────
        from datetime import date, timedelta
        today_str = date.today().isoformat()
        week_ago  = (date.today() - timedelta(days=6)).isoformat()
        records   = load_records()
        week_recs = [r for r in records if week_ago <= r.date <= today_str]

        if week_recs:
            days_with_data = len(set(r.date for r in week_recs))
            total_sec = sum(r.duration_sec for r in week_recs)
            avg_sec   = total_sec / max(days_with_data, 1)
            # streak days: consecutive days up to today with records
            all_days = sorted(set(r.date for r in records), reverse=True)
            streak_days = 0
            check = date.today()
            for d in all_days:
                if d == check.isoformat():
                    streak_days += 1
                    check -= timedelta(days=1)
                elif d < check.isoformat():
                    break

            self._week_labels["week_avg"].setText(fmt_dur(avg_sec))
            self._week_labels["week_avg"].setStyleSheet(
                f"color:{C_TEXT};font-size:12px;font-weight:bold;")
            self._week_labels["week_streak"].setText(str(streak_days))
            self._week_labels["week_streak"].setStyleSheet(
                f"color:{C_BLUE};font-size:12px;font-weight:bold;")
        else:
            self._week_labels["week_avg"].setText("—")
            self._week_labels["week_streak"].setText("0")

        # Quality = good posture pct this session (best proxy we have)
        self._week_labels["week_quality"].setText(f"{int(today_pct * 100)}%")
        col = C_GREEN if today_pct >= 0.7 else C_YELLOW if today_pct >= 0.4 else C_RED
        self._week_labels["week_quality"].setStyleSheet(
            f"color:{col};font-size:12px;font-weight:bold;")

    def _refresh_frame(self):
        if not self._cam_on:
            return
        frame = self.engine.latest_frame
        if frame is None or frame.overlay_image is None:
            return
        # Switch from loading placeholder to live video on first frame
        if not self._cam_initialized:
            self._cam_initialized = True
            self._video_stack.setCurrentIndex(0)
        import cv2
        img = frame.overlay_image; h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qi = QImage(rgb.data, w, h, 3*w, QImage.Format.Format_RGB888)
        # Scale to fill the entire container (no letterboxing)
        pm = QPixmap.fromImage(qi).scaled(
            self._video_label.width(), self._video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Crop to exact label size (center crop)
        if pm.width() > self._video_label.width() or pm.height() > self._video_label.height():
            x = (pm.width()  - self._video_label.width())  // 2
            y = (pm.height() - self._video_label.height()) // 2
            pm = pm.copy(x, y, self._video_label.width(), self._video_label.height())
        self._video_label.setPixmap(pm)

    # ──────────────────────────────────────────────────────────────────
    # State change
    # ──────────────────────────────────────────────────────────────────
    def _on_state_changed(self, state: State):
        cfg = _STATE_CFG[state]
        self._status_dot.set_color(cfg["dot"])
        self._session_lbl.setText(t(cfg["label"]))
        if state == State.PAUSED:
            self._pause_btn.set_svg("play")
            self._pause_btn.setToolTip(t("btn_resume"))
        else:
            self._pause_btn.set_svg("pause")
            self._pause_btn.setToolTip(t("btn_pause"))

    def _refresh_warning_labels(self):
        self._warn_lbl.setText(
            f'<span style="color:{C_YELLOW};font-size:14px;">{self._warning_count}</span>'
            f'<span style="color:{C_SUBTEXT};font-size:12px;"> {t("warn_poses")}</span>'
        )
        self._crit_lbl.setText(
            f'<span style="color:#f87171;font-size:14px;">{self._critical_count}</span>'
            f'<span style="color:{C_SUBTEXT};font-size:12px;"> {t("warn_critical")}</span>'
        )

    def _on_warning(self):
        self._warning_count = self.engine.warning_count
        self._critical_count = self.engine.critical_warning_count
        self._refresh_warning_labels()

    def _on_record_saved(self, record: StreakRecord):
        pass  # leaderboard is now a separate window, reloads on open

    def _confirm_reset_stats(self):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(t("reset_confirm_title"))
        dlg.setModal(True)
        dlg.setStyleSheet(
            f"QDialog{{background:{C_BG};border-radius:12px;}}"
            f"QLabel{{color:{C_TEXT};font-size:13px;background:transparent;}}"
        )
        v = QVBoxLayout(dlg); v.setContentsMargins(24, 20, 24, 20); v.setSpacing(16)

        msg = QLabel(t("reset_confirm_msg"))
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        v.addWidget(msg)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)

        cancel_btn = QPushButton(t("reset_no"))
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:{C_BORDER};color:{C_TEXT};font-size:13px;"
            f"border:none;border-radius:8px;padding:0 16px;}}"
            f"QPushButton:hover{{background:{C_HOVER};}}"
        )
        cancel_btn.clicked.connect(dlg.reject)

        confirm_btn = QPushButton(t("reset_yes"))
        confirm_btn.setMinimumHeight(36)
        confirm_btn.setStyleSheet(
            f"QPushButton{{background:#7f1d1d;color:#fca5a5;font-size:13px;font-weight:bold;"
            f"border:none;border-radius:8px;padding:0 16px;}}"
            f"QPushButton:hover{{background:#991b1b;color:white;}}"
        )
        confirm_btn.clicked.connect(dlg.accept)

        btn_row.addWidget(cancel_btn); btn_row.addWidget(confirm_btn)
        v.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            from core.session_tracker import save_records
            save_records([])
            # Reset in-session counters too
            self._good_posture_sec  = 0.0
            self._session_active_sec = 0.0
            self._session_start_time = __import__('time').monotonic()
            self._last_tick_time     = __import__('time').monotonic()
            self._warning_count = 0
            self._critical_count = 0
            self._refresh_warning_labels()
            self._refresh_today_stats(0.0)

    def _open_leaderboard(self):
        from ui.leaderboard_window import LeaderboardWindow
        cfg = load_config()
        dlg = LeaderboardWindow(
            current_strictness=cfg.get("strictness", "medium"),
            parent=self,
        )
        dlg.exec()

    # ──────────────────────────────────────────────────────────────────
    # Controls
    # ──────────────────────────────────────────────────────────────────
    def _toggle_pause(self):
        if self.engine.state == State.PAUSED: self.engine.resume()
        else: self.engine.pause()

    def _toggle_sound(self):
        self._sound_on = not self._sound_on
        # Mute = volume → 0 only; loop keeps running for instant unmute
        self.audio.set_muted(not self._sound_on)
        if self._sound_on:
            self._sound_btn.set_svg("volume2")
            self._sound_btn.setToolTip(t("btn_sound_off"))
        else:
            self._sound_btn.set_svg("volumex")
            self._sound_btn.setToolTip(t("btn_sound_on"))

    def _toggle_camera(self):
        self._cam_on = not self._cam_on
        if self._cam_on:
            self._cam_btn.set_svg("video")
            self._cam_btn.setToolTip(t("btn_cam_off"))
            self._cam_initialized = False
            self._video_label.clear()
            self._video_stack.setCurrentIndex(1)  # show loading
            self.engine.detector.start()
        else:
            self._cam_btn.set_svg("videooff")
            self._cam_btn.setToolTip(t("btn_cam_on"))
            self.engine.detector.stop()
            self._video_label.clear()
            self._video_stack.setCurrentIndex(2)  # cam-off

    def _open_calibration(self):
        from ui.calibration_window import CalibrationWindow
        CalibrationWindow(self.engine, parent=self).exec()

    def _show_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea
        dlg = QDialog(self)
        dlg.setWindowTitle(t("about_title"))
        dlg.setMinimumSize(560, 520)
        dlg.setStyleSheet(f"""
            QDialog, QWidget {{ background:{C_BG}; color:{C_TEXT};
                font-family:"Segoe UI",Arial,sans-serif; font-size:13px; }}
            QLabel {{ background:transparent; }}
            QScrollArea {{ border:none; background:transparent; }}
            QPushButton {{ background:{C_SURFACE}; color:{C_SUBTEXT};
                border:1px solid {C_BORDER}; border-radius:6px;
                padding:6px 20px; min-height:32px; }}
            QPushButton:hover {{ background:{C_BORDER}; color:{C_TEXT}; }}
        """)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(10)

        if _LANG == "ru":
            html = f"""
<h2 style="color:{C_BLUE};margin:0 0 4px 0;">PostureGuard 1.0</h2>
<p style="color:{C_SUBTEXT};margin:0 0 14px 0;">
  Автор: <b style="color:{C_TEXT};">Андрей Марков</b>
</p>

<p>PostureGuard следит за осанкой в реальном времени через веб-камеру
и мягко напоминает выпрямиться, когда вы начинаете сутулиться
или тянуть голову вперёд.</p>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">🎯 Калибровка</h3>
<p>Калибровка — <b>обязательный первый шаг</b>. Она запоминает вашу
правильную позу и служит точкой отсчёта для всех дальнейших измерений.</p>
<ul>
  <li>Сядьте так, как вам <i>комфортно сидеть прямо</i> — не напрягайтесь
      специально, поза должна быть естественной.</li>
  <li>Камера должна быть <b>примерно на уровне глаз</b>, оба плеча в кадре.</li>
  <li>Нажмите «Зафиксировать позу» — начнётся отсчёт 3 секунды,
      после чего эталон сохранится.</li>
  <li><b>Когда перекалибровать:</b> если вы поменяли стул, монитор, расположение
      камеры, или приложение стало давать слишком много ложных срабатываний.</li>
  <li><b>Не стоит</b> калибровать в плохой позе — это обнулит защиту.</li>
</ul>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">⚙️ Настройки</h3>
<ul>
  <li><b>Уровень строгости</b> — как долго (сек) нужно держать плохую позу,
      чтобы сработало напоминание. Начните с «Мягкого», потом ужесточайте.</li>
  <li><b>Громкость звука</b> — можно регулировать ползунком прямо
      на кнопке 🔊 в нижней панели, не заходя в настройки.</li>
  <li><b>Свой звук</b> — можно выбрать любой WAV/MP3/OGG файл вместо встроенного.</li>
  <li><b>Грейс-периоды</b> — время, в течение которого приложение не реагирует
      при временном уходе или взгляде вниз (чай, клавиатура).</li>
  <li><b>Следить за шеей / спиной</b> — можно отключить отдельные метрики,
      если они дают ложные срабатывания.</li>
</ul>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">🎮 Нижняя панель</h3>
<ul>
  <li><b>🔊</b> — вкл/выкл звук. Наведите курсор — появится ползунок громкости.</li>
  <li><b>📷</b> — скрыть/показать видео (трекинг продолжается).</li>
  <li><b>⏸</b> — пауза: отслеживание останавливается, таймер серии сбрасывается.</li>
  <li><b>🧿</b> — открыть окно калибровки.</li>
  <li><b>↓</b> — свернуть в системный трей, приложение продолжит работу.</li>
</ul>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">🏆 Таблица рекордов</h3>
<p>Приложение автоматически записывает лучшие серии хорошей осанки
(от 10 секунд). Рекорды ведутся отдельно для каждого уровня строгости.
Откройте через кнопку в вкладке «Статистика».</p>

<hr style="border:none;border-top:1px solid {C_BORDER};margin:14px 0 10px 0;">
<p style="color:{C_MUTED};font-size:11px;">
  Использует: MediaPipe · OpenCV · PyQt6 · NumPy<br>
  Лицензия: MIT
</p>
"""
        else:
            html = f"""
<h2 style="color:{C_BLUE};margin:0 0 4px 0;">PostureGuard 1.0</h2>
<p style="color:{C_SUBTEXT};margin:0 0 14px 0;">
  Author: <b style="color:{C_TEXT};">Andrey Markov</b>
</p>

<p>PostureGuard monitors your posture in real time using a webcam
and gently reminds you to straighten up when you start slouching
or craning your neck forward.</p>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">🎯 Calibration</h3>
<p>Calibration is a <b>mandatory first step</b>. It memorises your correct
posture and serves as the baseline for all subsequent measurements.</p>
<ul>
  <li>Sit the way you <i>comfortably sit upright</i> — don't force it,
      the pose should feel natural.</li>
  <li>The camera should be <b>roughly at eye level</b>, both shoulders in frame.</li>
  <li>Press «Fix Pose» — a 3-second countdown begins, then the baseline is saved.</li>
  <li><b>When to re-calibrate:</b> if you change your chair, monitor, camera
      position, or the app starts triggering too many false positives.</li>
  <li><b>Don't</b> calibrate while slouching — that defeats the purpose.</li>
</ul>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">⚙️ Settings</h3>
<ul>
  <li><b>Strictness level</b> — how long (sec) you need to hold a bad posture
      before a reminder fires. Start with «Light», then tighten as needed.</li>
  <li><b>Volume</b> — adjust directly via the slider that appears when you
      hover over the 🔊 button in the bottom bar.</li>
  <li><b>Custom sound</b> — choose any WAV/MP3/OGG file instead of the built-in beep.</li>
  <li><b>Grace periods</b> — how long the app ignores posture changes
      when you look away briefly (tea break, keyboard glance).</li>
  <li><b>Track neck / back</b> — disable individual metrics if they trigger
      false positives for your setup.</li>
</ul>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">🎮 Bottom Bar</h3>
<ul>
  <li><b>🔊</b> — mute/unmute. Hover to reveal a volume slider.</li>
  <li><b>📷</b> — hide/show video preview (tracking continues).</li>
  <li><b>⏸</b> — pause: tracking stops, current streak resets.</li>
  <li><b>🧿</b> — open the calibration window.</li>
  <li><b>↓</b> — minimise to system tray; the app keeps running.</li>
</ul>

<h3 style="color:{C_BLUE};margin:12px 0 6px 0;">🏆 Leaderboard</h3>
<p>The app automatically saves your best good-posture streaks (10 sec minimum).
Records are kept separately per strictness level.
Open via the button in the Statistics tab.</p>

<hr style="border:none;border-top:1px solid {C_BORDER};margin:14px 0 10px 0;">
<p style="color:{C_MUTED};font-size:11px;">
  Powered by: MediaPipe · OpenCV · PyQt6 · NumPy<br>
  License: MIT
</p>
"""

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QLabel(html)
        content.setWordWrap(True)
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        content.setContentsMargins(4, 0, 8, 0)
        scroll.setWidget(content)
        root.addWidget(scroll)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(100)
        ok_btn.clicked.connect(dlg.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(ok_btn)
        root.addLayout(row)

        dlg.exec()

    # ──────────────────────────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────────────────────────
    def _auto_save(self, *_):
        """Save all settings immediately — called on any change."""
        cfg = load_config()
        cfg["use_default_sound"] = self._use_default_cb.isChecked()
        sound = self._sound_path_edit.text().strip()
        cfg["sound_file"] = sound or None
        cfg["track_neck"] = self._track_neck_cb.isChecked()
        cfg["track_back"] = self._track_back_cb.isChecked()
        for key, spin in self._grace_spins.items():
            cfg[key] = spin.value()
        save_config(cfg)
        self.engine.reload_config(cfg)
        sf = cfg.get("sound_file") if not cfg.get("use_default_sound", True) else None
        self.audio.set_sound(sf)
        if self._sound_on:
            self.audio.set_volume(cfg.get("volume", 0.8))

    def _on_strictness_btn(self, key: str):
        self._set_strictness_buttons(key)
        cfg = load_config(); cfg["strictness"] = key
        cfg[f"{key}_timeout_sec"] = self._timeout_spin.value()
        save_config(cfg); self.engine.reload_config(cfg)
        self._tracker.set_strictness(key)

    def _set_strictness_buttons(self, active: str):
        for key, btn in self._strict_btns.items():
            if key == active:
                col = _STRICTNESS_COLORS[key]
                btn.setStyleSheet(
                    f"QPushButton{{background:{col};color:white;"
                    f"border-radius:6px;font-size:13px;font-weight:bold;border:none;"
                    f"min-height:36px;padding:4px 12px;}}"
                    f"QPushButton:hover{{background:{col};}}")
                btn.setChecked(True)
            else:
                btn.setStyleSheet(
                    f"QPushButton{{background:{C_BORDER};color:{C_SUBTEXT};"
                    f"border-radius:6px;font-size:13px;border:none;"
                    f"min-height:36px;padding:4px 12px;}}"
                    f"QPushButton:hover{{background:{C_HOVER};color:white;}}")
                btn.setChecked(False)

    def _on_default_sound_toggle(self, checked: bool):
        self._sound_path_edit.setEnabled(not checked)
        self._auto_save()

    def _browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("open_file"), "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)")
        if path:
            self._sound_path_edit.setText(path)
            self._use_default_cb.setChecked(False)
            self._auto_save()

    def _set_volume_from_popup(self, val: int):
        """Called by hover popup — syncs to settings slider too."""
        self.audio.set_volume(val / 100.0)
        if hasattr(self, '_vol_slider'):
            self._vol_slider.blockSignals(True)
            self._vol_slider.setValue(val)
            self._vol_slider.blockSignals(False)
            self._vol_val_lbl.setText(f"{val}%")
        # save config immediately
        cfg = load_config(); cfg["volume"] = val / 100.0; save_config(cfg)

    def _on_volume_changed(self, val: int):
        self._vol_val_lbl.setText(f"{val}%")
        self.audio.set_volume(val / 100.0)  # instant, no I/O
        # sync hover popup slider
        if hasattr(self, '_vol_popup'):
            self._vol_popup.sync()

    def _save_volume_cfg(self):
        val = self._vol_slider.value()
        cfg = load_config(); cfg["volume"] = val / 100.0; save_config(cfg)

    def _save_settings(self):
        self._auto_save()

    def _show_lang_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background:{C_SURFACE}; color:{C_TEXT};
                border:1px solid {C_BORDER}; border-radius:8px;
                padding:4px;
                font-size:13px;
            }}
            QMenu::item {{
                padding:7px 20px 7px 12px;
                border-radius:5px;
            }}
            QMenu::item:selected {{
                background:{C_HOVER}; color:white;
            }}
            QMenu::item:checked {{
                color:{C_BLUE}; font-weight:bold;
            }}
        """)
        for code, label in [("ru", "Русский"), ("en", "English")]:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(_LANG == code)
            action.setData(code)
        chosen = menu.exec(self._lang_btn.mapToGlobal(
            self._lang_btn.rect().bottomLeft()))
        if chosen:
            self._on_lang_btn(chosen.data())

    def _on_lang_btn(self, lang: str):
        set_lang(lang)
        cfg = load_config(); cfg["language"] = lang; save_config(cfg)
        self._lang_btn.setText(lang.upper())
        self._rebuild_ui()

    def _rebuild_ui(self):
        """Rebuild both sidebar panels in-place with new language strings."""
        cfg = load_config()
        # Rebuild stats panel
        new_stats = self._build_stats_panel()
        self._sidebar_stack.removeWidget(self._sidebar_stack.widget(0))
        self._sidebar_stack.insertWidget(0, new_stats)
        # Rebuild settings panel
        new_settings = self._build_settings_panel(cfg)
        self._sidebar_stack.removeWidget(self._sidebar_stack.widget(1))
        self._sidebar_stack.insertWidget(1, new_settings)
        # Restore current tab
        self._sidebar_stack.setCurrentIndex(1)
        # Update tab bar labels
        self._tab_stats.setText(t("tab_stats"))
        self._tab_settings.setText(t("tab_settings"))
        # Update bottom bar tooltips
        self._session_lbl.setText(t(_STATE_CFG[self.engine.state]["label"]))
        self._sound_btn.setToolTip(t("btn_sound_off") if self._sound_on else t("btn_sound_on"))
        self._cam_btn.setToolTip(t("btn_cam_off") if self._cam_on else t("btn_cam_on"))
        self._settings_btn.setToolTip(t("btn_settings"))
        self._stats_btn.setToolTip(t("btn_stats"))
        self._pause_btn.setToolTip(
            t("btn_resume") if self.engine.state.name == "PAUSED" else t("btn_pause")
        )
        self._cal_btn.setToolTip(t("btn_calibrate"))
        self._info_btn.setToolTip(t("btn_about_info"))
        self._tray_btn.setToolTip(t("btn_tray"))
        self._chevron_btn.setToolTip(t("hide_panel"))

    def closeEvent(self, event):
        event.ignore(); self.hide()

