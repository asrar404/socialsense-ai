from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, Future
import threading


class BaseQueueProvider(ABC):
    @abstractmethod
    def submit(self, fn, *args, **kwargs):
        pass

    @abstractmethod
    def shutdown(self, wait=True):
        pass

    @abstractmethod
    def get_active_count(self):
        pass

    @abstractmethod
    def get_queue_size(self):
        pass


class ThreadPoolQueueProvider(BaseQueueProvider):
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._futures = {}
        self._counter = 0

    def submit(self, fn, *args, **kwargs):
        future = self.executor.submit(fn, *args, **kwargs)
        with self._lock:
            self._counter += 1
            fid = self._counter
            self._futures[fid] = future
            future._ss_fid = fid
        return future

    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait)

    def get_active_count(self):
        count = 0
        with self._lock:
            for fid, f in list(self._futures.items()):
                if not f.done():
                    count += 1
                else:
                    del self._futures[fid]
        return count

    def get_queue_size(self):
        return self.executor._work_queue.qsize() if hasattr(self.executor, '_work_queue') else 0


class CeleryQueueProvider(BaseQueueProvider):
    def __init__(self):
        from celery_app import celery_app
        self.celery_app = celery_app
        self._active = {}

    def submit(self, fn, *args, **kwargs):
        from celery_tasks import run_analysis
        job_id = args[0] if args else kwargs.get('job_id')
        result = run_analysis.delay(job_id=job_id)
        self._active[job_id] = result.id
        return result

    def shutdown(self, wait=True):
        pass

    def get_active_count(self):
        from celery_app import celery_app
        try:
            inspector = celery_app.control.inspect()
            active = inspector.active() or {}
            count = sum(len(tasks) for tasks in active.values())
            return count
        except Exception:
            return 0

    def get_queue_size(self):
        try:
            from services.redis_service import redis_service
            return redis_service.get_queue_length('celery')
        except Exception:
            from celery_app import celery_app
            try:
                inspector = celery_app.control.inspect()
                reserved = inspector.reserved() or {}
                count = sum(len(tasks) for tasks in reserved.values())
                return count
            except Exception:
                return 0


class RQQueueProvider(BaseQueueProvider):
    def __init__(self):
        raise NotImplementedError('RQ integration not yet implemented')

    def submit(self, fn, *args, **kwargs):
        raise NotImplementedError('RQ integration not yet implemented')

    def shutdown(self, wait=True):
        pass

    def get_active_count(self):
        return 0

    def get_queue_size(self):
        return 0
