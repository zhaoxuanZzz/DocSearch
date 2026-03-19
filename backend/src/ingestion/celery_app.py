"""Celery application configuration."""

from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "docsearch",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.ingestion.pipeline"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,  # 1 hour
)
