from flask import Blueprint, jsonify
from services.database_health_service import database_health_service
from services.redis_service import redis_service

health_bp = Blueprint('health', __name__, url_prefix='/health')


@health_bp.route('')
@health_bp.route('/')
def health():
    db_health = database_health_service.get_health()
    redis_ok = redis_service.check_connection()

    celery_ok = False
    celery_active = 0
    celery_queue = 0
    try:
        from celery_app import celery_app
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        celery_active = sum(len(tasks) for tasks in active.values())
        celery_ok = True
    except Exception:
        pass

    try:
        celery_queue = redis_service.get_queue_length('celery')
    except Exception:
        pass

    app_ok = db_health['connectivity'] and redis_ok

    return jsonify({
        'application': 'healthy' if app_ok else 'degraded',
        'database': db_health['status'],
        'redis': 'connected' if redis_ok else 'disconnected',
        'celery': 'connected' if celery_ok else 'disconnected',
        'version': '10',
        'details': {
            'database': {
                'pool_usage': db_health['pool_usage'],
                'active_connections': db_health['active_connections'],
                'database_size': db_health['database_size'],
                'migration_status': db_health['migration_status'],
                'uptime_seconds': db_health['uptime_seconds'],
            },
            'redis': {
                'connected': redis_ok,
                'info': redis_service.get_info() if redis_ok else {},
            },
            'celery': {
                'connected': celery_ok,
                'active_workers': len(active) if celery_ok else 0,
                'active_tasks': celery_active,
                'queue_length': celery_queue,
            },
        },
    })
