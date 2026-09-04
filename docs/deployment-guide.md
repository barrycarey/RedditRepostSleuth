# RepostSleuth Step-by-Step Deployment Guide

This guide walks you through deploying RepostSleuth from scratch on a fresh server.

> **Related Documentation:**
> - [Docker Deployment Reference](docker-deployment.md) - Detailed reference for Docker configuration
> - [Docker Development Guide](docker-development.md) - Local development setup

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Server Setup](#2-server-setup)
3. [Environment Configuration](#3-environment-configuration)
4. [Deployment Steps](#4-deployment-steps)
5. [CI/CD Setup (Optional)](#5-cicd-setup-optional)
6. [Updating Services](#6-updating-services)
7. [Monitoring & Troubleshooting](#7-monitoring--troubleshooting)

---

## 1. Prerequisites

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| RAM | 8GB | 16GB+ |
| CPU | 4 cores | 8+ cores |
| Disk | 50GB | 200GB+ (for image index) |
| OS | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 LTS |

### Software Requirements

- **Docker Engine 24.0+**
- **Docker Compose V2** (included with Docker Engine)

#### Install Docker (Ubuntu/Debian)

```bash
# Update package index
sudo apt update

# Install prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

#### Add User to Docker Group

```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### External Dependencies

Before deploying, ensure you have:

- **MySQL/MariaDB database** - Can be self-hosted or managed (e.g., AWS RDS)
- **Reddit API credentials** - Create an app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)

---

## 2. Server Setup

### Create Application User (UID 1001)

All containers run as UID 1001 for security. Create a matching user:

```bash
# Create user with UID 1001 (if doesn't exist)
sudo useradd -u 1001 -m -s /bin/bash repostsleuth

# Or verify existing user UID
id repostsleuth
```

### Create Required Directories

```bash
# Application data directories
sudo mkdir -p /opt/repostsleuth-celery
sudo mkdir -p /opt/imageindex
sudo mkdir -p /opt/imageuploads
sudo mkdir -p /opt/letsencrypt/etc/letsencrypt/live/www.repostsleuth.com

# Infrastructure config directories
sudo mkdir -p /config/redis
sudo mkdir -p /config/registry
sudo mkdir -p /config/grafana
sudo mkdir -p /config/loki/data
sudo mkdir -p /config/loki/wal
sudo mkdir -p /config/influxdb/data
sudo mkdir -p /config/telegraf
sudo mkdir -p /config/promtail
sudo mkdir -p /config/swag/log/nginx

# Set ownership to UID 1001
sudo chown -R 1001:1001 /opt/repostsleuth-celery
sudo chown -R 1001:1001 /opt/imageindex
sudo chown -R 1001:1001 /opt/imageuploads
sudo chown -R 1001:1001 /config/redis
sudo chown -R 1001:1001 /config/grafana
sudo chown -R 1001:1001 /config/loki
sudo chown -R 1001:1001 /config/influxdb
sudo chown -R 1001:1001 /config/telegraf
sudo chown -R 1001:1001 /config/promtail
```

### Clone Repository

```bash
cd /opt
sudo git clone https://github.com/barrycarey/RedditRepostSleuth.git
sudo chown -R $USER:$USER RedditRepostSleuth
cd RedditRepostSleuth
```

---

## 3. Environment Configuration

### Copy Environment Template

```bash
cp .env.example .env
chmod 600 .env  # Restrict permissions (contains secrets)
```

### Configure Environment Variables

Edit `.env` with your values:

```bash
nano .env  # or your preferred editor
```

#### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| **Database** | | |
| `db_host` | MySQL host address | `db.example.com` |
| `db_port` | MySQL port | `3306` |
| `db_name` | Database name | `repostsleuth` |
| `db_user` | Database username | `repostsleuth` |
| `db_password` | Database password | `secure_password_here` |
| **Reddit API** | | |
| `reddit_client_id` | Reddit app client ID | `abc123xyz` |
| `reddit_client_secret` | Reddit app client secret | `secret_key_here` |
| `reddit_username` | Bot Reddit username | `RepostSleuthBot` |
| `reddit_password` | Bot Reddit password | `bot_password` |
| `reddit_useragent` | User agent string | `RepostSleuthBot/1.0` |
| **Redis** | | |
| `redis_host` | Redis host (use `redis` for Docker) | `redis` |
| `redis_port` | Redis port | `6379` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend | `redis://redis:6379/0` |
| **Security** | | |
| `API_SECRET_KEY` | API secret (generate random) | `$(openssl rand -hex 32)` |
| `JWT_SECRET_KEY` | JWT signing key (generate random) | `$(openssl rand -hex 32)` |

#### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RUN_ENV` | Environment mode | `production` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `influx_host` | InfluxDB host | `influxdb` |
| `influx_port` | InfluxDB port | `8086` |
| `influx_token` | InfluxDB auth token | (required for metrics) |
| `SENTRY_DSN` | Sentry error tracking | (optional) |
| `GITHUB_RUNNER_TOKEN` | CI/CD runner token | (optional) |

### Generate Secret Keys

```bash
# Generate random keys
echo "API_SECRET_KEY=$(openssl rand -hex 32)"
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
```

### Create Configuration Files

#### Loki Configuration

```bash
cat > /config/loki/loki-config.yaml << 'EOF'
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks
EOF

sudo chown 1001:1001 /config/loki/loki-config.yaml
```

#### Promtail Configuration

```bash
cat > /config/promtail/promtail.yaml << 'EOF'
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /logs/*.log
EOF

sudo chown 1001:1001 /config/promtail/promtail.yaml
```

---

## 4. Deployment Steps

### Step 1: Start Infrastructure Services

Infrastructure includes Redis, Grafana, Loki, InfluxDB, and supporting services.

```bash
cd /opt/RedditRepostSleuth

# Start infrastructure
docker compose -f docker-compose-infra.yml up -d
```

**Verify infrastructure is running:**

```bash
docker compose -f docker-compose-infra.yml ps
```

Expected output - all services should show `healthy` or `running`:

```
NAME        STATUS                   PORTS
grafana     Up (healthy)             0.0.0.0:3000->3000/tcp
influxdb    Up (healthy)             0.0.0.0:8086->8086/tcp
loki        Up (healthy)             0.0.0.0:3100->3100/tcp
promtail    Up
redis       Up (healthy)             0.0.0.0:6379->6379/tcp
registry    Up                       0.0.0.0:5000->5000/tcp
telegraf    Up
```

**Test Redis connectivity:**

```bash
docker exec redis redis-cli ping
# Expected: PONG
```

### Step 2: Build Application Images

```bash
# Build all images (first time will take several minutes)
docker compose build
```

### Step 3: Start Core Worker Services

Worker services handle background tasks like post ingestion, repost detection, and monitoring.

```bash
# Start core workers
docker compose up -d
```

**Verify workers are running:**

```bash
docker compose ps
```

Key services to check:
- `ingest-svc` - Ingests new posts from Reddit
- `beat_scheduler` - Schedules periodic tasks
- `image-repost-worker` - Processes image repost checks
- `link-repost-worker` - Processes link repost checks
- `submonitor-worker` - Monitors subreddits

**Check worker logs:**

```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f image-repost-worker
```

### Step 4: Start Public API

The public API serves the website and external API requests.

```bash
# Start API service
docker compose -f docker-compose-public.yml up -d
```

**Verify API is running:**

```bash
docker compose -f docker-compose-public.yml ps
```

**Test API health endpoint:**

```bash
curl http://localhost:8443/api/health
# Expected: {"status": "healthy"}
```

### Step 5: Verify Complete Deployment

Run a full health check:

```bash
# Check all containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Verify no containers are restarting
docker ps --filter "status=restarting"
```

---

## 5. CI/CD Setup (Optional)

Enable automatic builds and deployments using GitHub Actions with a self-hosted runner.

### Get Runner Token

1. Go to your GitHub repository
2. Navigate to **Settings** > **Actions** > **Runners**
3. Click **New self-hosted runner**
4. Copy the token (valid for 1 hour)

### Configure Runner

Add the token to your `.env`:

```bash
echo "GITHUB_RUNNER_TOKEN=your_token_here" >> .env
```

### Start GitHub Runner

```bash
# Start with CI profile
docker compose -f docker-compose-infra.yml --profile ci up -d github-runner
```

**Verify runner is registered:**

1. Check GitHub: **Settings** > **Actions** > **Runners**
2. Runner `repostsleuth-runner` should appear as "Idle"

### How Automatic Builds Work

When you push to `master` or `dev`:

1. GitHub Actions workflow triggers
2. Self-hosted runner builds new Docker images
3. Images are pushed to local registry (`localhost:5000`)
4. Services can be updated to use new images

See `.github/workflows/docker-build.yml` for workflow details.

---

## 6. Updating Services

### Manual Update Process

```bash
cd /opt/RedditRepostSleuth

# Pull latest code
git pull origin master

# Rebuild images
docker compose build

# Restart services (zero-downtime for workers)
docker compose up -d

# For API updates
docker compose -f docker-compose-public.yml build
docker compose -f docker-compose-public.yml up -d
```

### CI/CD-Based Updates

If using the GitHub runner:

```bash
# After CI builds new images, pull from local registry
docker compose pull

# Restart with new images
docker compose up -d
```

### Rolling Restart (Minimal Downtime)

```bash
# Restart one worker at a time
docker compose up -d --no-deps image-repost-worker
docker compose up -d --no-deps link-repost-worker
# ... repeat for other workers
```

### Rollback

```bash
# Tag current images before update
docker tag localhost:5000/repostsleuth/worker:latest \
           localhost:5000/repostsleuth/worker:backup-$(date +%Y%m%d)

# Rollback if needed
docker tag localhost:5000/repostsleuth/worker:backup-YYYYMMDD \
           localhost:5000/repostsleuth/worker:latest
docker compose up -d
```

---

## 7. Monitoring & Troubleshooting

### Accessing Grafana

1. Open `http://your-server:3000` in browser
2. Default credentials: `admin` / `admin` (change on first login)
3. Add data sources:
   - **InfluxDB**: `http://influxdb:8086`
   - **Loki**: `http://loki:3100`

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f ingest-svc

# Last 100 lines
docker compose logs --tail 100 image-repost-worker

# Since specific time
docker compose logs --since 1h image-repost-worker
```

**Centralized logs in Grafana:**

1. Go to Grafana > Explore
2. Select Loki data source
3. Query: `{job="nginx"}` or `{container_name="ingest-svc"}`

### Health Check Commands

```bash
# Check all container health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# Detailed health info for specific container
docker inspect --format='{{json .State.Health}}' ingest-svc | jq

# Celery worker status
docker exec scheduled_task_worker celery -A redditrepostsleuth.core.celery inspect active

# Redis queue depth
docker exec redis redis-cli llen celery
```

### Common Issues

#### Containers Restarting

```bash
# Check why container is restarting
docker logs --tail 50 [container_name]

# Check resource limits
docker stats --no-stream
```

#### Permission Denied Errors

```bash
# Verify directory ownership
ls -la /opt/repostsleuth-celery
ls -la /config/

# Fix permissions
sudo chown -R 1001:1001 /opt/repostsleuth-celery
sudo chown -R 1001:1001 /config/grafana
```

#### Database Connection Issues

```bash
# Test from container
docker exec ingest-svc python -c "
from redditrepostsleuth.core.db.db_utils import get_db_engine
engine = get_db_engine()
print('Connection successful!' if engine else 'Failed')
"
```

#### Redis Connection Issues

```bash
# Test Redis from worker
docker exec scheduled_task_worker redis-cli -h redis ping

# Check Redis memory
docker exec redis redis-cli info memory
```

#### High Memory Usage

```bash
# Check container memory usage
docker stats --no-stream

# Add memory limits in compose file
# deploy:
#   resources:
#     limits:
#       memory: 2G
```

### Useful Commands Reference

```bash
# Stop all services
docker compose down
docker compose -f docker-compose-infra.yml down
docker compose -f docker-compose-public.yml down

# Restart specific service
docker compose restart image-repost-worker

# View resource usage
docker stats

# Clean up unused images/containers
docker system prune -f

# Force rebuild without cache
docker compose build --no-cache

# Execute command in running container
docker exec -it ingest-svc bash
```

---

## Quick Reference Card

| Action | Command |
|--------|---------|
| Start infrastructure | `docker compose -f docker-compose-infra.yml up -d` |
| Start workers | `docker compose up -d` |
| Start API | `docker compose -f docker-compose-public.yml up -d` |
| Stop all | `docker compose down && docker compose -f docker-compose-infra.yml down` |
| View logs | `docker compose logs -f [service]` |
| Check health | `docker ps` |
| Rebuild | `docker compose build` |
| Update & restart | `git pull && docker compose build && docker compose up -d` |

---

## Next Steps

After deployment:

1. **Configure Grafana dashboards** for monitoring
2. **Set up alerting** for critical metrics
3. **Configure SSL/TLS** for API if exposing publicly
4. **Set up backups** for `/config` and `/opt` directories
5. **Review security** - firewall rules, fail2ban, etc.
