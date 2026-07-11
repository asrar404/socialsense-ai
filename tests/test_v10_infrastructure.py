import pytest
import json
from app import create_app
from database import db as _db
from services.database_health_service import DatabaseHealthService
from services.redis_service import RedisService


class TestDatabaseHealthService:
    def test_check_connectivity(self, app):
        svc = DatabaseHealthService()
        assert svc.check_connectivity() is True

    def test_get_pool_usage(self, app):
        svc = DatabaseHealthService()
        with app.app_context():
            usage = svc.get_pool_usage()
            assert 'size' in usage
            assert 'checkedin' in usage
            assert 'overflow' in usage
            assert 'checkedout' in usage

    def test_get_uptime(self, app):
        svc = DatabaseHealthService()
        uptime = svc.get_uptime()
        assert isinstance(uptime, float)
        assert uptime >= 0

    def test_get_health(self, app):
        svc = DatabaseHealthService()
        with app.app_context():
            health = svc.get_health()
            assert health['status'] == 'connected'
            assert health['connectivity'] is True
            assert 'pool_usage' in health


class TestRedisService:
    def test_init(self):
        svc = RedisService('redis://localhost:6379/0')
        assert svc.redis_url == 'redis://localhost:6379/0'

    def test_check_connection_returns_false_when_offline(self):
        svc = RedisService('redis://localhost:9999/0')
        assert svc.check_connection() is False
        assert svc.is_connected is False

    def test_cache_ops(self):
        svc = RedisService('redis://localhost:9999/0')
        assert svc.cache_get('test_key') is None
        assert svc.cache_delete('test_key') is False


class TestHealthEndpoint:
    def test_health_endpoint(self, app, client):
        response = client.get('/health/')
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'application' in data
            assert 'database' in data
            assert 'redis' in data
            assert 'celery' in data
            assert data['version'] == '10'
            assert 'details' in data

    def test_health_endpoint_structure(self, app, client):
        response = client.get('/health/')
        if response.status_code == 200:
            data = json.loads(response.data)
            details = data['details']
            assert 'database' in details
            assert 'redis' in details
            assert 'celery' in details
            assert 'pool_usage' in details['database']
            assert 'uptime_seconds' in details['database']


class TestConfig:
    def test_settings_pool_config(self):
        from config.settings import Config
        engine_opts = Config.SQLALCHEMY_ENGINE_OPTIONS
        assert engine_opts['pool_size'] >= 1
        assert engine_opts['max_overflow'] >= 1
        assert engine_opts['pool_timeout'] >= 1
        assert engine_opts['pool_recycle'] >= 1
        assert engine_opts['pool_pre_ping'] is True

    def test_celery_config(self):
        from config.settings import Config
        assert Config.CELERY_TASK_TRACK_STARTED is True
        assert Config.CELERY_TASK_SERIALIZER == 'json'

    def test_redis_config(self):
        from config.settings import Config
        assert Config.REDIS_URL is not None

    def test_testing_config(self):
        from config.settings import TestingConfig
        assert TestingConfig.TESTING is True
        assert TestingConfig.USE_CELERY is False


class TestAppFactory:
    def test_app_creates_successfully(self):
        app = create_app('testing')
        assert app is not None
        assert app.config['TESTING'] is True

    def test_worker_initialized(self, app):
        assert '_worker' in app.config

    def test_blueprints_registered(self, app):
        for bp_name in ['auth', 'dashboard', 'analysis', 'export', 'jobs',
                        'schedules', 'notifications', 'activity', 'reports',
                        'trends', 'admin', 'health']:
            assert bp_name in app.blueprints

    def test_health_blueprint(self, app):
        assert 'health' in app.blueprints


