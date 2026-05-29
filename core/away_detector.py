"""
away_detector.py — Simple, reliable "user left the desk" detection.

Two definitive signals:
  1. No landmarks detected at all (sustained absence)
  2. Hip/knee/ankle landmarks visible (user is standing)

Both → AWAY immediately. No scoring, no ambiguity.
"""
from __future__ import annotations

import time
from typing import Optional

import mediapipe as mp

from core.detector import PostureFrame, MIN_VISIBILITY

LM = mp.solutions.pose.PoseLandmark

IDX_LEFT_HIP    = LM.LEFT_HIP.value
IDX_RIGHT_HIP   = LM.RIGHT_HIP.value
IDX_LEFT_KNEE   = LM.LEFT_KNEE.value
IDX_RIGHT_KNEE  = LM.RIGHT_KNEE.value
IDX_LEFT_ANKLE  = LM.LEFT_ANKLE.value
IDX_RIGHT_ANKLE = LM.RIGHT_ANKLE.value

HIP_VISIBILITY_THRESHOLD = 0.55


class AwayDetector:
    """
    Call update(frame) on every frame.
    Returns True if user is considered away from the desk.
    """

    def __init__(self, absence_timeout_sec: float = 5.0):
        self.absence_timeout_sec = absence_timeout_sec
        self._absence_start: Optional[float] = None

    def update(self, frame: PostureFrame) -> tuple[bool, str]:
        """
        Returns (is_away, reason_string).
        """
        now  = frame.timestamp
        lms  = frame.landmarks

        # ── Signal 1: Lower body visible → standing up ───────────────
        if lms:
            def vis(idx):
                lm = lms.get(idx)
                return lm.visibility if lm else 0.0

            hip_vis   = max(vis(IDX_LEFT_HIP),   vis(IDX_RIGHT_HIP))
            knee_vis  = max(vis(IDX_LEFT_KNEE),  vis(IDX_RIGHT_KNEE))
            ankle_vis = max(vis(IDX_LEFT_ANKLE), vis(IDX_RIGHT_ANKLE))

            if hip_vis >= HIP_VISIBILITY_THRESHOLD:
                self._absence_start = None
                return True, "тазовые точки обнаружены — пользователь встал"
            if knee_vis >= 0.5:
                self._absence_start = None
                return True, "колени в кадре — пользователь встал"
            if ankle_vis >= 0.4:
                self._absence_start = None
                return True, "лодыжки в кадре — пользователь встал"

        # ── Signal 2: No landmarks at all → sustained absence ────────
        if lms is None:
            if self._absence_start is None:
                self._absence_start = now
            elapsed = now - self._absence_start
            if elapsed >= self.absence_timeout_sec:
                return True, f"нет точек {elapsed:.0f}с — пользователь отошёл"
            return False, f"нет точек {elapsed:.0f}с (ожидание {self.absence_timeout_sec:.0f}с)"

        # ── Landmarks present, no lower body → at desk ───────────────
        self._absence_start = None
        return False, "за компьютером"

    def reset(self):
        self._absence_start = None
