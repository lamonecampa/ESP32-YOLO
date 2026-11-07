# NOVIX Web Dashboard

## Start
```bash
cd ESP32-YOLO
source .venv/bin/activate
python -m edge_server.app --config config/server.yaml
```

Open `http://<RASPBERRY_PI_IP>:8000/` from a browser on the same trusted network.

## Pages
- Overview: server counters, registered cameras, recent detections, inference health.
- Live monitoring: camera cards using the latest received JPEG frames.
- Detection logs: recent inference events and CSV export.
- Alerts: recent person/intruder class detections.
- System monitor: API counters and camera node last-seen information.
- Settings: API base URL and supported MQTT camera settings.

## Camera control
Set `mqtt.enabled: true` and configure broker host, port, and credentials in `config/server.yaml`. The firmware subscribes to `<topic_prefix>/<camera_id>/control`. Supported JSON keys:
```json
{"capture_interval_ms": 2000, "resolution": "QVGA", "streaming_enabled": true}
```
The server validates commands before publishing. MQTT commands are not acknowledged by the firmware, so a successful publish confirms delivery to the broker, not that the camera applied the setting.

## Stream semantics
The MJPEG endpoint emits a frame when a new JPEG is received. It does not generate intermediate frames or guarantee a fixed video frame rate. Effective refresh is bounded by camera capture interval, Wi-Fi throughput, upload time, and inference processing.

## Current limitations
- Motor movement is not implemented in the current ESP32-CAM firmware.
- Camera battery telemetry is not available.
- CPU, RAM, and temperature telemetry are not currently collected.
- The browser dashboard has no authentication layer. Keep it on a trusted LAN; do not publish it directly to the internet.
