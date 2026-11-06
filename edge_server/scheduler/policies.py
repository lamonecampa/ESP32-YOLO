"""Baseline and experimental camera priority policies.

AEBAS is an experimental heuristic. It is intentionally transparent and must
be benchmarked against the continuous, periodic, and fixed-event baselines.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Priority(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class CameraSignal:
    camera_id: str
    motion_score: float = 0.0
    last_confidence: float = 0.0
    urgency: float = 0.0
    age_ms: float = 0.0
    queue_length: int = 0


@dataclass
class SchedulerConfig:
    low_threshold: float = 0.08
    high_threshold: float = 0.35
    motion_weight: float = 0.30
    confidence_weight: float = 0.20
    urgency_weight: float = 0.25
    freshness_weight: float = 0.25
    max_frame_age_ms: float = 2500.0
    starvation_limit_ms: float = 10000.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def priority_score(signal: CameraSignal, cfg: SchedulerConfig) -> float:
    """Compute normalized priority; age is normalized against max_frame_age_ms."""
    age_norm = _clamp01(signal.age_ms / max(cfg.max_frame_age_ms, 1.0))
    weights = (
        cfg.motion_weight + cfg.confidence_weight +
        cfg.urgency_weight + cfg.freshness_weight
    )
    if weights <= 0:
        raise ValueError("At least one scheduler weight must be positive")
    score = (
        cfg.motion_weight * _clamp01(signal.motion_score)
        + cfg.confidence_weight * _clamp01(signal.last_confidence)
        + cfg.urgency_weight * _clamp01(signal.urgency)
        + cfg.freshness_weight * age_norm
    ) / weights
    return _clamp01(score)


def classify_priority(signal: CameraSignal, cfg: SchedulerConfig) -> Priority:
    score = priority_score(signal, cfg)
    if score >= cfg.high_threshold:
        return Priority.HIGH
    if score >= cfg.low_threshold:
        return Priority.MEDIUM
    return Priority.LOW


def effective_priority(
    signal: CameraSignal, cfg: SchedulerConfig, waiting_ms: Optional[float] = None
) -> Priority:
    """Prevent starvation by promoting a camera after a configured waiting time."""
    if waiting_ms is not None and waiting_ms >= cfg.starvation_limit_ms:
        return Priority.HIGH
    return classify_priority(signal, cfg)
