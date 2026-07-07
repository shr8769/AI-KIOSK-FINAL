import asyncio

from app.core.dependencies import ConnectionManager


class DummyWebSocket:
    def __init__(self, exc=None):
        self.exc = exc
        self.sent = []

    async def send_json(self, message):
        if self.exc is not None:
            raise self.exc
        self.sent.append(message)


def test_send_drops_message_when_socket_is_already_closed():
    async def _run_test():
        mgr = ConnectionManager()
        ws = DummyWebSocket(RuntimeError('Cannot call "send" once a close message has been sent.'))
        mgr.active["session-1"] = ws

        await mgr.send("session-1", {"type": "answer", "payload": {"text": "ok"}})

        assert "session-1" not in mgr.active
        assert ws.sent == []

    asyncio.run(_run_test())
