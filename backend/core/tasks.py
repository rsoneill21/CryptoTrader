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


@celery_app.task
def monitor_active_strategies():
    """
    Periodic task to monitor health of active strategies.
    Identifies degrading strategies and triggers AI analysis.
    """
    import asyncio
    from db.database import AsyncSessionLocal
    from services.strategy_service import monitor_strategies
    import logging

    logger = logging.getLogger("cryptotrader.tasks")

    async def _run():
        async with AsyncSessionLocal() as db:
            return await monitor_strategies(db)

    try:
        # Check if we are already in an event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In a running loop, we can't use asyncio.run
            # This is common in some test environments or if celery is running with an event loop
            import threading
            
            # Use a separate thread to run the async logic if we're blocked
            # Actually, for celery, it usually runs in a worker process.
            # If we're here, we're likely in a sync context.
            return asyncio.run(_run())
        else:
            return asyncio.run(_run())
    except Exception:
        # Fallback for complex environments
        return asyncio.run(_run())


@celery_app.task
def capture_periodic_snapshot():
    """
    Periodic task to capture portfolio performance snapshot.
    """
    import asyncio
    from services.performance_service import performance_service

    return asyncio.run(performance_service.capture_snapshot())


@celery_app.task
def cleanup_old_performance_snapshots():
    """
    Periodic task to cleanup old performance snapshots based on retention policy.
    """
    import asyncio
    from services.performance_service import performance_service

    return asyncio.run(performance_service.cleanup_old_snapshots())
