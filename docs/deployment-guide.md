# MCP for Retriever - Deployment Guide

## Prerequisites

### System Requirements
- Python 3.12 or higher
- Docker and Docker Compose (for containerized deployment)
- PostgreSQL 15+
- Qdrant 1.7+
- Redis 7+ (for caching and rate limiting)
- Minimum 4GB RAM, 2 CPU cores

### Required Services
1. **PostgreSQL** - User data and permissions
2. **Qdrant** - Vector database
3. **Redis** - Caching and rate limiting
4. **Tavily API** - Web search service (API key required)

## Local Development Setup

### 1. Clone Repository
```bash
git clone https://github.com/your-org/make-mcp-server-vibe.git
cd make-mcp-server-vibe
```

### 2. Install Dependencies
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize Python environment
uv init --python 3.12

# Install dependencies
uv sync
```

### 3. Environment Configuration

Create `.env` file in project root:
```bash
# Authentication
JWT_SECRET_KEY=your-secret-key-here-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Database
POSTGRES_DSN=postgresql://user:password@localhost:5432/mcp_retriever
POSTGRES_POOL_SIZE=10
POSTGRES_MAX_OVERFLOW=20

# Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=optional-api-key

# Redis
REDIS_URL=redis://localhost:6379/0

# Tavily API
TAVILY_API_KEY=tvly-your-api-key-here

# Server Configuration
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8001

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Rate Limiting
RATE_LIMIT_PER_MINUTE=100
```

### 4. Database Setup

#### PostgreSQL
```sql
-- Create database
CREATE DATABASE mcp_retriever;

-- Connect to database
\c mcp_retriever;

-- Run migrations
-- (Execute from project root)
```

```bash
# Run database migrations
uv run alembic upgrade head
```

#### Qdrant
```bash
# Using Docker
docker run -p 6333:6333 qdrant/qdrant
```

#### Redis
```bash
# Using Docker
docker run -p 6379:6379 redis:7-alpine
```

### 5. Start Services

```bash
# Terminal 1: Start Gateway
uv run python -m src.auth.server

# Terminal 2: Start MCP Server
uv run python -m src.server

# Or use the combined startup script
uv run python scripts/start_dev.py
```

## Docker Deployment

### 1. Build Images

Create `Dockerfile.gateway`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY src/ ./src/

# Expose port
EXPOSE 8000

# Run gateway
CMD ["uv", "run", "python", "-m", "src.auth.server"]
```

Create `Dockerfile.mcp`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY src/ ./src/

# Expose port
EXPOSE 8001

# Run MCP server
CMD ["uv", "run", "python", "-m", "src.server"]
```

### 2. Docker Compose Configuration

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: mcp_retriever
      POSTGRES_USER: mcp_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mcp_user -d mcp_retriever"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  gateway:
    build:
      context: .
      dockerfile: Dockerfile.gateway
    ports:
      - "8000:8000"
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - POSTGRES_DSN=postgresql://mcp_user:${POSTGRES_PASSWORD}@postgres:5432/mcp_retriever
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    ports:
      - "8001:8001"
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - POSTGRES_DSN=postgresql://mcp_user:${POSTGRES_PASSWORD}@postgres:5432/mcp_retriever
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - QDRANT_API_KEY=${QDRANT_API_KEY}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - qdrant
      - redis
      - gateway
    restart: unless-stopped

volumes:
  postgres_data:
  qdrant_data:
  redis_data:
```

### 3. Deploy with Docker Compose

```bash
# Create .env file with production values
cp .env.example .env
# Edit .env with production values

# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Kubernetes Deployment

### 1. ConfigMap for Configuration

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-retriever-config
data:
  GATEWAY_HOST: "0.0.0.0"
  GATEWAY_PORT: "8000"
  MCP_SERVER_HOST: "0.0.0.0"
  MCP_SERVER_PORT: "8001"
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
```

### 2. Secret for Sensitive Data

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mcp-retriever-secrets
type: Opaque
stringData:
  JWT_SECRET_KEY: "your-secret-key"
  POSTGRES_PASSWORD: "your-db-password"
  TAVILY_API_KEY: "your-tavily-key"
  QDRANT_API_KEY: "your-qdrant-key"
```

### 3. Deployment Manifests

Gateway Deployment:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mcp-gateway
  template:
    metadata:
      labels:
        app: mcp-gateway
    spec:
      containers:
      - name: gateway
        image: your-registry/mcp-gateway:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: mcp-retriever-config
        - secretRef:
            name: mcp-retriever-secrets
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/detailed
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
```

### 4. Service Definitions

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mcp-gateway-service
spec:
  selector:
    app: mcp-gateway
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

### 5. Apply Kubernetes Resources

