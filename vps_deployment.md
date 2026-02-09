# VPS Deployment Plan - Media Compressor

## Overview

Deploy the Media Compressor app to a Linux VPS with CI/CD pipeline and test coverage.

**Target Stack:**
- Server: Linux VPS (Ubuntu 22.04+)
- Runtime: Python 3.11+ with uvicorn
- Reverse Proxy: Nginx (SSL termination, static files)
- Process Manager: systemd
- CI/CD: GitHub Actions
- Container: Docker (optional)

---

## Phase 1: Test Coverage

### 1.1 Unit Tests

Create `tests/` directory with pytest:

```
tests/
├── __init__.py
├── conftest.py              # Fixtures (test files, temp dirs)
├── test_compressor.py       # Image/video compression logic
├── test_job_manager.py      # Job CRUD operations
├── test_api.py              # FastAPI endpoint tests
└── test_data/
    ├── sample.jpg
    ├── sample.png
    └── sample.mp4
```

**Key Test Cases:**

| Module | Tests |
|--------|-------|
| `ffmpeg_compressor.py` | HEIC→JPG, PNG→JPG, video compression, preset configs, resize logic |
| `job_manager.py` | Create/update/delete jobs, status transitions, cleanup |
| `main.py` | Upload endpoint, download endpoint, job status, health check |

### 1.2 Test Dependencies

Add to `requirements-dev.txt`:
```
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.1
httpx>=0.27          # For FastAPI TestClient async
```

### 1.3 Coverage Target

- Minimum: 80% line coverage
- Critical paths: 100% (compression, job state machine)

---

## Phase 2: Project Structure Updates

### 2.1 Configuration Management

Create `app/config.py` environment-aware config:

```python
# Support: development, staging, production
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Production settings
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))
```

### 2.2 File Structure

```
image_video_zip/
├── app/
│   ├── main.py
│   ├── config.py
│   └── services/
├── tests/
├── scripts/
│   ├── setup.sh           # VPS initial setup
│   └── deploy.sh          # Deployment script
├── .github/
│   └── workflows/
│       ├── test.yml       # Run tests on PR
│       └── deploy.yml     # Deploy on main push
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

---

## Phase 3: Docker Setup

### 3.1 Dockerfile

```dockerfile
FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.2 docker-compose.yml

```yaml
version: "3.8"
services:
  app:
    build: .
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost when running multiple apps
    volumes:
      - ./uploads:/app/uploads
      - ./downloads:/app/downloads
    environment:
      - ENVIRONMENT=production
      - MAX_UPLOAD_SIZE_MB=500
    container_name: imagezip
    restart: unless-stopped
```

---

## Phase 4: CI/CD Pipeline (GitHub Actions)

### 4.1 Test Workflow (`.github/workflows/test.yml`)

```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install FFmpeg
        run: sudo apt-get update && sudo apt-get install -y ffmpeg
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run tests with coverage
        run: pytest --cov=app --cov-report=xml --cov-fail-under=80
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
```

### 4.2 Deploy Workflow (`.github/workflows/deploy.yml`)

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/imagezip
            git pull origin main
             docker compose down
             docker compose build --no-cache
             docker compose up -d
            docker system prune -f
```

---

## Phase 5: VPS Setup

### 5.1 Initial Server Setup

```bash
# Run as root on fresh Ubuntu 22.04 VPS

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker

# Install Docker Compose
apt install docker-compose-plugin -y

# Create app user
useradd -m -s /bin/bash appuser
usermod -aG docker appuser

# Create app directory
mkdir -p /opt/imagezip
chown appuser:appuser /opt/imagezip

# Setup firewall
ufw allow 22
ufw allow 80
ufw allow 443
ufw enable
```

### 5.2 Nginx Configuration (Single App)

```nginx
# /etc/nginx/sites-available/imagezip

