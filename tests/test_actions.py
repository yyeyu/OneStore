from __future__ import annotations

import pytest
from uuid import uuid4

from app.actions import execute_probe_action
from app.db import ActionLog, get_session_factory
from app.modules import ModuleOperationsService


pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("require_postgresql"),
]


def _bootstrap_account() -> int:
    service = ModuleOperationsService()
    suffix = uuid4().hex[:8]
    bootstrap = service.bootstrap_local(
        name="Action Test Account",
        client_id=f"action-test-client-{suffix}",
        client_secret=f"action-test-secret-{suffix}",
        module_name="system_core",
    )
    return bootstrap.account.account.id


def test_probe_action_success_logs_action() -> None:
    account_id = _bootstrap_account()
    result = execute_probe_action(
        target="test-target",
        message="hello",
        account_id=account_id,
    )

    assert result.status == "success"
    session_factory = get_session_factory()
    with session_factory() as session:
        action_log = session.get(ActionLog, result.action_log_id)

    assert action_log is not None
    assert action_log.status == "success"
    assert action_log.action_name == "probe_dispatch"
    assert action_log.account_id == account_id


def test_probe_action_failure_logs_error() -> None:
    account_id = _bootstrap_account()
    result = execute_probe_action(
        target="test-target",
        message="hello",
        account_id=account_id,
        should_fail=True,
    )

    assert result.status == "error"
    assert result.error_message == "Probe action failed on purpose."
    session_factory = get_session_factory()
    with session_factory() as session:
        action_log = session.get(ActionLog, result.action_log_id)

    assert action_log is not None
    assert action_log.status == "error"
    assert action_log.error_message == "Probe action failed on purpose."
