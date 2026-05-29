"""
calibration.py — save and load calibration data.
Config path is resolved from POSTURE_GUARD_DATA_DIR env var
so it works correctly from both dev mode and PyInstaller EXE.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from core.detector import CalibrationData, PostureFrame, SmoothingBuffer


def _config_path() -> str:
    data_dir = os.environ.get(
        'POSTURE_GUARD_DATA_DIR',
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(data_dir, "config.json")


def load_config() -> dict:
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_config()


def save_config(cfg: dict):
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _default_config() -> dict:
    return {
        "strictness": "medium",
        "language": "ru",

        # --- Timing (grace period before alarm) ---
        "soft_timeout_sec":   15,
        "medium_timeout_sec": 10,
        "hard_timeout_sec":    5,

        # --- Deviation thresholds per strictness ---
        # head_drop: fraction of baseline; lower = more sensitive
        "soft_head_drop_threshold":   0.82,   # 18% drop
        "medium_head_drop_threshold": 0.89,   # 11% drop
        "hard_head_drop_threshold":   0.93,   #  7% drop

        # shoulder_ratio: relative drop; lower = more sensitive
        "soft_shoulder_ratio_threshold":   0.08,
        "medium_shoulder_ratio_threshold": 0.11,
        "hard_shoulder_ratio_threshold":   0.05,

        # tilt angle degrees
        "soft_tilt_angle_threshold_deg":   10.0,
        "medium_tilt_angle_threshold_deg":  7.0,
        "hard_tilt_angle_threshold_deg":    5.0,

        # --- Tracking ---
        "track_back": True,
        "track_neck": True,
        "sound_file": None,
        "use_default_sound": True,
        "calibration": None,
        "grace_period_sec": 10,
        "keyboard_grace_sec": 5,
        "away_absence_timeout_sec": 5,
        "smoothing_window_sec": 3,
        "volume": 0.8,
        "autostart": False,
    }


def load_calibration() -> Optional[CalibrationData]:
    cfg = load_config()
    cal = cfg.get("calibration")
    if cal is None:
        return None
    try:
        return CalibrationData.from_dict(cal)
    except (KeyError, TypeError):
        return None


def save_calibration(cal: CalibrationData):
    cfg = load_config()
    cfg["calibration"] = cal.to_dict()
    save_config(cfg)


def calibrate_from_frame(frame: PostureFrame) -> Optional[CalibrationData]:
    if frame.head_shoulder_dist is None:
        return None
    if frame.shoulder_eye_ratio is None:
        return None
    if frame.shoulder_tilt_deg is None:
        return None
    if not frame.face_visible or not frame.shoulders_visible:
        return None
    return CalibrationData(
        head_shoulder_dist=frame.head_shoulder_dist,
        shoulder_eye_ratio=frame.shoulder_eye_ratio,
        shoulder_tilt_deg=frame.shoulder_tilt_deg,
    )


def calibrate_from_buffer(buffer: Optional[SmoothingBuffer]) -> Optional[CalibrationData]:
    if buffer is None:
        return None
    h = buffer.median_head_dist()
    r = buffer.median_shoulder_ratio()
    t = buffer.median_tilt()
    if h is None or r is None or t is None:
        return None
    return CalibrationData(
        head_shoulder_dist=h,
        shoulder_eye_ratio=r,
        shoulder_tilt_deg=t,
    )
