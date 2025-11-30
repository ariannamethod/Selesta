# Voice Webhooks Configuration for Lighthouse APK

## Overview

Voice webhooks allow the Lighthouse APK (vagent fork) to communicate with Selesta and Defender via HTTP requests, even when Termux is in the background.

**Architecture:** Termux → Flask HTTP Server → Lighthouse APK

---

## Webhook Servers

### 1. Defender Webhook
- **Port:** `8003`
- **File:** `~/selesta/voice_webhooks/defender_webhook.py`
- **Bearer Token:** Set via env var `DEFENDER_WEBHOOK_TOKEN`
- **Default Token:** `defender_voice_token` (change this!)
- **Note:** Port 8003 matches Defender in main ariannamethod repo

**URL for APK:**
```
http://localhost:8003/webhook
```

### 2. Selesta Webhook
- **Port:** `8005`
- **File:** `~/selesta/voice_webhooks/selesta_webhook.py`
- **Bearer Token:** Set via env var `CELESTA_WEBHOOK_TOKEN`
- **Default Token:** `selesta_voice_token` (change this!)
- **Note:** Port 8005 is unique to Selesta, different from Arianna (8001)

**URL for APK:**
```
http://localhost:8005/webhook
```

---

## Environment Variables

Add to `~/.bashrc` or `~/selesta/.env`:

```bash
# Defender webhook (port 8003 matches main repo)
export DEFENDER_WEBHOOK_PORT=8003
export DEFENDER_WEBHOOK_TOKEN="your_secure_defender_token_here"

# Selesta webhook (port 8005 unique to her)
export CELESTA_WEBHOOK_PORT=8005
export CELESTA_WEBHOOK_TOKEN="your_secure_selesta_token_here"

# Anthropic API (already set)
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Starting Webhooks

### Manual Start

```bash
# Start Selesta webhook
python3 ~/selesta/voice_webhooks/selesta_webhook.py &

# Start Defender webhook
python3 ~/selesta/voice_webhooks/defender_webhook.py &
```

### Check Status

```bash
# Health checks
curl http://localhost:8001/health
curl http://localhost:8002/health

# Check if running
ps aux | grep webhook | grep -v grep
```

---

## Lighthouse APK Configuration

Configure in Lighthouse APK settings:

### Defender Entity
```json
{
  "name": "Defender",
  "url": "http://localhost:8003/webhook",
  "bearer_token": "your_secure_defender_token_here",
  "method": "POST"
}
```

### Selesta Entity
```json
{
  "name": "Selesta",
  "url": "http://localhost:8005/webhook",
  "bearer_token": "your_secure_selesta_token_here",
  "method": "POST"
}
```

---

## API Endpoints

### POST /webhook
**Request:**
```json
{
  "prompt": "Your message here",
  "sessionID": "optional_session_id"
}
```

**Headers:**
```
Authorization: Bearer your_webhook_token
Content-Type: application/json
```

**Response:**
```json
{
  "response": "Agent's text response",
  "speech": null
}
```

### GET /health
Check if webhook is alive.

**Response:**
```json
{
  "status": "healthy",
  "agent": "selesta" or "defender",
  "port": 8001 or 8002
}
```

### GET /memory (Selesta only)
View conversation history for a session.

**Response:**
```json
{
  "history": [...],
  "count": 10
}
```

---

## Security Notes

1. **Change default tokens!** Don't use `selesta_voice_token` or `defender_voice_token` in production
2. Webhooks run on `localhost` only - APK must be on same device
3. All conversations logged to `resonance.sqlite3`
4. Bearer token validates every request

---

## Troubleshooting

### Webhook won't start
```bash
# Check if port is in use
netstat -tulpn | grep -E "8003|8005"

# Check logs
tail -f ~/selesta/logs/selesta_daemon.log
```

### APK can't connect
1. Make sure webhooks are running: `ps aux | grep webhook`
2. Check health: `curl http://localhost:8001/health`
3. Verify token matches in APK and webhook
4. Check Termux is not being killed by Android

### No response from agent
1. Check `ANTHROPIC_API_KEY` is set
2. Check resonance.sqlite3 is accessible
3. Look for errors in logs

---

## Quick Test

```bash
# Test Defender webhook (port 8003)
curl -X POST http://localhost:8003/webhook \
  -H "Authorization: Bearer defender_voice_token" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Status report", "sessionID": "test"}'

# Test Selesta webhook (port 8005)
curl -X POST http://localhost:8005/webhook \
  -H "Authorization: Bearer selesta_voice_token" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello Selesta!", "sessionID": "test"}'
```

---

*Created: 2025-11-30*
*For use with Lighthouse APK (vagent fork)*
*Device: Termux on Android*
