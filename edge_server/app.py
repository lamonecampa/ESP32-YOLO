"""FastAPI edge receiver with optional Ultralytics YOLO inference."""
from __future__ import annotations

import argparse
import logging
import asyncio
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.publish as mqtt_publish
from ultralytics import YOLO

from edge_server.scheduler.policies import CameraSignal, SchedulerConfig, priority_score, classify_priority

LOG = logging.getLogger("esp32yolo")


class Runtime:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.lock = threading.Lock()
        self.cameras: dict[str, dict[str, Any]] = {}
        self.latest_frames: dict[str, bytes] = {}
        self.mqtt_cfg = config.get("mqtt", {})
        self.events = deque(maxlen=int(config["server"].get("recent_event_limit", 500)))
        self.counters = defaultdict(int)
        self.latencies_ms = deque(maxlen=2000)
        self.model = None
        self.model_lock = threading.Lock()
        self.scheduler_cfg = self._scheduler_config(config.get("scheduler", {}))
        inf = config.get("inference", {})
        self.inference_enabled = bool(inf.get("enabled", True))
        self.model_path = str(inf.get("model", "yolov8n.pt"))
        self.device = str(inf.get("device", "cpu"))
        self.image_size = int(inf.get("image_size", 640))
        self.confidence = float(inf.get("confidence", 0.35))
        self.iou = float(inf.get("iou", 0.45))
        self.classes = inf.get("classes")
        if self.inference_enabled:
            model_file = Path(self.model_path)
            if model_file.suffix in (".pt", ".onnx") and not model_file.exists():
                LOG.warning("Configured model file does not exist: %s; inference disabled", self.model_path)
                self.inference_enabled = False
            else:
                try:
                    self.model = YOLO(self.model_path)
                    LOG.info("Loaded YOLO model: %s", self.model_path)
                except Exception:
                    LOG.exception("Could not load YOLO model; inference disabled")
                    self.inference_enabled = False

    @staticmethod
    def _scheduler_config(raw: dict[str, Any]) -> SchedulerConfig:
        weights = raw.get("weights", {})
        return SchedulerConfig(
            low_threshold=float(raw.get("low_threshold", 0.08)),
            high_threshold=float(raw.get("high_threshold", 0.35)),
            motion_weight=float(weights.get("motion", 0.30)),
            confidence_weight=float(weights.get("confidence", 0.20)),
            urgency_weight=float(weights.get("urgency", 0.25)),
            freshness_weight=float(weights.get("freshness", 0.25)),
            max_frame_age_ms=float(raw.get("max_frame_age_ms", 2500)),
            starvation_limit_ms=float(raw.get("starvation_limit_ms", 10000)),
        )

    def infer(self, image: np.ndarray) -> list[dict[str, Any]]:
        if self.model is None:
            return []
        with self.model_lock:
            results = self.model.predict(
                source=image, imgsz=self.image_size, conf=self.confidence,
                iou=self.iou, classes=self.classes, device=self.device,
                verbose=False
            )
        detections: list[dict[str, Any]] = []
        for result in results:
            names = result.names
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls.item())
                detections.append({
                    "class_id": cls_id,
                    "class_name": str(names.get(cls_id, cls_id)),
                    "confidence": float(box.conf.item()),
                    "xyxy": [float(v) for v in box.xyxy[0].tolist()],
                })
        return detections


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    config = config or {}
    config.setdefault("server", {})
    config.setdefault("inference", {})
    config.setdefault("scheduler", {})
    runtime = Runtime(config)
    app = FastAPI(
        title="ESP32-YOLO Edge Vision API",
        version="0.1.0",
        description="Multi-camera JPEG receiver and edge-side YOLO inference.",
    )
    app.state.runtime = runtime

    @app.get("/health")
    def health():
        return {"status": "ok", "inference_enabled": runtime.inference_enabled,
                "model_loaded": runtime.model is not None}

    @app.get("/api/v1/cameras")
    def cameras():
        with runtime.lock:
            return {"cameras": list(runtime.cameras.values())}

    @app.post("/api/v1/frames")
    async def receive_frame(
        file: UploadFile = File(...),
        x_camera_id: str = Header(default="camera-unknown", alias="X-Camera-ID"),
        x_capture_timestamp_ms: int | None = Header(default=None, alias="X-Capture-Timestamp-Ms"),
        x_motion_score: float = Header(default=0.0, alias="X-Motion-Score"),
    ):
        max_bytes = int(config["server"].get("max_upload_bytes", 2_000_000))
        if file.content_type not in ("image/jpeg", "application/octet-stream"):
            raise HTTPException(status_code=415, detail="Expected JPEG image")
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail="Image exceeds configured upload limit")
        if not data:
            raise HTTPException(status_code=400, detail="Empty image payload")

        started = time.perf_counter()
        decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise HTTPException(status_code=400, detail="Invalid JPEG payload")

        capture_ms = x_capture_timestamp_ms
        age_ms = max(0.0, time.time() * 1000 - capture_ms) if capture_ms else None
        detections = runtime.infer(decoded)
        inference_ms = (time.perf_counter() - started) * 1000
        max_conf = max((d["confidence"] for d in detections), default=0.0)
        urgency = 1.0 if any(d["class_id"] == 0 for d in detections) else 0.0

        signal = CameraSignal(
            camera_id=x_camera_id,
            motion_score=max(0.0, min(1.0, x_motion_score)),
            last_confidence=max_conf,
            urgency=urgency,
            age_ms=age_ms or 0.0,
        )
        score = priority_score(signal, runtime.scheduler_cfg)
        priority = classify_priority(signal, runtime.scheduler_cfg).name.lower()
        received_ms = int(time.time() * 1000)
        event = {
            "camera_id": x_camera_id,
            "capture_timestamp_ms": capture_ms,
            "received_timestamp_ms": received_ms,
            "age_ms": age_ms,
            "image_width": int(decoded.shape[1]),
            "image_height": int(decoded.shape[0]),
            "image_bytes": len(data),
            "inference_ms": inference_ms,
            "end_to_end_server_ms": (time.perf_counter() - started) * 1000,
            "detections": detections,
            "priority_score": score,
            "priority": priority,
        }
        with runtime.lock:
            runtime.latest_frames[x_camera_id] = data
            runtime.counters["frames_received"] += 1
            runtime.counters["bytes_received"] += len(data)
            runtime.counters["detections"] += len(detections)
            runtime.latencies_ms.append(event["end_to_end_server_ms"])
            previous = runtime.cameras.get(x_camera_id, {})
            runtime.cameras[x_camera_id] = {
                "camera_id": x_camera_id,
                "last_seen_ms": received_ms,
                "frames_received": int(previous.get("frames_received", 0)) + 1,
                "last_width": event["image_width"],
                "last_height": event["image_height"],
                "last_priority": priority,
            }
            runtime.events.append(event)
        return JSONResponse(event)

    @app.get("/api/v1/metrics")
    def metrics():
        with runtime.lock:
            latencies = sorted(runtime.latencies_ms)
            p95 = latencies[min(len(latencies)-1, int(0.95 * len(latencies)))] if latencies else None
            counters = dict(runtime.counters)
            cameras_count = len(runtime.cameras)
        return {**counters, "registered_cameras": cameras_count,
                "server_latency_p95_ms": p95,
                "inference_enabled": runtime.inference_enabled}

    @app.get("/api/v1/events")
    def events(limit: int = Query(default=50, ge=1, le=500)):
        with runtime.lock:
            return {"events": list(runtime.events)[-limit:]}


    @app.get("/api/v1/cameras/{camera_id}/snapshot")
    def camera_snapshot(camera_id: str):
        with runtime.lock:
            frame = runtime.latest_frames.get(camera_id)
        if frame is None:
            raise HTTPException(status_code=404, detail="No frame received from this camera yet")
        return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/cameras/{camera_id}/stream")
    async def camera_stream(camera_id: str):
        with runtime.lock:
            known = camera_id in runtime.cameras
        if not known:
            raise HTTPException(status_code=404, detail="Unknown camera")
        async def frame_generator():
            last_frame = None
            while True:
                with runtime.lock:
                    frame = runtime.latest_frames.get(camera_id)
                if frame is not None and frame is not last_frame:
                    last_frame = frame
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-store\r\n\r\n" + frame + b"\r\n"
                await asyncio.sleep(0.15)
        return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

    @app.post("/api/v1/control/{camera_id}")
    def control_camera(camera_id: str, command: dict[str, Any]):
        mqtt_cfg = runtime.mqtt_cfg
        if not mqtt_cfg.get("enabled", False):
            raise HTTPException(status_code=503, detail="MQTT control is disabled in server configuration")
        with runtime.lock:
            known = camera_id in runtime.cameras
        if not known:
            raise HTTPException(status_code=404, detail="Unknown camera")
        allowed: dict[str, Any] = {}
        if "capture_interval_ms" in command:
            interval = command["capture_interval_ms"]
            if not isinstance(interval, int) or not 250 <= interval <= 60000:
                raise HTTPException(status_code=422, detail="capture_interval_ms must be 250..60000")
            allowed["capture_interval_ms"] = interval
        if "streaming_enabled" in command:
            if not isinstance(command["streaming_enabled"], bool):
                raise HTTPException(status_code=422, detail="streaming_enabled must be boolean")
            allowed["streaming_enabled"] = command["streaming_enabled"]
        if "resolution" in command:
            resolution = str(command["resolution"]).upper()
            if resolution not in ("QVGA", "VGA"):
                raise HTTPException(status_code=422, detail="resolution must be QVGA or VGA")
            allowed["resolution"] = resolution
        if not allowed:
            raise HTTPException(status_code=422, detail="No supported camera command supplied")
        topic = f"{mqtt_cfg.get('topic_prefix', 'esp32yolo')}/{camera_id}/control"
        try:
            mqtt_publish.single(topic, payload=__import__("json").dumps(allowed),
                hostname=str(mqtt_cfg.get("host", "127.0.0.1")), port=int(mqtt_cfg.get("port", 1883)),
                auth=({"username": mqtt_cfg.get("username"), "password": mqtt_cfg.get("password")}
                      if mqtt_cfg.get("username") else None), qos=1, retain=False, keepalive=10)
        except Exception as exc:
            LOG.exception("MQTT command failed for %s", camera_id)
            raise HTTPException(status_code=502, detail=f"MQTT publish failed: {exc}") from exc
        return {"status": "published", "camera_id": camera_id, "topic": topic, "command": allowed}

    web_dir = Path(__file__).resolve().parent / "web"
    if web_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(web_dir)), name="assets")
        @app.get("/", include_in_schema=False)
        def web_dashboard():
            return FileResponse(web_dir / "index.html")

    return app


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def main():
    parser = argparse.ArgumentParser(description="ESP32-YOLO edge server")
    parser.add_argument("--config", default="config/server.yaml")
    args = parser.parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config not found: {config_path}. Copy config/server.example.yaml first.")
    config = load_config(str(config_path))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import uvicorn
    uvicorn.run(create_app(config), host=config.get("server", {}).get("host", "0.0.0.0"),
                port=int(config.get("server", {}).get("port", 8000)))


if __name__ == "__main__":
    main()
