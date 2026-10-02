from celery import Celery

from app.config.settings import get_settings

settings = get_settings()
celery = Celery("whatsapp_gateway", broker=settings.redis_url, include=["app.workers.tasks"])
celery.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    task_ignore_result=True, worker_prefetch_multiplier=1,
    task_acks_late=True, task_reject_on_worker_lost=True,
    task_time_limit=settings.task_time_limit_seconds,
    broker_transport_options={"visibility_timeout": settings.stale_processing_seconds + 120},
    broker_connection_retry_on_startup=True, worker_hijack_root_logger=False,
    worker_redirect_stdouts=False, task_send_sent_event=False,
)
