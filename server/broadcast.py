# server/broadcast.py
import json
import logging
import threading
from server.shared_state import state

# Configure logging
logger = logging.getLogger("Broadcast")

def init_broadcaster(server):
    """
    Initialize the broadcaster with reference to server
    
    Args:
        server: WebsocketServer instance
    """
    state.set_server(server)
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
    server = state.get_server()
    if not server:
        logger.error("Broadcaster not initialized")
        return
    
    # Convert message to string if it's not already
    data = message if isinstance(message, str) else json.dumps(message)
    
    client_count = 0
    house_clients = state.get_house_clients(house_id)
    
    for client_id, client_data in house_clients.items():
        # Skip excluded client (originator of the request)
        if exclude_client_id and client_id == exclude_client_id:
            continue
            
        try:
            # Find the client object by ID in server clients list
            client_obj = next((c for c in server.clients if c['id'] == client_id), None)
            if client_obj:
                server.send_message(client_obj, data)
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
    server = state.get_server()
    if not server:
        logger.error("Broadcaster not initialized")
        return
    
    # Convert message to string if it's not already
    data = message if isinstance(message, str) else json.dumps(message)
    
    for client in server.clients:
        try:
            server.send_message(client, data)
        except Exception as e:
            logger.error(f"Error broadcasting to client {client['id']}: {str(e)}")
            
    logger.debug(f"Broadcasted message to all {len(server.clients)} clients")