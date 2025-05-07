import sys
import os
import traceback

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.setup import init_db
from server.full_server import start_server

def main():
    try:
        print("[INIT] Starting smart home server...")
        print("[DEBUG] About to initialize database...")
        init_db()
        print("[DB] Tables created.")
        print("[DEBUG] About to start server...")
        start_server()
        print("[SERVER] Server started successfully") # This will only print if start_server returns
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    print("[MAIN] Script started")
    main()
    print("[MAIN] Script completed") # This will only print if main() returns
