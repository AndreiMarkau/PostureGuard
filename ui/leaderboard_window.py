"""
leaderboard_window.py — Redesigned Leaderboard + Stats window for PostureGuard.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │  [Activity heatmap]  │  [Progress line chart]       │
  ├─────────────────────────────────────────────────────┤
  │  [Toggle: All time | Today]                         │
  │  Top-10 records table (tabs: Light / Medium / Hard) │
  └─────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from PyQt6.QtCore import Qt, QSize, QRect, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QWidget, QSizePolicy,
)

from core.session_tracker import load_records, StreakRecord
from core.calibration import load_config

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG      = "#202124"
C_SURFACE = "#292a2d"
C_BORDER  = "#3c4043"
C_HOVER   = "#4d5156"
C_MUTED   = "#5f6368"
C_TEXT    = "#e8eaed"
C_SUBTEXT = "#9ca3af"
C_BLUE    = "#8ab4f8"
C_GREEN   = "#4ade80"
C_YELLOW  = "#fbbf24"
C_RED     = "#f87171"

# Strictness → colour mapping
S_COLOR   = {"soft": C_GREEN, "medium": C_YELLOW, "hard": C_RED}
S_ALPHA   = {"soft": 60,      "medium": 50,       "hard": 50}   # fill alpha 0-255
S_KEYS    = ["soft", "medium", "hard"]

_STRINGS = {
    "title":      {"ru": "Статистика и рекорды",         "en": "Stats & Records"},
    "win_title":  {"ru": "Статистика — PostureGuard",    "en": "Statistics — PostureGuard"},
    "close":      {"ru": "Закрыть",                      "en": "Close"},
    "toggle_all": {"ru": "За всё время",                 "en": "All time"},
    "toggle_today":{"ru": "Сегодня",                    "en": "Today"},
    "empty":      {"ru": "Рекордов пока нет — начните тренировку!",
                   "en": "No records yet — start a session!"},
    "col_rank":   {"ru": "#",            "en": "#"},
    "col_date":   {"ru": "Дата",         "en": "Date"},
    "col_time":   {"ru": "Время",        "en": "Time"},
    "col_dur":    {"ru": "Длительность", "en": "Duration"},
    "tab_soft":   {"ru": "Мягкий",   "en": "Light"},
    "tab_medium": {"ru": "Средний",  "en": "Medium"},
    "tab_hard":   {"ru": "Строгий",  "en": "Hard"},
    "chart_days": {"ru": "дн.",          "en": "d"},
    "legend_soft":  {"ru": "Мягкий",    "en": "Light"},
    "legend_medium":{"ru": "Средний",   "en": "Medium"},
    "legend_hard":  {"ru": "Строгий",   "en": "Hard"},
    "heatmap_lbl":  {"ru": "Активность","en": "Activity"},
    "stats_streak":       {"ru": "🔥 Дней подряд",                   "en": "🔥 Days in a row"},
    "stats_best_streak":  {"ru": "🏆 Лучший результат",              "en": "🏆 Best result"},
    "stats_best_day":     {"ru": "⏱ Лучшее суммарное время за день", "en": "⏱ Best total time per day"},
    "stats_best_quality": {"ru": "✅ Лучший процент качества за день","en": "✅ Best posture quality per day"},
    "stats_mode_soft":    {"ru": "мягкий",  "en": "light"},
    "stats_mode_medium":  {"ru": "средний", "en": "medium"},
    "stats_mode_hard":    {"ru": "строгий", "en": "hard"},
    "stats_no_data":      {"ru": "—",       "en": "—"},
    "stats_days_suffix":  {"ru": "дн.",     "en": "d"},
    "tip_total":          {"ru": "Итого",         "en": "Total"},
    "tip_max_streak":     {"ru": "Макс. серия",   "en": "Best streak"},
}
_TAB_KEYS = ["soft", "medium", "hard"]

def _lang() -> str:
    # Prefer the already-resolved _LANG from main_window to avoid
    # re-reading config (which may lack the "language" key entirely)
    try:
        from ui.main_window import _LANG as _mw_lang
        return _mw_lang
    except Exception:
        return load_config().get("language", "ru")

def _t(key: str) -> str:
    d = _STRINGS.get(key, {})
    lang = _lang()
    return d.get(lang, d.get("ru", key))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_dur(sec: float) -> str:
    total_ds = int(sec * 10)
    ds = total_ds % 10
    s  = (total_ds // 10) % 60
    m  = (total_ds // 600) % 60
    h  = total_ds // 36000
    return f"{h:02d}:{m:02d}:{s:02d}.{ds}"

def _hex_to_qcolor(h: str, alpha: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(alpha)
    return c


# ── Activity Heatmap ──────────────────────────────────────────────────────────

class HeatmapWidget(QWidget):
    """GitHub-style activity calendar (last 17 weeks × 7 days)."""

    CELL  = 11
    GAP   = 3
    COLS  = 17    # weeks shown
    ROWS  = 7     # Mon–Sun

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict[str, float] = {}   # date-str → total seconds
        self._max_sec = 1.0
        w = self.COLS * (self.CELL + self.GAP) + 24   # extra for day labels
        h = self.ROWS * (self.CELL + self.GAP) + 30   # extra for month labels
        self.setFixedSize(w, h)
        self.setToolTip("")

    def load(self, records: list[StreakRecord]):
        day_totals: dict[str, float] = defaultdict(float)
        for r in records:
            day_totals[r.date] += r.duration_sec
        self._data = dict(day_totals)
        self._max_sec = max(day_totals.values(), default=1.0)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        today = date.today()
        # Start from Monday of 17 weeks ago
        start = today - timedelta(weeks=self.COLS - 1)
        start -= timedelta(days=start.weekday())   # back to Monday

        ox = 20   # left offset (for day labels)
        oy = 18   # top offset (for month labels)

        # Month labels
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor(C_SUBTEXT))
        prev_month = -1
        for col in range(self.COLS):
            d = start + timedelta(weeks=col)
            if d.month != prev_month:
                x = ox + col * (self.CELL + self.GAP)
                p.drawText(x, oy - 4, d.strftime("%b"))
                prev_month = d.month

        # Day labels (Mon / Wed / Fri)
        for row, label in ((0, "M"), (2, "W"), (4, "F")):
            y = oy + row * (self.CELL + self.GAP) + self.CELL - 2
            p.drawText(0, y, label)

        # Cells
        for col in range(self.COLS):
            for row in range(self.ROWS):
                d = start + timedelta(weeks=col, days=row)
                if d > today:
                    continue
                ds = d.isoformat()
                sec = self._data.get(ds, 0.0)
                intensity = min(sec / self._max_sec, 1.0) if self._max_sec > 0 else 0.0

                x = ox + col * (self.CELL + self.GAP)
                y = oy + row * (self.CELL + self.GAP)

                # Colour: dark surface → bright green
                if intensity == 0:
                    color = QColor(C_SURFACE)
                else:
                    # interpolate surface → C_GREEN
                    bg = QColor(C_SURFACE)
                    fg = QColor(C_GREEN)
                    t  = intensity
                    r = int(bg.red()   + (fg.red()   - bg.red())   * t)
                    g = int(bg.green() + (fg.green() - bg.green()) * t)
                    b = int(bg.blue()  + (fg.blue()  - bg.blue())  * t)
                    color = QColor(r, g, b)

                # Today highlight
                is_today = (d == today)
                if is_today:
                    p.setPen(QPen(QColor(C_BLUE), 1))
                else:
                    p.setPen(Qt.PenStyle.NoPen)

                p.setBrush(QBrush(color))
                p.drawRoundedRect(x, y, self.CELL, self.CELL, 2, 2)

        p.end()

    def mouseMoveEvent(self, event):
        today = date.today()
        start = today - timedelta(weeks=self.COLS - 1)
        start -= timedelta(days=start.weekday())
        ox, oy = 20, 18
        for col in range(self.COLS):
            for row in range(self.ROWS):
                d = start + timedelta(weeks=col, days=row)
                x = ox + col * (self.CELL + self.GAP)
                y = oy + row * (self.CELL + self.GAP)
                if QRect(x, y, self.CELL, self.CELL).contains(event.pos()):
                    sec = self._data.get(d.isoformat(), 0.0)
                    m, s = divmod(int(sec), 60)
                    h, m = divmod(m, 60)
                    self.setToolTip(f"{d.strftime('%d %b %Y')}  {h:02d}:{m:02d}:{s:02d}")
                    return
        self.setToolTip("")


# ── Progress Chart ────────────────────────────────────────────────────────────

class ProgressChart(QWidget):
    """Line chart: x=date, y=total streak seconds per strictness.
    Also draws thin vertical bars for the daily maximum streak,
    coloured by the mode in which that maximum was achieved.
    Rich tooltip on hover shows date, per-mode totals and daily max.
    """

    DAYS = 30   # show last 30 days

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: dict[str, list[tuple[str, float]]] = {k: [] for k in S_KEYS}
        # per-day maximum single streak and its mode
        self._day_max: dict[str, tuple[float, str]] = {}   # date → (sec, strictness)
        # per-day totals across all modes  (for tooltip)
        self._day_total: dict[str, float] = {}
        # cached pixel columns for hit-testing
        self._col_xs: list[int] = []
        self._days: list[str] = []
        self._pad = (44, 12, 12, 28)   # l, r, t, b
        self._tooltip_widget: "_ChartTooltip | None" = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    def load(self, records: list):
        today = date.today()
        days  = [(today - timedelta(days=i)).isoformat() for i in range(self.DAYS - 1, -1, -1)]
        self._days = days
        by_day: dict[str, dict[str, float]] = {d: {k: 0.0 for k in S_KEYS} for d in days}
        day_max: dict[str, tuple[float, str]] = {d: (0.0, "soft") for d in days}

        for r in records:
            if r.date in by_day and r.strictness in S_KEYS:
                by_day[r.date][r.strictness] += r.duration_sec
                cur_max, _ = day_max[r.date]
                if r.duration_sec > cur_max:
                    day_max[r.date] = (r.duration_sec, r.strictness)

        for k in S_KEYS:
            self._series[k] = [(d, by_day[d][k]) for d in days]

        self._day_max   = day_max
        self._day_total = {d: sum(by_day[d][k] for k in S_KEYS) for d in days}
        self.update()

    # ── helpers ────────────────────────────────────────────────────────────────

    def _layout(self):
        pad_l, pad_r, pad_t, pad_b = self._pad
        cw = self.width()  - pad_l - pad_r
        ch = self.height() - pad_t - pad_b
        return pad_l, pad_r, pad_t, pad_b, cw, ch

    def _col_x(self, i: int, n: int, pad_l: int, cw: int) -> int:
        return pad_l + int(i / max(n - 1, 1) * cw)

    # ── paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pad_l, pad_r, pad_t, pad_b, cw, ch = self._layout()
        if cw <= 0 or ch <= 0:
            p.end(); return

        # Compute max value across totals AND individual maxima (for bar scale)
        all_vals = [v for k in S_KEYS for _, v in self._series[k]]
        all_vals += [sec for sec, _ in self._day_max.values()]
        max_val  = max(all_vals, default=1.0) or 1.0

        n = len(self._series[S_KEYS[0]]) if self._series[S_KEYS[0]] else 0

        # ── Grid lines + Y labels ──────────────────────────────────
        p.setFont(QFont("Segoe UI", 7))
        grid_col = QColor(C_BORDER)
        for i in range(5):
            y = pad_t + ch - int(i / 4 * ch)
            sec = max_val * i / 4
            m2, s2 = divmod(int(sec), 60)
            h2, m2 = divmod(m2, 60)
            lbl = f"{h2}h" if h2 else f"{m2}m"
            p.setPen(grid_col)
            p.drawLine(pad_l, y, pad_l + cw, y)
            p.setPen(QColor(C_SUBTEXT))
            p.drawText(QRect(0, y - 8, pad_l - 4, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)

        # ── X axis labels (every ~7 days) ──────────────────────────
        xs: list[int] = []
        for i in range(n):
            xs.append(self._col_x(i, n, pad_l, cw))
        self._col_xs = xs

        for i in range(0, n, 7):
            lbl = self._days[i][5:] if i < len(self._days) else ""
            p.setPen(QColor(C_SUBTEXT))
            p.drawText(QRect(xs[i] - 20, pad_t + ch + 4, 40, 20),
                       Qt.AlignmentFlag.AlignCenter, lbl)

        # ── Daily-max bars (drawn first, below everything) ─────────
        BAR_W = 3
        for i, ds in enumerate(self._days):
            sec, mode = self._day_max.get(ds, (0.0, "soft"))
            if sec <= 0:
                continue
            x  = xs[i] if i < len(xs) else self._col_x(i, n, pad_l, cw)
            bh = int(sec / max_val * ch)
            y  = pad_t + ch - bh
            color = QColor(S_COLOR.get(mode, C_SUBTEXT))
            color.setAlpha(130)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(x - BAR_W // 2, y, BAR_W, bh, 1, 1)

        # ── Series lines + gradient fills ─────────────────────────
        for key in S_KEYS:
            pts = self._series[key]
            if not pts:
                continue
            color      = QColor(S_COLOR[key])
            fill_color = QColor(S_COLOR[key])
            fill_color.setAlpha(S_ALPHA[key])

            coords = [(xs[i], pad_t + ch - int(v / max_val * ch))
                      for i, (_, v) in enumerate(pts)]

            if len(coords) >= 2:
                path = QPainterPath()
                path.moveTo(coords[0][0], pad_t + ch)
                path.lineTo(coords[0][0], coords[0][1])
                for x, y in coords[1:]:
                    path.lineTo(x, y)
                path.lineTo(coords[-1][0], pad_t + ch)
                path.closeSubpath()
                p.setBrush(QBrush(fill_color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(path)

            pen = QPen(color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(len(coords) - 1):
                p.drawLine(coords[i][0], coords[i][1],
                           coords[i+1][0], coords[i+1][1])

        # ── Legend ─────────────────────────────────────────────────
        lx = pad_l + 6
        ly = pad_t + 6
        p.setFont(QFont("Segoe UI", 8))
        legend_keys = [("soft",   _t("legend_soft")),
                       ("medium", _t("legend_medium")),
                       ("hard",   _t("legend_hard"))]
        for key, label in legend_keys:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(S_COLOR[key])))
            p.drawEllipse(lx, ly + 3, 7, 7)
            p.setPen(QColor(C_SUBTEXT))
            p.drawText(lx + 11, ly + 11, label)
            lx += len(label) * 7 + 22

        p.end()

    # ── Mouse → tooltip ────────────────────────────────────────────────────────

    def _hit_index(self, pos: QPoint) -> int | None:
        """Return day index closest to mouse x within ±touch zone."""
        if not self._col_xs:
            return None
        mx = pos.x()
        # column spacing
        step = (self._col_xs[-1] - self._col_xs[0]) / max(len(self._col_xs) - 1, 1) if len(self._col_xs) > 1 else 20
        half = max(int(step / 2), 6)
        best, best_dist = None, half + 1
        for i, cx in enumerate(self._col_xs):
            d = abs(mx - cx)
            if d < best_dist:
                best, best_dist = i, d
        return best

    def mouseMoveEvent(self, event):
        idx = self._hit_index(event.pos())
        if idx is None or idx >= len(self._days):
            self._hide_tooltip()
            return

        ds = self._days[idx]
        total = self._day_total.get(ds, 0.0)
        max_sec, max_mode = self._day_max.get(ds, (0.0, "soft"))

        lines = [ds]
        # per-mode totals
        for k in S_KEYS:
            val = self._series[k][idx][1] if idx < len(self._series[k]) else 0.0
            if val > 0:
                label = _mode_label(k)
                lines.append(f"{label}: {_fmt_dur(val)}")
        # total
        if total > 0:
            lines.append(f"{_t('tip_total')}: {_fmt_dur(total)}")
            lines.append(f"{_t('tip_max_streak')}: {_fmt_dur(max_sec)}  ({_mode_label(max_mode)})")

        if total == 0:
            self._hide_tooltip()
            return

        # show tooltip near cursor
        global_pos = self.mapToGlobal(event.pos()) + QPoint(14, -10)
        self._show_tooltip("\n".join(lines), global_pos)

    def leaveEvent(self, _event):
        self._hide_tooltip()

    def _show_tooltip(self, text: str, global_pos: QPoint):
        if self._tooltip_widget is None:
            self._tooltip_widget = _ChartTooltip()
        self._tooltip_widget.set_text(text)
        self._tooltip_widget.move(global_pos)
        self._tooltip_widget.show()

    def _hide_tooltip(self):
        if self._tooltip_widget is not None:
            self._tooltip_widget.hide()


class _ChartTooltip(QWidget):
    """Floating dark tooltip panel for the chart."""

    def __init__(self):
        super().__init__(None,
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._lines: list[str] = []
        self.setFont(QFont("Segoe UI", 10))

    def set_text(self, text: str):
        self._lines = text.split("\n")
        self._relayout()
        self.update()

    def _relayout(self):
        fm = self.fontMetrics()
        w = max((fm.horizontalAdvance(l) for l in self._lines), default=60) + 24
        h = len(self._lines) * (fm.height() + 4) + 16
        self.setFixedSize(w, h)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # background
        bg = QColor(C_SURFACE)
        bg.setAlpha(230)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(C_BORDER), 1))
        p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 8, 8)

        fm = self.fontMetrics()
        lh = fm.height() + 4
        y  = 10
        for i, line in enumerate(self._lines):
            if i == 0:
                p.setPen(QColor(C_TEXT))
                p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            else:
                p.setPen(QColor(C_SUBTEXT))
                p.setFont(QFont("Segoe UI", 10))
            p.drawText(12, y + fm.ascent(), line)
            y += lh
        p.end()


# ── Toggle bar ────────────────────────────────────────────────────────────────

class FilterBar(QWidget):
    """Single row: pill toggle (All / Today) on the left,
    pill group (Soft / Medium / Hard) on the right.
    Callbacks: on_period(0|1), on_mode(key_str).
    """

    _MODES = ["soft", "medium", "hard"]

    def __init__(self, on_period, on_mode, parent=None):
        super().__init__(parent)
        self._on_period = on_period
        self._on_mode   = on_mode
        self._period    = 0   # 0=all, 1=today
        self._mode_idx  = 1   # default: medium

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Period pill ───────────────────────────────────────────
        self._period_pill = _PillGroup(
            [_t("toggle_all"), _t("toggle_today")],
            self._period,
            self._period_changed,
            accent=C_BLUE,
        )
        layout.addWidget(self._period_pill)

        layout.addStretch()

        # ── Mode pill ─────────────────────────────────────────────
        mode_labels = [_t("tab_soft"), _t("tab_medium"), _t("tab_hard")]
        mode_colors = [S_COLOR["soft"], S_COLOR["medium"], S_COLOR["hard"]]
        self._mode_pill = _PillGroup(
            mode_labels,
            self._mode_idx,
            self._mode_changed,
            accent_list=mode_colors,
        )
        layout.addWidget(self._mode_pill)

    def _period_changed(self, idx: int):
        self._period = idx
        self._on_period(idx)

    def _mode_changed(self, idx: int):
        self._mode_idx = idx
        self._on_mode(self._MODES[idx])

    def current_mode(self) -> str:
        return self._MODES[self._mode_idx]

    def set_mode(self, key: str):
        if key in self._MODES:
            idx = self._MODES.index(key)
            self._mode_idx = idx
            self._mode_pill.set_selected(idx)


class _PillGroup(QWidget):
    """Horizontal pill-style button group.
    accent        – single color for all selected states
    accent_list   – per-tab colors (overrides accent)
    """

    def __init__(self, labels, selected, on_change, accent=None, accent_list=None, parent=None):
        super().__init__(parent)
        self._labels      = labels
        self._selected    = selected
        self._on_change   = on_change
        self._accent      = accent or C_BLUE
        self._accent_list = accent_list   # list[str] | None
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_selected(self, idx: int):
        self._selected = idx
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n   = len(self._labels)
        w   = self.width()
        h   = self.height()
        seg = w // n

        # Container background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C_SURFACE))
        p.drawRoundedRect(0, 0, w, h, 7, 7)

        # Border
        pen = QPen(QColor(C_BORDER), 1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, w - 1, h - 1, 7, 7)
        p.setPen(Qt.PenStyle.NoPen)

        # Active pill
        ax = self._selected * seg
        accent = (QColor(self._accent_list[self._selected])
                  if self._accent_list else QColor(self._accent))
        accent.setAlpha(200)
        p.setBrush(accent)
        p.drawRoundedRect(ax + 2, 2, seg - 4, h - 4, 5, 5)

        # Separators between tabs
        p.setPen(QPen(QColor(C_BORDER), 1))
        for i in range(1, n):
            x = i * seg
            p.drawLine(x, 4, x, h - 4)

        # Labels
        p.setFont(QFont("Segoe UI", 11))
        for i, lbl in enumerate(self._labels):
            x   = i * seg
            txt_color = (QColor(C_TEXT) if i == self._selected
                         else QColor(C_SUBTEXT))
            p.setPen(txt_color)
            p.drawText(QRect(x, 0, seg, h), Qt.AlignmentFlag.AlignCenter, lbl)

        p.end()

    def mousePressEvent(self, event):
        n   = len(self._labels)
        idx = min(int(event.pos().x() / (self.width() / n)), n - 1)
        if idx != self._selected:
            self._selected = idx
            self.update()
            self._on_change(idx)

    def sizeHint(self):
        fm   = self.fontMetrics()
        w    = sum(fm.horizontalAdvance(l) + 36 for l in self._labels)
        return QSize(w, 30)


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _compute_stats(records: list) -> dict:
    """Compute summary statistics from all records."""
    from collections import defaultdict

    if not records:
        return {}

    # ── Consecutive active days (streak) ──────────────────────────────────────
    active_days = sorted({r.date for r in records}, reverse=True)
    streak = 0
    if active_days:
        check = date.today()
        for ds in active_days:
            d = date.fromisoformat(ds)
            if d == check or d == check - timedelta(days=1):
                streak += 1
                check = d - timedelta(days=1)  # next expected day
            elif d < check:
                break

    # ── Best single streak record ─────────────────────────────────────────────
    best_rec = max(records, key=lambda r: r.duration_sec)

    # ── Best total active time in a single day ────────────────────────────────
    day_totals: dict[str, float] = defaultdict(float)
    for r in records:
        day_totals[r.date] += r.duration_sec
    best_day_date, best_day_sec = max(day_totals.items(), key=lambda x: x[1])

    # ── Best posture quality % for a day ─────────────────────────────────────
    # Quality = total good-posture time / total possible time in that day's
    # sessions. We approximate: for each record we know the wall-clock window
    # (time_from → time_to) and duration_sec (actual good posture).
    # quality_day = sum(duration_sec) / sum(window_sec) * 100
    day_window: dict[str, float] = defaultdict(float)
    day_good:   dict[str, float] = defaultdict(float)
    for r in records:
        try:
            from datetime import datetime as _dt
            t0 = _dt.strptime(r.time_from, "%H:%M")
            t1 = _dt.strptime(r.time_to,   "%H:%M")
            window = (t1 - t0).total_seconds()
            if window <= 0:
                window = r.duration_sec   # fallback: same-minute entries
        except Exception:
            window = r.duration_sec
        day_window[r.date] += window
        day_good[r.date]   += r.duration_sec

    best_quality_day  = max(day_good, key=lambda d: (
        day_good[d] / max(day_window[d], 1.0) if day_window[d] else 0.0
    ))
    best_quality_pct = (
        day_good[best_quality_day] / max(day_window[best_quality_day], 1.0) * 100
    )

    return {
        "streak":           streak,
        "best_rec":         best_rec,
        "best_day_date":    best_day_date,
        "best_day_sec":     best_day_sec,
        "best_quality_day": best_quality_day,
        "best_quality_pct": best_quality_pct,
    }


def _mode_label(strictness: str) -> str:
    key = f"stats_mode_{strictness}"
    return _t(key) if key in _STRINGS else strictness


# ── Stats Block ───────────────────────────────────────────────────────────────

class StatsBlock(QWidget):
    """Four-cell text statistics row shown below the heatmap."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: list = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)

        self._cells: list[tuple[QLabel, QLabel]] = []
        for _ in range(4):
            cell = QWidget()
            cell.setStyleSheet(
                f"background:{C_SURFACE}; border:1px solid {C_BORDER}; border-radius:8px;"
            )
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(12, 8, 12, 8)
            cell_layout.setSpacing(2)

            lbl_title = QLabel()
            lbl_title.setStyleSheet(f"color:{C_SUBTEXT}; font-size:11px; border:none;")
            lbl_title.setWordWrap(True)

            lbl_value = QLabel()
            lbl_value.setStyleSheet(
                f"color:{C_TEXT}; font-size:15px; font-weight:bold; border:none;"
            )
            lbl_value.setWordWrap(True)

            cell_layout.addWidget(lbl_title)
            cell_layout.addWidget(lbl_value)
            layout.addWidget(cell, stretch=1)
            self._cells.append((lbl_title, lbl_value))

    def load(self, records: list):
        self._records = records
        self._refresh()

    def _refresh(self):
        nd = _t("stats_no_data")
        stats = _compute_stats(self._records)

        # ── Cell 0: consecutive days ───────────────────────────────
        t0, v0 = self._cells[0]
        t0.setText(_t("stats_streak"))
        if stats:
            days_sfx = _t("stats_days_suffix")
            v0.setText(f"{stats['streak']} {days_sfx}")
            v0.setStyleSheet(
                f"color:{C_GREEN if stats['streak'] > 0 else C_SUBTEXT};"
                f" font-size:15px; font-weight:bold; border:none;"
            )
        else:
            v0.setText(nd)

        # ── Cell 1: best single streak record ─────────────────────
        t1, v1 = self._cells[1]
        t1.setText(_t("stats_best_streak"))
        if stats:
            r = stats["best_rec"]
            mode = _mode_label(r.strictness)
            v1.setText(f"{_fmt_dur(r.duration_sec)}  ({mode})")
            color = S_COLOR.get(r.strictness, C_TEXT)
            v1.setStyleSheet(
                f"color:{color}; font-size:13px; font-weight:bold; border:none;"
            )
        else:
            v1.setText(nd)

        # ── Cell 2: best total time in a day ──────────────────────
        t2, v2 = self._cells[2]
        t2.setText(_t("stats_best_day"))
        if stats:
            v2.setText(f"{_fmt_dur(stats['best_day_sec'])}  ({stats['best_day_date']})")
            v2.setStyleSheet(
                f"color:{C_BLUE}; font-size:13px; font-weight:bold; border:none;"
            )
        else:
            v2.setText(nd)

        # ── Cell 3: best quality % ─────────────────────────────────
        t3, v3 = self._cells[3]
        t3.setText(_t("stats_best_quality"))
        if stats:
            pct = stats["best_quality_pct"]
            d   = stats["best_quality_day"]
            v3.setText(f"{pct:.0f}%  ({d})")
            color = (C_GREEN if pct >= 80 else C_YELLOW if pct >= 50 else C_RED)
            v3.setStyleSheet(
                f"color:{color}; font-size:15px; font-weight:bold; border:none;"
            )
        else:
            v3.setText(nd)


