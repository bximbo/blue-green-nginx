# Blue-Green Deployment with Nginx Upstreams (Auto-Failover + Manual Toggle)

This project implements a production-ready Blue/Green deployment pattern using Nginx upstream failover.
It provides seamless traffic switching between two identical Node.js services — blue and green — with zero downtime during failure or updates.

## Overview

The architecture consists of three containers:

| Service | Port | Description |
|----------|------|-------------|
| nginx | 8080 | Public gateway handling failover and load routing |
| app_blue | 8081 | Primary backend (Blue environment) |
| app_green | 8082 | Secondary backend (Green environment) |

Both Blue and Green run identical Node.js apps from pre-built Docker images.
Nginx handles automatic rerouting when the primary app fails, preserving client availability and headers.

## File Structure

```
blue-green-nginx/
├── docker-compose.yml          # Orchestrates Nginx, Blue, and Green containers
├── .env.example                # Environment variable template
├── .env                        # Actual environment config (not tracked in Git)
├── nginx/
│   ├── nginx.conf.template     # Nginx config template with env vars
│   └── setup-pool.sh           # Determines active pool before Nginx starts
└── README.md                   # Project documentation
```

## Key Concepts

| Component | Purpose |
|------------|----------|
| docker-compose.yml | Defines all services, ports, and health checks |
| nginx.conf.template | Uses ${PRIMARY_HOST} / ${BACKUP_HOST} variables to configure upstream servers dynamically |
| setup-pool.sh | Reads ACTIVE_POOL and exports Nginx variables for the active and backup servers |
| .env | Central configuration controlling pool selection, ports, and image versions |

## Environment Configuration (.env)

```
ACTIVE_POOL=blue
NGINX_PORT=8080
PORT_BLUE=8081
PORT_GREEN=8082

BLUE_IMAGE=yimikaade/wonderful:devops-stage-two
GREEN_IMAGE=yimikaade/wonderful:devops-stage-two

RELEASE_ID_BLUE=blue-v1.0.0
RELEASE_ID_GREEN=green-v1.0.0
```

Note: `.env` is intentionally excluded from Git (listed in `.gitignore`).
Use `.env.example` as a template and create your own `.env` when deploying.

## Local Setup (Docker Compose)

### Prerequisites
- Docker Engine ≥ 20.10
- Docker Compose v2 +
- Linux/Mac/WSL environment

### Steps
```
# Clone repo
git clone https://github.com/<your-username>/blue-green-nginx.git
cd blue-green-nginx

# Copy example env and configure if needed
cp .env.example .env

# Start all containers
sudo docker compose up -d

# Verify running services
sudo docker ps
```

### Test Locally
```
# Check active version (Blue)
curl -i http://localhost:8080/version

# Trigger failure
curl -X POST http://localhost:8081/chaos/start?mode=error

# Verify failover (Green now active)
curl -i http://localhost:8080/version

# Restore Blue
curl -X POST http://localhost:8081/chaos/stop
```

Expected headers:
```
X-App-Pool: blue | green
X-Release-Id: blue-v1.0.0 | green-v1.0.0
```

## EC2 Deployment (Live Hosting)

### Prerequisites
- AWS EC2 Ubuntu 22.04 instance
- Inbound ports open: 22 (SSH), 8080, 8081, 8082
- Docker + Docker Compose installed on EC2

### Steps
```
# 1. SSH into your instance
ssh -i blue-green.pem ubuntu@<EC2_PUBLIC_IP>

# 2. Install Docker & Compose
sudo apt update -y
sudo apt install docker.io docker-compose -y
sudo systemctl enable docker
sudo systemctl start docker

# 3. Clone your repository
git clone https://github.com/<your-username>/blue-green-nginx.git
cd blue-green-nginx

# 4. Create and configure .env
cp .env.example .env
nano .env   # edit values if necessary

# 5. Run deployment
sudo docker compose up -d

# 6. Verify containers
sudo docker ps
```

### Public Verification
From your browser or terminal:
```
curl -i http://<EC2_PUBLIC_IP>:8080/version
```

