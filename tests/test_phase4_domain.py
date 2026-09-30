"""Domain compatibility and dependency-boundary checks."""

from src.dss.application.ports.clock import Clock
from src.dss.domain.conversations.clock import Clock as DomainClock


def test_clock_port_keeps_identity() -> None:
    assert Clock is DomainClock
