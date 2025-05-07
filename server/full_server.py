import json
import threading
import logging
from websocket_server import WebsocketServer

import signal
import sys

from db.setup import SessionLocal
from model.db import User, House, HouseUserRole

from server.shared_state import state



def setup_signal_handlers(server):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received, closing connections...")
        
        # Notify all clients about the shutdown
        shutdown_message = json.dumps({
            "type": "server_shutdown", 
            "message": "Server is shutting down for maintenance"
        })
        
        # Send message to all connected clients
        for client in server.clients:
            try:
                server.send_message(client, shutdown_message)
            except Exception as e:
                logger.error(f"Error notifying client {client['id']} of shutdown: {str(e)}")
        
        # Log active connections before shutting down
        try:
            lock_acquired = state.clients_lock.acquire(timeout=5)
            if lock_acquired:
                try:
                    logger.info(f"Shutting down with {len(state.clients)} active connections")
                    # Could perform additional cleanup of client resources here
                finally:
                    state.clients_lock.release()
        except Exception as e:
            logger.error(f"Error accessing client lock during shutdown: {str(e)}")
        
        # Clean up any other resources
        # For example, you might want to commit any pending database transactions
        try:
            session = SessionLocal()
            session.commit()
            session.close()
            logger.info("Database session closed")
        except Exception as e:
            logger.error(f"Error closing database session: {str(e)}")
        
        # Close the websocket server
        try:
            server.server_close()
            logger.info("WebSocket server closed")
        except Exception as e:
            logger.error(f"Error closing server: {str(e)}")
        
        logger.info("Server shutdown complete")
        sys.exit(0)
    
    # Register the signal handler for various signals
    signal.signal(signal.SIGINT, signal_handler)   # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle termination signal
    
    logger.info("Signal handlers registered for graceful shutdown")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('WebSocketServer')


# Configuration
HOST = '0.0.0.0'
PORT = 12345

def new_client(client, server):
    """Handle new client connection"""
    client_id = client['id']
    logger.info(f"New client connected: {client_id}")
    
    state.add_client(client_id, {
        'user_id': None,
        'username': None,
        'house_id': None,
        'authenticated': False
    })

def client_left(client, server):
    """Handle client disconnection"""
    client_id = client['id']
    logger.info(f"Client disconnected: {client_id}")
    
    client_data = state.get_client(client_id)
    if client_data:
        # Get house_id before removing client
        house_id = client_data.get('house_id')
        if house_id:
            from server.broadcast import unregister_client
            unregister_client(house_id, client)
        
        # Remove client from tracking
        state.remove_client(client_id)

def handle_login(client, server, data):
    """Process login request"""
    client_id = client['id']
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        send_error(client, server, "Username and password are required")
        return
    
    session = SessionLocal()
    try:
        # Find user
        user = session.query(User).filter_by(username=username).first()
        
        # Check password (should use proper password hashing)
        if not user or user.password_hash != password:
            send_error(client, server, "Invalid username or password")
            return
        
        # Get houses this user has access to
        houses_query = session.query(
            House, HouseUserRole.role
        ).join(
            HouseUserRole, House.id == HouseUserRole.house_id
        ).filter(
            HouseUserRole.user_id == user.id
        ).all()
        
        houses_info = [
            {
                "id": house.id, 
                "name": house.name, 
                "role": role
            }
            for house, role in houses_query
        ]
        
        # Update client tracking info using shared state
        state.update_client(client_id, {
            'user_id': user.id,
            'username': user.username,
            'authenticated': True,
            'house_id': None  # Will be set when they join a house
        })
        
        # Send login success response
        response = {
            "type": "login_response",
            "status": "success",
            "user_id": user.id,
            "username": user.username,
            "houses": houses_info
        }
        
        server.send_message(client, json.dumps(response))
        logger.info(f"User {username} logged in successfully")
    
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        send_error(client, server, f"Login failed: {str(e)}")
    finally:
        session.close()

