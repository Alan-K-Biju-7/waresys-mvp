from celery import Celery

# Define the Celery app instance here, and only here.
celery_app = Celery(
    "waresys",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)
# Optional: You can include autodiscovery for tasks if you have many task files
# celery_app.autodiscover_tasks(['app'])