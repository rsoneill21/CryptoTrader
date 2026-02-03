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
    from db.database import purge_expired_sessions

    deleted = purge_expired_sessions()
    return {"deleted": deleted}


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


@celery_app.task
def sync_manual_trades(lookback_minutes: int = 60):
    """
    Task to sync trades from Kraken exchange that were not initiated by the system.
    """
    import asyncio
    from services.trade_sync import manual_trade_sync_service

    # manual_trade_sync_service is async, so we need to run it in an event loop
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # This shouldn't happen in a celery worker process usually
        future = asyncio.run_coroutine_threadsafe(
            manual_trade_sync_service.detect_manual_trades(lookback_minutes=lookback_minutes),
            loop
        )
        report = future.result()
    else:
        report = asyncio.run(manual_trade_sync_service.detect_manual_trades(lookback_minutes=lookback_minutes))

    return {
        "inspected": report.inspected,
        "manual_detected": report.manual_detected,
        "manual_trade_ids": report.manual_trade_ids
    }
