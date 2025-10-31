import os
import time
import json
import requests
from collections import deque, defaultdict

# =========================
# Environment configuration
# =========================
LOG_FILE = os.getenv("NGINX_LOG_FILE", "/logs/access_stage3.log")

# Slack + presentation
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()
SLACK_USERNAME    = os.getenv("SLACK_USERNAME", "").strip()
SLACK_ICON_EMOJI  = os.getenv("SLACK_ICON_EMOJI", "").strip()  # ignored if empty
SLACK_MODE        = os.getenv("SLACK_MODE", "attachments").lower()  # blocks | attachments
SLACK_FORCE_SECTIONS = os.getenv("SLACK_FORCE_SECTIONS", "true").lower() == "true"

# Attachment colors (sidebars). Can be hex (e.g., #FF0000) or the keys "red|yellow|green"
COLOR_RED    = os.getenv("COLOR_RED", "#E01E5A")
COLOR_YELLOW = os.getenv("COLOR_YELLOW", "#E3B341")
COLOR_GREEN  = os.getenv("COLOR_GREEN", "#2EB67D")

# JSON snippet in Slack
LOG_SNIPPET     = os.getenv("LOG_SNIPPET", "true").lower() == "true"
LOG_SNIPPET_MAX = int(os.getenv("LOG_SNIPPET_MAX", "600"))

# Console echo (stdout) of the same alert for docker logs
ALERT_STDOUT    = os.getenv("ALERT_STDOUT", "true").lower() == "true"

# Detection thresholds
ERROR_RATE_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", "2"))
WINDOW_SIZE          = int(os.getenv("WINDOW_SIZE", "200"))
ALERT_COOLDOWN_SEC   = int(os.getenv("ALERT_COOLDOWN_SEC", "300"))
MAINTENANCE_MODE     = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"

# =====
# State
# =====
window = deque(maxlen=WINDOW_SIZE)
last_pool = None
last_alert_ts = defaultdict(lambda: 0)

# =========
# Utilities
# =========
def is_5xx(up_status_field: str) -> bool:
    """True if any upstream status in a comma list is 5xx."""
    if not up_status_field:
        return False
    for token in str(up_status_field).split(","):
        token = token.strip()
        if token.isdigit() and 500 <= int(token) <= 599:
            return True
    return False

def error_rate() -> float:
    return 0.0 if not window else 100.0 * (sum(1 for x in window if x) / len(window))

def cooldown(key: str) -> bool:
    now = time.time()
    if now - last_alert_ts[key] < ALERT_COOLDOWN_SEC:
        return True
    last_alert_ts[key] = now
    return False

def make_log_snippet(rec):
    """Return prettified + truncated JSON fenced in ```json for Slack and console."""
    if not LOG_SNIPPET or not rec:
        return None
    keys = [
        "time_local","remote_addr","request","status",
        "upstream_status","upstream_addr","pool","release",
        "request_time","upstream_response_time",
    ]
    slim = {k: rec.get(k) for k in keys if k in rec}
    s = json.dumps(slim, indent=2)
    if len(s) > LOG_SNIPPET_MAX:
        s = s[: LOG_SNIPPET_MAX - 3] + "..."
    return f"```json\n{s}\n```"

# ===============
# Console printing
# ===============
def print_console(lines, snippet=None):
    """Print a clean, line-by-line block to stdout (what you see in docker logs)."""
    if not ALERT_STDOUT:
        return
    print("\n[watcher] ----------------------------------------", flush=True)
    for ln in lines:
        print(f"[watcher] {ln}", flush=True)
    if snippet:
        for ln in snippet.splitlines():
            print(f"[watcher] {ln}", flush=True)
    print("[watcher] ----------------------------------------\n", flush=True)

# ==================
# Slack post (blocks or attachments)
# ==================
def _color_value(name_or_hex: str) -> str:
    name = name_or_hex.lower()
    if name == "red":
        return COLOR_RED
    if name == "yellow":
        return COLOR_YELLOW
    if name == "green":
        return COLOR_GREEN
    return name_or_hex  # assume hex or Slack-valid color

