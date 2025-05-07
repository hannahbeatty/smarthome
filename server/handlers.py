import json
import logging
from db.setup import SessionLocal
from model.db import User, House, HouseUserRole
from model.db import Lamp as LampORM, Lock as LockORM, Blinds as BlindsORM, CeilingLight as CeilingLightORM, Alarm as AlarmORM
from model.db import Room as RoomORM
from model.bridge import domain_user_from_orm, domain_house_from_orm
from model.bridge import update_orm_lamp_from_domain, update_orm_lock_from_domain, update_orm_blinds_from_domain
from model.bridge import update_orm_ceiling_light_from_domain, update_orm_alarm_from_domain
from server.broadcast import register_client, unregister_client, broadcast_to_house
from model.domain import User, SmartHouse, Room, Lamp, Lock, Blinds, CeilingLight, Alarm


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

def get_device_from_house(house, room_id, device_id):
    room = house.rooms.get(room_id)
    if not room:
        return None
    return room.device_map.get(device_id)
        

def handle_device_action(house, user, session, request_data, client_id=None):
    """
    Generic device action handler that routes to the appropriate method
    based on device type and action.
    """
    room_id = request_data.get("room_id")
    device_id = request_data.get("device_id")
    action = request_data.get("action")
    params = request_data.get("params", {})
    device = get_device_from_house(house, room_id, device_id)
    device_type = type(device).__name__ if device else None
    
    # Authorization check
    if not user.can_control():
        return {"status": "error", "message": "User lacks permission to control devices"}
    
    # Get the device
    device = get_device_from_house(house, room_id, device_id)
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

        # Make broadcast message consistent
        broadcast_message = {
            "type": f"{device_type.lower()}_update",
            "device_id": device_id,
            "room_id": room_id, 
            "action": action,
            "status": device_status
        }
    
        # Pass the client_id to exclude it from broadcast
        broadcast_to_house(house.house_id, broadcast_message, exclude_client_id=client_id)
        logger.info(f"Broadcasted update for device {device_id} to house {house.house_id} (excluding client {client_id})")
        
        return response
        
    except Exception as e:
        logger.error(f"Error executing device action: {str(e)}")
        return {"status": "error", "message": str(e)}

def handle_device_status(request_data, house, user):
    room_id = request_data.get("room_id")
    device_id = request_data.get("device_id")

    device = get_device_from_house(house, room_id, device_id)
    if not device:
        return {"type": "error", "message": "Device not found"}

    return {
        "type": "device_status",
        "device_id": device.device_id,
        "device_type": type(device).__name__,
        "status": device.check_status()
    }

def handle_device_group_status(request_data, house, user):
    """Handle request to check status of all devices of a specific type"""
    device_type = request_data.get("device_type")
    valid_types = ["Lamp", "Lock", "CeilingLight", "Blinds"]
    
    if not device_type or device_type not in valid_types:
        return {"type": "error", "message": f"Invalid device type. Must be one of: {', '.join(valid_types)}"}
    
    devices = {}
    # Collect all devices of the specified type across all rooms
    for room_id, room in house.rooms.items():
        for device_id, device in room.device_map.items():
            if type(device).__name__ == device_type:
                devices[device_id] = {
                    "room_id": room_id,
                    "status": device.check_status()
                }
    
    return {
        "type": "device_group_status",
        "device_type": device_type,
        "devices": devices
    }

