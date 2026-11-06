#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include "esp_timer.h"
#include "secrets.h"

// AI Thinker ESP32-CAM pin mapping
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WebServer web(80);
WiFiClient mqttNet;
PubSubClient mqtt(mqttNet);

String cameraId = CAMERA_ID;
uint32_t captureIntervalMs = 2000;
uint32_t lastCaptureMs = 0;
bool streamingEnabled = true;
framesize_t frameSize = FRAMESIZE_QVGA;
int jpegQuality = 12;
uint32_t sentFrames = 0;
uint32_t failedFrames = 0;
uint32_t lastReconnectMs = 0;

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting Wi-Fi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 25000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Node IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection timed out; reconnect loop will retry.");
  }
}

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = frameSize;
  config.jpeg_quality = jpegQuality;
  config.fb_count = psramFound() ? 2 : 1;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String body;
  for (unsigned int i = 0; i < length; i++) body += (char)payload[i];
  if (body.indexOf("\"capture_interval_ms\"") >= 0) {
    int keyPos = body.indexOf("capture_interval_ms");
    int pos = body.indexOf(':', keyPos);
    if (pos > 0) {
      uint32_t requested = (uint32_t)body.substring(pos + 1).toInt();
      captureIntervalMs = constrain(requested, (uint32_t)250, (uint32_t)60000);
    }
  }
  if (body.indexOf("\"streaming_enabled\":false") >= 0) streamingEnabled = false;
  if (body.indexOf("\"streaming_enabled\":true") >= 0) streamingEnabled = true;
  if (body.indexOf("\"resolution\":\"VGA\"") >= 0) {
    frameSize = FRAMESIZE_VGA;
    sensor_t* sensor = esp_camera_sensor_get();
    sensor->set_framesize(sensor, frameSize);
  }
  if (body.indexOf("\"resolution\":\"QVGA\"") >= 0) {
    frameSize = FRAMESIZE_QVGA;
    sensor_t* sensor = esp_camera_sensor_get();
    sensor->set_framesize(sensor, frameSize);
  }
}

void ensureMqtt() {
#if MQTT_ENABLED
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  String clientId = "esp32yolo-" + cameraId;
  bool ok;
  if (String(MQTT_USER).length()) ok = mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD);
  else ok = mqtt.connect(clientId.c_str());
  if (ok) {
    String topic = String("esp32yolo/") + cameraId + "/control";
    mqtt.subscribe(topic.c_str());
    String statusTopic = String("esp32yolo/") + cameraId + "/status";
    String payload = String("{\"online\":true,\"ip\":\"") + WiFi.localIP().toString() + "\"}";
    mqtt.publish(statusTopic.c_str(), payload.c_str(), true);
  }
#endif
}

void handleRoot() {
  String html = "<html><head><meta name='viewport' content='width=device-width'></head><body>";
  html += "<h2>ESP32-YOLO Camera Node</h2><p>ID: " + cameraId + "</p>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p>Sent: " + String(sentFrames) + " Failed: " + String(failedFrames) + "</p>";
  html += "<p>Interval: " + String(captureIntervalMs) + " ms</p>";
  html += "<p><a href='/capture'>Capture test</a> | <a href='/status'>JSON status</a></p>";
  html += "</body></html>";
  web.send(200, "text/html", html);
}

void handleStatus() {
  String json = "{";
  json += "\"camera_id\":\"" + cameraId + "\",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"sent_frames\":" + String(sentFrames) + ",";
  json += "\"failed_frames\":" + String(failedFrames) + ",";
  json += "\"capture_interval_ms\":" + String(captureIntervalMs) + ",";
  json += "\"psram\":" + String(psramFound() ? "true" : "false");
  json += "}";
  web.send(200, "application/json", json);
}

bool sendFrame(camera_fb_t* fb) {
  if (!fb || WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  String url = String(EDGE_SERVER_URL) + "/api/v1/frames";
  if (!http.begin(url)) return false;
  http.setTimeout(10000);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Camera-ID", cameraId);
  // ESP timer is monotonic, not Unix time. Server computes frame age only
  // when a Unix epoch timestamp is supplied, so this header is diagnostic.
  http.addHeader("X-Node-Uptime-Ms", String((uint64_t)esp_timer_get_time() / 1000ULL));
  http.addHeader("X-Motion-Score", "0");
  int code = http.POST(fb->buf, fb->len);
  http.end();
  return code >= 200 && code < 300;
}

void handleCapture() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    web.send(500, "text/plain", "Capture failed");
    return;
  }
  bool ok = sendFrame(fb);
  esp_camera_fb_return(fb);
  web.send(ok ? 200 : 502, "text/plain", ok ? "Frame sent to edge server" : "Upload failed");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  if (!initCamera()) {
    Serial.println("Camera initialization failed. Check board selection and power.");
    while (true) delay(1000);
  }
  connectWifi();
  mqtt.setCallback(mqttCallback);
  web.on("/", handleRoot);
  web.on("/status", handleStatus);
  web.on("/capture", handleCapture);
  web.begin();
}

void loop() {
  web.handleClient();
  if (WiFi.status() != WL_CONNECTED && millis() - lastReconnectMs >= 10000) {
    lastReconnectMs = millis();
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
  ensureMqtt();
  mqtt.loop();
  if (WiFi.status() != WL_CONNECTED) {
    delay(10);
    return;
  }
  uint32_t now = millis();
  if (streamingEnabled && now - lastCaptureMs >= captureIntervalMs) {
    lastCaptureMs = now;
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb) {
      bool ok = sendFrame(fb);
      esp_camera_fb_return(fb);
      if (ok) sentFrames++; else failedFrames++;
    } else {
      failedFrames++;
    }
  }
  delay(2);
}
