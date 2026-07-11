import logging
from datetime import datetime, timezone
from flask import current_app
from database import db
from sqlalchemy import text

logger = logging.getLogger(__name__)


class DatabaseHealthService:
    def __init__(self):
        self._uptime_start = datetime.now(timezone.utc)

    def check_connectivity(self) -> bool:
        try:
            db.session.execute(text('SELECT 1'))
            return True
        except Exception as e:
            logger.error(f'Database connectivity check failed: {e}')
            return False

    def get_pool_usage(self) -> dict:
        engine = db.engine
        try:
            pool = engine.pool
            return {
                'size': pool.size(),
                'checkedin': pool.checkedin(),
                'overflow': pool.overflow(),
                'checkedout': pool.checkedout(),
            }
        except Exception:
            return {
                'size': 0,
                'checkedin': 0,
                'overflow': 0,
                'checkedout': 0,
            }

    def get_active_connections(self) -> int:
        try:
            result = db.session.execute(
                text('SELECT count(*) FROM pg_stat_activity WHERE state = \'active\'')
            )
            return result.scalar() or 0
        except Exception:
            return -1

    def get_database_size(self) -> str:
        try:
            result = db.session.execute(
                text("SELECT pg_size_pretty(pg_database_size(current_database()))")
            )
            return result.scalar() or 'unknown'
        except Exception:
            return 'unknown'

    def get_migration_status(self) -> dict:
        try:
            result = db.session.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            )
            row = result.fetchone()
            return {
                'current_version': row[0] if row else None,
                'has_migrations': row is not None,
            }
        except Exception:
            return {
                'current_version': None,
                'has_migrations': False,
            }

    def get_uptime(self) -> float:
        return (datetime.now(timezone.utc) - self._uptime_start).total_seconds()

    def get_health(self) -> dict:
        connected = self.check_connectivity()
        return {
            'status': 'connected' if connected else 'error',
            'connectivity': connected,
            'pool_usage': self.get_pool_usage() if connected else {},
            'active_connections': self.get_active_connections() if connected else -1,
            'database_size': self.get_database_size() if connected else 'unknown',
            'migration_status': self.get_migration_status() if connected else {},
            'uptime_seconds': self.get_uptime(),
            'engine_url': str(db.engine.url).replace('//', '//***:***@') if connected else 'unknown',
        }


database_health_service = DatabaseHealthService()
