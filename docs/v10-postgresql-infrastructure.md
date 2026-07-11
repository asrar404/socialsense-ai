# SocialSense AI — Version 10: PostgreSQL + Redis + Celery Infrastructure

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Flask App                          │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Auth     │  │ Dashboard│  │ Analysis │  │ Health │ │
│  │ Routes   │  │ Routes   │  │ Routes   │  │ Routes │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬───┘ │
│       │             │             │             │      │
│  ┌────┴─────────────┴─────────────┴─────────────┴───┐  │
│  │               Service Layer                       │  │
│  │  AnalysisService │ JobService │ RedisService     │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                              │
│  ┌───────────────────────┴───────────────────────────┐  │
│  │              Repository Layer                     │  │
│  │  UserRepo │ JobRepo │ AnalysisRepo │ ...          │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                              │
├──────────────────────────┼──────────────────────────────┤
│                          │                              │
│  ┌───────────────────────┴───────────────────────────┐  │
│  │              SQLAlchemy ORM                       │  │
│  │        22 Models with relationships               │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                              │
│  ┌───────────────────────┴───────────────────────────┐  │
│  │              PostgreSQL                            │  │
│  │         Connection Pool (QueuePool)                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────┐  ┌────────────────────────────────┐   │
│  │    Redis     │  │         Celery Workers         │   │
│  │  ┌────────┐  │  │  ┌──────────┐ ┌─────────────┐  │   │
│  │  │ Broker │  │  │  │ Analysis │ │ Scheduler   │  │   │
│  │  ├────────┤  │  │  │ Tasks    │ │ Tasks       │  │   │
│  │  │ Cache  │  │  │  ├──────────┤ ├─────────────┤  │   │
│  │  ├────────┤  │  │  │ Reports  │ │ Cleanup     │  │   │
│  │  │ Rate   │  │  │  │ Tasks    │ │ Tasks       │  │   │
│  │  │ Limiter│  │  │  └──────────┘ └─────────────┘  │   │
│  │  └────────┘  │  └────────────────────────────────┘   │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
```

## What Changed

### SQLite → PostgreSQL
- `database/__init__.py` — unchanged (Flask-SQLAlchemy handles the switch)
- `config/settings.py` — added `SQLALCHEMY_ENGINE_OPTIONS` with connection pooling
- All 22 ORM models — unchanged (SQLAlchemy abstraction)
- All migrations — unchanged (Alembic handles PostgreSQL natively)

### Redis Integration
- `services/redis_service.py` — NEW
  - Connection management with health checks
  - Cache get/set/delete with TTL support
  - Rate limiting via sorted sets
  - Queue length monitoring
  - Redis INFO endpoint

### Celery Integration
- `celery_app.py` — NEW (Celery application configuration)
- `celery_tasks.py` — NEW (Task definitions)
  - `run_analysis` — replaces thread-based background analysis
  - `run_scheduler` — replaces inline scheduler execution
  - `run_scheduled_reports` — replaces inline report generation
  - `cleanup_old_data` — replaces inline cleanup
- `services/job_queue_interface.py` — updated `CeleryQueueProvider` to be functional
- `services/background_worker.py` — updated to support Celery mode via `USE_CELERY` flag

### Health Endpoint
- `routes/health_routes.py` — NEW
  - GET `/health/` returns JSON with application, database, redis, celery status
- `services/database_health_service.py` — NEW
  - Connectivity checks, pool usage, active connections, migration status

### Dashboard
- `templates/dashboard/dashboard.html` — added Infrastructure Status section
- `routes/dashboard_routes.py` — passes infrastructure data to template

### Configuration
- `config/settings.py` — added PostgreSQL pool settings, Redis URL, Celery configuration
- `.env.example` — added all V10 environment variables

### Docker
- `Dockerfile` — NEW (Python 3.11 slim, gunicorn)
- `docker-compose.yml` — NEW (Flask + PostgreSQL + Redis + Celery Worker + Celery Beat)

## PostgreSQL Setup

### Local Development

1. Install PostgreSQL:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib libpq-dev

   # macOS
   brew install postgresql
   ```

2. Start PostgreSQL:
   ```bash
   sudo service postgresql start
   ```

3. Create database and user:
   ```bash
   sudo -u postgres createuser --superuser socialsense
   sudo -u postgres createdb socialsense -O socialsense
   ```

4. Set environment variable:
   ```bash
   export DATABASE_URL=postgresql://socialsense:socialsense@localhost:5432/socialsense
   ```

### Using Docker (recommended for development)

```bash
docker compose up db -d
```

### Alembic Migrations

```bash
flask db upgrade
```

To create a new migration:
```bash
flask db migrate -m "description"
flask db upgrade
```

## Redis Setup

### Local Development

```bash
# Ubuntu/Debian
sudo apt-get install redis-server
sudo service redis-server start

# macOS
brew install redis
brew services start redis
```

### Using Docker

```bash
docker compose up redis -d
```

