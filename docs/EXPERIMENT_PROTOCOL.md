# Experimental Protocol

## Research question
Can event-coverage-aware adaptive acquisition and freshness-based scheduling reduce network load while preserving event detection performance in a low-cost multi-camera edge-vision testbed?

## Baselines
1. Continuous: transmit each available frame at the configured capture rate.
2. Periodic: fixed interval transmission.
3. Fixed event-triggered: transmit when a fixed scene-change threshold is crossed.
4. Proposed: configurable priority/freshness-aware acquisition and edge scheduling.

## Independent variables
- Camera count: 1, 2, 3, 5.
- Resolution: QVGA (320x240), VGA (640x480).
- Capture/transmit interval.
- Policy.
- Network conditions: baseline and controlled impairment.
- Scene activity and illumination.

## Outcomes
- Object detection: precision, recall, mAP50, mAP50-95.
- Event detection: event recall, missed-event count, time-to-detect.
- Network: bytes/frame, bytes/minute, throughput, packet loss, retransmissions where measurable.
- Timing: capture-to-receive, inference, end-to-end server latency, p50/p95.
- Compute: CPU, RAM, queue depth.
- Energy: joules/frame and joules/hour measured with a calibrated external power meter.

## Ground truth
Use a continuous reference recording independent of the ESP32-CAM transmission policy. Annotate event start/end, object class, and bounding boxes for a representative subset. Otherwise a policy that drops difficult frames can misleadingly appear accurate when evaluated only on transmitted frames.

## Reproducibility
Log date/time, firmware commit, server commit, model SHA-256, model version, image size, confidence/IoU thresholds, camera placement, lighting, access point, signal strength, channel, background traffic, and scheduler configuration.

## Repetitions and analysis
Use at least five independent runs per primary configuration where practical. Report mean/median, spread, and 95% confidence intervals. Use paired tests when runs share the same scene and conditions. Select paired t-test or Wilcoxon signed-rank based on distribution and assumptions. Include ablations for motion, urgency, freshness, and anti-starvation.

## Limitations
The classic ESP32-CAM is an acquisition node, not a YOLO inference accelerator. Pi 5 throughput must be benchmarked under the complete multi-camera pipeline. The prototype scheduler is a heuristic and must not be presented as optimal without formal proof.
