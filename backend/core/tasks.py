"""
Background tasks for CryptoTrader.

Tasks defined here are executed by Celery workers.
"""

from core.celery_app import celery_app


@celery_app.task
def cleanup_expired_sessions():
    """
    Periodic task to clean up expired sessions.

    Should be scheduled in celery beat.
    """
    from datetime import datetime
    from db.database import SessionLocal
    from db.models import Session as UserSession

    db = SessionLocal()
    try:
        expired = db.query(UserSession).filter(
            UserSession.expires_at < datetime.utcnow()
        ).delete()
        db.commit()
        return {"deleted": expired}
    finally:
        db.close()


@celery_app.task
def log_system_event(level: str, source: str, message: str, details: dict = None):
    """
    Task to log system events asynchronously.

    Args:
        level: Log level (debug, info, warning, error, critical)
        source: Source component
        message: Log message
        details: Additional details as dict
    """
    from db.database import SessionLocal
    from db.models import SystemLog

    db = SessionLocal()
    try:
        log = SystemLog(
            level=level,
            source=source,
            message=message,
            details_json=details,
        )
        db.add(log)
        db.commit()
        return {"id": log.id}
    finally:
        db.close()