def handle_device_group_action(house, user, session, request_data):
    """Handle action on all devices of a specific type"""
    device_type = request_data.get("device_type")
    action = request_data.get("action")
    params = request_data.get("params", {})
    
    valid_types = ["Lamp", "Lock", "CeilingLight", "Blinds"]
    if not device_type or device_type not in valid_types:
        return {"status": "error", "message": f"Invalid device type. Must be one of: {', '.join(valid_types)}"}
    
    # Authorization check
    if not user.can_control():
        return {"status": "error", "message": "User lacks permission to control devices"}
    
    results = {"succeeded": [], "failed": []}
    
    # Execute action on all devices of the specified type
    for room_id, room in house.rooms.items():
        for device_id, device in room.device_map.items():
            if type(device).__name__ == device_type:
                try:
                    execute_device_action(device, action, params)
                    
                    # Update the database for this device
                    mapping = DEVICE_MAPPINGS.get(device_type)
                    if mapping:
                        orm_class = mapping["orm_class"]
                        update_func = mapping["update_func"]
                        
                        device_orm = session.query(orm_class).filter_by(id=device_id).first()
                        if device_orm:
                            update_func(device, device_orm)
                            results["succeeded"].append({
                                "device_id": device_id,
                                "room_id": room_id
                            })
                        else:
                            results["failed"].append({
                                "device_id": device_id,
                                "room_id": room_id,
                                "reason": "Device not found in database"
                            })
                except Exception as e:
                    results["failed"].append({
                        "device_id": device_id,
                        "room_id": room_id,
                        "reason": str(e)
                    })
    
    # Commit all changes at once
    session.commit()
    
    # Broadcast updates
    broadcast_message = {
        "type": f"{device_type.lower()}_group_update",
        "device_type": device_type,
        "action": action,
        "results": results
    }
    broadcast_to_house(house.house_id, broadcast_message)
    
    return {
        "status": "success",
        "device_type": device_type,
        "action": action,
        "results": results
    }

def handle_list_house_devices(house, user):
    """List all devices in the house with minimal info"""
    devices = []
    
    # Add house alarm if present
    if house.alarm:
        devices.append({
            "device_id": house.alarm.device_id,
            "type": "Alarm",
            "room_id": None  # House-level device
        })
    
    # Add all room devices
    for room_id, room in house.rooms.items():
        for device_id, device in room.device_map.items():
            devices.append({
                "device_id": device_id,
                "type": type(device).__name__,
                "room_id": room_id,
                "room_name": room.name
            })
    
    return {
        "type": "device_list",
        "scope": "house",
        "house_id": house.house_id,
        "devices": devices
    }

def handle_list_room_devices(house, user, room_id):
    """List all devices in a specific room with minimal info"""
    room = house.rooms.get(room_id)
    if not room:
        return {"type": "error", "message": f"Room {room_id} not found"}
    
    devices = []
    for device_id, device in room.device_map.items():
        devices.append({
            "device_id": device_id,
            "type": type(device).__name__
        })
    
    return {
        "type": "device_list",
        "scope": "room",
        "house_id": house.house_id,
        "room_id": room_id,
        "room_name": room.name,
        "devices": devices
    }

def handle_list_group_devices(house, user, device_type):
    """List all devices of a specific type across the house"""
    valid_types = ["Lamp", "Lock", "CeilingLight", "Blinds", "Alarm"]
    
    if not device_type or device_type not in valid_types:
        return {"type": "error", "message": f"Invalid device type. Must be one of: {', '.join(valid_types)}"}
    
    devices = []
    
    # Special case for Alarm (house-level device)
    if device_type == "Alarm" and house.alarm:
        devices.append({
            "device_id": house.alarm.device_id,
            "room_id": None,
            "room_name": None
        })
    
    # Add all matching devices from rooms
    for room_id, room in house.rooms.items():
        for device_id, device in room.device_map.items():
            if type(device).__name__ == device_type:
                devices.append({
                    "device_id": device_id,
                    "room_id": room_id,
                    "room_name": room.name
                })
    
    return {
        "type": "device_list",
        "scope": "group",
        "device_type": device_type,
        "house_id": house.house_id,
        "devices": devices
    }

