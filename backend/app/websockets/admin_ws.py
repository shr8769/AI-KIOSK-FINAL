"""
admin_ws.py

WebSocket handler for real-time admin sync monitoring.

Broadcasts sync progress events to all connected admin clients.
Uses the existing ConnectionManager pattern but with a dedicated
admin connection registry.

Endpoint: /ws/admin/sync
"""

import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("admin.websocket")


class AdminSyncWsManager:
    """
    Manages WebSocket connections for admin sync monitoring.

    Maintains a set of active admin connections and broadcasts
    sync progress events from the SyncStateManager.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._registered = False

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new admin WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Admin WS connected (total: {len(self.active_connections)})")

        # Send current state on connect
        try:
            from app.services.sync_state_manager import SyncStateManager
            mgr = SyncStateManager()
            await websocket.send_json({
                "type": "connected",
                "data": mgr.get_progress(),
            })
        except Exception as e:
            logger.warning(f"Could not send initial state: {e}")

        # Register callback if not already done
        if not self._registered:
            self._register_callback()

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected admin WebSocket."""
        self.active_connections.discard(websocket)
        logger.info(f"Admin WS disconnected (total: {len(self.active_connections)})")

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected admin clients."""
        disconnected = set()
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)

        # Clean up disconnected
        for ws in disconnected:
            self.active_connections.discard(ws)

    def _broadcast_sync(self, message: dict) -> None:
        """
        Synchronous callback for SyncStateManager events.
        Schedules the async broadcast on the running event loop.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(message))
        except RuntimeError:
            # No running event loop — queue for later
            pass

    def _register_callback(self) -> None:
        """Register the broadcast callback with the SyncStateManager."""
        try:
            from app.services.sync_state_manager import SyncStateManager
            mgr = SyncStateManager()
            mgr.register_event_callback(self._broadcast_sync)
            self._registered = True
            logger.info("Admin WS callback registered with SyncStateManager")
        except Exception as e:
            logger.warning(f"Could not register WS callback: {e}")


# Singleton instance
_admin_ws_manager = AdminSyncWsManager()


def get_admin_ws_manager() -> AdminSyncWsManager:
    return _admin_ws_manager


async def admin_sync_ws_handler(websocket: WebSocket) -> None:
    """
    WebSocket endpoint handler for /ws/admin/sync.

    Keeps the connection alive and broadcasts sync progress
    events in real time. The client can also send commands.
    """
    manager = get_admin_ws_manager()
    await manager.connect(websocket)

    try:
        while True:
            # Keep connection alive; handle incoming messages
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                # Handle admin commands
                try:
                    msg = json.loads(data)
                    cmd = msg.get("command", "")

                    if cmd == "get_progress":
                        from app.services.sync_state_manager import SyncStateManager
                        mgr = SyncStateManager()
                        await websocket.send_json({
                            "type": "progress",
                            "data": mgr.get_progress(),
                        })
                    elif cmd == "ping":
                        await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Admin WS error: {e}")
    finally:
        manager.disconnect(websocket)
