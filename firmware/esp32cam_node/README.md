# ESP32-CAM firmware

Board target: AI Thinker ESP32-CAM with OV2640.

## Dependencies
- Espressif Arduino-ESP32 board package (use a current stable release).
- PubSubClient by Nick O'Leary.
- ESP32 camera driver provided by the Espressif Arduino core.

## Configure
Copy `secrets.example.h` to `secrets.h` and set Wi-Fi credentials, camera ID, and the Raspberry Pi server URL.

## Upload notes
- Select **AI Thinker ESP32-CAM** in Arduino IDE.
- Use a stable 5V supply capable of handling camera/Wi-Fi current peaks.
- For flashing, connect GPIO0 to GND and reset; remove GPIO0 from GND after upload and reset again.
- Serial monitor: 115200 baud.

The firmware transmits periodic JPEG frames. MQTT is optional and disabled by default. When enabled, the node subscribes to `esp32yolo/<camera-id>/control` and publishes status to `esp32yolo/<camera-id>/status`.

Current prototype note: capture interval/resolution can be controlled by MQTT, but event score is currently a server-side research input. Local visual change estimation and secure MQTT/TLS are planned hardening tasks.
