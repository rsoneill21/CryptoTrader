"""
Celery application configuration for background tasks.

Requires Redis to be running:
  - Local: redis-server
  - Docker: docker run -d -p 6379:6379 redis
"""

import os
from celery import Celery

# Redis URL from environment or default
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "cryptotrader",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "core.tasks",  # Will contain background tasks
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task result expiration (24 hours)
    result_expires=86400,

    # Task acknowledgment
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,

    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-sessions": {
            "task": "core.tasks.cleanup_expired_sessions",
            "schedule": 3600.0,  # Every hour
        },
        "sync-manual-trades": {
            "task": "core.tasks.sync_manual_trades",
            "schedule": 300.0,  # Every 5 minutes
            "args": (60,),  # 60 minute lookback
        },
    },
)


# Test task
@celery_app.task(bind=True)
def test_task(self, message: str) -> dict:
    """Test task to verify Celery is working."""
    return {
        "status": "success",
        "message": message,
        "task_id": self.request.id,
    }