def execute_device_action(device, action, params):
    """
    Execute an action on a device with the given parameters.
    Uses reflection to call methods on the device object.
    """
    # Map action names to method names
    method_map = {
        # Light actions
        "toggle": "flip_switch",
        "on": "turn_on",
        "off": "turn_off",
        "dim": "set_shade",
        "color": "change_color",
        
        # Lock actions
        "lock": "lock",
        "unlock": "unlock",
        
        # Blinds actions
        "toggle": "toggle",  # For blinds position
        "up": "set_up",
        "down": "set_down",
        "shutter": "shutter",
        "open": "set_open",
        "close": "set_close",
        
        # Alarm actions
        "arm": "arm",
        "disarm": "disarm",
        "trigger": "trigger_alarm",
        "stop": "stop_alarm"
    }
    
    method_name = method_map.get(action)
    if not method_name:
        raise ValueError(f"Unknown action: {action}")
    
    # Note: Removed the special handling for on/off since we now have explicit methods
    
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
    """Get the state of a room including all devices using device_map"""
    state = {
        "room_id": room.room_id,
        "name": room.name,
        "devices": {}
    }
    
    # Use device_map to get all devices
    for device_id, device in room.device_map.items():
        state["devices"][device_id] = {
            "type": type(device).__name__,
            "status": device.check_status()
        }
    
    return state


def handle_add_room(data, session, user):
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    house_id = data.get("house_id")
    name = data.get("room_name", None)

    # Find the next room_id for this house
    existing_ids = session.query(RoomORM.room_id).filter_by(house_id=house_id).all()
    used_ids = {rid for (rid,) in existing_ids}
    next_room_id = 1
    while next_room_id in used_ids:
        next_room_id += 1

    new_room = RoomORM(house_id=house_id, room_id=next_room_id, name=name)
    session.add(new_room)
    session.commit()

    return {
        "status": "success",
        "message": f"Room {next_room_id} added",
        "room_id": next_room_id
    }

def add_device_to_room(house, room_id, device_type, attributes=None):
    """
    Add a new device to a room with a unique device ID.
    
    Args:
        house: The SmartHouse domain object
        room_id: The ID of the room to add the device to
        device_type: The type of device to add ("lamp", "lock", etc.)
        attributes: Optional dictionary of device attributes
    
    Returns:
        dict: Status response with device_id if successful
    """
    if attributes is None:
        attributes = {}
    
    room = house.rooms.get(room_id)
    if not room:
        return {"status": "error", "message": f"Room {room_id} not found"}
    
    # Get a unique device ID for the new device
    device_id = house.get_next_device_id()
    
    # Create the appropriate device with the allocated ID
    if device_type.lower() == "lamp":
        device = Lamp(
            device_id=device_id,
            on=attributes.get("on", False),
            shade=attributes.get("shade", 100),
            color=attributes.get("color", "white")
        )
        room.add_lamp(device)
    elif device_type.lower() == "lock":
        code = attributes.get("code", "0000")
        # Convert code to list if it's a string
        if isinstance(code, str):
            code_list = code.split(",") if "," in code else [code]
        else:
            code_list = [str(code)]
        device = Lock(
            device_id=device_id,
            code=code_list,
            is_unlocked=attributes.get("is_unlocked", False)
        )
        room.add_lock(device)
    elif device_type.lower() == "blinds":
        device = Blinds(
            device_id=device_id,
            is_up=attributes.get("is_up", True),
            is_open=attributes.get("is_open", False)
        )
        room.add_blinds(device)
    elif device_type.lower() == "ceiling_light":
        device = CeilingLight(
            device_id=device_id,
            on=attributes.get("on", False),
            shade=attributes.get("shade", 100),
            color=attributes.get("color", "white")
        )
        room.add_ceiling_light(device)
    else:
        return {"status": "error", "message": f"Unknown device type: {device_type}"}
    
    # Update the device cache
    room.build_device_cache()
    
    return {
        "status": "success",
        "message": f"{device_type} added successfully",
        "device_id": device_id
    }


