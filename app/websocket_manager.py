import json
from typing import Dict, List
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self._connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, id_akun: int, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(id_akun, []).append(ws)

    def disconnect(self, id_akun: int, ws: WebSocket):
        conns = self._connections.get(id_akun, [])
        try:
            conns.remove(ws)
        except ValueError:
            pass
        if not conns:
            self._connections.pop(id_akun, None)

    async def kirim_ke_akun(self, id_akun: int, data: dict):
        conns = list(self._connections.get(id_akun, []))
        payload = json.dumps(data)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(id_akun, ws)

    def aktif(self, id_akun: int) -> bool:
        return bool(self._connections.get(id_akun))


ws_manager = WebSocketManager()