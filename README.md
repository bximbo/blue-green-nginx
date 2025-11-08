# Blue-Green Deployment with Nginx Upstreams 

This project implements a production ready Blue/Green deployment pattern using Nginx upstream failover.
It provides seamless traffic switching between two identical Node.js services — blue and green — with zero downtime during failure or updates. Timeless. 

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
├── .env.example                # Environment variable template (suffices)
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
Use `.env.example` as a template and create your own `.env` when deploying. Also a note to my future self.

## Local Setup (Docker Compose)

### Prerequisites
- Docker Engine ≥ 20.10
- Docker Compose v2 + (See my first line in the compose file)
- Linux/Mac/WSL environment (Definitely friendly)

### Steps
```
# Clone repo
git clone https://github.com/bximbo/blue-green-nginx.git
cd blue-green-nginx

# Copy example env and configure if needed
cp .env.example .env

# Insert your webhook in SLACK_WEBHOOK_URL

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

### Prerequisites - Mine at least
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
git clone  https://github.com/bximbo/blue-green-nginx.git
cd blue-green-nginx

# 4. Create and configure .env
cp .env.example .env
nano .env   # edit values if necessary

# 5. Insert your webhook in SLACK_WEBHOOK_URL

# 6. Run deployment
sudo docker compose up -d

# 7. Verify containers
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

## Credits

Pre-built Node.js images:
[yimikaade/wonderful:devops-stage-two](https://hub.docker.com/r/yimikaade/wonderful)

Implementation and documentation by Bimbo for the DevOps Intern Stage 2 Task :)