## Celery Setup

### Start Celery Worker

```bash
# Activate environment first
source venv/bin/activate

# Start worker
celery -A celery_app worker --loglevel=info --concurrency=4
```

### Start Celery Beat (scheduler)

```bash
celery -A celery_app beat --loglevel=info
```

### Start Flower (monitoring dashboard)

```bash
celery -A celery_app flower --port=5555
```

## Docker Usage

### One-Command Launch

```bash
# Start entire stack
docker compose up --build

# Start in background
docker compose up --build -d

# View logs
docker compose logs -f
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| Web     | 5000 | Flask application (gunicorn) |
| DB      | 5432 | PostgreSQL |
| Redis   | 6379 | Redis |
| Celery Worker | — | Background task processing |
| Celery Beat | — | Scheduled task dispatcher |

### Environment Variables

Required in `.env` or passed to `docker compose`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://socialsense:socialsense@db:5432/socialsense` | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Celery result backend |
| `SECRET_KEY` | `change-me-in-production` | Flask secret key |
| `YOUTUBE_API_KEY` | — | YouTube Data API key |
| `REDDIT_CLIENT_ID` | — | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | — | Reddit API client secret |
| `USE_CELERY` | `false` | Enable Celery workers instead of threads |
| `POSTGRES_DB` | `socialsense` | PostgreSQL database name |
| `POSTGRES_USER` | `socialsense` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `socialsense` | PostgreSQL password |

## Render Deployment

### Web Service

1. Create a new Web Service on Render
2. Connect your repository
3. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120`
4. Environment Variables:
   - `DATABASE_URL`: Internal PostgreSQL URL from Render Dashboard
   - `REDIS_URL`: Internal Redis URL from Render Dashboard
   - `SECRET_KEY`: Generate a random secret
   - `YOUTUBE_API_KEY`: Your YouTube API key
   - `FLASK_ENV`: `production`
   - `USE_CELERY`: `false` (Render doesn't support background workers on free tier)

### Background Worker (Render)

1. Create a new Background Worker
2. Settings:
   - **Start Command**: `celery -A celery_app worker --loglevel=info --concurrency=2`
3. Same environment variables as Web Service
4. Add a Redis instance from Render Dashboard

### Cron Jobs (for scheduler)

Use Render's cron jobs or an external service:
```bash
curl -X POST https://your-app.com/admin/scheduler/run
```

## Migration Guide

### From SQLite to PostgreSQL

1. **Dump SQLite data:**
   ```bash
   sqlite3 instance/socialsense.db .dump > dump.sql
   ```

2. **Create PostgreSQL database:**
   ```bash
   createdb socialsense
   ```

3. **Update DATABASE_URL:**
   ```
   DATABASE_URL=postgresql://user:password@localhost:5432/socialsense
   ```

4. **Run migrations:**
   ```bash
   flask db upgrade
   ```

5. **Import data:**
   Convert the SQLite dump to PostgreSQL-compatible format and import.

## Rollback Guide

### To SQLite

1. Change `DATABASE_URL` back to `sqlite:///socialsense.db`
2. Restore SQLite backup
3. Restart application

### Migration Rollback

```bash
flask db downgrade
```

## Performance Improvements

### Connection Pooling
- `QueuePool` with configurable size, overflow, timeout, and recycle
- `pool_pre_ping=True` prevents stale connections
- Automatic connection health checks

### Bulk Operations
- Use `db.session.add_all()` for batch inserts
- Use Query.delete() for batch deletes
- Use joinedload() for eager loading

### Query Optimization
- Pagination with `limit()`/`offset()` for large datasets
- Eager loading via `joinedload()` to reduce N+1 queries
- Proper indexing on foreign keys and frequently queried columns

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run V10 infrastructure tests specifically
python -m pytest tests/test_v10_infrastructure.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term
```

## Known Limitations

1. **Celery requires a running Redis instance** — falls back to threads if unavailable
2. **Flower monitoring** — needs to be started separately
3. **PostgreSQL connection pool** — needs tuning based on concurrent user load
4. **Migration from SQLite to PostgreSQL** — requires manual data dump/import for existing data
5. **Render free tier** — does not support background workers; USE_CELERY must be `false`

## Recommendations for Version 11

1. **Kubernetes/Orchestration** — container orchestration for auto-scaling workers
2. **Read Replicas** — separate read/write database connections for scaling
3. **Distributed Caching** — Redis caching layer for API responses and analysis results
4. **Async API** — WebSocket support for real-time job progress updates
5. **Prometheus Monitoring** — export metrics for Prometheus/Grafana
6. **Automated Backups** — PostgreSQL automated backup/restore procedures
7. **Database Sharding** — horizontal scaling for very large datasets
8. **Message Queue Monitoring** — Celery Flower or custom monitoring dashboard
9. **Connection Pool Autoscaling** — dynamic pool sizing based on load
10. **Query Performance Monitoring** — slow query logging and analysis with pg_stat_statements
