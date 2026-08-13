"""Monitor Agent — 데모에서는 실제 GPS/시장 감시 없이 Mock Event를 주입받아 전달"""

from __future__ import annotations

from app.models.event import EventType, MockEvent


def receive_event(event: MockEvent) -> MockEvent:
    return event


def should_trigger_rebuild(event: MockEvent) -> bool:
    return event.event_type in (
        EventType.DELAY,
        EventType.CANCEL,
        EventType.NEW_ORDER,
        EventType.CONGESTION,
    )
