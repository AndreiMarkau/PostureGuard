"""
engine.py — posture tracking state machine and violation timer logic.

States:
  IDLE        — tracking not started
  TRACKING    — normal, posture OK
  GRACE       — posture bad, but within grace period (no alarm yet)
  BAD_POSTURE — grace period expired, alarm active
  AWAY        — user not in frame
  PAUSED      — user manually paused tracking

Transitions are driven by PostureFrame objects fed via feed().
"""
from __future__ import annotations

import time
from enum import Enum, auto
from typing import Callable, Optional

from core.calibration import CalibrationData, load_calibration
from core.detector import PostureDetector, PostureFrame, SmoothingBuffer
from core.away_detector import AwayDetector


class State(Enum):
    IDLE        = auto()
    TRACKING    = auto()
    GRACE       = auto()
    BAD_POSTURE = auto()
    AWAY        = auto()
    PAUSED      = auto()


class PostureEngine:
    """
    Receives PostureFrame events, manages state machine, fires callbacks.

    Callbacks:
      on_state_change(new_state: State)
      on_alarm_start()
      on_alarm_stop()
    """

    def __init__(
        self,
        config: dict,
        on_state_change: Optional[Callable[[State], None]] = None,
        on_alarm_start:  Optional[Callable[[], None]]      = None,
        on_alarm_stop:   Optional[Callable[[], None]]      = None,
        on_warning:      Optional[Callable[[], None]]      = None,
    ):
        self.config          = config
        self.on_state_change = on_state_change
        self.on_alarm_start  = on_alarm_start
        self.on_alarm_stop   = on_alarm_stop
        self.on_warning      = on_warning

        # Warning counters (reset on resume/start)
        self.warning_count          = 0
        self.critical_warning_count = 0

        self._state = State.IDLE
        self._calibration: Optional[CalibrationData] = load_calibration()

        # Smoothing buffer — 3 sec window, 5 fps
        fps = 5.0
        self._buffer = SmoothingBuffer(
            window_sec=config.get("smoothing_window_sec", 3.0),
            fps=fps,
        )

        self._detector = PostureDetector(
            camera_index=0,
            target_fps=fps,
            on_frame=self._on_frame,
        )

        # Timers
        self._grace_start:   Optional[float] = None
        self._away_start:    Optional[float] = None
        self._alarm_active   = False

        # Away detection
        self._away_detector = AwayDetector(
            absence_timeout_sec=config.get("away_absence_timeout_sec", 5.0),
        )

        # Cache latest raw frame for UI
        self._latest_frame: Optional[PostureFrame] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start webcam capture and tracking."""
        self._detector.start()
        self._set_state(State.TRACKING if self._calibration else State.TRACKING)

    def stop(self):
        self._detector.stop()
        self._stop_alarm()
        self._set_state(State.IDLE)

    def pause(self):
        if self._state not in (State.IDLE, State.PAUSED):
            self._stop_alarm()
            self._set_state(State.PAUSED)

    def resume(self):
        if self._state == State.PAUSED:
            self._buffer.clear()
            self._away_detector.reset()
            self._set_state(State.TRACKING)

    def set_calibration(self, cal: CalibrationData):
        self._calibration = cal
        self._buffer.clear()
        # Pass baseline shoulder width to away detector
        if hasattr(cal, 'shoulder_width') and cal.shoulder_width:
            self._away_detector.set_baseline_shoulder_width(cal.shoulder_width)

    def reload_config(self, config: dict):
        self.config = config
        self._buffer = SmoothingBuffer(
            window_sec=config.get("smoothing_window_sec", 3.0),
            fps=5.0,
        )

    @property
    def state(self) -> State:
        return self._state

    @property
    def calibration(self) -> Optional[CalibrationData]:
        return self._calibration

    @property
    def latest_frame(self) -> Optional[PostureFrame]:
        return self._latest_frame

    @property
    def detector(self) -> PostureDetector:
        return self._detector

    # ------------------------------------------------------------------
    # Frame handler (called from detector thread)
    # ------------------------------------------------------------------

    def _on_frame(self, frame: PostureFrame):
        self._latest_frame = frame

        if self._state in (State.IDLE, State.PAUSED):
            return

        now = time.time()

        # ---- Away detection ----------------------------------------
        is_away, _away_reason = self._away_detector.update(frame)

        if is_away:
            if self._state != State.AWAY:
                self._stop_alarm()
                self._grace_start = None
                self._set_state(State.AWAY)
            return
        else:
            if self._state == State.AWAY:
                self._away_detector.reset()
                self._buffer.clear()
                self._set_state(State.TRACKING)

        # ---- Need calibration ----------------------------------------
        if self._calibration is None:
            # Can't evaluate posture yet
            return

        # ---- Push to smoothing buffer --------------------------------
        self._buffer.push(frame)

        # ---- Evaluate smoothed metrics --------------------------------
        h = self._buffer.median_head_dist()
        r = self._buffer.median_shoulder_ratio()
        t = self._buffer.median_tilt()

        cfg = self.config
        strictness = cfg.get("strictness", "soft")
        pfx = strictness  # "soft" | "medium" | "hard"

        # Pick thresholds based on strictness level
        _head_defaults   = {"soft": 0.82, "medium": 0.89, "hard": 0.93}
        _ratio_defaults  = {"soft": 0.08, "medium": 0.11, "hard": 0.05}
        _tilt_defaults   = {"soft": 10.0, "medium":  7.0, "hard":  5.0}
        head_drop  = cfg.get(f"{pfx}_head_drop_threshold",      _head_defaults.get(pfx, 0.89))
        ratio_drop = cfg.get(f"{pfx}_shoulder_ratio_threshold", _ratio_defaults.get(pfx, 0.11))
        tilt_deg   = cfg.get(f"{pfx}_tilt_angle_threshold_deg", _tilt_defaults.get(pfx,  7.0))

        neck_v, back_v, tilt_v = self._detector.compute_violations(
            smoothed_head_dist=h,
            smoothed_ratio=r,
            smoothed_tilt=t,
            calibration=self._calibration,
            track_neck=cfg.get("track_neck", True),
            track_back=cfg.get("track_back", True),
            head_drop_threshold=head_drop,
            shoulder_ratio_drop=ratio_drop,
            tilt_threshold_deg=tilt_deg,
        )

        # Handle shoulder occlusion grace (drinking tea / phone)
        if not frame.shoulders_visible:
            grace_sec = cfg.get("grace_period_sec", 10.0)
            self._handle_grace(now, grace_sec)
            return

        # Handle keyboard look (head down, shoulders stable)
        if neck_v and not back_v and not tilt_v:
            grace_sec = cfg.get("keyboard_grace_sec", 5.0)
            self._handle_grace(now, grace_sec)
            return

        any_violation = neck_v or back_v or tilt_v

        if not any_violation:
            # Posture OK
            self._grace_start = None
            if self._alarm_active:
                self._stop_alarm()
            if self._state != State.TRACKING:
                self._set_state(State.TRACKING)
        else:
            # Posture bad — start or continue grace timer
            if strictness == "soft":
                timeout = cfg.get("soft_timeout_sec", 15.0)
            elif strictness == "hard":
                timeout = cfg.get("hard_timeout_sec", 5.0)
            else:
                timeout = cfg.get("medium_timeout_sec", 10.0)
            self._handle_grace(now, timeout)

    def _handle_grace(self, now: float, timeout: float):
        if self._grace_start is None:
            self._grace_start = now
            if self._state != State.GRACE:
                self._set_state(State.GRACE)
        elif now - self._grace_start >= timeout:
            if self._state != State.BAD_POSTURE:
                self._set_state(State.BAD_POSTURE)
            if not self._alarm_active:
                self._start_alarm()

    # ------------------------------------------------------------------
    # Alarm helpers
    # ------------------------------------------------------------------

    def reset_warning_counts(self):
        self.warning_count          = 0
        self.critical_warning_count = 0

    def _start_alarm(self):
        self._alarm_active = True
        self.warning_count += 1
        if self.config.get("strictness", "medium") == "hard":
            self.critical_warning_count += 1
        if self.on_alarm_start:
            self.on_alarm_start()
        if self.on_warning:
            self.on_warning()

    def _stop_alarm(self):
        if self._alarm_active:
            self._alarm_active = False
            if self.on_alarm_stop:
                self.on_alarm_stop()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_state(self, new_state: State):
        if self._state == new_state:
            return
        self._state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)
