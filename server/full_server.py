import json
import threading
import logging
from websocket_server import WebsocketServer

from db.setup import SessionLocal
from model.db import User, House, HouseUserRole
from server.handlers import handle_device_action

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('WebSocketServer')

# Client tracking - maps client IDs to user info
clients = {}
clients_lock = threading.Lock()

# Configuration
HOST = '0.0.0.0'
PORT = 8765

def new_client(client, server):
    """Handle new client connection"""
    client_id = client['id']
    logger.info(f"New client connected: {client_id}")
    
    with clients_lock:
        clients[client_id] = {
            'user_id': None,
            'username': None,
            'house_id': None,
            'authenticated': False
        }

def client_left(client, server):
    """Handle client disconnection"""
    client_id = client['id']
    logger.info(f"Client disconnected: {client_id}")
    
    with clients_lock:
        if client_id in clients:
            # Get house_id before removing client
            house_id = clients[client_id].get('house_id')
            if house_id:
                from server.broadcast import unregister_client
                unregister_client(house_id, client)
            
            # Remove client from tracking
            del clients[client_id]

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
        
        # Update client tracking info
        with clients_lock:
            clients[client_id] = {
                'user_id': user.id,
                'username': user.username,
                'authenticated': True,
                'house_id': None  # Will be set when they join a house
            }
        
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        
        client_data = clients[client_id]
    
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
        
        # Update client's current house
        with clients_lock:
            clients[client_id]['house_id'] = house_id
            clients[client_id]['role'] = house_role.role
        
        # Register client for broadcasts to this house
        register_client(house_id, client)
        
        # Load house data and send initial state
        from model.bridge import domain_house_from_orm
        from server.handlers import get_house_state, active_houses
        
        house_row = session.query(House).get(house_id)
        if house_id not in active_houses:
            active_houses[house_id] = domain_house_from_orm(house_row)
        
        house = active_houses[house_id]
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
    
    with clients_lock:
        if client_id not in clients:
            return
        
        # Get house_id before resetting
        house_id = clients[client_id].get('house_id')
        
        # Reset client state
        clients[client_id] = {
            'user_id': None,
            'username': None,
            'house_id': None,
            'authenticated': False
        }
    
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        
        client_data = clients[client_id]
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import active_houses
        from server.handlers import handle_device_action
        
        # Create domain user with role
        user = User(
            user_id=client_data['user_id'], 
            username=client_data['username'], 
            role=client_data['role']
        )
        
        # Get house and call handler
        house = active_houses.get(house_id)
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

    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        client_data = clients[client_id]

    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return

    try:
        from model.domain import User
        from server.handlers import active_houses, handle_device_status

        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )

        house = active_houses.get(house_id)
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        
        client_data = clients[client_id]
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    try:
        from server.handlers import active_houses, get_house_state
        
        house = active_houses.get(house_id)
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        
        client_data = clients[client_id]
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    room_id = data.get('room_id')
    if not room_id:
        send_error(client, server, "Room ID is required")
        return
    
    try:
        from server.handlers import active_houses, get_room_state
        
        house = active_houses.get(house_id)
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        client_data = clients[client_id]
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    try:
        from model.domain import User
        from server.handlers import active_houses, handle_device_group_status
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        house = active_houses.get(house_id)
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        
        client_data = clients[client_id]
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    session = SessionLocal()
    try:
        from model.domain import User
        from server.handlers import active_houses, handle_device_group_action
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        house = active_houses.get(house_id)
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        client_data = clients[client_id]
    
    house_id = client_data.get('house_id')
    if not house_id:
        send_error(client, server, "Not currently in a house")
        return
    
    try:
        from model.domain import User
        from server.handlers import active_houses, handle_list_house_devices
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        house = active_houses.get(house_id)
        if not house:
            send_error(client, server, "House data not loaded")
            return
        
        result = handle_list_house_devices(house, user)
        server.send_message(client, json.dumps(result))
        
    except Exception as e:
        logger.error(f"Error listing house devices: {str(e)}")
        send_error(client, server, f"Error: {str(e)}")

def handle_list_room_devices_message(client, server, data):
    client_id = client['id']
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        client_data = clients[client_id]
    
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
        from server.handlers import active_houses, handle_list_room_devices
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        house = active_houses.get(house_id)
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
    
    with clients_lock:
        if client_id not in clients or not clients[client_id].get('authenticated'):
            send_error(client, server, "Not authenticated")
            return
        client_data = clients[client_id]
    
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
        from server.handlers import active_houses, handle_list_group_devices
        
        user = User(
            user_id=client_data['user_id'],
            username=client_data['username'],
            role=client_data['role']
        )
        
        house = active_houses.get(house_id)
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
    
    # Initialize the broadcaster with references to server and clients
    from server.broadcast import init_broadcaster
    init_broadcaster(server, clients, clients_lock)
    
    logger.info(f"Starting WebSocket server on {HOST}:{PORT}")
    server.run_forever()