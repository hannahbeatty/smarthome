from db.setup import init_db
# from server.websocket_server import start_server  # To be implemented

def main():
    print("[INIT] Starting smart home server...")
    init_db()
    print("[DB] Tables created.")

    # Placeholder for where the WebSocket server will be started
    # start_server()
    print("[SERVER] WebSocket server would start here.")

if __name__ == "__main__":
    main()

