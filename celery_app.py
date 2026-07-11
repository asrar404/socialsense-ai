import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL)

celery_app = Celery(
    'socialsense',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=int(os.environ.get('MAX_JOB_RUNTIME', '600')),
    task_time_limit=int(os.environ.get('MAX_JOB_RUNTIME', '600')) + 60,
    result_expires=86400,
    worker_concurrency=int(os.environ.get('CELERY_WORKER_CONCURRENCY', '4')),
    beat_schedule={
        'run-scheduler-every-minute': {
            'task': 'celery_tasks.run_scheduler',
            'schedule': 60.0,
        },
        'run-scheduled-reports-every-5-minutes': {
            'task': 'celery_tasks.run_scheduled_reports',
            'schedule': 300.0,
        },
        'cleanup-old-data-daily': {
            'task': 'celery_tasks.cleanup_old_data',
            'schedule': 86400.0,
        },
    },
    timezone='UTC',
)

import celery_tasks  # noqa: F401, E402
