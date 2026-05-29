"""
settings.py — Settings dialog (strictness, toggles, sound choice).
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QSlider, QCheckBox, QComboBox,
    QFileDialog, QLineEdit, QSpinBox, QDoubleSpinBox,
    QFrame,
)

from core.calibration import load_config, save_config


class SettingsWindow(QDialog):

    def __init__(self, on_config_changed: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self.on_config_changed = on_config_changed
        self.setWindowTitle("Настройки — PostureGuard")
        self.setMinimumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint
        )
        self._cfg = load_config()
        self._setup_ui()
        self._load_values()

    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self._section_label("⚙️  Уровень строгости"))

        # Strictness
        strict_group = QGroupBox()
        strict_group.setStyleSheet(self._group_style())
        strict_layout = QVBoxLayout(strict_group)

        self._strict_combo = QComboBox()
        self._strict_combo.addItems(["soft — сигнал через 15 сек", "hard — сигнал через 5 сек"])
        self._strict_combo.setStyleSheet(self._combo_style())
        strict_layout.addWidget(QLabel("Режим:", styleSheet="color:#ccc;"))
        strict_layout.addWidget(self._strict_combo)

        soft_row = QHBoxLayout()
        soft_row.addWidget(QLabel("Soft-тайаут (сек):", styleSheet="color:#ccc;"))
        self._soft_spin = QSpinBox()
        self._soft_spin.setRange(5, 120)
        self._soft_spin.setStyleSheet(self._spin_style())
        soft_row.addWidget(self._soft_spin)
        soft_row.addStretch()
        strict_layout.addLayout(soft_row)

        hard_row = QHBoxLayout()
        hard_row.addWidget(QLabel("Hard-тайаут (сек):", styleSheet="color:#ccc;"))
        self._hard_spin = QSpinBox()
        self._hard_spin.setRange(2, 60)
        self._hard_spin.setStyleSheet(self._spin_style())
        hard_row.addWidget(self._hard_spin)
        hard_row.addStretch()
        strict_layout.addLayout(hard_row)

        layout.addWidget(strict_group)

        # --- Tracking toggles
        layout.addWidget(self._section_label("👁️  Что отслеживать"))

        track_group = QGroupBox()
        track_group.setStyleSheet(self._group_style())
        track_layout = QVBoxLayout(track_group)

        self._track_neck_cb = QCheckBox("Следить за шеей (наклон головы)")
        self._track_back_cb  = QCheckBox("Следить за спиной (скругление плеч)")
        for cb in (self._track_neck_cb, self._track_back_cb):
            cb.setStyleSheet("color:#ddd; font-size:13px;")
        track_layout.addWidget(self._track_neck_cb)
        track_layout.addWidget(self._track_back_cb)
        layout.addWidget(track_group)

        # --- Sound
        layout.addWidget(self._section_label("🔊  Звук"))

        sound_group = QGroupBox()
        sound_group.setStyleSheet(self._group_style())
        sound_layout = QVBoxLayout(sound_group)

        self._use_default_cb = QCheckBox("Использовать встроенный звук (зуммер)")
        self._use_default_cb.setStyleSheet("color:#ddd; font-size:13px;")
        self._use_default_cb.toggled.connect(self._on_default_sound_toggle)
        sound_layout.addWidget(self._use_default_cb)

        mp3_row = QHBoxLayout()
        self._sound_path_edit = QLineEdit()
        self._sound_path_edit.setPlaceholderText("Путь к MP3/WAV файлу…")
        self._sound_path_edit.setStyleSheet(
            "background:#1a1a2e; color:#ddd; border:1px solid #333; "
            "border-radius:4px; padding:4px 8px;"
        )
        mp3_row.addWidget(self._sound_path_edit)
        browse_btn = QPushButton("Обзор…")
        browse_btn.setStyleSheet(self._btn_style_secondary())
        browse_btn.clicked.connect(self._browse_sound)
        mp3_row.addWidget(browse_btn)
        sound_layout.addLayout(mp3_row)
        layout.addWidget(sound_group)

        # --- Grace periods
        layout.addWidget(self._section_label("⏱️  Грейс-периоды"))

        grace_group = QGroupBox()
        grace_group.setStyleSheet(self._group_style())
        grace_layout = QVBoxLayout(grace_group)

        for label, attr in [
            ("Чай/телефон (сек):", "_grace_spin"),
            ("Взгляд на клавиатуру (сек):", "_kb_grace_spin"),
            ("Away (нет в кадре) (сек):", "_away_spin"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label, styleSheet="color:#ccc;"))
            spin = QSpinBox()
            spin.setRange(1, 60)
            spin.setStyleSheet(self._spin_style())
            setattr(self, attr, spin)
            row.addWidget(spin)
            row.addStretch()
            grace_layout.addLayout(row)

        layout.addWidget(grace_group)

        # --- Save button
        save_btn = QPushButton("💾  Сохранить настройки")
        save_btn.setMinimumHeight(42)
        save_btn.setStyleSheet(
            "QPushButton {"
            "  background:#1a6b3c; color:white; border-radius:6px;"
            "  font-size:14px; font-weight:bold;"
            "}"
            "QPushButton:hover { background:#1f8049; }"
        )
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    # ------------------------------------------------------------------

    def _load_values(self):
        cfg = self._cfg
        self._strict_combo.setCurrentIndex(0 if cfg.get("strictness","soft")=="soft" else 1)
        self._soft_spin.setValue(cfg.get("soft_timeout_sec", 15))
        self._hard_spin.setValue(cfg.get("hard_timeout_sec", 5))
        self._track_neck_cb.setChecked(cfg.get("track_neck", True))
        self._track_back_cb.setChecked(cfg.get("track_back", True))
        self._use_default_cb.setChecked(cfg.get("use_default_sound", True))
        self._sound_path_edit.setText(cfg.get("sound_file") or "")
        self._sound_path_edit.setEnabled(not cfg.get("use_default_sound", True))
        self._grace_spin.setValue(cfg.get("grace_period_sec", 10))
        self._kb_grace_spin.setValue(cfg.get("keyboard_grace_sec", 5))
        self._away_spin.setValue(cfg.get("away_timeout_sec", 3))

    def _save(self):
        cfg = self._cfg
        cfg["strictness"] = "soft" if self._strict_combo.currentIndex() == 0 else "hard"
        cfg["soft_timeout_sec"]   = self._soft_spin.value()
        cfg["hard_timeout_sec"]   = self._hard_spin.value()
        cfg["track_neck"]         = self._track_neck_cb.isChecked()
        cfg["track_back"]         = self._track_back_cb.isChecked()
        cfg["use_default_sound"]  = self._use_default_cb.isChecked()
        sound = self._sound_path_edit.text().strip()
        cfg["sound_file"]         = sound if sound else None
        cfg["grace_period_sec"]   = self._grace_spin.value()
        cfg["keyboard_grace_sec"] = self._kb_grace_spin.value()
        cfg["away_timeout_sec"]   = self._away_spin.value()
        save_config(cfg)
        if self.on_config_changed:
            self.on_config_changed(cfg)
        self.close()

    def _on_default_sound_toggle(self, checked: bool):
        self._sound_path_edit.setEnabled(not checked)

    def _browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите звуковой файл", "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)"
        )
        if path:
            self._sound_path_edit.setText(path)
            self._use_default_cb.setChecked(False)

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#a0cfee; font-size:13px; font-weight:bold; "
            "margin-top:4px; padding-bottom:2px;"
        )
        return lbl

    def _group_style(self):
        return (
            "QGroupBox { background:#121224; border:1px solid #2a2a4a; "
            "border-radius:6px; padding:10px; }"
        )

    def _combo_style(self):
        return (
            "QComboBox { background:#1a1a2e; color:#ddd; border:1px solid #333; "
            "border-radius:4px; padding:4px 8px; font-size:13px; }"
            "QComboBox::drop-down { border:none; }"
            "QComboBox QAbstractItemView { background:#1a1a2e; color:#ddd; "
            "selection-background-color:#2a4a6e; }"
        )

    def _spin_style(self):
        return (
            "QSpinBox { background:#1a1a2e; color:#ddd; border:1px solid #333; "
            "border-radius:4px; padding:3px 8px; font-size:13px; min-width:70px; }"
        )

    def _btn_style_secondary(self):
        return (
            "QPushButton { background:#2a2a3e; color:#aaa; border-radius:4px; "
            "padding:5px 12px; }"
            "QPushButton:hover { background:#3a3a5e; color:white; }"
        )
