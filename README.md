# Blue–Green Nginx (Stage 2) + Stage 3 Observability & Slack Alerts

This repository implements a production‑grade **Blue/Green** deployment with Nginx upstream failover (Stage 2) and extends it with **log‑based observability + Slack alerts** (Stage 3). No app images are modified — everything happens at the Nginx and sidecar levels.

## Contents
- Nginx upstream config with **dynamic primary/backup** from `ACTIVE_POOL`
- **Structured JSON access logs** capturing: `pool`, `release`, `upstream_status`, `upstream_addr`, `request_time`, `upstream_response_time`
- **Python log watcher** that tails Nginx logs and posts to Slack on:
  - Failover events (blue ↔ green)
  - Elevated upstream 5xx error rate over a sliding window
- Operator **runbook** with clear actions and a maintenance‑mode flag to suppress noise

---

## Prerequisites
- Docker Engine ≥ 20.10, Docker Compose v2+
- `.env` created from `.env.example` (do **not** commit real secrets)
- Ports open locally (or on EC2): `8080` (Nginx), `8081` (Blue), `8082` (Green)

---

## Quick Start
```bash
# 1) Copy example env and configure
cp .env.example .env
# Fill in (at minimum):
#   ACTIVE_POOL=blue|green
#   SLACK_WEBHOOK_URL=<Slack Incoming Webhook URL>

# 2) Bring up the stack
docker compose up -d

# 3) Sanity checks
curl -I http://localhost:8080/version | grep -Ei 'X-App-Pool|X-Release-Id'
docker compose logs -f alert_watcher
docker compose exec nginx tail -n 3 /var/log/nginx/access_stage3.log
```

**Expected headers (steady state):**
```
X-App-Pool: blue | green
X-Release-Id: <value from .env>
```

---

## Environment Variables (Stage 2 + Stage 3)
These live in `.env` (real) and `.env.example` (safe to commit).

### Core
- `BLUE_IMAGE`, `GREEN_IMAGE` — Docker images for each app
- `ACTIVE_POOL` — initial primary pool (`blue` or `green`)
- `RELEASE_ID_BLUE`, `RELEASE_ID_GREEN` — shown in `X-Release-Id`
- `NGINX_PORT`, `PORT_BLUE`, `PORT_GREEN` — host port mappings

### Alerts
- `SLACK_WEBHOOK_URL` — Slack Incoming Webhook (**set in real `.env` only**)
- `ERROR_RATE_THRESHOLD` — percent 5xx to trigger alert (default `2`)
- `WINDOW_SIZE` — sliding window size in requests (default `200`)
- `ALERT_COOLDOWN_SEC` — rate‑limit for repeated alerts (default `300`)
- `MAINTENANCE_MODE` — `true` to suppress alerts for planned toggles

---

## What the Logs Capture
Per request, Nginx writes JSON lines like:
```json
{
  "time_local": "29/Oct/2025:23:59:59 +0000",
  "remote_addr": "172.20.0.1",
  "request": "GET /version HTTP/1.1",
  "status": 200,
  "bytes_sent": 123,
  "request_time": 0.012,
  "upstream_response_time": "0.011",
  "upstream_status": "200",
  "upstream_addr": "app_blue:3000",
  "pool": "blue",
  "release": "blue-v1.0.0",
  "request_id": "…"
}
```

These are tailed by the watcher to compute rolling error rates and detect pool flips.

---

## Trigger the Required Screenshots

1. **Slack Alert — Failover Event**
   ```bash
   # If ACTIVE_POOL=blue
   curl -s -o /dev/null http://localhost:8080/version
   docker compose stop app_blue
   # Observe Slack for “Failover Detected”
   ```

2. **Slack Alert — High Error Rate**
   ```bash
   docker compose stop app_blue && sleep 5 && docker compose up -d app_blue
   # Observe Slack for “High Upstream Error Rate … % over last N requests”
   ```

3. **Container Logs (JSON line)**
   ```bash
   docker compose exec nginx tail -n 3 /var/log/nginx/access_stage3.log
   ```

See the **Runbook** for operator actions.

---

## EC2 Notes (Optional)
- Open inbound: `22`, `8080`, `8081`, `8082`
- After `docker compose up -d`, verify with:
  ```bash
  curl -i http://<EC2_PUBLIC_IP>:8080/version
  ```

---

## Troubleshooting
- **No Slack alerts**: Ensure `SLACK_WEBHOOK_URL` is set; check `alert_watcher` logs.
- **No `pool`/`release` in logs**: Verify app sets `X-App-Pool` and `X-Release-Id` headers.
- **Too noisy**: Increase `ALERT_COOLDOWN_SEC`, or set `MAINTENANCE_MODE=true` during planned work.