def handle_join_house(client, server, data):
    """Process request to join a house"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = data.get('house_id')
    if not house_id:
        send_error(client, server, "House ID is required")
        return
    
    session = SessionLocal()
    try:
        # Check if user has access to this house
        user_id = client_data['user_id']
        house_role = session.query(HouseUserRole).filter_by(
            user_id=user_id,
            house_id=house_id
        ).first()
        
        if not house_role:
            send_error(client, server, "Access denied to this house")
            return
        
        # If client was in another house, remove them
        from server.broadcast import unregister_client, register_client
        old_house_id = client_data.get('house_id')
        if old_house_id:
            unregister_client(old_house_id, client)
        
        # Update client's current house using shared state
        state.update_client(client_id, {
            'house_id': house_id,
            'role': house_role.role
        })
        
        # Register client for broadcasts to this house
        register_client(house_id, client)
        
        # Load house data and send initial state
        from model.bridge import domain_house_from_orm
        from server.handlers import get_house_state
        
        house_row = session.query(House).get(house_id)
        # Use state to check and update active_houses
        house = state.get_house(house_id)
        if not house:
            house = domain_house_from_orm(house_row)
            state.add_house(house_id, house)
        
        house_state = get_house_state(house)
        
        # Send house joined response with initial state
        response = {
            "type": "house_state",
            "status": "success",
            "house_id": house_id,
            "name": house.name,
            "state": house_state
        }
        
        server.send_message(client, json.dumps(response))
        logger.info(f"Client {client_id} joined house {house_id}")
        
    except Exception as e:
        logger.error(f"Error joining house: {str(e)}")
        send_error(client, server, f"Failed to join house: {str(e)}")
    finally:
        session.close()

def handle_logout(client, server, data):
    """Process logout request"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data:
        return
    
    # Get house_id before resetting
    house_id = client_data.get('house_id')
    
    # Reset client state using shared state
    state.update_client(client_id, {
        'user_id': None,
        'username': None,
        'house_id': None,
        'authenticated': False
    })
    
    # Unregister from broadcasts if in a house
    if house_id:
        from server.broadcast import unregister_client
        unregister_client(house_id, client)
    
    # Send logout confirmation
    response = {
        "type": "logout_response",
        "status": "success"
    }
    server.send_message(client, json.dumps(response))
    logger.info(f"Client {client_id} logged out")

def handle_device_action_message(client, server, data):
    """Process device control request"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import handle_device_action
        
        # Create domain user with role
        user = User(
            user_id=client_data['user_id'], 
            username=client_data['username'], 
            role=client_data['role']
        )
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        # Pass the client ID to the handler
        result = handle_device_action(house, user, session, data, client_id=client_id)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error handling device action: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")
    finally:
        session.close()

def handle_device_status_message(client, server, data):
    client_id = client['id']

    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return

    try:
        from model.domain import User
        from server.handlers import handle_device_status

        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )

        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return

        result = handle_device_status(data, house, user)
        server.send_message(client, json.dumps(result))

    except Exception as e:
        logger.error(f"Error handling device status: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")

def handle_query_house(client, server, data):
    """Process request to query entire house state"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    try:
        from server.handlers import get_house_state
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        house_state = get_house_state(house)
        
        response = {
            "type": "house_state",
            "status": "success",
            "house_id": house_id,
            "state": house_state
        }
        
        server.send_message(client, json.dumps(response))
        
    except Exception as e:
        logger.error(f"Error querying house: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")