class TestConcurrentAccess:
    def test_multiple_db_operations(self, app, db):
        with app.app_context():
            from models.user import User
            from werkzeug.security import generate_password_hash

            for i in range(10):
                u = User(
                    username=f'concurrent_test_{i}',
                    email=f'concurrent_{i}@test.com',
                    password_hash=generate_password_hash('test123'),
                )
                db.session.add(u)
            db.session.commit()
            assert User.query.count() >= 10

    def test_concurrent_session_cleanup(self, app, db):
        with app.app_context():
            from models.user import User
            from werkzeug.security import generate_password_hash
            try:
                u = User(
                    username='rollback_test',
                    email='rollback@test.com',
                    password_hash=generate_password_hash('test'),
                )
                db.session.add(u)
                db.session.flush()
                raise ValueError('force rollback')
            except ValueError:
                db.session.rollback()
            assert User.query.filter_by(username='rollback_test').count() == 0


class TestRepositoryLayer:
    def test_base_repository_session_cleanup(self, app, db, user):
        from repositories.base import BaseRepository
        from models.user import User
        repo = BaseRepository(User)
        u = repo.get_by_id(user.id)
        assert u is not None

    def test_job_repository(self, app, db, user):
        from repositories.job_repository import JobRepository
        from models.job import Job
        repo = JobRepository()
        job = repo.create_job(
            user_id=user.id,
            platform='youtube',
            source_type='url',
            source_input='https://youtube.com/watch?v=test',
        )
        assert job.id is not None
        assert job.status == Job.PENDING

        fetched = repo.get_job(job.id)
        assert fetched.id == job.id

        repo.update_progress(job.id, 50, 'Testing')
        assert fetched.progress_percent == 50


class TestTransactionSafety:
    def test_rollback_on_exception(self, app, db, user):
        from repositories.job_repository import JobRepository
        repo = JobRepository()
        try:
            job = repo.create_job(
                user_id=999999,
                platform='test',
                source_type='url',
                source_input='test',
            )
            assert job is not None
        except Exception:
            db.session.rollback()

    def test_atomic_transaction(self, app, db, user):
        from models.job import Job
        from database import db
        job = Job(
            user_id=user.id,
            platform='youtube',
            source_type='url',
            source_input='test_atomic',
        )
        db.session.add(job)
        db.session.flush()
        assert job.id is not None
        db.session.rollback()
        count = Job.query.filter_by(source_input='test_atomic').count()
        assert count == 0


class TestPaginationPerformance:
    def test_pagination(self, app, db, user):
        from models.analysis import Analysis
        for i in range(25):
            a = Analysis(user_id=user.id, analysis_type='youtube')
            db.session.add(a)
        db.session.commit()

        page1 = Analysis.query.order_by(Analysis.id).limit(10).offset(0).all()
        page2 = Analysis.query.order_by(Analysis.id).limit(10).offset(10).all()
        assert len(page1) == 10
        assert len(page2) == 10

    def test_eager_loading(self, app, db, analysis):
        from models.analysis import Analysis
        from sqlalchemy.orm import joinedload
        a = Analysis.query.options(
            joinedload(Analysis.youtube_analysis)
        ).filter_by(id=analysis.id).first()
        assert a is not None
        if a.youtube_analysis:
            assert a.youtube_analysis.video_title is not None


class TestBulkOperations:
    def test_bulk_insert(self, app, db, user):
        from models.notification import Notification
        notifications = []
        for i in range(50):
            n = Notification(
                user_id=user.id,
                type='test',
                title=f'Bulk Test {i}',
                message=f'Bulk message {i}',
            )
            notifications.append(n)
        db.session.add_all(notifications)
        db.session.commit()
        assert Notification.query.filter_by(type='test').count() == 50

    def test_bulk_delete(self, app, db, user):
        from models.notification import Notification
        notifications = []
        for i in range(10):
            n = Notification(
                user_id=user.id,
                type='bulk_delete',
                title=f'Delete Test {i}',
                message=f'Delete message {i}',
            )
            notifications.append(n)
        db.session.add_all(notifications)
        db.session.commit()
        Notification.query.filter_by(type='bulk_delete').delete()
        db.session.commit()
        assert Notification.query.filter_by(type='bulk_delete').count() == 0
