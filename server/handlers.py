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
from server.shared_state import state

# Configure logging
logger = logging.getLogger("Handlers")

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

def is_alarm_triggered(house):
    """Check if the house alarm is triggered"""
    return house.alarm and house.alarm.is_alarm and house.alarm.is_armed

def notify_alarm_triggered(house_id):
    """Broadcast an alarm notification to all clients in the house"""
    broadcast_message = {
        "type": "alarm_triggered",
        "house_id": house_id,
        "message": "SECURITY ALERT: House alarm has been triggered! Only administrators can perform actions."
    }
    broadcast_to_house(house_id, broadcast_message)
    logger.warning(f"Alarm triggered in house {house_id}, notification broadcast to all clients")

def get_device_from_house(house, room_id, device_id):
    # Special case for the alarm (house-level device)
    if room_id is None or room_id == "None":
        if house.alarm and str(house.alarm.device_id) == str(device_id):
            return house.alarm
            
    # Normal case for room devices
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
    
    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }

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
        
        # IMPORTANT: Check alarm state again after the action (in case it triggered the alarm)
        if is_alarm_triggered(house) and not user.can_modify_structure():
            # Still perform the action but notify about alarm state
            notify_alarm_triggered(house.house_id)
            
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
    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }

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
    if not user.can_control():
        return {"status": "error", "message": "User lacks permission to control devices"}
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
            result = method(params.get("code", ""))
            # Check if this failed unlock attempt triggered the alarm
            if not result and hasattr(device, '_room'):  # result will be False for failed unlock
                for room_id, room in device._room.items():
                    if hasattr(room, 'house') and room.house and room.house.alarm:
                        if room.house.alarm.is_alarm:
                            from server.handlers import notify_alarm_triggered
                            notify_alarm_triggered(room.house.house_id)
            return result
        else:
            return method(**params)
    else:
        return method()
    
def get_house_state(house):
    """Get the complete state of a house including all rooms and devices"""
    state_data = {
        "house_id": house.house_id,
        "name": house.name,
        "rooms": {}
    }
    
    for room_id, room in house.rooms.items():
        state_data["rooms"][room_id] = get_room_state(room)
    
    if house.alarm:
        state_data["alarm"] = {
            "device_id": house.alarm.device_id,
            "type": "Alarm",
            "status": house.alarm.check_status()
        }
    
    return state_data

def get_room_state(room):
    """Get the state of a room including all devices using device_map"""
    state_data = {
        "room_id": room.room_id,
        "name": room.name,
        "devices": {}
    }
    
    # Use device_map to get all devices
    for device_id, device in room.device_map.items():
        state_data["devices"][device_id] = {
            "type": type(device).__name__,
            "status": device.check_status()
        }
    
    return state_data


def handle_add_room(data, session, user):

    house_id = data.get("house_id")
    name = data.get("room_name", "New Room")  # Default name if none provided
    
    # Update domain model if house is in memory
    house = state.get_house(house_id)

    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }

    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    # Create new room
    new_room = RoomORM(house_id=house_id, name=name)
    session.add(new_room)
    session.flush()  # This generates the primary key (id)

    if house:
        # Create a domain room object with the new room's ID
        from model.domain import Room
        room = Room(room_id=new_room.id, name=name)
        # Add to house
        house.add_room(room)
        room.build_device_cache()
    
    session.commit()

    return {
        "status": "success",
        "message": f"Room '{name}' added",
        "room_id": new_room.id
    }


