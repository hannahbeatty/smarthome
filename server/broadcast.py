import threading
import json

# house_id → set of sockets
_house_clients = {}
_house_locks = {}

def register_client(house_id, socket):
    if house_id not in _house_clients:
        _house_clients[house_id] = set()
        _house_locks[house_id] = threading.Lock()

    with _house_locks[house_id]:
        _house_clients[house_id].add(socket)
        print(f"[REGISTER] Client registered for house {house_id}. Total: {len(_house_clients[house_id])}")

def unregister_client(user, socket):
    for house_id, clients in _house_clients.items():
        if socket in clients:
            with _house_locks[house_id]:
                clients.remove(socket)
                print(f"[UNREGISTER] Client removed from house {house_id}. Remaining: {len(clients)}")
            break

def broadcast_to_house(house_id, message):
    if house_id not in _house_clients:
        return

    data = message if isinstance(message, bytes) else message.encode()

    with _house_locks[house_id]:
        to_remove = set()
        for sock in _house_clients[house_id]:
            try:
                sock.send(data + b"\n")
            except Exception as e:
                print(f"[BROADCAST ERROR] {e}")
                to_remove.add(sock)

        for sock in to_remove:
            _house_clients[house_id].remove(sock)