```bash
# Create namespace
kubectl create namespace mcp-retriever

# Apply configurations
kubectl apply -f k8s/ -n mcp-retriever

# Check status
kubectl get pods -n mcp-retriever
kubectl get services -n mcp-retriever
```

## Production Configuration

### 1. Security Hardening

#### Use Strong JWT Keys
```python
# Generate secure JWT key
import secrets
jwt_secret = secrets.token_urlsafe(64)
print(f"JWT_SECRET_KEY={jwt_secret}")
```

#### Enable HTTPS
- Use TLS certificates for all endpoints
- Configure reverse proxy (nginx/traefik)
- Enforce HTTPS redirects

#### Network Security
- Use private networks for internal communication
- Configure firewall rules
- Enable VPN for database access

### 2. Performance Optimization

#### Database Connection Pooling
```python
# In config.py
POSTGRES_POOL_SIZE = 20
POSTGRES_MAX_OVERFLOW = 40
POSTGRES_POOL_TIMEOUT = 30
```

#### Redis Configuration
```redis
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
```

#### Qdrant Optimization
```yaml
# qdrant config
service:
  max_request_size_mb: 10
  max_workers: 0  # Auto-detect

storage:
  optimizers:
    indexing_threshold_kb: 20000
```

### 3. Monitoring Setup

#### Prometheus Configuration
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'mcp-gateway'
    static_configs:
    - targets: ['gateway:8000']
    
  - job_name: 'mcp-server'
    static_configs:
    - targets: ['mcp-server:8001']
```

#### Grafana Dashboards
Import provided dashboards from `monitoring/grafana/`:
- System Overview
- API Performance
- Error Rates
- Resource Usage

### 4. Backup Strategy

#### PostgreSQL Backup
```bash
#!/bin/bash
# backup-postgres.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="mcp_retriever_backup_${DATE}.sql"

pg_dump -h localhost -U mcp_user -d mcp_retriever > $BACKUP_FILE
gzip $BACKUP_FILE

# Upload to S3
aws s3 cp ${BACKUP_FILE}.gz s3://your-backup-bucket/postgres/
```

#### Qdrant Backup
```bash
# Snapshot API
curl -X POST "http://localhost:6333/collections/my_collection/snapshots"
```

## Scaling Considerations

### Horizontal Scaling

#### Gateway Scaling
- Add more gateway replicas
- Use load balancer (HAProxy, AWS ALB)
- Session affinity not required

#### MCP Server Scaling
- Scale based on CPU/memory usage
- Consider connection limits to databases
- Use connection pooling

### Vertical Scaling

#### Database Scaling
- PostgreSQL: Consider read replicas
- Qdrant: Use sharding for large datasets
- Redis: Use Redis Cluster for high availability

## Troubleshooting

### Common Issues

#### 1. Authentication Failures
```bash
# Check JWT configuration
echo $JWT_SECRET_KEY

# Verify token generation
uv run python scripts/test_auth.py
```

#### 2. Database Connection Issues
```bash
# Test PostgreSQL connection
psql -h localhost -U mcp_user -d mcp_retriever -c "SELECT 1"

# Check Qdrant
curl http://localhost:6333/health
```

#### 3. Performance Issues
```bash
# Check resource usage
docker stats

# View slow queries
SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;
```

### Log Analysis

#### Gateway Logs
```bash
# View gateway logs
docker logs mcp-gateway --tail 100 -f

# Search for errors
docker logs mcp-gateway 2>&1 | grep ERROR
```

#### Structured Log Queries
```python
# analyze_logs.py
import json
import sys

for line in sys.stdin:
    try:
        log = json.loads(line)
        if log.get('level') == 'ERROR':
            print(f"{log['timestamp']}: {log['message']}")
    except:
        pass
```

## Maintenance

### Regular Tasks

1. **Daily**
   - Check error logs
   - Monitor resource usage
   - Verify backup completion

2. **Weekly**
   - Review performance metrics
   - Update dependencies
   - Test disaster recovery

3. **Monthly**
   - Security updates
   - Performance optimization
   - Capacity planning

### Update Procedure

```bash
# 1. Backup current state
./scripts/backup_all.sh

# 2. Test in staging
docker-compose -f docker-compose.staging.yml up

# 3. Rolling update
kubectl set image deployment/mcp-gateway gateway=your-registry/mcp-gateway:new-version
kubectl set image deployment/mcp-server mcp-server=your-registry/mcp-server:new-version

# 4. Verify
kubectl rollout status deployment/mcp-gateway
kubectl rollout status deployment/mcp-server
```

## Support

### Getting Help
- Check logs first
- Review documentation
- Search existing issues
- Contact support team

### Useful Commands
```bash
# Health check all services
./scripts/health_check.sh

# Export metrics
./scripts/export_metrics.sh

# Generate support bundle
./scripts/support_bundle.sh
```