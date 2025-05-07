import json
import logging
from db.setup import SessionLocal
from model.db import User, House, HouseUserRole
from model.db import Lamp as LampORM, Lock as LockORM, Blinds as BlindsORM, CeilingLight as CeilingLightORM, Alarm as AlarmORM
from model.bridge import domain_user_from_orm, domain_house_from_orm
from model.bridge import update_orm_lamp_from_domain, update_orm_lock_from_domain, update_orm_blinds_from_domain
from model.bridge import update_orm_ceiling_light_from_domain, update_orm_alarm_from_domain
from server.broadcast import register_client, unregister_client, broadcast_to_house

# Configure logging
logger = logging.getLogger("Handlers")

# Dictionary to store active houses in memory
active_houses = {}

# Define a mapping of device types to their ORM classes and update functions
DEVICE_MAPPINGS = {
    "Lamp": {
        "orm_class": LampORM,
        "update_func": update_orm_lamp_from_domain
    },
    "Lock": {
        "orm_class": LockORM,
        "update_func": update_orm_lock_from_domain
    },
    "Blinds": {
        "orm_class": BlindsORM,
        "update_func": update_orm_blinds_from_domain
    },
    "CeilingLight": {
        "orm_class": CeilingLightORM,
        "update_func": update_orm_ceiling_light_from_domain
    },
    "Alarm": {
        "orm_class": AlarmORM,
        "update_func": update_orm_alarm_from_domain
    }
}

def get_device_from_house(house, device_type, room_id, device_id):
    """
    Locate a device in a house by type, room, and device ID.
    
    Args:
        house: The house object
        device_type: Type of device ("Lamp", "Lock", etc.)
        room_id: ID of the room containing the device
        device_id: ID of the device
        
    Returns:
        device: The device object if found, None otherwise
    """
    room = house.rooms.get(room_id)
    if not room:
        return None
        
    device = None
    if device_type == "Lamp":
        device = room.lamps.get(device_id)
    elif device_type == "Lock":
        device = room.locks.get(device_id)
    elif device_type == "CeilingLight":
        device = room.ceiling_light if room.ceiling_light and room.ceiling_light.device_id == device_id else None
    elif device_type == "Blinds":
        device = room.blinds if room.blinds and room.blinds.device_id == device_id else None
    elif device_type == "Alarm" and house.alarm and house.alarm.device_id == device_id:
        device = house.alarm
        
    return device

def handle_device_action(house, user, session, request_data):
    """
    Generic device action handler that routes to the appropriate method
    based on device type and action.
    """
    room_id = request_data.get("room_id")
    device_id = request_data.get("device_id")
    action = request_data.get("action")
    params = request_data.get("params", {})
    device_type = request_data.get("device_type")
    
    # Authorization check
    if not user.can_control():
        return {"status": "error", "message": "User lacks permission to control devices"}
    
    # Get the device
    device = get_device_from_house(house, device_type, room_id, device_id)
    if not device:
        return {"status": "error", "message": f"Device {device_id} not found in room {room_id}"}
    
    # Execute the action on the device
    try:
        result = execute_device_action(device, action, params)
        
        # Sync changes to the database
        mapping = DEVICE_MAPPINGS.get(device_type)
        if mapping:
            orm_class = mapping["orm_class"]
            update_func = mapping["update_func"]
            
            device_orm = session.query(orm_class).filter_by(id=device_id).first()
            if device_orm:
                update_func(device, device_orm)
                session.commit()
                logger.info(f"Updated device {device_id} ({device_type}) in database")
            else:
                logger.warning(f"Could not find device {device_id} ({device_type}) in database")
        
        # Include device status in the response
        device_status = device.check_status()
        
        # Prepare response and broadcast message
        response = {
            "status": "success",
            "device_id": device_id,
            "device_type": device_type,
            "room_id": room_id,
            "action": action,
            "device_state": device_status
        }
        
        # Broadcast the updated state to all clients viewing this house
        broadcast_message = {
            "type": f"{device_type.lower()}_update",
            "device_id": device_id,
            "room_id": room_id,
            "status": device_status
        }
        broadcast_to_house(house.house_id, json.dumps(broadcast_message))
        logger.info(f"Broadcasted update for device {device_id} to house {house.house_id}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error executing device action: {str(e)}")
        return {"status": "error", "message": str(e)}

