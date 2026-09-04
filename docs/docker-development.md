# Docker Development Guide

This guide covers local development with Docker for RepostSleuth.

## Prerequisites

- Docker Engine 24.0+
- Docker Compose V2
- Python 3.11+ (for local development outside containers)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/barrycarey/RedditRepostSleuth.git
cd RedditRepostSleuth
cp .env.example .env

# Start infrastructure only
docker compose -f docker-compose-infra.yml up -d redis

# Run service locally (outside Docker)
python -m redditrepostsleuth.ingestsvc.ingestsvc
```

## Development Workflow

### Option 1: Full Docker Stack

Run everything in containers:

```bash
# Build images
docker compose build

# Start all services
docker compose up -d
```

### Option 2: Hybrid Development

Run infrastructure in Docker, services locally:

```bash
# Start infrastructure
docker compose -f docker-compose-infra.yml up -d redis influxdb

# Install Python dependencies
pip install -r requirements.txt

# Run service locally
python -m redditrepostsleuth.ingestsvc.ingestsvc
```

### Option 3: Single Service Development

Build and run individual service:

```bash
# Build single image
docker build -f docker/Dockerfile.worker -t repostsleuth/worker:dev .

# Run with local code mounted
docker run -it --rm \
  -v $(pwd)/redditrepostsleuth:/app/redditrepostsleuth \
  --env-file .env \
  repostsleuth/worker:dev \
  celery -A redditrepostsleuth.core.celery worker -Q test
```

## Building Images

### Multi-stage Builds

Images use multi-stage builds for smaller size:

```bash
# Build worker image
docker build -f docker/Dockerfile.worker -t repostsleuth/worker:dev .

# Build API image
docker build -f docker/Dockerfile.api -t repostsleuth/api:dev .

# Build monitor image
docker build -f docker/Dockerfile.monitor -t repostsleuth/monitor:dev .
```

### Image Sizes

Expected sizes with multi-stage builds:
- Worker: ~400MB
- API: ~500MB (includes OpenCV)
- Monitor: ~350MB

## Requirements Structure

```
requirements/
  base.txt      # Core dependencies
  worker.txt    # Worker-specific (-r base.txt)
  api.txt       # API-specific (-r base.txt)
  monitor.txt   # Monitor-specific (-r base.txt)
```

Update requirements:
```bash
# Edit requirements/base.txt, then rebuild
docker compose build --no-cache
```

## Testing

### Run Tests in Container

```bash
docker run --rm \
  -v $(pwd):/app \
  -w /app \
  python:3.11-slim \
  bash -c "pip install -r requirements.txt && pytest"
```

### Lint Dockerfiles

```bash
# Install hadolint
brew install hadolint  # macOS
# or
docker run --rm -i hadolint/hadolint < docker/Dockerfile.worker

# Lint all Dockerfiles
hadolint docker/Dockerfile.*
```

## Debugging

### Attach to Running Container

```bash
docker exec -it [container_name] bash
```

### View Logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f image_repost_worker
```

### Debug Celery Worker

```bash
docker compose run --rm image_repost_worker \
  celery -A redditrepostsleuth.core.celery inspect active
```

### Python Debugger

Mount debugpy and attach from IDE:

```yaml
# docker-compose.override.yml
services:
  image_repost_worker:
    volumes:
      - ./redditrepostsleuth:/app/redditrepostsleuth
    ports:
      - "5678:5678"
    entrypoint: |
      python -m debugpy --listen 0.0.0.0:5678 --wait-for-client
      -m celery -A redditrepostsleuth.core.celery worker
```

## Local Registry

For testing CI/CD workflow:

```bash
# Start local registry
docker compose -f docker-compose-infra.yml up -d registry

# Tag and push
docker tag repostsleuth/worker:dev localhost:5000/repostsleuth/worker:dev
docker push localhost:5000/repostsleuth/worker:dev

# Pull from registry
docker pull localhost:5000/repostsleuth/worker:dev
```

## Environment Configuration

### Development .env

```bash
# Minimal .env for development
RUN_ENV=development
LOG_LEVEL=DEBUG
db_host=localhost
db_name=repostsleuth_dev
redis_host=localhost
```

### Docker Compose Override

Create `docker-compose.override.yml` for local modifications:

```yaml
services:
  image_repost_worker:
    volumes:
      - ./redditrepostsleuth:/app/redditrepostsleuth:ro
    environment:
      - LOG_LEVEL=DEBUG
```

## Common Issues

### Import Errors

Ensure `PYTHONPATH` includes app directory:
```bash
docker run -e PYTHONPATH=/app ...
```

### Permission Denied

Check volume ownership:
```bash
docker run --rm -v /opt/repostsleuth-celery:/test alpine ls -la /test
```

### Slow Builds

Use BuildKit for faster builds:
```bash
DOCKER_BUILDKIT=1 docker compose build
```

### Cache Issues

Clear Docker build cache:
```bash
docker builder prune -f
```
