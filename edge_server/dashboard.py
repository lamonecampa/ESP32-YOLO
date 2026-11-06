"""Small Streamlit dashboard for the edge server's research metrics."""
import os
import time

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="ESP32-YOLO Research Monitor", layout="wide")
st.title("ESP32-YOLO | Research Monitor")
st.caption("Live telemetry from the Raspberry Pi edge server")

default_url = os.getenv("EDGE_API_URL", "http://127.0.0.1:8000")
base_url = st.sidebar.text_input("Edge API URL", default_url).rstrip("/")
refresh = st.sidebar.slider("Refresh interval (seconds)", 2, 30, 5)
auto = st.sidebar.checkbox("Auto refresh", value=True)

try:
    health = requests.get(f"{base_url}/health", timeout=3).json()
    metrics = requests.get(f"{base_url}/api/v1/metrics", timeout=3).json()
    cameras = requests.get(f"{base_url}/api/v1/cameras", timeout=3).json().get("cameras", [])
    events = requests.get(f"{base_url}/api/v1/events?limit=100", timeout=3).json().get("events", [])
except requests.RequestException as exc:
    st.error(f"Cannot reach edge API: {exc}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Server", health.get("status", "unknown"))
c2.metric("Frames received", metrics.get("frames_received", 0))
c3.metric("Registered cameras", metrics.get("registered_cameras", 0))
c4.metric("P95 server latency", f"{metrics['server_latency_p95_ms']:.1f} ms" if metrics.get("server_latency_p95_ms") is not None else "n/a")

st.subheader("Camera nodes")
if cameras:
    st.dataframe(pd.DataFrame(cameras), use_container_width=True, hide_index=True)
else:
    st.info("No camera has uploaded a frame yet.")

st.subheader("Recent inference events")
if events:
    rows = []
    for event in reversed(events):
        rows.append({
            "camera": event.get("camera_id"),
            "received_ms": event.get("received_timestamp_ms"),
            "image": f"{event.get('image_width')}x{event.get('image_height')}",
            "bytes": event.get("image_bytes"),
            "inference_ms": round(event.get("inference_ms", 0), 2),
            "priority": event.get("priority"),
            "detections": ", ".join(
                f"{d.get('class_name')} ({d.get('confidence', 0):.2f})"
                for d in event.get("detections", [])
            ),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No detection events yet.")

st.subheader("Research note")
st.warning("P95 shown here is server processing latency, not synchronized camera-to-edge latency. Use synchronized clocks or capture/receive clock calibration before reporting end-to-end latency in a paper.")

if auto:
    time.sleep(refresh)
    st.rerun()
