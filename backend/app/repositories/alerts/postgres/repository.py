"""SQLAlchemy async ORM implementations of BaseAlertRuleRepository and
BaseAlertRepository.

Contains no business logic (duplicate-name prevention, max rule/channel
counts, cooldown/deduplication — see `app.alerts.engine.AlertService`) —
only translation between domain models and SQL operations, via the
mapper. Written against SQLAlchemy's database-agnostic async engine, the
same shape already used by every other Postgres repository in this
codebase: a real PostgreSQL server in production, an in-memory SQLite
database (via aiosqlite) in tests.
"""

from __future__ import annotations

import copy as copy_module
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.alerts.models import Alert, AlertRule
from app.repositories.alerts.postgres.mapper import (
    alert_to_model,
    model_to_alert,
    model_to_rule,
    rule_to_model,
)
from app.repositories.alerts.postgres.models import AlertModel, AlertRuleModel
from app.repositories.alerts.repository import BaseAlertRepository, BaseAlertRuleRepository

__all__ = ["PostgresAlertRuleRepository", "PostgresAlertRepository"]


class PostgresAlertRuleRepository(BaseAlertRuleRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_rule(self, rule: AlertRule) -> AlertRule:
        async with self._session_factory() as session:
            session.add(rule_to_model(rule))
            await session.commit()
        return rule

    async def update_rule(self, rule: AlertRule) -> AlertRule | None:
        async with self._session_factory() as session:
            existing = await session.get(AlertRuleModel, rule.id)
            if existing is None:
                return None
            existing.name = rule.name
            existing.description = rule.description
            existing.enabled = rule.enabled
            existing.priority = rule.priority.value
            existing.conditions = [c.model_dump(mode="json") for c in rule.conditions]
            existing.cooldown_minutes = rule.cooldown_minutes
            existing.repeat_allowed = rule.repeat_allowed
            existing.channels = [c.value for c in rule.channels]
            existing.updated_at = rule.updated_at
            await session.commit()
            return model_to_rule(existing)

    async def delete_rule(self, rule_id: str) -> bool:
        async with self._session_factory() as session:
            model = await session.get(AlertRuleModel, rule_id)
            existed = model is not None
            if model is not None:
                await session.delete(model)
                await session.commit()
        return existed

    async def list_rules(self) -> list[AlertRule]:
        async with self._session_factory() as session:
            result = await session.execute(select(AlertRuleModel))
            models = result.scalars().all()
        return [model_to_rule(model) for model in models]

    async def get_rule(self, rule_id: str) -> AlertRule | None:
        async with self._session_factory() as session:
            model = await session.get(AlertRuleModel, rule_id)
        return model_to_rule(model) if model is not None else None

    async def duplicate_rule(self, rule_id: str, new_rule_id: str, new_name: str) -> AlertRule | None:
        async with self._session_factory() as session:
            source = await session.get(AlertRuleModel, rule_id)
            if source is None:
                return None
            now = datetime.now(UTC)
            new_model = AlertRuleModel(
                id=new_rule_id,
                name=new_name,
                description=source.description,
                enabled=source.enabled,
                priority=source.priority,
                conditions=copy_module.deepcopy(source.conditions),
                cooldown_minutes=source.cooldown_minutes,
                repeat_allowed=source.repeat_allowed,
                channels=copy_module.deepcopy(source.channels),
                created_at=now,
                updated_at=now,
            )
            session.add(new_model)
            await session.commit()
            return model_to_rule(new_model)

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False


class PostgresAlertRepository(BaseAlertRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_alert(self, alert: Alert) -> Alert:
        async with self._session_factory() as session:
            session.add(alert_to_model(alert))
            await session.commit()
        return alert

    async def get_alert(self, alert_id: str) -> Alert | None:
        async with self._session_factory() as session:
            model = await session.get(AlertModel, alert_id)
        return model_to_alert(model) if model is not None else None

    async def list_alerts(self) -> list[Alert]:
        async with self._session_factory() as session:
            result = await session.execute(select(AlertModel))
            models = result.scalars().all()
        return [model_to_alert(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
