"""
Connections subsystem for Aether (Phase C).
"""
from aether.connections.models import CalendarEvent, Connection, ConnectionStatus
from aether.connections.store import ConnectionStore
from aether.connections.service import CalendarConnector, ConnectionService
from aether.connections.sync import ConnectorSyncEngine, ConnectorSyncResult

__all__ = [
    "CalendarEvent",
    "Connection",
    "ConnectionStatus",
    "ConnectionStore",
    "CalendarConnector",
    "ConnectionService",
    "ConnectorSyncEngine",
    "ConnectorSyncResult",
]
