# Docker Deployment Guide

This guide covers production deployment of RepostSleuth using Docker.

## Prerequisites

- Docker Engine 24.0+
- Docker Compose V2
- 16GB+ RAM recommended
- User with UID 1001 for container processes

## Quick Start

```bash
# Clone repository
git clone https://github.com/barrycarey/RedditRepostSleuth.git
cd RedditRepostSleuth

# Copy and configure environment
cp .env.example .env
# Edit .env with your configuration

# Start infrastructure services
docker compose -f docker-compose-infra.yml up -d

# Start worker services
docker compose up -d

# Start public API
docker compose -f docker-compose-public.yml up -d
```

## Architecture

### Service Types

| Type | Dockerfile | Description |
|------|------------|-------------|
| Worker | `docker/Dockerfile.worker` | Celery workers for async tasks |
| API | `docker/Dockerfile.api` | Public REST API |
| Monitor | `docker/Dockerfile.monitor` | Long-running monitoring services |

### Compose Files

- `docker-compose.yml` - Core worker services
- `docker-compose-infra.yml` - Infrastructure (Redis, Grafana, Loki, etc.)
- `docker-compose-public.yml` - Public API service

## Configuration

### Environment Variables

All services read configuration from `.env`. See `.env.example` for available options.

Key variables:
- `db_host` - MySQL host
- `db_user` - MySQL user
- `db_password` - MySQL password
- `reddit_client_id` - Reddit API client ID
- `reddit_client_secret` - Reddit API client secret

### Volume Permissions

Containers run as user 1001. Ensure volumes have proper ownership:

```bash
sudo chown -R 1001:1001 /opt/repostsleuth-celery
sudo chown -R 1001:1001 /opt/imageindex
sudo chown -R 1001:1001 /config/grafana
sudo chown -R 1001:1001 /config/loki
```

## Health Checks

All services include health checks. View status:

```bash
docker compose ps
```

Health check types:
- **Workers**: Celery ping command
- **API**: HTTP health endpoint
- **Monitors**: Process check (pgrep)
- **Infrastructure**: Service-specific health endpoints

## Logging

Logs use JSON driver with rotation:
- Max size: 10MB per file
- Max files: 3

View logs:
```bash
docker compose logs -f [service_name]
```

Logs are also sent to Loki for centralized viewing in Grafana.

## Networks

| Network | Services |
|---------|----------|
| `backend` | All worker services |
| `api` | Public API and its Redis |
| `monitoring` | Infrastructure services |

## Local Registry (CI/CD)

A local Docker registry is included for CI/CD:

```bash
# Start registry
docker compose -f docker-compose-infra.yml up -d registry

# Configure Docker to trust local registry
# Add to /etc/docker/daemon.json:
{
  "insecure-registries": ["localhost:5000"]
}

# Restart Docker
sudo systemctl restart docker
```

## GitHub Actions Runner

To enable CI/CD with local builds:

1. Get runner token from GitHub:
   - Repository Settings > Actions > Runners > New self-hosted runner
   - Copy the token

2. Add to `.env`:
   ```
   GITHUB_RUNNER_TOKEN=your_token_here
   ```

3. Start runner:
   ```bash
   docker compose -f docker-compose-infra.yml --profile ci up -d
   ```

## Scaling

Scale workers based on queue depth:

```bash
# Scale image repost workers
docker compose up -d --scale image_repost_worker=3

# Or adjust autoscale in compose file
entrypoint: celery ... --autoscale=20,5
```

## Monitoring

### Grafana

Access at `http://localhost:3000`

Default dashboards:
- Celery task metrics
- Redis queue depth
- System resources

### InfluxDB

Metrics stored in InfluxDB. Access at `http://localhost:8086`

## Troubleshooting

### Container won't start

Check logs:
```bash
docker compose logs [service_name]
```

### Health check failing

Check service health:
```bash
docker inspect --format='{{json .State.Health}}' [container_name]
```

### Permission denied

Ensure volumes owned by UID 1001:
```bash
ls -la /opt/repostsleuth-celery
sudo chown -R 1001:1001 /opt/repostsleuth-celery
```

### Memory issues

Workers may need memory limits:
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

## Rollback

Tag current images before upgrades:

```bash
docker tag localhost:5000/repostsleuth/worker:latest \
           localhost:5000/repostsleuth/worker:backup-$(date +%Y%m%d)
```

Rollback:
```bash
docker tag localhost:5000/repostsleuth/worker:backup-YYYYMMDD \
           localhost:5000/repostsleuth/worker:latest
docker compose up -d
```
