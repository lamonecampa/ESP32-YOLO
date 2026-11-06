# Edge API

Base URL: `http://<edge-host>:8000`

## Upload a frame
`POST /api/v1/frames`

Multipart field: `file` (JPEG)

Headers:
- `X-Camera-ID`: stable node identifier.
- `X-Capture-Timestamp-Ms`: capture timestamp in Unix milliseconds (recommended).
- `X-Motion-Score`: optional normalized scene-change score [0,1].

Example:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/frames \
  -H 'X-Camera-ID: camera-01' \
  -F 'file=@frame.jpg;type=image/jpeg'
```

## Read endpoints
- `GET /health`
- `GET /api/v1/cameras`
- `GET /api/v1/metrics`
- `GET /api/v1/events?limit=50`

The API currently keeps recent metrics/events in process memory. Use an external time-series database for long-running research trials.