server {
    listen 80;
    server_name imagezip.tmusml.cloud;
    
    client_max_body_size 500M;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

### 5.3 SSL with Certbot

```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d imagezip.tmusml.cloud
```

---

## Phase 6: GitHub Secrets Setup

Add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | VPS IP address or hostname |
| `VPS_USER` | SSH username (e.g., `appuser`) |
| `VPS_SSH_KEY` | Private SSH key for deployment |

---

## Phase 7: Monitoring & Maintenance

### 7.1 Health Check Endpoint

Already implemented: `GET /health`

### 7.2 Log Rotation

```bash
# /etc/logrotate.d/imagezip
/opt/imagezip/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

### 7.3 Disk Cleanup Cron

```bash
# Cleanup old files daily (add to crontab)
0 3 * * * docker exec imagezip python -c "from app.services.job_manager import job_manager; job_manager.cleanup_old_jobs(24)"
```

---

## Implementation Order

| Step | Task | Effort |
|------|------|--------|
| 1 | Write unit tests (`tests/`) | 2-3 hours |
| 2 | Add `requirements-dev.txt` | 10 min |
| 3 | Create `Dockerfile` | 30 min |
| 4 | Create `docker-compose.yml` | 15 min |
| 5 | Test Docker build locally | 30 min |
| 6 | Create GitHub Actions workflows | 1 hour |
| 7 | Setup VPS (Docker, Nginx, SSL) | 1-2 hours |
| 8 | Configure GitHub secrets | 15 min |
| 9 | First deployment | 30 min |
| 10 | Verify & monitor | 30 min |

**Total estimated time: 6-8 hours**

---

## Quick Start Commands

```bash
# Local development
python run.py

# Run tests
pytest -v --cov=app

# Build Docker image
docker build -t imagezip .

# Run with Docker Compose
docker compose up -d

# View logs
docker compose logs -f

# Deploy (manual)
ssh user@vps "cd /opt/imagezip && git pull && docker compose up -d --build"
```

---

## Phase 8: Multi-App VPS Setup

Run multiple applications (Python, Java, Node.js) on a single VPS using Docker. This guide assumes **Hostinger KVM 2** (8GB RAM, 2 vCPU) or similar.

### 8.1 VPS Resource Allocation

| Application | Memory Limit | Port | Typical Usage |
|-------------|--------------|------|---------------|
| Media Compressor (Python) | 512MB | 8000 | ~200MB idle, spikes during compression |
| Java App (Spring Boot) | 1GB | 8080 | ~512MB-1GB with JVM heap |
| Node.js App | 256MB | 3000 | ~100-150MB typical |
| Nginx | - | 80/443 | ~50MB |
| System/Docker | - | - | ~1GB reserved |
| **Total** | ~2.8GB | | Leaves ~5GB free for bursts |

### 8.2 Directory Structure

```
/opt/
├── imagezip/                # This Python app (imagezip.tmusml.cloud)
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── ...
├── java-app/                # Your Java/Spring Boot app
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── ...
└── nodejs-app/              # Your Node.js app
    ├── docker-compose.yml
    ├── Dockerfile
    └── ...
```

### 8.3 Shared Docker Network

Create a shared network for all apps to communicate (optional, for inter-service calls):

```bash
docker network create apps-network
```

Update each `docker-compose.yml` to use external network:

```yaml
networks:
  default:
    external:
      name: apps-network
```

### 8.4 Java App Docker Setup

**Example Dockerfile for Spring Boot:**

```dockerfile
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Copy the built JAR (build with: ./gradlew bootJar or mvn package)
COPY target/*.jar app.jar

# JVM memory settings - crucial for containers
ENV JAVA_OPTS="-Xms256m -Xmx768m -XX:+UseContainerSupport"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

**docker-compose.yml for Java App:**

```yaml
version: "3.8"
services:
  java-app:
    build: .
    container_name: java-app
    ports:
      - "8080:8080"
    mem_limit: 1g
    mem_reservation: 512m
    environment:
      - SPRING_PROFILES_ACTIVE=production
      - JAVA_OPTS=-Xms256m -Xmx768m
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

**Key Java/JVM Notes:**
- Always set `-XX:+UseContainerSupport` (default in Java 11+) for container-aware memory
- Set explicit heap limits (`-Xmx`) to ~75% of `mem_limit`
- Use Alpine-based images for smaller footprint (~200MB vs ~400MB)
- Spring Boot Actuator provides `/actuator/health` for health checks

### 8.5 Node.js App Docker Setup

**Example Dockerfile for Node.js:**

```dockerfile
FROM node:20-alpine

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm ci --only=production

# Copy application code
COPY . .

# Run as non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001
USER nodejs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:3000/health || exit 1

CMD ["node", "server.js"]
```

**docker-compose.yml for Node.js App:**

```yaml
version: "3.8"
services:
  nodejs-app:
    build: .
    container_name: nodejs-app
    ports:
      - "3000:3000"
    mem_limit: 256m
    mem_reservation: 128m
    environment:
      - NODE_ENV=production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

**Key Node.js Notes:**
- Use `npm ci` instead of `npm install` for reproducible builds
- Alpine images are ~50MB vs ~300MB for full Node images
- Set `NODE_ENV=production` for performance optimizations
- Add a `/health` endpoint in your app for health checks

### 8.6 Shared Nginx Configuration

Single Nginx instance reverse-proxying to all apps with different subdomains:

```nginx
# /etc/nginx/sites-available/apps

# Media Compressor - imagezip.tmusml.cloud
server {
    listen 80;
    server_name imagezip.tmusml.cloud;
    
    client_max_body_size 500M;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}

# Java App - api.yourdomain.com
server {
    listen 80;
    server_name api.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Node.js App - app.yourdomain.com
server {
    listen 80;
    server_name app.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Enable and get SSL for all:**

```bash
# Enable the config
sudo ln -s /etc/nginx/sites-available/apps /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Get SSL certificates for all subdomains
sudo certbot --nginx -d imagezip.tmusml.cloud -d api.yourdomain.com -d app.yourdomain.com
```

### 8.7 Deployment Scripts

**Deploy all apps (`/opt/deploy-all.sh`):**

```bash
#!/bin/bash
set -e

echo "=== Deploying all applications ==="

# ImageZip (Media Compressor)
echo "→ Deploying ImageZip..."
cd /opt/imagezip
git pull origin main
docker compose up -d --build

# Java App
echo "→ Deploying Java App..."
cd /opt/java-app
git pull origin main
docker compose up -d --build

# Node.js App
echo "→ Deploying Node.js App..."
cd /opt/nodejs-app
git pull origin main
docker compose up -d --build

# Cleanup
echo "→ Cleaning up..."
docker system prune -f

echo "=== All deployments complete ==="
docker ps
```

**Check all apps status (`/opt/status.sh`):**

```bash
#!/bin/bash
echo "=== Container Status ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== Memory Usage ==="
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo ""
echo "=== Disk Usage ==="
df -h /
```

### 8.8 GitHub Actions for Multi-App

Each app should have its own GitHub Actions workflow. Example for Java app:

```yaml
# .github/workflows/deploy.yml (in java-app repo)
name: Deploy Java App

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: 'temurin'
      
      - name: Build with Gradle
        run: ./gradlew bootJar
      
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/java-app
            git pull origin main
            docker compose down
            docker compose build --no-cache
            docker compose up -d
```

### 8.9 Monitoring Commands

```bash
# View all container logs
docker compose logs -f                    # In each app directory

# View specific container logs
docker logs -f imagezip
docker logs -f java-app
docker logs -f nodejs-app

# Resource usage (real-time)
docker stats

# Check container health
docker inspect --format='{{.State.Health.Status}}' imagezip

# Restart a specific app
cd /opt/java-app && docker compose restart

# View Nginx access logs
tail -f /var/log/nginx/access.log
```

### 8.10 Troubleshooting

| Issue | Solution |
|-------|----------|
| Java app OOM killed | Increase `mem_limit` or reduce `-Xmx` heap size |
| Container won't start | Check logs: `docker logs <container>` |
| Port already in use | Check: `sudo lsof -i :<port>` |
| Nginx 502 Bad Gateway | Container not running or wrong port in nginx config |
| Slow Java startup | Increase `start_period` in healthcheck (JVM warmup) |
| Node.js memory issues | Set `--max-old-space-size=200` in Node options |
