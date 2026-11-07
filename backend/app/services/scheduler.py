import asyncio
import logging
import time

from sqlalchemy import or_, select

from app.config import settings
from app.database import SessionLocal
from app.models import Monitor, utcnow
from app.services.maintenance import sweep_maintenance
from app.services.monitoring import (
    CheckInProgressError,
    MonitorNotFoundError,
    perform_check,
    sweep_heartbeats,
)
from app.services.retention import prune_old_checks

logger = logging.getLogger(__name__)


class MonitorScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._last_prune: float | None = None
        self.running = False

    async def start(self) -> None:
        if not settings.scheduler_enabled:
            logger.info("Scheduler disabled by configuration")
            return
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="monitor-scheduler")
        logger.info(
            "Scheduler started (tick=%ss, concurrency=%s)",
            settings.scheduler_tick_seconds,
            settings.check_concurrency,
        )

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        while self.running:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler iteration failed")
            await asyncio.sleep(max(1, settings.scheduler_tick_seconds))

    async def _run_once(self) -> None:
        try:
            async with SessionLocal() as session:
                await sweep_maintenance(session)
        except Exception:
            logger.exception("Maintenance sweep failed")

        try:
            await sweep_heartbeats()
        except Exception:
            logger.exception("Heartbeat sweep failed")

        now_mono = time.monotonic()
        if self._last_prune is None or now_mono - self._last_prune >= 3600:
            self._last_prune = now_mono
            try:
                removed = await prune_old_checks()
                if removed:
                    logger.info("Removed %s check rows older than the retention window", removed)
            except Exception:
                logger.exception("Retention cleanup failed")

        now = utcnow()
        async with SessionLocal() as session:
            monitor_ids = (
                (
                    await session.execute(
                        select(Monitor.id)
                        .where(
                            Monitor.active.is_(True),
                            Monitor.monitor_type == "http",
                            or_(
                                Monitor.next_check_at.is_(None),
                                Monitor.next_check_at <= now,
                            ),
                        )
                        .order_by(Monitor.next_check_at.asc().nullsfirst())
                        .limit(settings.scheduler_batch_size)
                    )
                )
                .scalars()
                .all()
            )

        if not monitor_ids:
            return

        results = await asyncio.gather(
            *(perform_check(monitor_id) for monitor_id in monitor_ids),
            return_exceptions=True,
        )
        for monitor_id, result in zip(monitor_ids, results, strict=False):
            if isinstance(result, CheckInProgressError):
                logger.debug("Monitor %s is already being checked", monitor_id)
            elif isinstance(result, MonitorNotFoundError):
                logger.warning("Monitor %s disappeared before its check", monitor_id)
            elif isinstance(result, Exception):
                logger.error("Check failed for monitor %s: %s", monitor_id, result)


scheduler = MonitorScheduler()