def handle_query_room(client, server, data):
    """Process request to query a room's state"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    room_id = data.get('room_id')
    if not room_id:
        send_error(client, server, "Room ID is required")
        return
    
    try:
        from server.handlers import get_room_state
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        room = house.rooms.get(room_id)
        if not room:
            send_error(client, server, f"Room {room_id} not found")
            return
        
        room_state = get_room_state(room)
        
        response = {
            "type": "room_state",
            "status": "success",
            "room_id": room_id,
            "state": room_state
        }
        
        server.send_message(client, json.dumps(response))
        
    except Exception as e:
        logger.error(f"Error querying room: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")

def handle_device_group_status_message(client, server, data):
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    try:
        from model.domain import User
        from server.handlers import handle_device_group_status
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        result = handle_device_group_status(data, house, user)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error handling device group status: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")


def handle_device_group_action_message(client, server, data):
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import handle_device_group_action
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        result = handle_device_group_action(house, user, session, data)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error handling device group action: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")
    finally:
        session.close()

def handle_list_house_devices_message(client, server, data):
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    try:
        from model.domain import User
        from server.handlers import handle_list_house_devices
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        result = handle_list_house_devices(house, user)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error listing house devices: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")


def handle_add_room(client, server, data):
    """Process request to add a new room"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import handle_add_room as handler_add_room
        from server.broadcast import broadcast_to_house
        
        # Create domain user with role
        user = User(
            user_id=client_data['user_id'], 
            username=client_data['username'], 
            role=client_data['role']
        )
        
        # Add house_id to the data
        data['house_id'] = house_id
        
        # Call the handler
        result = handler_add_room(data, session, user)
        server.send_message(client, json.dumps(result))
        
        # Broadcast room addition to other clients if successful
        if result.get('status') == 'success':
            broadcast_message = {
                "type": "room_added",
                "house_id": house_id,
                "room_id": result.get('room_id'),
                "room_name": data.get('room_name', "New Room")
            }
            broadcast_to_house(house_id, broadcast_message, exclude_client_id=client_id)
            logger.info(f"Room {result.get('room_id')} added and broadcasted to house {house_id}")
        
    except Exception as e:
        logger.error(f"Error adding room: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")
    finally:
        session.close()

def handle_add_device(client, server, data):
    """Process request to add a new device"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import handle_add_device as handler_add_device
        from server.broadcast import broadcast_to_house
        
        # Create domain user with role
        user = User(
            user_id=client_data['user_id'], 
            username=client_data['username'], 
            role=client_data['role']
        )
        
        # Add house_id to the data
        data['house_id'] = house_id
        
        # Call the handler
        result = handler_add_device(data, session, user)
        server.send_message(client, json.dumps(result))
        
        # Broadcast device addition to other clients if successful
        if result.get('status') == 'success':
            broadcast_message = {
                "type": "device_added",
                "house_id": house_id,
                "room_id": data.get('room_id'),
                "device_id": result.get('device_id'),
                "device_type": data.get('device_type')
            }
            broadcast_to_house(house_id, broadcast_message, exclude_client_id=client_id)
            logger.info(f"Device {result.get('device_id')} added and broadcasted to house {house_id}")
        
    except Exception as e:
        logger.error(f"Error adding device: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")
    finally:
        session.close()

def handle_remove_room(client, server, data):
    """Process request to remove a room"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    # Store room_id for broadcasting before it might be removed from result
    room_id = data.get('room_id')
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import handle_remove_room as handler_remove_room
        from server.broadcast import broadcast_to_house
        
        # Create domain user with role
        user = User(
            user_id=client_data['user_id'], 
            username=client_data['username'], 
            role=client_data['role']
        )
        
        # Add house_id to the data
        data['house_id'] = house_id
        
        # Call the handler
        result = handler_remove_room(data, session, user)
        server.send_message(client, json.dumps(result))
        
        # Broadcast room removal to other clients if successful
        if result.get('status') == 'success':
            broadcast_message = {
                "type": "room_removed",
                "house_id": house_id,
                "room_id": room_id
            }
            broadcast_to_house(house_id, broadcast_message, exclude_client_id=client_id)
            logger.info(f"Room {room_id} removed and broadcasted to house {house_id}")
        
    except Exception as e:
        logger.error(f"Error removing room: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")
    finally:
        session.close()


