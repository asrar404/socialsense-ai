import logging
from flask import current_app
from repositories.job_repository import JobRepository
from repositories.notification_repository import NotificationRepository
from repositories.activity_log_repository import ActivityLogRepository
from repositories.scheduled_report_repository import ScheduledReportRepository
from services.notification_service import NotificationService
from services.database_health_service import database_health_service
from services.redis_service import redis_service

logger = logging.getLogger(__name__)


class SystemHealthService:
    def __init__(self):
        self.job_repo = JobRepository()
        self.notification_repo = NotificationRepository()

    def get_health(self):
        from database import db
        db_ok = True
        try:
            db.session.execute(db.text('SELECT 1'))
        except Exception:
            db_ok = False

        redis_ok = redis_service.check_connection()
        pool_usage = database_health_service.get_pool_usage() if db_ok else {}
        db_size = database_health_service.get_database_size() if db_ok else 'unknown'
        migration = database_health_service.get_migration_status() if db_ok else {}

        celery_ok = False
        active_workers = 0
        active_jobs = 0
        queue_length = 0
        try:
            from celery_app import celery_app
            inspector = celery_app.control.inspect()
            active = inspector.active() or {}
            active_workers = len(active)
            active_jobs = sum(len(tasks) for tasks in active.values())
            celery_ok = True
        except Exception:
            pass

        try:
            queue_length = redis_service.get_queue_length('celery')
        except Exception:
            pass

        from models.job import Job
        pending = self.job_repo.count_all_by_status(Job.PENDING)
        running = self.job_repo.count_all_by_status(Job.RUNNING)
        failed = self.job_repo.count_all_by_status(Job.FAILED)

        latest = Job.query.order_by(Job.created_at.desc()).first()

        app = current_app._get_current_object() if current_app else None
        yt_key = bool(app.config.get('YOUTUBE_API_KEY')) if app else False
        reddit_id = bool(app.config.get('REDDIT_CLIENT_ID')) if app else False
        reddit_secret = bool(app.config.get('REDDIT_CLIENT_SECRET')) if app else False

        return {
            'database': 'connected' if db_ok else 'error',
            'redis_status': 'connected' if redis_ok else 'disconnected',
            'celery_status': 'connected' if celery_ok else 'disconnected',
            'worker_status': 'active' if running > 0 else 'idle',
            'pending_jobs': pending,
            'running_jobs': running,
            'failed_jobs': failed,
            'queue_length': queue_length,
            'active_workers': active_workers,
            'active_jobs': active_jobs,
            'pool_size': pool_usage.get('size', 0),
            'pool_checkedout': pool_usage.get('checkedout', 0),
            'pool_overflow': pool_usage.get('overflow', 0),
            'database_size': db_size,
            'database_uptime': f'{database_health_service.get_uptime():.0f}s',
            'migration_version': migration.get('current_version'),
            'latest_job_id': latest.id if latest else None,
            'latest_job_status': latest.status if latest else None,
            'app_version': '10',
            'environment': app.config.get('ENV', 'development') if app else 'unknown',
            'youtube_api': 'configured' if yt_key else 'missing',
            'reddit_api': 'configured' if (reddit_id and reddit_secret) else 'missing',
        }


class MaintenanceService:
    def __init__(self):
        self.job_repo = JobRepository()
        self.notification_service = NotificationService()
        self.activity_repo = ActivityLogRepository()
        self.report_repo = ScheduledReportRepository()

    def cleanup_all(self, app):
        from flask import current_app
        config = app.config if app else current_app.config if current_app else {}
        job_days = config.get('JOB_LOG_RETENTION_DAYS', 30)
        notif_days = config.get('NOTIFICATION_RETENTION_DAYS', 30)
        report_days = config.get('REPORT_RETENTION_DAYS', 30)

        results = {}
        results['job_logs'] = self.activity_repo.delete_old_logs(days=job_days)
        results['notifications'] = self.notification_service.cleanup_old(days=notif_days)
        results['reports'] = self.report_repo.delete_old_reports(days=report_days)
        results['jobs'] = self.job_repo.cleanup_old_jobs(days=job_days)
        return results
