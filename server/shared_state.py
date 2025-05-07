# server/shared_state.py
import threading

# Thread-safe global state for active houses and connected clients

# Houses in memory
active_houses = {}
active_houses_lock = threading.RLock()

# Connected clients (from websocket_server)
clients = {}
clients_lock = threading.RLock()