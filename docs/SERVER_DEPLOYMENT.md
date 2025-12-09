# Server Deployment Guide

This guide covers deploying the YouTube Summarizer backend on Alibaba Cloud Linux 3.

## Prerequisites

- Alibaba Cloud Linux 3.2104 LTS 64-bit
- Root or sudo access
- Internet connection

## 1. Deploy Clash Proxy Service

The backend requires a proxy to access YouTube. We use Clash as the local proxy.

### Quick Deploy

```bash
# Upload the deployment script to server
scp deploy_clash_proxy.sh root@YOUR_SERVER_IP:/root/

# SSH to server and run
ssh root@YOUR_SERVER_IP
chmod +x /root/deploy_clash_proxy.sh
sudo /root/deploy_clash_proxy.sh
```

### What the Script Does

1. Installs Clash Premium/Meta
2. Downloads SakuraCat subscription config
3. Sets up systemd service (auto-start on boot)
4. Configures daily subscription updates
5. Tests proxy connectivity

### Verify Proxy

```bash
# Check service status
systemctl status clash

# Test proxy connection
curl -x http://127.0.0.1:7890 https://www.google.com

# View logs
journalctl -u clash -f
```

### Proxy Management Commands

| Command | Description |
|---------|-------------|
| `systemctl start clash` | Start proxy |
| `systemctl stop clash` | Stop proxy |
| `systemctl restart clash` | Restart proxy |
| `/opt/clash/update_subscription.sh` | Update subscription |

## 2. Configure Environment Variables

Create or edit `.env` file in the backend directory:

```bash
cd /path/to/My_Youtube_Summarizer/backend
nano .env
```

Add the following configuration:

```env
# YouTube Proxy (Required for YouTube access)
YOUTUBE_PROXY=http://127.0.0.1:7890

# Alibaba Cloud OSS
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_BUCKET=your_bucket_name

# Qwen API
QWEN_API_KEY=your_qwen_api_key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key

# Temporary directory
TEMP_DIR=/tmp/video_analysis
```

## 3. Install Python Dependencies

```bash
# Create virtual environment
cd /path/to/My_Youtube_Summarizer/backend
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install yt-dlp (latest version)
pip install -U yt-dlp

# Install ffmpeg (required for video processing)
yum install -y ffmpeg || dnf install -y ffmpeg
```

## 4. Start Backend Service

### Development Mode

```bash
cd /path/to/My_Youtube_Summarizer/backend
source venv/bin/activate
export YOUTUBE_PROXY=http://127.0.0.1:7890
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Production Mode (systemd)

Create systemd service file:

```bash
sudo nano /etc/systemd/system/youtube-summarizer.service
```

```ini
[Unit]
Description=YouTube Summarizer Backend
After=network.target clash.service

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/My_Youtube_Summarizer/backend
Environment=YOUTUBE_PROXY=http://127.0.0.1:7890
ExecStart=/path/to/My_Youtube_Summarizer/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable youtube-summarizer
sudo systemctl start youtube-summarizer
```

## 5. Verify Deployment

### Check Services Status

```bash
# Clash proxy
systemctl status clash

# Backend service
systemctl status youtube-summarizer

# Test API
curl http://localhost:8000/docs
```

### Test YouTube Download

```bash
# Manual test with yt-dlp
yt-dlp --proxy http://127.0.0.1:7890 \
  --force-ipv4 \
  --extractor-args "youtube:player_client=android" \
  -f "best[height<=360]" \
  "https://www.youtube.com/watch?v=TOmDbuXg5Qs"
```

## Troubleshooting

### Clash Proxy Issues

```bash
# Check if Clash is running
ps aux | grep clash

# Check port
netstat -tlnp | grep 7890

# View detailed logs
journalctl -u clash -n 50
```

### YouTube Download Fails

1. Check proxy is working:
   ```bash
   curl -x http://127.0.0.1:7890 https://www.youtube.com
   ```

2. Update yt-dlp:
   ```bash
   pip install -U yt-dlp
   ```

3. Check environment variable:
   ```bash
   echo $YOUTUBE_PROXY
   ```

### Backend Service Issues

```bash
# Check logs
journalctl -u youtube-summarizer -f

# Check port
netstat -tlnp | grep 8000
```

## Security Notes

1. **Firewall**: Only expose port 8000 (backend) to trusted networks
2. **Clash**: Keep `allow-lan: false` in config to prevent external access
3. **API Keys**: Never commit `.env` file to version control
4. **Updates**: Regularly update yt-dlp and dependencies

## Architecture Overview

```
                    ┌─────────────────────────┐
                    │    Alibaba Cloud ECS    │
                    │                         │
┌─────────┐        │  ┌─────────────────┐    │
│  User   │───────►│  │  Backend :8000  │    │
└─────────┘        │  └────────┬────────┘    │
                    │           │             │
                    │           ▼             │
                    │  ┌─────────────────┐    │
                    │  │  Clash :7890    │    │
                    │  └────────┬────────┘    │
                    │           │             │
                    └───────────┼─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │  Proxy Nodes (SakuraCat)│
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │       YouTube           │
                    └─────────────────────────┘
```