# ── Leaderboard window ────────────────────────────────────────────────────────

class LeaderboardWindow(QDialog):
    def __init__(self, current_strictness: str = "medium", parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("win_title"))
        self.resize(820, 620)
        self.setMinimumSize(680, 500)
        self._today_only = False
        self._records: list[StreakRecord] = []

        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {C_BG};
                color: {C_TEXT};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 13px;
            }}
            QTabWidget::pane {{ border: none; background: {C_BG}; }}
            QTabBar::tab {{
                background: {C_SURFACE}; color: {C_SUBTEXT};
                padding: 6px 20px; font-size: 13px;
                border: 1px solid {C_BORDER};
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                margin-right: 3px;
            }}
            QTabBar::tab:selected {{ background: {C_BG}; color: {C_BLUE}; }}
            QTabBar::tab:hover    {{ color: {C_TEXT}; }}
            QTableWidget {{
                background: {C_BG}; color: {C_TEXT};
                font-size: 13px; border: none;
                alternate-background-color: {C_SURFACE};
                gridline-color: transparent;
            }}
            QHeaderView::section {{
                background: {C_SURFACE}; color: {C_SUBTEXT};
                font-size: 11px; font-weight: bold;
                letter-spacing: 1px; padding: 6px 8px;
                border: none; border-bottom: 1px solid {C_BORDER};
            }}
            QTableWidget::item:selected {{ background: #1a3a5a; color: white; }}
            QPushButton {{
                border-radius: 6px; font-size: 13px;
                padding: 6px 16px; min-height: 32px;
            }}
            QScrollBar:vertical {{
                background: {C_SURFACE}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {C_MUTED}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QToolTip {{
                background: {C_SURFACE}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                font-size: 11px; padding: 4px 8px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Fixed top block (does not grow when window is resized) ─
        top_block = QWidget()
        top_block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tb = QVBoxLayout(top_block)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(14)

        # ── Header ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title_lbl = QLabel(_t("title"))
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color:{C_TEXT};")
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        tb.addLayout(hdr)

        # ── Top: heatmap + chart ───────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # Heatmap block
        hmap_col = QVBoxLayout()
        hmap_col.setSpacing(4)
        hmap_lbl = QLabel(_t("heatmap_lbl"))
        hmap_lbl.setStyleSheet(f"color:{C_SUBTEXT}; font-size:11px; font-weight:bold; letter-spacing:1px;")
        hmap_col.addWidget(hmap_lbl)
        self._heatmap = HeatmapWidget()
        self._heatmap.setMouseTracking(True)
        hmap_col.addWidget(self._heatmap)
        hmap_col.addStretch()
        top_row.addLayout(hmap_col)

        # Chart block
        chart_col = QVBoxLayout()
        chart_col.setSpacing(4)
        self._chart = ProgressChart()
        self._chart.setFixedHeight(160)
        chart_col.addWidget(self._chart)
        chart_col.addStretch()
        top_row.addLayout(chart_col, stretch=1)

        tb.addLayout(top_row)

        # ── Stats block ────────────────────────────────────────────
        self._stats_block = StatsBlock()
        tb.addWidget(self._stats_block)

        # Divider
        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet(f"background:{C_BORDER};")
        tb.addWidget(div)

        # ── Filter bar (period + mode in one row) ─────────────────
        self._filter_bar = FilterBar(
            on_period=self._on_period_changed,
            on_mode=self._on_mode_changed,
        )
        tb.addWidget(self._filter_bar)

        root.addWidget(top_block)

        # ── Table (stretches to fill remaining space) ──────────────
        self._table = self._make_table()
        root.addWidget(self._table, stretch=1)

        if current_strictness in _TAB_KEYS:
            self._filter_bar.set_mode(current_strictness)
        self.reload()

    # ── Data loading ───────────────────────────────────────────────

    def reload(self):
        self._records = load_records()
        self._heatmap.load(self._records)
        self._chart.load(self._records)
        self._stats_block.load(self._records)
        self._populate_tables()

    def _on_period_changed(self, idx: int):
        self._today_only = (idx == 1)
        self._populate_tables()

    def _on_mode_changed(self, _key: str):
        self._populate_tables()

    def _populate_tables(self):
        today_str = date.today().isoformat()
        records = self._records
        if self._today_only:
            records = [r for r in records if r.date == today_str]

        key  = self._filter_bar.current_mode()
        recs = [r for r in records if r.strictness == key]
        recs.sort(key=lambda r: r.duration_sec, reverse=True)
        top10 = recs[:10]
        tbl   = self._table
        tbl.setRowCount(0)

        if not top10:
            tbl.insertRow(0)
            item = QTableWidgetItem(_t("empty"))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(C_MUTED))
            tbl.setItem(0, 0, item)
            tbl.setSpan(0, 0, 1, 4)
            return

        tbl.setSpan(0, 0, 1, 1)

        for pos, rec in enumerate(top10, 1):
            tbl.insertRow(tbl.rowCount())
            row = tbl.rowCount() - 1

            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, str(pos))
            data = [medal, rec.date, f"{rec.time_from} — {rec.time_to}", _fmt_dur(rec.duration_sec)]

            for col, val in enumerate(data):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    font = QFont("Segoe UI", 13, QFont.Weight.Bold)
                    item.setFont(font)
                    if pos > 3:
                        item.setForeground(QColor(C_SUBTEXT))
                if col == 3:
                    item.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
                    color = (C_YELLOW if pos == 1 else
                             "#bdc3c7" if pos == 2 else
                             "#cd7f32" if pos == 3 else C_SUBTEXT)
                    item.setForeground(QColor(color))
                tbl.setItem(row, col, item)
        tbl.resizeRowsToContents()

    # ── Table factory ──────────────────────────────────────────────

    def _make_table(self) -> QTableWidget:
        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(
            [_t("col_rank"), _t("col_date"), _t("col_time"), _t("col_dur")]
        )
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        return tbl
