class WebSocketHandler:
    def __init__(self):
        self.active_connections = {}
        self.last_active_sid = None  # 👈 Track last SID

    def handle_connection(self, sid):
        self.active_connections[sid] = {"buffer": []}
        self.last_active_sid = sid  # 👈 Update last active SID

    def handle_disconnection(self, sid):
        self.active_connections.pop(sid, None)
        if self.last_active_sid == sid:
            self.last_active_sid = None
