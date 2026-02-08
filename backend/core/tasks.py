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
def monitor_strategy_health():
    """
    Periodic task to monitor health of active strategies.
    Identifies degrading strategies and triggers AI analysis.
    """
    import asyncio
    from db.database import AsyncSessionLocal
    from db.models import Strategy, Alert
    from sqlalchemy import select
    from services.strategy_service import check_strategy_health, HealthStatus
    from services.strategy_ai import strategy_ai_service
    import logging

    logger = logging.getLogger("cryptotrader.tasks")

    async def _monitor():
        async with AsyncSessionLocal() as db:
            # Iterate all live/paper strategies
            query = select(Strategy).where(Strategy.status.in_(["live", "paper"]))
            result = await db.execute(query)
            strategies = result.scalars().all()
            
            monitored_count = 0
            degraded_count = 0
            
            for strategy in strategies:
                monitored_count += 1
                health_result = await check_strategy_health(db, strategy.id)
                status = health_result["status"]
                
                # Update strategy health status in DB
                strategy.health_status = status.value
                
                if status in [HealthStatus.DEGRADED, HealthStatus.CRITICAL]:
                    degraded_count += 1
                    # 1. Create System Alert
                    alert = Alert(
                        type="strategy_health",
                        title=f"Strategy {strategy.name} is {status.value}",
                        message=f"Performance degradation detected for {strategy.name}: Win Rate {health_result['metrics']['win_rate']:.2%}",
                        severity="warning" if status == HealthStatus.DEGRADED else "critical",
                        related_strategy_id=strategy.id
                    )
                    db.add(alert)
                    
                    # 2. Call AI for suggestions
                    try:
                        suggestions = await strategy_ai_service.analyze_degradation(
                            strategy.id,
                            strategy.name,
                            health_result["metrics"]
                        )
                        # 3. Save suggestion
                        strategy.pending_adjustment_json = suggestions
                    except Exception:
                        logger.exception("AI degradation analysis failed for strategy %s", strategy.id)
            
            await db.commit()
            return {
                "strategies_monitored": monitored_count,
                "degraded_identified": degraded_count
            }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_monitor(), loop)
            return future.result()
        else:
            return asyncio.run(_monitor())
    except Exception:
        return asyncio.run(_monitor())
