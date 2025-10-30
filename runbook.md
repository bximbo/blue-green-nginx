# Stage 3 Runbook — Alerts, Meanings, and Actions

This runbook explains what alerts mean, what to do, and how to suppress noise during planned switches.

---

## Alerts You’ll See

### 1) Failover Detected — `blue → green` (or `green → blue`)
**What it means**  
The pool reported by the upstream header (`X-App-Pool`) differs from the previous request sample. This indicates:
- The active pool flipped due to failure (timeouts/5xx), **or**
- An operator deliberately toggled pools.

**Immediate actions**
1. Identify the unhealthy app:
   ```bash
   docker compose ps
   docker compose logs app_blue -f   # or app_green
   ```
2. If it crashed or is misbehaving, restart:
   ```bash
   docker compose up -d app_blue     # or app_green
   ```
3. Verify recovery:
   ```bash
   curl -I http://localhost:8080/version | grep -Ei 'X-App-Pool|X-Release-Id'
   ```

**If this was planned**  
Toggle **maintenance mode** to suppress alerts:
```bash
# in .env
MAINTENANCE_MODE=true
docker compose up -d alert_watcher
# ...perform your switch...
# then
MAINTENANCE_MODE=false
docker compose up -d alert_watcher
```

---

### 2) High Upstream Error Rate
**What it means**  
Over the last `WINDOW_SIZE` requests, the percentage of 5xx observed in `upstream_status` exceeded `ERROR_RATE_THRESHOLD` (defaults: 200 requests, 2%). Nginx counts gateway errors like `502/504` when the app is down or slow.

**Immediate actions**
1. Inspect which upstream is failing:
   ```bash
   docker compose exec nginx tail -n 50 /var/log/nginx/access_stage3.log
   # Look at: upstream_status, upstream_addr, pool, release
   ```
2. Check app health:
   ```bash
   docker compose logs app_blue -f   # or app_green
   ```
3. If needed, **toggle pools** deliberately:
   ```bash
   # edit .env
   ACTIVE_POOL=green   # or blue
   docker compose up -d nginx
   ```
4. After stabilization, ensure `MAINTENANCE_MODE=false` and keep watcher running.

**Noise reduction**  
- Increase `ALERT_COOLDOWN_SEC` to rate‑limit repeats.
- Increase `WINDOW_SIZE` for more smoothing.

---

## Routine Ops

**View recent JSON logs**
```bash
docker compose exec nginx tail -n 3 /var/log/nginx/access_stage3.log
```

**Tail watcher logs**
```bash
docker compose logs -f alert_watcher
```

**Temporarily suppress all alerts (planned work)**
```bash
# in .env
MAINTENANCE_MODE=true
docker compose up -d alert_watcher
```

**Re‑enable alerts after maintenance**
```bash
MAINTENANCE_MODE=false
docker compose up -d alert_watcher
```

---

## Common Failure Patterns & Hints
- **Frequent 502/504:** App restart loops, DB connectivity issues, or resource starvation.
- **Flip‑flopping pools:** Tight timeouts + intermittent latency spikes. Consider widening upstream timeouts slightly if this is expected under load.
- **No flip but high 5xx:** Both pools unhealthy. Investigate shared dependencies.

---

## Optional Enhancements
- **Recovery alerts:** Emit a “Recovered” message after sustained period below threshold.
- **Per‑pool error breakdown:** Track error rate per upstream to pinpoint the failing side.
- **Export metrics:** Ship logs to Loki/Promtail or emit Prometheus metrics from the watcher.