def handle_add_device(data, session, user):
    """Handle adding a new device to a room with unique device ID"""
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    house_id = data["house_id"]
    room_id = data["room_id"]
    device_type = data["device_type"]
    attrs = data.get("attributes", {})

    # Get the house from active houses
    house = active_houses.get(house_id)
    if not house:
        return {"status": "error", "message": "House not found in memory"}
    
    # Get a unique device ID for the new device
    device_id = house.get_next_device_id()
    
    # Get actual Room DB entry using house_id + room_id
    room_orm = session.query(RoomORM).filter_by(house_id=house_id, id=room_id).first()
    if not room_orm:
        return {"status": "error", "message": "Room not found."}

    try:
        # Create the device with the assigned ID
        if device_type.lower() == "lamp":
            dev = LampORM(id=device_id, room_id=room_orm.id, **attrs)
        elif device_type.lower() == "lock":
            dev = LockORM(id=device_id, room_id=room_orm.id, **attrs)
        elif device_type.lower() == "blinds":
            dev = BlindsORM(id=device_id, room_id=room_orm.id, **attrs)
        elif device_type.lower() == "ceiling_light":
            dev = CeilingLightORM(id=device_id, room_id=room_orm.id, **attrs)
        else:
            return {"status": "error", "message": "Invalid device type"}

        session.add(dev)
        session.commit()
        
        # Also update domain model
        domain_room = house.rooms.get(room_id)
        if domain_room:
            if device_type.lower() == "lamp":
                domain_device = Lamp(
                    device_id=device_id,
                    on=attrs.get("on", False),
                    shade=attrs.get("shade", 100),
                    color=attrs.get("color", "white")
                )
                domain_room.add_lamp(domain_device)
            elif device_type.lower() == "lock":
                code = attrs.get("code", "0000")
                domain_device = Lock(
                    device_id=device_id,
                    code=code.split(",") if "," in code else [code],
                    is_unlocked=attrs.get("is_unlocked", False)
                )
                domain_room.add_lock(domain_device)
            elif device_type.lower() == "blinds":
                domain_device = Blinds(
                    device_id=device_id,
                    is_up=attrs.get("is_up", True),
                    is_open=attrs.get("is_open", False)
                )
                domain_room.add_blinds(domain_device)
            elif device_type.lower() == "ceiling_light":
                domain_device = CeilingLight(
                    device_id=device_id,
                    on=attrs.get("on", False),
                    shade=attrs.get("shade", 100),
                    color=attrs.get("color", "white")
                )
                domain_room.add_ceiling_light(domain_device)
                
            # Update device cache
            domain_room.build_device_cache()

        return {
            "status": "success", 
            "message": f"{device_type} added",
            "device_id": device_id
        }
        
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Failed to add device: {str(e)}"}

def handle_remove_device(data, session, user):
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    dtype = data["device_type"]
    dev_id = data["device_id"]

    cls = DEVICE_CLASSES.get(dtype)
    if not cls:
        return {"status": "error", "message": "Invalid device type"}

    dev = session.query(cls).get(dev_id)
    if not dev:
        return {"status": "error", "message": "Device not found"}

    session.delete(dev)
    session.commit()

    return {"status": "success", "message": f"{dtype} removed"}

def handle_remove_room(data, session, user):
    # 1. Authorization check
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied"}

    # 2. Get parameters from the message
    house_id = data["house_id"]
    room_id = data["room_id"]

    # 3. Fetch the room (must match on both house and room_id)
    room = session.query(RoomORM).filter_by(house_id=house_id, room_id=room_id).first()
    if not room:
        return {"status": "error", "message": "Room not found"}

    # 4. Delete the room (cascade will clean up the devices!)
    session.delete(room)
    session.commit()

    return {"status": "success", "message": f"Room {room_id} deleted from house {house_id}"}



def handle_set_alarm_threshold(data, house, user):
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied"}

    threshold = data.get("threshold")
    if not isinstance(threshold, int) or threshold < 1:
        return {"status": "error", "message": "Invalid threshold"}

    if house.alarm:
        house.alarm.threshold = threshold
        return {"status": "success", "message": f"Alarm threshold set to {threshold}"}
    else:
        return {"status": "error", "message": "No alarm in house"}

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