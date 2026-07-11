from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from services.analysis_service import AnalysisService
from services.job_service import JobService
from services.database_health_service import database_health_service
from services.redis_service import redis_service

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')
analysis_service = AnalysisService()
job_service = JobService()


@dashboard_bp.route('/')
@login_required
def index():
    platform = request.args.get('platform', 'all')
    if platform not in ('all', 'youtube', 'reddit'):
        platform = 'all'
    stats = analysis_service.get_dashboard_stats(current_user.id, platform=platform)
    recent = analysis_service.get_all_user_analyses_with_data(current_user.id, limit=10)
    job_stats = job_service.get_dashboard_metrics(current_user.id)

    db_ok = database_health_service.check_connectivity()
    redis_ok = redis_service.check_connection()
    pool_usage = database_health_service.get_pool_usage()

    celery_ok = False
    celery_active = 0
    try:
        from celery_app import celery_app
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        celery_active = sum(len(tasks) for tasks in active.values())
        celery_ok = True
    except Exception:
        pass

    infra = {
        'database': 'connected' if db_ok else 'error',
        'redis': 'connected' if redis_ok else 'disconnected',
        'celery': 'connected' if celery_ok else 'disconnected',
        'pool_checkedout': pool_usage.get('checkedout', 0),
        'pool_size': pool_usage.get('size', 0),
        'active_tasks': celery_active,
    }

    return render_template('dashboard/dashboard.html', stats=stats, analyses=recent,
                           current_platform=platform, job_stats=job_stats, infra=infra)
