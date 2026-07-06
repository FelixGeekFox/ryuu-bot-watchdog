# Ryuu K Bot Watchdog

Auto-restart and remote control for the Ryuu K Discord bot.

## What It Does

- **Watchdog loop**: checks every 60 seconds if the bot is alive. If it died, restarts it automatically.
- **Webhook server**: small HTTP API on port 8734 for remote control.
- **No more stale locks**: handles lock cleanup automatically.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check (`{"status":"ok"}`) |
| GET | `/status` | Bot status (`{"online":true,"pid":12345,"uptime_seconds":3600}`) |
| POST | `/restart` | Kill and restart the bot |
| POST | `/stop` | Stop the bot (watchdog will restart within 60s) |

All POST endpoints require `Authorization: Bearer <WATCHDOG_TOKEN>` header if a token is set.

## Setup

### 1. Download

```powershell
cd "C:\Users\EliteBook\OneDrive\Ryuu\GPT docs\Ryuu_RAG\discord-rag-bot"
git clone https://github.com/FelixGeekFox/ryuu-bot-watchdog.git watchdog
cd watchdog
```

### 2. Configure

Copy `.env.example` to `.env` and set your token:

```powershell
copy .env.example .env
notepad .env
```

Set `WATCHDOG_TOKEN` to a random string. You can generate one:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Run

Instead of running `python bot.py` directly, run:

```powershell
python watchdog.py
```

Or double-click `install-watchdog.bat` for the auto-restart wrapper.

The watchdog will:
1. Start the bot immediately
2. Start the watchdog loop (checks every 60s)
3. Start the webhook server on port 8734

### 4. For remote access (optional)

To allow remote restart from anywhere, expose port 8734 using one of:

**Cloudflare Tunnel (free, recommended):**
```powershell
# Install cloudflared
winget install --id Cloudflare.cloudflared
# Create a tunnel
cloudflared tunnel --url http://localhost:8734
```

**ngrok (free tier):**
```powershell
# Install ngrok
winget install --id ngrok.ngrok
# Expose the port
ngrok http 8734
```

This gives you a public URL like `https://your-tunnel.example.com` that you can use to restart the bot from anywhere.

## Usage

### Check status
```bash
curl http://localhost:8734/status
```

### Restart the bot
```bash
curl -X POST http://localhost:8734/restart -H "Authorization: Bearer YOUR_TOKEN"
```

### From any remote machine (with tunnel)
```bash
curl -X POST https://your-tunnel.example.com/restart -H "Authorization: Bearer YOUR_TOKEN"
```

## Windows Startup (optional)

To make the watchdog start when Windows boots:

1. Press `Win+R`, type `shell:startup`
2. Create a shortcut to `install-watchdog.bat` in that folder
3. The watchdog will auto-start on boot and keep the bot alive

## Files

- `watchdog.py` - Main watchdog + webhook server
- `.env.example` - Configuration template
- `install-watchdog.bat` - Windows launcher with auto-restart wrapper