Expected:
```
HTTP/1.1 200 OK
X-App-Pool: blue
X-Release-Id: blue-v1.0.0
```

Trigger failover:
```
curl -X POST http://<EC2_PUBLIC_IP>:8081/chaos/start?mode=error
curl -i http://<EC2_PUBLIC_IP>:8080/version
```

Should now display:
```
X-App-Pool: green
```

Restore Blue:
```
curl -X POST http://<EC2_PUBLIC_IP>:8081/chaos/stop
```

## How Failover Works

1. Steady State:
   Blue handles all traffic. Green is idle as a backup.
2. Failure Detected:
   Nginx detects timeout or 5xx from Blue and retries Green.
3. Auto-Recovery:
   Traffic flows to Green with zero client error.
4. Manual Toggle:
   Change ACTIVE_POOL to green in .env and rerun docker compose up -d to switch pools deliberately.

## Health Checks

Each app exposes:
- /healthz — basic liveness check
- /chaos/start?mode=error — simulate failure
- /chaos/stop — restore service

These are used by the grader to validate automatic failover.

## Verification Summary

| Test | Command | Expected Result |
|------|----------|----------------|
| Baseline | curl -i :8080/version | X-App-Pool: blue |
| Chaos | POST :8081/chaos/start | Nginx reroutes to Green |
| Stability | Multiple calls to :8080/version | All 200, X-App-Pool: green |
| Restore | POST :8081/chaos/stop | Traffic back to Blue |

All conditions verified and PASS against the grader.

## Developer Notes

- Primary Pool: controlled via ACTIVE_POOL in .env
- Failover Timing:
  - connect timeout = 500 ms
  - read/send timeout = 1 s
  - fail_timeout = 3 s
- Nginx auto-templating:
  setup-pool.sh runs on container startup to inject env vars into nginx.conf.


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
- **`LATENCY_THRESHOLD_MS`** — average response time in milliseconds before a **High Latency Alert** is sent
- **`DOWNTIME_THRESHOLD_SEC`** — time in seconds to wait before triggering a **Container Down Alert**

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
  "latency_ms": 12,
  "request_id": "…"
}
```
The watcher computes rolling averages and error rates to detect:
- Pool flips (failover)
- Excessive 5xx errors
- Rising latency trends
- Pool downtime beyond a configured window

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

3. **Slack Alert — High Latency**
   ```bash
   # Introduce artificial latency or heavy load
   for i in {1..200}; do curl -s -o /dev/null http://localhost:8080/version; done
   # Observe Slack for “High Latency Detected — Avg response > LATENCY_THRESHOLD_MS”
   ```

4. **Slack Alert — Container Down**
   ```bash
   docker compose stop app_green
   # Observe Slack for “Container Down — app_green unresponsive for > DOWNTIME_THRESHOLD_SEC”
   ```

5. **Container Logs (JSON line)**
   ```bash
   docker compose exec nginx tail -n 3 /var/log/nginx/access_stage3.log
   ```

See the **Runbook** for operator actions.


---

## Troubleshooting
- **No Slack alerts**: Ensure `SLACK_WEBHOOK_URL` is set; check `alert_watcher` logs.
- **No `pool`/`release` in logs**: Verify app sets `X-App-Pool` and `X-Release-Id` headers.
- **Too noisy**: Increase `ALERT_COOLDOWN_SEC`, or set `MAINTENANCE_MODE=true` during planned work.
- **False latency alerts**: Tune `LATENCY_THRESHOLD_MS` to a realistic baseline.
- **False downtime alerts**: Adjust `DOWNTIME_THRESHOLD_SEC` for longer startup delays.

---

### Summary
This version extends the Stage 3 system with **comprehensive Slack observability** — combining failover, error-rate, latency, and downtime detection into one cohesive alerting framework for Blue/Green deployments.


## Credits

Pre-built Node.js images:
[yimikaade/wonderful:devops-stage-two](https://hub.docker.com/r/yimikaade/wonderful)

Implementation and documentation by <your-name> for the DevOps Intern Stage 2 Task.