def handle_remove_device(client, server, data):
    """Process request to remove a device"""
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    # Store these for broadcasting before they might be removed from result
    room_id = data.get('room_id')
    device_id = data.get('device_id')
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import handle_remove_device as handler_remove_device
        from server.broadcast import broadcast_to_house
        
        # Create domain user with role
        user = User(
            user_id=client_data['user_id'], 
            username=client_data['username'], 
            role=client_data['role']
        )
        
        # Add house_id to the data
        data['house_id'] = house_id
        
        # Call the handler
        result = handler_remove_device(data, session, user)
        server.send_message(client, json.dumps(result))
        
        # Broadcast device removal to other clients if successful
        if result.get('status') == 'success':
            broadcast_message = {
                "type": "device_removed",
                "house_id": house_id,
                "room_id": room_id,
                "device_id": device_id
            }
            broadcast_to_house(house_id, broadcast_message, exclude_client_id=client_id)
            logger.info(f"Device {device_id} removed and broadcasted to house {house_id}")
        
    except Exception as e:
        logger.error(f"Error removing device: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")
    finally:
        session.close()


def handle_list_room_devices_message(client, server, data):
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    room_id = data.get('room_id')
    if not room_id:
        send_error(client, server, "Room ID is required")
        return
    
    try:
        from model.domain import User
        from server.handlers import handle_list_room_devices
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        result = handle_list_room_devices(house, user, room_id)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error listing room devices: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")

def handle_list_group_devices_message(client, server, data):
    client_id = client['id']
    
    # Get client data from shared state
    client_data = state.get_client(client_id)
    if not client_data or not client_data.get('authenticated'):
        send_error(client, server, "Not authenticated")
        return
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    device_type = data.get('device_type')
    if not device_type:
        send_error(client, server, "Device type is required")
        return
    
    try:
        from model.domain import User
        from server.handlers import handle_list_group_devices
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        # Get house from shared state
        house = state.get_house(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        result = handle_list_group_devices(house, user, device_type)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error listing group devices: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")

def message_received(client, server, message):
    """Process incoming messages from clients"""
    client_id = client['id']
    logger.debug(f"Message from client {client_id}: {message[:100]}...")
    
    try:
        data = json.loads(message)
        command = data.get('command')
        
        if command == 'login':
            handle_login(client, server, data)
        elif command == 'join_house':
            handle_join_house(client, server, data)
        elif command == 'logout':
            handle_logout(client, server, data)
        elif command == 'device_action':
            handle_device_action_message(client, server, data)
        elif command == 'device_group_action':
            handle_device_group_action_message(client, server, data)
        elif command == 'query_house':
            handle_query_house(client, server, data)
        elif command == 'query_room':
            handle_query_room(client, server, data)
        elif command == 'device_status':
            handle_device_status_message(client, server, data)
        elif command == 'device_group_status':
            handle_device_group_status_message(client, server, data)
        elif command == 'list_house_devices':
            handle_list_house_devices_message(client, server, data)
        elif command == 'list_room_devices':
            handle_list_room_devices_message(client, server, data)
        elif command == 'list_group_devices':
            handle_list_group_devices_message(client, server, data)
        # Add the new command handlers here
        elif command == 'add_room':
            handle_add_room(client, server, data)
        elif command == 'add_device':
            handle_add_device(client, server, data)
        elif command == 'remove_room':
            handle_remove_room(client, server, data)
        elif command == 'remove_device':
            handle_remove_device(client, server, data)
        else:
            send_error(client, server, f"Unknown command: {command}")
    
    except json.JSONDecodeError:
        send_error(client, server, "Invalid JSON format")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        send_error(client, server, "Internal server error")

def send_error(client, server, message):
    """Send error response to client"""
    response = {
        "type": "error",
        "message": message
    }
    server.send_message(client, json.dumps(response))
    logger.warning(f"Error sent to client {client['id']}: {message}")

def start_server():
    """Start the WebSocket server"""
    server = WebsocketServer(host=HOST, port=PORT)
    
    # Set up callbacks
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)
    
    # Initialize the broadcaster with reference to server
    from server.broadcast import init_broadcaster
    init_broadcaster(server)
    
    # Setup signal handlers for graceful shutdown
    setup_signal_handlers(server)
    
    logger.info(f"Starting WebSocket server on {HOST}:{PORT}")
    server.run_forever()