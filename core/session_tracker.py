"""
session_tracker.py — Tracks posture-good streaks and stores records.

A streak starts when state enters TRACKING and ends when:
  - State becomes BAD_POSTURE (posture violation)
  - State becomes AWAY (user left)
  - State becomes PAUSED (user paused)

Only streaks >= MIN_RECORD_SEC are saved to the leaderboard.
Records are stored per strictness level in a JSON file.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

MIN_RECORD_SEC = 10.0   # discard streaks shorter than this


def _records_path() -> str:
    data_dir = os.environ.get(
        'POSTURE_GUARD_DATA_DIR',
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(data_dir, "records.json")


@dataclass
class StreakRecord:
    strictness: str       # "soft" | "medium" | "hard"
    date:       str       # "2026-05-22"
    time_from:  str       # "08:34"
    time_to:    str       # "08:45"
    duration_sec: float   # total seconds

    def duration_fmt(self) -> str:
        """Return HH:MM:SS:DS (DS = deciseconds 0-9)."""
        total_ds = int(self.duration_sec * 10)
        ds  = total_ds % 10
        s   = (total_ds // 10) % 60
        m   = (total_ds // 600) % 60
        h   = total_ds // 36000
        return f"{h:02d}:{m:02d}:{s:02d}:{ds:01d}"

    def to_dict(self) -> dict:
        return {
            "strictness":   self.strictness,
            "date":         self.date,
            "time_from":    self.time_from,
            "time_to":      self.time_to,
            "duration_sec": self.duration_sec,
        }

    @staticmethod
    def from_dict(d: dict) -> "StreakRecord":
        return StreakRecord(
            strictness   = d["strictness"],
            date         = d["date"],
            time_from    = d["time_from"],
            time_to      = d["time_to"],
            duration_sec = d["duration_sec"],
        )


def load_records() -> list[StreakRecord]:
    try:
        with open(_records_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return [StreakRecord.from_dict(r) for r in data]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def save_records(records: list[StreakRecord]):
    path = _records_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in records], f, indent=2, ensure_ascii=False)


def add_record(record: StreakRecord, max_per_strictness: int = 100):
    records = load_records()
    records.append(record)
    # Sort each strictness group by duration desc, keep top N
    from itertools import groupby
    result = []
    by_s = {}
    for r in records:
        by_s.setdefault(r.strictness, []).append(r)
    for s, recs in by_s.items():
        recs.sort(key=lambda r: r.duration_sec, reverse=True)
        result.extend(recs[:max_per_strictness])
    save_records(result)


class SessionTracker:
    """
    Stateful streak timer. Call on_state_change(state) on every engine state change.
    Call tick() frequently (e.g. every 100ms) to update the running timer.

    Callbacks:
      on_streak_update(elapsed_sec: float)  — called on every tick while tracking
      on_record_saved(record: StreakRecord) — called when a record is committed
    """

    def __init__(
        self,
        strictness: str = "medium",
        on_streak_update=None,
        on_record_saved=None,
    ):
        self.strictness        = strictness
        self.on_streak_update  = on_streak_update
        self.on_record_saved   = on_record_saved

        self._streak_start:    Optional[float]   = None
        self._streak_start_dt: Optional[datetime] = None
        self._running          = False

    def set_strictness(self, strictness: str):
        self.strictness = strictness

    def on_state_change(self, state):
        from core.engine import State
        # GRACE = posture worsening but streak continues (user has time to correct)
        if state in (State.TRACKING, State.GRACE):
            if not self._running:
                self._start_streak()
        else:
            # BAD_POSTURE, AWAY, PAUSED, IDLE → end streak
            if self._running:
                self._end_streak()

    def tick(self) -> float:
        """Returns current streak duration in seconds (0 if not running)."""
        if not self._running or self._streak_start is None:
            return 0.0
        elapsed = time.monotonic() - self._streak_start
        if self.on_streak_update:
            self.on_streak_update(elapsed)
        return elapsed

    def reset(self):
        if self._running:
            self._end_streak()

    # ------------------------------------------------------------------

    def _start_streak(self):
        self._running          = True
        self._streak_start     = time.monotonic()
        self._streak_start_dt  = datetime.now()

    def _end_streak(self):
        if not self._running or self._streak_start is None:
            return
        self._running  = False
        elapsed        = time.monotonic() - self._streak_start
        end_dt         = datetime.now()

        if elapsed >= MIN_RECORD_SEC:
            record = StreakRecord(
                strictness   = self.strictness,
                date         = self._streak_start_dt.strftime("%Y-%m-%d"),
                time_from    = self._streak_start_dt.strftime("%H:%M"),
                time_to      = end_dt.strftime("%H:%M"),
                duration_sec = elapsed,
            )
            add_record(record)
            if self.on_record_saved:
                self.on_record_saved(record)

        self._streak_start    = None
        self._streak_start_dt = None
