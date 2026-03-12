"""
Paper trading state persistence service.

Provides async helpers to load, save, archive, and snapshot paper trading state
without blocking the event loop.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PaperTradingState

logger = logging.getLogger(__name__)


class PaperTradingStateService:
    """Service for managing paper trading state persistence."""

    @staticmethod
    async def load_active_session(async_session: AsyncSession) -> Optional[Dict[str, Any]]:
        """
        Load the currently active paper trading session state.

        Returns:
            State payload dict if an active session exists, None otherwise.
        """
        try:
            stmt = select(PaperTradingState).where(
                PaperTradingState.is_active == True
            ).order_by(
                PaperTradingState.updated_at.desc()
            ).limit(1)

            result = await async_session.execute(stmt)
            state = result.scalar_one_or_none()

            if state is None:
                logger.info("No active paper trading session found")
                return None

            logger.info(
                "Loaded active paper trading session: %s (updated: %s)",
                state.session_id,
                state.updated_at
            )
            return state.state_json

        except Exception as exc:
            logger.exception("Failed to load active paper trading session: %s", exc)
            return None

    @staticmethod
    async def save_state(
        async_session: AsyncSession,
        session_id: str,
        state_payload: Dict[str, Any]
    ) -> bool:
        """
        Save or update paper trading state for a session.

        Args:
            async_session: Database session
            session_id: Unique identifier for the session
            state_payload: Complete state snapshot as JSON-serializable dict

        Returns:
            True if save succeeded, False otherwise.
        """
        try:
            # Check if session exists
            stmt = select(PaperTradingState).where(
                PaperTradingState.session_id == session_id
            )
            result = await async_session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing session
                existing.state_json = state_payload
                existing.updated_at = datetime.utcnow()
                logger.debug("Updated paper trading session: %s", session_id)
            else:
                # Create new session (deactivate all others first)
                await async_session.execute(
                    update(PaperTradingState)
                    .where(PaperTradingState.is_active == True)
                    .values(is_active=False)
                )

                new_state = PaperTradingState(
                    session_id=session_id,
                    state_json=state_payload,
                    is_active=True
                )
                async_session.add(new_state)
                logger.info("Created new paper trading session: %s", session_id)

            await async_session.commit()
            return True

        except Exception as exc:
            logger.exception("Failed to save paper trading state for %s: %s", session_id, exc)
            await async_session.rollback()
            return False

    @staticmethod
    async def archive_session(
        async_session: AsyncSession,
        session_id: str
    ) -> bool:
        """
        Archive a paper trading session (mark as inactive and set archived_at).

        Args:
            async_session: Database session
            session_id: Session to archive

        Returns:
            True if archive succeeded, False otherwise.
        """
        try:
            stmt = (
                update(PaperTradingState)
                .where(PaperTradingState.session_id == session_id)
                .values(
                    is_active=False,
                    archived_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            )

            result = await async_session.execute(stmt)
            await async_session.commit()

            if result.rowcount > 0:
                logger.info("Archived paper trading session: %s", session_id)
                return True
            else:
                logger.warning("No session found to archive: %s", session_id)
                return False

        except Exception as exc:
            logger.exception("Failed to archive session %s: %s", session_id, exc)
            await async_session.rollback()
            return False

    @staticmethod
    async def get_session(
        async_session: AsyncSession,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load a specific session by ID (active or archived).

        Args:
            async_session: Database session
            session_id: Session to load

        Returns:
            State payload dict if session exists, None otherwise.
        """
        try:
            stmt = select(PaperTradingState).where(
                PaperTradingState.session_id == session_id
            )
            result = await async_session.execute(stmt)
            state = result.scalar_one_or_none()

            if state is None:
                logger.warning("Session not found: %s", session_id)
                return None

            return state.state_json

        except Exception as exc:
            logger.exception("Failed to load session %s: %s", session_id, exc)
            return None


__all__ = ["PaperTradingStateService"]