def post_slack(lines, snippet=None, color="yellow"):
    """Send alert to Slack. Default uses legacy attachments (widely supported, with colored sidebar).
       Always echoes the alert to stdout.
    """
    # Always echo to console
    print_console(lines, snippet)

    # Dry-run (no webhook) — just return after printing
    if not SLACK_WEBHOOK_URL:
        return

    payload = {}
    mode = SLACK_MODE

    if mode == "blocks":
        # BLOCK KIT (only if your webhook supports it)
        blocks = []
        if SLACK_FORCE_SECTIONS:
            for ln in lines:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": ln}})
        else:
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]
        if snippet:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": " "}})
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": snippet}})
        payload = {"text": lines[0] if lines else "alert", "blocks": blocks}
    else:
        # ATTACHMENTS (default, works on all incoming webhooks)
        fields = [{"title": "", "value": ln, "short": False} for ln in lines]
        attachments = [{
            "color": _color_value(color),
            "mrkdwn_in": ["text", "fields"],
            "fields": fields
        }]
        if snippet:
            attachments.append({"color": "#CCCCCC", "mrkdwn_in": ["text"], "text": " "})  # spacer line
            attachments.append({"color": _color_value(color), "mrkdwn_in": ["text"], "text": snippet})
        payload = {"text": lines[0] if lines else "alert", "attachments": attachments}

    if SLACK_USERNAME:
        payload["username"] = SLACK_USERNAME
    if SLACK_ICON_EMOJI:
        payload["icon_emoji"] = SLACK_ICON_EMOJI  # ignored by Slack if empty

    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        ok = r.status_code < 300
        print(f"[watcher] posted_to_slack ok={ok} status={r.status_code}", flush=True)
        if not ok:
            print(f"[watcher] slack_error: {r.text}", flush=True)
    except Exception as e:
        print(f"[watcher] slack_exception: {e}", flush=True)

# =====================
# Line builders (no emojis, one line per field)
# =====================
def failover_lines(prev_pool, new_pool, rec):
    up      = rec.get("upstream_addr", "-")
    upst    = rec.get("upstream_status", "-")
    release = rec.get("release", "-")
    req     = rec.get("request", "-")
    return [
        f"Failover Detected — {prev_pool} → {new_pool}",
        f"Upstream: {up}",
        f"Status: {upst}",
        f"Release: {release}",
        f"Request: {req}",
    ]

def error_rate_lines(rate, window_len):
    return [
        "High Upstream Error Rate",
        f"{rate:.2f}% 5xx over last {window_len} requests",
        f"(threshold {ERROR_RATE_THRESHOLD:.2f}%, window {WINDOW_SIZE})",
    ]

# ============
# Alert senders (colors: red=failover, yellow=high error rate; use green for recovery if added)
# ============
def alert_failover(prev_pool: str, new_pool: str, sample):
    if MAINTENANCE_MODE or cooldown(f"failover:{prev_pool}->{new_pool}"):
        return
    lines   = failover_lines(prev_pool, new_pool, sample)
    snippet = make_log_snippet(sample)
    post_slack(lines, snippet, color="red")

def alert_error_rate(rate: float, n: int, sample=None):
    if MAINTENANCE_MODE or cooldown("error_rate"):
        return
    lines   = error_rate_lines(rate, n)
    snippet = make_log_snippet(sample)
    post_slack(lines, snippet, color="yellow")

# ===========
# Log follower
# ===========
def follow(path: str):
    while not os.path.exists(path):
        print(f"[watcher] waiting for log file {path}", flush=True)
        time.sleep(0.5)
    with open(path, "r") as f:
        f.seek(0, 2)  # tail -f
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.25)
                continue
            yield line

# =====
# Main
# =====
def main():
    global last_pool
    last_rec = None
    print(
        f"[watcher] LOG_FILE={LOG_FILE} WINDOW={WINDOW_SIZE} "
        f"THRESH={ERROR_RATE_THRESHOLD}% COOLDOWN={ALERT_COOLDOWN_SEC}s "
        f"MAINT={MAINTENANCE_MODE} MODE={SLACK_MODE} "
        f"SNIPPET={LOG_SNIPPET} STDOUT={ALERT_STDOUT}",
        flush=True,
    )
    for line in follow(LOG_FILE):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue

        last_rec = rec

        pool = rec.get("pool") or None
        up_status = rec.get("upstream_status", "")

        # update rolling window
        window.append(is_5xx(up_status))

        # failover detection (pool flip)
        if pool and last_pool and pool != last_pool:
            alert_failover(last_pool, pool, rec)
        if pool:
            last_pool = pool

        # error rate detection
        rate = error_rate()
        if len(window) >= max(25, int(WINDOW_SIZE * 0.25)) and rate >= ERROR_RATE_THRESHOLD:
            alert_error_rate(rate, len(window), sample=last_rec)

if __name__ == "__main__":
    main()