def execute_device_action(device, action, params):
    """
    Execute an action on a device with the given parameters.
    Uses reflection to call methods on the device object.
    """
    # Map action names to method names
    method_map = {
        "toggle": "flip_switch",
        "on": "flip_switch",
        "off": "flip_switch",
        "dim": "set_shade",
        "color": "change_color",
        "lock": "lock",
        "unlock": "unlock",
        "up": "toggle",
        "down": "toggle",
        "open": "shutter",
        "close": "shutter",
        "arm": "arm",
        "disarm": "disarm",
        "trigger": "trigger_alarm",
        "stop": "stop_alarm"
    }
    
    method_name = method_map.get(action)
    if not method_name:
        raise ValueError(f"Unknown action: {action}")
    
    # Special handling for on/off to ensure correct state
    if action in ["on", "off"]:
        desired_state = (action == "on")
        # Check if device has 'on' attribute (should be Lamp or CeilingLight)
        if hasattr(device, 'on') and device.on == desired_state:
            # Already in desired state
            return True
        
    # Get the method from the device
    method = getattr(device, method_name, None)
    if not method:
        raise ValueError(f"Device does not support action: {action}")
    
    # Call the method with parameters
    if params:
        # Extract parameters based on the action
        if action == "dim":
            return method(params.get("level", 100))
        elif action == "color":
            return method(params.get("color", "white"))
        elif action == "unlock":
            return method(params.get("code", ""))
        else:
            return method(**params)
    else:
        return method()

def get_house_state(house):
    """Get the complete state of a house including all rooms and devices"""
    state = {
        "house_id": house.house_id,
        "name": house.name,
        "rooms": {}
    }
    
    for room_id, room in house.rooms.items():
        state["rooms"][room_id] = get_room_state(room)
    
    if house.alarm:
        state["alarm"] = {
            "device_id": house.alarm.device_id,
            "type": "Alarm",
            "status": house.alarm.check_status()
        }
    
    return state

def get_room_state(room):
    """Get the state of a room including all devices"""
    state = {
        "room_id": room.room_id,
        "name": room.name,
        "devices": {}
    }
    
    # Add lamps
    for lamp_id, lamp in room.lamps.items():
        state["devices"][lamp_id] = {
            "type": "Lamp",
            "status": lamp.check_status()
        }
    
    # Add locks
    for lock_id, lock in room.locks.items():
        state["devices"][lock_id] = {
            "type": "Lock",
            "status": lock.check_status()
        }
    
    # Add ceiling light if present
    if room.ceiling_light:
        state["devices"][room.ceiling_light.device_id] = {
            "type": "CeilingLight",
            "status": room.ceiling_light.check_status()
        }
    
    # Add blinds if present
    if room.blinds:
        state["devices"][room.blinds.device_id] = {
            "type": "Blinds",
            "status": room.blinds.check_status()
        }
    
    return state

# This function is no longer needed since the WebSocket server handles connections
# Keep it for reference until WebSocket implementation is complete
"""
def handle_client(client_socket, addr):
    print(f"[HANDLER] Handling client from {addr}")
    session = SessionLocal()
    user = None
    house = None

    try:
        # ... rest of the function ...
    except Exception as e:
        print(f"[ERROR] Handler failed for {addr}: {e}")
    finally:
        if house and house.house_id:
            unregister_client(house.house_id, client_socket)
        session.close()
        client_socket.close()
        print(f"[DISCONNECT] {addr} closed")
"""

def load_house_if_needed(house_id, session):
    """
    Load a house from the database if it's not already in memory.
    
    Args:
        house_id: The ID of the house to load
        session: SQLAlchemy session
        
    Returns:
        house: The domain House object
    """
    if house_id not in active_houses:
        house_row = session.query(House).get(house_id)
        if not house_row:
            raise ValueError(f"House {house_id} not found in database")
            
        house = domain_house_from_orm(house_row)
        active_houses[house_id] = house
        logger.info(f"Loaded house {house_id} into memory")
    
    return active_houses[house_id]

def check_user_house_access(user_id, house_id, session):
    """
    Check if a user has access to a house and return their role.
    
    Args:
        user_id: The user ID
        house_id: The house ID
        session: SQLAlchemy session
        
    Returns:
        role: The user's role for this house, or None if no access
    """
    house_role = session.query(HouseUserRole).filter_by(
        user_id=user_id,
        house_id=house_id
    ).first()
    
    return house_role.role if house_role else None