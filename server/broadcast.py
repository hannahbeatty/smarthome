import json
import logging
import threading

# Configure logging
logger = logging.getLogger("Broadcast")

# Global reference to server instance (will be set from full_server.py)
_server = None
_clients_lock = threading.Lock()

# Will be initialized in init_broadcaster() function
_clients = None

def init_broadcaster(server, clients_dict, lock):
    """
    Initialize the broadcaster with references to server and clients
    
    Args:
        server: WebsocketServer instance
        clients_dict: Dictionary of connected clients
        lock: Lock for thread-safe access to clients dictionary
    """
    global _server, _clients, _clients_lock
    _server = server
    _clients = clients_dict
    _clients_lock = lock
    logger.info("Broadcaster initialized")


def register_client(house_id, client):
    """
    Register a client to receive broadcasts for a specific house
    
    Args:
        house_id: ID of the house
        client: WebSocket client object
    """
    logger.info(f"Client {client['id']} registered for broadcasts to house {house_id}")
    # No actual registration needed as broadcasts are sent based on client tracking
    # in the clients dictionary which is updated when joining a house
    
def unregister_client(house_id, client):
    """
    Unregister a client from receiving broadcasts for a specific house
    
    Args:
        house_id: ID of the house
        client: WebSocket client object
    """
    logger.info(f"Client {client['id']} unregistered from broadcasts to house {house_id}")

    
def broadcast_to_house(house_id, message, exclude_client_id=None):
    """
    Broadcast a message to all clients connected to a specific house,
    optionally excluding the originating client.
    
    Args:
        house_id: ID of the house to broadcast to
        message: Message to broadcast (string or serializable object)
        exclude_client_id: Optional client ID to exclude from broadcast
    """
    if not _server:
        logger.error("Broadcaster not initialized")
        return
    
    # Convert message to string if it's not already
    data = message if isinstance(message, str) else json.dumps(message)
    
    client_count = 0
    with _clients_lock:
        for client_id, client_data in _clients.items():
            # Skip excluded client (originator of the request)
            if exclude_client_id and client_id == exclude_client_id:
                continue
                
            # Check if client is in the specified house
            if client_data.get('house_id') == house_id:
                try:
                    # Find the client object by ID in server clients list
                    client_obj = next((c for c in _server.clients if c['id'] == client_id), None)
                    if client_obj:
                        _server.send_message(client_obj, data)
                        client_count += 1
                    else:
                        logger.warning(f"Client {client_id} not found in server clients")
                except Exception as e:
                    logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
    
    logger.debug(f"Broadcasted message to {client_count} clients in house {house_id} (excluding {exclude_client_id})")

def broadcast_to_all(message):
    """
    Broadcast a message to all connected clients
    
    Args:
        message: Message to broadcast (string or serializable object)
    """
    if not _server:
        logger.error("Broadcaster not initialized")
        return
    
    # Convert message to string if it's not already
    data = message if isinstance(message, str) else json.dumps(message)
    
    for client in _server.clients:
        try:
            _server.send_message(client, data)
        except Exception as e:
            logger.error(f"Error broadcasting to client {client['id']}: {str(e)}")
            
    logger.debug(f"Broadcasted message to all {len(_server.clients)} clients")
