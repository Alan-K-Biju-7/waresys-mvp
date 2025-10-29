from celery import Celery
celery_app = Celery("waresys", broker="redis://redis:6379/0", backend="redis://redis:6379/0")
celery_app.autodiscover_tasks(["app"])
import app.tasks  # force registration
