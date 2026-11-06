from edge_server.scheduler.policies import (
    CameraSignal, Priority, SchedulerConfig, classify_priority,
    effective_priority, priority_score
)


def test_priority_score_is_normalized():
    cfg = SchedulerConfig()
    score = priority_score(CameraSignal("cam", 1, 1, 1, 2500), cfg)
    assert 0.0 <= score <= 1.0


def test_high_urgency_promotes_priority():
    cfg = SchedulerConfig()
    signal = CameraSignal("cam", motion_score=0.8, urgency=1.0, age_ms=2000)
    assert classify_priority(signal, cfg) == Priority.HIGH


def test_starvation_promotion():
    cfg = SchedulerConfig(starvation_limit_ms=1000)
    signal = CameraSignal("cam")
    assert effective_priority(signal, cfg, waiting_ms=1500) == Priority.HIGH


def test_weights_are_normalized_in_scoring():
    cfg = SchedulerConfig(
        motion_weight=3, confidence_weight=2,
        urgency_weight=2, freshness_weight=3
    )
    score = priority_score(CameraSignal("cam", 0.5, 0.5, 0.5, 1250), cfg)
    assert abs(score - 0.625) < 1e-9