def handle_add_device(data, session, user):
    """Handle adding a new device to a room with unique device ID"""
    house_id = data.get("house_id")
    room_id = data.get("room_id")
    device_type = data.get("device_type")
    attrs = data.get("attributes", {})
    
    # Get the house from shared state
    house = state.get_house(house_id)
    if not house:
        return {"status": "error", "message": "House not found in memory"}
    
    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }

    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    # Validate device type
    valid_device_types = ["lamp", "lock", "blinds", "ceiling_light"]
    if device_type.lower() not in valid_device_types:
        return {
            "status": "error", 
            "message": f"Invalid device type: '{device_type}'. Valid types are: {', '.join(valid_device_types)}"
        }


    if not house:
        return {"status": "error", "message": "House not found in memory"}
    
    # Get the room
    domain_room = house.rooms.get(room_id)
    if not domain_room:
        return {"status": "error", "message": f"Room {room_id} not found."}
    
    # Get a unique device ID for the new device within this room
    device_id = domain_room.get_next_device_id()
    
    # Get actual Room DB entry using house_id + room_id
    room_orm = session.query(RoomORM).filter_by(house_id=house_id, id=room_id).first()
    if not room_orm:
        return {"status": "error", "message": "Room not found in database."}
    
    # Update the next_device_id in the database for this room
    room_orm.next_device_id = domain_room.next_device_id

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
        
        session.add(dev)
        session.commit()
        
        # Also update domain model
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
    """Remove a device from a room"""
    house_id = data.get("house_id")
    room_id = data.get("room_id")
    device_id = data.get("device_id")
    
    # Get house from shared state
    house = state.get_house(house_id)
    
    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    if not all([house_id, room_id, device_id]):
        return {"status": "error", "message": "Missing required parameters."}

    if not all([house_id, room_id, device_id]):
        return {"status": "error", "message": "Missing required parameters."}

    # Get house from shared state

    if not house:
        return {"status": "error", "message": "House not active in memory."}

    domain_room = house.rooms.get(room_id)

    if not domain_room:
        return {"status": "error", "message": f"Room {room_id} not found."}

    # Check if the device exists in the room
    if device_id not in domain_room.device_map:
        return {"status": "error", "message": f"Device {device_id} not found in room {room_id}."}

    try:
        # Delete device from the database using ID only
        deleted = False
        for orm_class in [LampORM, LockORM, BlindsORM, CeilingLightORM]:
            device = session.query(orm_class).filter_by(id=device_id).first()
            if device:
                session.delete(device)
                deleted = True
                break

        if not deleted:
            return {"status": "error", "message": f"Device {device_id} not found in database."}

        session.commit()

        # Remove from in-memory domain model
        if device_id in domain_room.lamps:
            del domain_room.lamps[device_id]
        elif device_id in domain_room.locks:
            del domain_room.locks[device_id]
        elif domain_room.ceiling_light and domain_room.ceiling_light.device_id == device_id:
            domain_room.ceiling_light = None
        elif domain_room.blinds and domain_room.blinds.device_id == device_id:
            domain_room.blinds = None

        # Rebuild device_map
        domain_room.build_device_cache()

        return {
            "status": "success",
            "message": f"Device {device_id} deleted successfully."
        }

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Failed to delete device: {str(e)}"}

def handle_remove_room(data, session, user):
    house_id = data.get("house_id")
    room_id = data.get("room_id")
    
    # Get house from shared state
    house = state.get_house(house_id)
    
    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }
    if not user.can_modify_structure():
        return {"status": "error", "message": "Permission denied."}

    # Check that the house is loaded in memory
    if not house:
        return {"status": "error", "message": "House not active in memory."}

    # Find room in DB
    room_orm = session.query(RoomORM).filter_by(house_id=house_id, id=room_id).first()
    if not room_orm:
        return {"status": "error", "message": f"Room {room_id} not found in database."}

    try:
        # Delete from database — cascades to devices
        session.delete(room_orm)
        session.commit()

        # Remove from domain model
        room = house.rooms.pop(room_id, None)
        if room:
            pass
            #this was where the device map thing was i removed

        return {
            "status": "success",
            "message": f"Room {room_id} deleted successfully."
        }

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Failed to delete room: {str(e)}"}

def handle_set_alarm_threshold(data, house, user):
    # ALARM CHECK - Only allow actions if alarm is not triggered or user is admin
    if is_alarm_triggered(house) and not user.can_modify_structure():
        return {
            "status": "error", 
            "message": "ALARM TRIGGERED: Only administrators can perform actions until the alarm is deactivated."
        }
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

def load_house_if_needed(house_id, session):
    """
    Load a house from the database if it's not already in memory.
    
    Args:
        house_id: The ID of the house to load
        session: SQLAlchemy session
        
    Returns:
        house: The domain House object
    """
    house = state.get_house(house_id)
    if not house:
        house_row = session.query(House).get(house_id)
        if not house_row:
            raise ValueError(f"House {house_id} not found in database")
            
        house = domain_house_from_orm(house_row)
        state.add_house(house_id, house)
        logger.info(f"Loaded house {house_id} into memory")
    
    return house

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