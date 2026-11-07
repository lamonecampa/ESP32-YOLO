# ESP32-YOLO
Distributed edge-vision research testbed using ESP32-CAM AI-Thinker (OV2640), Raspberry Pi 5, HTTP image transport, MQTT control, and YOLO inference.

## Research scope
This repository is the first reproducible software baseline for:
- Multi-camera image acquisition (1–5 ESP32-CAM nodes).
- HTTP JPEG frame upload and MQTT control/telemetry.
- Edge-side YOLO inference and optional object tracking.
- Baseline transmission policies: continuous, periodic, and event-triggered.
- AEBAS research prototype: event/priority/freshness-aware scheduling.
- Metrics collection for latency, throughput, dropped frames, inference time, and detection results.

> Important: ESP32-CAM is used for image acquisition and lightweight scene-change signaling. YOLO inference runs on the Raspberry Pi / edge host, not on the classic ESP32-CAM.

## Repository layout
```
firmware/esp32cam_node/     Arduino firmware for AI Thinker ESP32-CAM
edge_server/               FastAPI image receiver and YOLO inference
edge_server/scheduler/     Scheduling policies and AEBAS prototype
scripts/                   Dataset / benchmark utilities
config/                    Example configuration
docker/                    Docker Compose and service config
docs/                      Setup, API, experiment protocol
```

## Quick start: edge server
Tested target: Raspberry Pi 5, Raspberry Pi OS 64-bit, Python 3.11+.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git
git clone https://github.com/lamonecampa/ESP32-YOLO.git
cd ESP32-YOLO
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r edge_server/requirements.txt
cp config/server.example.yaml config/server.yaml
python -m edge_server.app --config config/server.yaml
```

Open `http://<PI_IP>:8000/` for the NOVIX responsive web dashboard and `http://<PI_IP>:8000/docs` for the API documentation. The dashboard includes overview metrics, multi-camera live frame panels (MJPEG), detection logs, alerts, system counters, and supported camera settings. The browser polls the API every 5 seconds; camera panels update whenever new JPEG frames arrive. The server defaults to a CPU-friendly configuration and uses a locally available model file when configured. It does not download model weights automatically.

The legacy Streamlit research monitor remains available with `streamlit run edge_server/dashboard.py`.

## ESP32-CAM firmware
1. Install Arduino IDE and the Espressif ESP32 board package.
2. Open `firmware/esp32cam_node/esp32cam_node.ino`.
3. Select **AI Thinker ESP32-CAM**.
4. Edit Wi-Fi, server URL, camera ID, and MQTT values in `firmware/esp32cam_node/secrets.example.h`, then save as `secrets.h`.
5. Upload using an FTDI adapter. Use a stable 5V supply; GPIO0 must be connected to GND during flashing and disconnected for normal boot.
6. Browse to the node IP to view status and configure capture settings.

Firmware sends JPEG frames to `POST /api/v1/frames` and publishes status/control through MQTT when enabled. The HTTP path works without MQTT.

## API overview
- `GET /health`: server health.
- `GET /api/v1/cameras`: registered camera nodes.
- `POST /api/v1/frames`: JPEG upload; headers `X-Camera-ID`, `X-Capture-Timestamp-Ms`.
- `GET /api/v1/metrics`: aggregate counters and latency summaries.
- `GET /api/v1/events`: recent detection events.
- `GET /api/v1/cameras/{camera_id}/snapshot`: latest JPEG frame.
- `GET /api/v1/cameras/{camera_id}/stream`: MJPEG stream of newly received frames.
- `POST /api/v1/control/{camera_id}`: publish supported camera settings through MQTT (requires MQTT enabled).

## Research integrity
Record firmware version, model file checksum, input dimensions, confidence/IoU thresholds, camera placement, lighting, network conditions, and all policy settings for each experiment. Keep continuous-video ground truth independent of transmitted frames to measure missed events. The included AEBAS policy is a prototype for controlled experiments, not a validated optimal algorithm.

## License
MIT. See [LICENSE](LICENSE).


## NOVIX web dashboard

The web UI is served by the same FastAPI process; no separate frontend build is required. Start the edge server, then open:

- Dashboard: `http://<PI_IP>:8000/`
- API docs: `http://<PI_IP>:8000/docs`

For camera controls, configure the MQTT broker in `config/server.yaml` and set `mqtt.enabled: true`. The current firmware accepts `capture_interval_ms`, `streaming_enabled`, and `resolution` (QVGA/VGA) on `<topic_prefix>/<camera_id>/control`. Keep MQTT credentials private. The web UI deliberately does not show motor movement controls because the current ESP32-CAM firmware does not implement a motor driver.

The live camera panel displays the newest JPEG uploaded by each camera. Its effective update rate is therefore limited by the ESP32-CAM capture interval and network upload rate; it is not a full-frame-rate video stream. Host CPU/RAM/temperature, camera battery, and Wi-Fi RSSI are not reported by the current edge API and are not displayed as invented values.

**Network security:** use this dashboard on a trusted LAN during development. Do not expose port 8000 or the MQTT broker directly to the public internet without authentication, TLS, firewall rules, and an access-control design.
