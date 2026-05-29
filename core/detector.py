"""
detector.py — MediaPipe Pose/Face detector and posture metric calculations.
Runs in a background thread, emits PostureFrame objects via a queue.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# MediaPipe landmark indices we care about
# ---------------------------------------------------------------------------
LM = mp.solutions.pose.PoseLandmark

IDX_LEFT_EAR      = LM.LEFT_EAR.value        # 7
IDX_RIGHT_EAR     = LM.RIGHT_EAR.value        # 8
IDX_LEFT_SHOULDER = LM.LEFT_SHOULDER.value    # 11
IDX_RIGHT_SHOULDER= LM.RIGHT_SHOULDER.value   # 12
IDX_LEFT_EYE      = LM.LEFT_EYE.value         # 2  (inner eye)
IDX_RIGHT_EYE     = LM.RIGHT_EYE.value        # 5  (inner eye)
IDX_NOSE          = LM.NOSE.value             # 0
# Lower body (for away detection)
IDX_LEFT_HIP      = LM.LEFT_HIP.value         # 23
IDX_RIGHT_HIP     = LM.RIGHT_HIP.value        # 24
IDX_LEFT_KNEE     = LM.LEFT_KNEE.value        # 25
IDX_RIGHT_KNEE    = LM.RIGHT_KNEE.value       # 26
IDX_LEFT_ANKLE    = LM.LEFT_ANKLE.value       # 27
IDX_RIGHT_ANKLE   = LM.RIGHT_ANKLE.value      # 28

MIN_VISIBILITY = 0.50   # below this → landmark is occluded / not reliable


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Landmark:
    x: float
    y: float
    z: float
    visibility: float


@dataclass
class PostureFrame:
    """Single processed frame result."""
    timestamp: float = field(default_factory=time.time)

    # Raw landmarks (None if not detected)
    landmarks: Optional[dict[int, Landmark]] = None

    # Face present in frame?
    face_visible: bool = False
    # Both shoulders visible?
    shoulders_visible: bool = False

    # Computed metrics (None if not computable)
    head_shoulder_dist: Optional[float] = None   # H_head
    shoulder_eye_ratio: Optional[float] = None   # Ratio_posture
    shoulder_tilt_deg:  Optional[float] = None   # theta

    # Calibration snapshot (set by caller after calibration)
    calibration: Optional[dict] = None

    # Posture violation flags
    neck_violation: bool = False
    back_violation: bool = False
    tilt_violation: bool = False

    # Overlay image for calibration window (BGR numpy array)
    overlay_image: Optional[np.ndarray] = None


@dataclass
class CalibrationData:
    head_shoulder_dist: float   # H_baseline
    shoulder_eye_ratio: float   # Ratio_baseline
    shoulder_tilt_deg:  float   # theta_baseline (should be ~0)

    def to_dict(self) -> dict:
        return {
            "head_shoulder_dist": self.head_shoulder_dist,
            "shoulder_eye_ratio": self.shoulder_eye_ratio,
            "shoulder_tilt_deg":  self.shoulder_tilt_deg,
        }

    @staticmethod
    def from_dict(d: dict) -> "CalibrationData":
        return CalibrationData(
            head_shoulder_dist=d["head_shoulder_dist"],
            shoulder_eye_ratio=d["shoulder_eye_ratio"],
            shoulder_tilt_deg=d["shoulder_tilt_deg"],
        )


# ---------------------------------------------------------------------------
# Smoothing buffer
# ---------------------------------------------------------------------------

class SmoothingBuffer:
    """Stores last N seconds of metric values and returns median."""

    def __init__(self, window_sec: float = 3.0, fps: float = 5.0):
        maxlen = max(1, int(window_sec * fps))
        self._head_dist:   deque[float] = deque(maxlen=maxlen)
        self._sh_ratio:    deque[float] = deque(maxlen=maxlen)
        self._tilt:        deque[float] = deque(maxlen=maxlen)

    def push(self, frame: PostureFrame):
        if frame.head_shoulder_dist is not None:
            self._head_dist.append(frame.head_shoulder_dist)
        if frame.shoulder_eye_ratio is not None:
            self._sh_ratio.append(frame.shoulder_eye_ratio)
        if frame.shoulder_tilt_deg is not None:
            self._tilt.append(frame.shoulder_tilt_deg)

    def median_head_dist(self) -> Optional[float]:
        return float(np.median(self._head_dist)) if self._head_dist else None

    def median_shoulder_ratio(self) -> Optional[float]:
        return float(np.median(self._sh_ratio)) if self._sh_ratio else None

    def median_tilt(self) -> Optional[float]:
        return float(np.median(self._tilt)) if self._tilt else None

    def clear(self):
        self._head_dist.clear()
        self._sh_ratio.clear()
        self._tilt.clear()


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class PostureDetector:
    """
    Captures from webcam, runs MediaPipe Pose, computes metrics.
    Runs in a daemon thread; call start() / stop().
    Latest frame accessible via .latest_frame.
    Optional callback: on_frame(PostureFrame).
    """

    def __init__(
        self,
        camera_index: int = 0,
        target_fps: float = 5.0,
        on_frame=None,
    ):
        self.camera_index = camera_index
        self.target_fps   = target_fps
        self.on_frame     = on_frame  # callable(PostureFrame)

        self._running   = False
        self._thread: Optional[threading.Thread] = None
        self._lock      = threading.Lock()
        self._latest_frame: Optional[PostureFrame] = None

        # MediaPipe Pose — higher complexity = more accurate, slower
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=2,          # 0=lite, 1=full, 2=heavy — accuracy priority
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self._mp_drawing = mp.solutions.drawing_utils
        self._mp_pose    = mp.solutions.pose

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    @property
    def latest_frame(self) -> Optional[PostureFrame]:
        with self._lock:
            return self._latest_frame

    def capture_calibration_frame(self) -> Optional[PostureFrame]:
        """Return the most recent frame with overlay, suitable for calibration."""
        return self.latest_frame

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self):
        # CAP_DSHOW is required on Windows for instant camera init.
        # Without it OpenCV probes every backend sequentially (~30 sec delay).
        # The console window it would normally open is already hidden via
        # FreeConsole() in main.py before this thread starts.
        import platform
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera_index, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        while self._running:
            ret, bgr = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame = self._process(bgr)

            with self._lock:
                self._latest_frame = frame

            if self.on_frame:
                try:
                    self.on_frame(frame)
                except Exception:
                    pass

        cap.release()

    def _process(self, bgr: np.ndarray) -> PostureFrame:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        results = self._pose.process(rgb)

        frame = PostureFrame()

        if results.pose_landmarks is None:
            frame.face_visible      = False
            frame.shoulders_visible = False
            frame.overlay_image     = bgr.copy()
            return frame

        lms_raw = results.pose_landmarks.landmark

        def lm(idx: int) -> Landmark:
            p = lms_raw[idx]
            return Landmark(x=p.x, y=p.y, z=p.z, visibility=p.visibility)

        landmarks = {i: lm(i) for i in [
            IDX_LEFT_EAR, IDX_RIGHT_EAR,
            IDX_LEFT_SHOULDER, IDX_RIGHT_SHOULDER,
            IDX_LEFT_EYE, IDX_RIGHT_EYE,
            IDX_NOSE,
            # Lower body
            IDX_LEFT_HIP, IDX_RIGHT_HIP,
            IDX_LEFT_KNEE, IDX_RIGHT_KNEE,
            IDX_LEFT_ANKLE, IDX_RIGHT_ANKLE,
        ]}
        frame.landmarks = landmarks

        # Visibility checks
        ear_vis  = min(landmarks[IDX_LEFT_EAR].visibility,
                       landmarks[IDX_RIGHT_EAR].visibility)
        eye_vis  = min(landmarks[IDX_LEFT_EYE].visibility,
                       landmarks[IDX_RIGHT_EYE].visibility)
        sh_vis   = min(landmarks[IDX_LEFT_SHOULDER].visibility,
                       landmarks[IDX_RIGHT_SHOULDER].visibility)

        face_ok      = max(ear_vis, eye_vis) >= MIN_VISIBILITY
        shoulders_ok = sh_vis >= MIN_VISIBILITY

        frame.face_visible      = face_ok
        frame.shoulders_visible = shoulders_ok

        # ---- Metric 1: head-shoulder vertical distance ----------------
        if shoulders_ok and face_ok:
            y_ears      = (landmarks[IDX_LEFT_EAR].y + landmarks[IDX_RIGHT_EAR].y) / 2
            y_shoulders = (landmarks[IDX_LEFT_SHOULDER].y + landmarks[IDX_RIGHT_SHOULDER].y) / 2
            frame.head_shoulder_dist = y_shoulders - y_ears   # positive when head above shoulders

        # ---- Metric 2: shoulder width / eye width ratio ---------------
        if shoulders_ok and eye_vis >= MIN_VISIBILITY:
            w_shoulders = abs(landmarks[IDX_LEFT_SHOULDER].x - landmarks[IDX_RIGHT_SHOULDER].x)
            w_eyes      = abs(landmarks[IDX_LEFT_EYE].x      - landmarks[IDX_RIGHT_EYE].x)
            if w_eyes > 1e-4:
                frame.shoulder_eye_ratio = w_shoulders / w_eyes

        # ---- Metric 3: shoulder tilt angle ----------------------------
        if shoulders_ok:
            dy = landmarks[IDX_LEFT_SHOULDER].y - landmarks[IDX_RIGHT_SHOULDER].y
            dx = landmarks[IDX_LEFT_SHOULDER].x - landmarks[IDX_RIGHT_SHOULDER].x
            frame.shoulder_tilt_deg = math.degrees(math.atan2(dy, dx))

        # ---- Overlay image for calibration window --------------------
        annotated = bgr.copy()
        h_img, w_img = annotated.shape[:2]

        # Theme colors (BGR for OpenCV): #8ab4f8 blue, #4ade80 green
        COLOR_LINE   = (248, 180, 138)   # #8ab4f8 — blue (BGR)
        COLOR_JOINT  = (128, 222, 74)    # #4ade80 — green (BGR)
        COLOR_FACE   = (200, 200, 255)   # soft lavender for face points
        ALPHA_LAYER  = 0.0               # we'll draw direct, no overlay needed

        # Upscale for smoother anti-aliased rendering then downscale
        SCALE = 2
        big = cv2.resize(annotated, (w_img * SCALE, h_img * SCALE),
                         interpolation=cv2.INTER_LINEAR)

        lms_all = results.pose_landmarks.landmark

        def pt(idx: int):
            """Return (x, y) in big-image pixel coords."""
            lm_p = lms_all[idx]
            return (int(lm_p.x * w_img * SCALE), int(lm_p.y * h_img * SCALE))

        def vis(idx: int) -> float:
            return lms_all[idx].visibility

        # Draw connections (only landmarks with sufficient visibility)
        for start_idx, end_idx in self._mp_pose.POSE_CONNECTIONS:
            if vis(start_idx) < 0.3 or vis(end_idx) < 0.3:
                continue
            p1, p2 = pt(start_idx), pt(end_idx)
            # Smooth anti-aliased line
            cv2.line(big, p1, p2, COLOR_LINE, thickness=3,
                     lineType=cv2.LINE_AA)

        # Draw joint dots — all the same green
        for idx in range(len(lms_all)):
            if vis(idx) < 0.3:
                continue
            p = pt(idx)
            # Outer glow ring
            cv2.circle(big, p, 7, COLOR_JOINT, thickness=2,
                       lineType=cv2.LINE_AA)
            # Filled center dot
            cv2.circle(big, p, 4, COLOR_JOINT, thickness=-1,
                       lineType=cv2.LINE_AA)

        # Downscale back — bilinear gives smooth result
        annotated = cv2.resize(big, (w_img, h_img),
                               interpolation=cv2.INTER_AREA)

        frame.overlay_image = annotated

        return frame

    def compute_violations(
        self,
        smoothed_head_dist: Optional[float],
        smoothed_ratio:     Optional[float],
        smoothed_tilt:      Optional[float],
        calibration:        CalibrationData,
        track_neck:         bool,
        track_back:         bool,
        head_drop_threshold:   float = 0.85,
        shoulder_ratio_drop:   float = 0.10,
        tilt_threshold_deg:    float = 7.0,
    ) -> tuple[bool, bool, bool]:
        """
        Returns (neck_violation, back_violation, tilt_violation).
        Uses smoothed median values from the buffer.
        """
        neck_v = False
        back_v = False
        tilt_v = False

        if track_neck and smoothed_head_dist is not None:
            baseline = calibration.head_shoulder_dist
            if baseline > 0 and smoothed_head_dist < baseline * head_drop_threshold:
                neck_v = True

        if track_back and smoothed_ratio is not None:
            baseline = calibration.shoulder_eye_ratio
            if baseline > 0:
                drop = (baseline - smoothed_ratio) / baseline
                if drop > shoulder_ratio_drop:
                    back_v = True

        if smoothed_tilt is not None:
            if abs(smoothed_tilt) > tilt_threshold_deg:
                tilt_v = True

        return neck_v, back_v, tilt_v
