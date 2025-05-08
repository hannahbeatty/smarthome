import websocket
import json
import sys

import threading
import queue

HOST = 'localhost'  # Server addy
PORT = 12345


broadcast_queue = queue.Queue()
response_queue = queue.Queue()
last_command_id = 0  # Track command IDs
command_lock = threading.Lock()  # Lock for thread-safe command ID increment

# Terminal colors for better UI
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def message_listener(ws):
    while True:
        try:
            message = ws.recv()
            data = json.loads(message)
            
            # Determine if this is a broadcast or a response
            if "type" in data and data["type"] in ["room_added", "device_added", "room_removed", "device_removed",
                                                  "lamp_update", "ceiling_light_update", "lock_update", 
                                                  "blinds_update", "alarm_triggered",
                                                  "lamp_group_update", "ceiling_light_group_update"]:
                # This is a broadcast notification
                broadcast_queue.put(data)
                handle_broadcast_message(data)
            else:
                # This is a response to a command
                response_queue.put(data)
        except Exception as e:
            print_error(f"Error in message listener: {e}")
            break

def handle_broadcast_message(data):
    msg_type = data.get("type", "unknown")
    print("\n" + "-" * 40)
    print_info(f"BROADCAST NOTIFICATION: {msg_type}")
    
    if msg_type == "room_added":
        print_info(f"New room '{data.get('room_name')}' (ID: {data.get('room_id')}) added to the house")
    elif msg_type == "room_removed":
        print_info(f"Room {data.get('room_id')} has been removed from the house")
    elif msg_type == "device_added":
        print_info(f"New {data.get('device_type')} (ID: {data.get('device_id')}) added to room {data.get('room_id')}")
    elif msg_type == "device_removed":
        print_info(f"Device {data.get('device_id')} removed from room {data.get('room_id')}")
    elif msg_type == "alarm_triggered":
        print_error(f"🚨 ALARM TRIGGERED: {data.get('message', 'Security alert!')}")
    elif "_update" in msg_type:
        device_type = msg_type.split("_")[0].capitalize()
        print_info(f"{device_type} update: Device {data.get('device_id')} in room {data.get('room_id')}")
        if "status" in data:
            print_info(f"New status: {data.get('status')}")
    
    print("-" * 40)
    # Print prompt again to indicate we're ready for input
    print(f"\n{Colors.BOLD}> {Colors.ENDC}", end="", flush=True)

def print_success(message):
    print(f"{Colors.GREEN}[SUCCESS] {message}{Colors.ENDC}")

def print_error(message):
    print(f"{Colors.RED}[ERROR] {message}{Colors.ENDC}")

def print_info(message):
    print(f"{Colors.BLUE}[INFO] {message}{Colors.ENDC}")

def print_warning(message):
    print(f"{Colors.YELLOW}[WARNING] {message}{Colors.ENDC}")

def send_and_print(ws, message):
    # Clear response queue before sending to ensure we get the right response
    while not response_queue.empty():
        response_queue.get()
        
    ws.send(json.dumps(message))
    
    # Wait for response with timeout
    try:
        response = response_queue.get(timeout=5)  # 5 second timeout
        
        try:
            parsed_response = response if isinstance(response, dict) else json.loads(response)
            
            # Handle error responses
            if parsed_response.get("status") == "error":
                print_error(parsed_response.get("message", "Unknown error"))
                return parsed_response
            
            # Handle house state responses
            if parsed_response.get("type") == "house_state":
                print_info(f"House ID: {parsed_response.get('house_id')} - {parsed_response.get('name', 'Unnamed')}")
                
                # Print rooms
                rooms = parsed_response.get("state", {}).get("rooms", {})
                print_info(f"Rooms ({len(rooms)}):")
                for room_id, room_data in rooms.items():
                    print(f"  Room {room_id}: {room_data.get('name')} - {len(room_data.get('devices', {}))} devices")
                
                # Print alarm if present
                if "alarm" in parsed_response.get("state", {}):
                    alarm = parsed_response["state"]["alarm"]
                    is_armed = alarm["status"]["is_armed"]
                    is_triggered = alarm["status"]["is_alarm"]
                    print_info(f"Alarm: {'ARMED' if is_armed else 'Disarmed'}{' [TRIGGERED]' if is_triggered else ''}")
                
                return parsed_response
            
            # Handle room state responses
            elif parsed_response.get("type") == "room_state":
                room_id = parsed_response.get("room_id")
                state = parsed_response.get("state", {})
                
                print_info(f"Room {room_id}: {state.get('name')}")
                
                # Print devices
                devices = state.get("devices", {})
                print_info(f"Devices ({len(devices)}):")
                for device_id, device_data in devices.items():
                    device_type = device_data.get("type", "Unknown")
                    status = device_data.get("status", {})
                    
                    if device_type == "Lamp" or device_type == "CeilingLight":
                        print(f"  {device_type} {device_id}: {'ON' if status.get('on') else 'OFF'}, " +
                              f"Shade: {status.get('shade')}%, Color: {status.get('color')}")
                    elif device_type == "Lock":
                        print(f"  Lock {device_id}: {'UNLOCKED' if status.get('is_unlocked') else 'LOCKED'}")
                    elif device_type == "Blinds":
                        position = 'Up' if status.get('is_up') else 'Down'
                        openness = 'Open' if status.get('is_open') else 'Closed'
                        print(f"  Blinds {device_id}: {position}, {openness}")
                
                return parsed_response
                
            # Handle device status response
            elif parsed_response.get("type") == "device_status":
                device_id = parsed_response.get("device_id")
                device_type = parsed_response.get("device_type")
                status = parsed_response.get("status", {})
                
                print_info(f"Device {device_id} ({device_type}):")
                
                if device_type == "Lamp" or device_type == "CeilingLight":
                    print(f"  Status: {'ON' if status.get('on') else 'OFF'}")
                    print(f"  Brightness: {status.get('shade')}%")
                    print(f"  Color: {status.get('color')}")
                elif device_type == "Lock":
                    print(f"  Status: {'UNLOCKED' if status.get('is_unlocked') else 'LOCKED'}")
                    print(f"  Failed Attempts: {status.get('failed_attempts', 0)}")
                elif device_type == "Blinds":
                    print(f"  Position: {'Up' if status.get('is_up') else 'Down'}")
                    print(f"  State: {'Open' if status.get('is_open') else 'Closed'}")
                elif device_type == "Alarm":
                    print(f"  Armed: {'Yes' if status.get('is_armed') else 'No'}")
                    print(f"  Triggered: {'Yes' if status.get('is_alarm') else 'No'}")
                    print(f"  Threshold: {status.get('threshold')}")
                
                return parsed_response
                
            # Handle device group status
            elif parsed_response.get("type") == "device_group_status":
                device_type = parsed_response.get("device_type")
                devices = parsed_response.get("devices", {})
                
                print_info(f"{device_type} devices ({len(devices)}):")
                
                for device_id, device_data in devices.items():
                    room_id = device_data.get("room_id")
                    status = device_data.get("status", {})
                    
                    if device_type == "Lamp" or device_type == "CeilingLight":
                        print(f"  {device_type} {device_id} (Room {room_id}): " +
                              f"{'ON' if status.get('on') else 'OFF'}, " +
                              f"Shade: {status.get('shade')}%, " + 
                              f"Color: {status.get('color')}")
                    elif device_type == "Lock":
                        print(f"  Lock {device_id} (Room {room_id}): " +
                              f"{'UNLOCKED' if status.get('is_unlocked') else 'LOCKED'}")
                    elif device_type == "Blinds":
                        position = 'Up' if status.get('is_up') else 'Down'
                        openness = 'Open' if status.get('is_open') else 'Closed'
                        print(f"  Blinds {device_id} (Room {room_id}): {position}, {openness}")
                
                return parsed_response
                
            # Handle device list responses
            elif parsed_response.get("type") == "device_list":
                scope = parsed_response.get("scope")
                devices = parsed_response.get("devices", [])
                
                if scope == "house":
                    print_info(f"All devices in house ({len(devices)}):")
                    for device in devices:
                        print(f"  {device.get('type')} {device.get('device_id')} - Room: {device.get('room_id', 'N/A')}")
                
                elif scope == "room":
                    room_id = parsed_response.get("room_id")
                    room_name = parsed_response.get("room_name")
                    print_info(f"Devices in Room {room_id} - {room_name} ({len(devices)}):")
                    for device in devices:
                        print(f"  {device.get('type')} {device.get('device_id')}")
                
                elif scope == "group":
                    device_type = parsed_response.get("device_type")
                    print_info(f"{device_type} devices ({len(devices)}):")
                    for device in devices:
                        print(f"  {device_type} {device.get('device_id')} - Room: {device.get('room_id', 'N/A')}")
                
                return parsed_response
            
            # Handle standard success messages
            elif "status" in parsed_response and parsed_response["status"] == "success":
                # Check if there's a specific message
                if "message" in parsed_response:
                    print_success(parsed_response["message"])
                else:
                    print_success("Command executed successfully")
                    
                # If there's additional state info, show it
                if "device_state" in parsed_response:
                    device_type = parsed_response.get("device_type", "Device")
                    device_id = parsed_response.get("device_id")
                    state = parsed_response["device_state"]
                    
                    print_info(f"{device_type} {device_id} state:")
                    for key, value in state.items():
                        if key != "device_id":  # Skip redundant info
                            print(f"  {key}: {value}")
                
                return parsed_response
            
            # Default case: just print the raw response
            else:
                print(f"[RECEIVED] {response}")
                return parsed_response
            
        except json.JSONDecodeError:
            print(f"[RECEIVED] {response}")
            return {"status": "error", "message": "Invalid response format"}
            
    except queue.Empty:
        print_error("Timeout waiting for server response")
        return {"status": "error", "message": "No response received from server"}
    
def login(ws):
    print_info("Please log in to the Smart Home System")
    while True:
        username = input("Username: ")
        password = input("Password: ")
        message = {"command": "login", "username": username, "password": password}
        response = send_and_print(ws, message)
        if response.get("status") == "success":
            print_success(f"Logged in as {username}")
            return response
        print_error("Login failed. Please try again.\n")

def join_house(ws, houses):
    print_info("\nAvailable Houses:")
    for h in houses:
        print(f"  ID {h['id']}: {h['name']} (Role: {h['role']})")
    while True:
        try:
            house_id = int(input("Enter house ID to join: "))
            response = send_and_print(ws, {"command": "join_house", "house_id": house_id})
            if response.get("status") == "success":
                # Find the house to get the role
                for h in houses:
                    if h['id'] == house_id:
                        role = h['role']
                        print_success(f"Joined house {house_id} with role: {role}")
                        return house_id, role
                return house_id, "unknown"
        except ValueError:
            print_error("Invalid input. Please enter a numeric ID.")
        print_error("Failed to join house. Try again.\n")

def get_action_params(action, params_list):
    """
    Get and validate parameters based on action type
    Returns a dict of validated parameters or None if validation fails
    """
    params = {}
    
    # Define parameter requirements for each action
    action_params = {
        "dim": {"required": ["level"], "optional": []},
        "color": {"required": ["color"], "optional": []},
        "unlock": {"required": ["code"], "optional": []},
        # Other actions don't require parameters
    }
    
    # If action doesn't need parameters, return empty dict
    if action not in action_params:
        return {}
    
    # Parse parameters from input
    for p in params_list:
        if '=' not in p:
            print_error(f"Parameter '{p}' is not in the format 'name=value'")
            return None
            
        k, v = p.split('=', 1)
        params[k] = int(v) if v.isdigit() else v
    
    # Check required parameters
    required_params = action_params[action]["required"]
    for param in required_params:
        if param not in params:
            print_error(f"Action '{action}' requires parameter '{param}'")
            print_info(f"Example: action {action} <room_id> <device_id> {param}=<value>")
            return None
    
    # Check for unknown parameters
    all_valid_params = required_params + action_params[action]["optional"]
    for param in params:
        if param not in all_valid_params:
            print_warning(f"Parameter '{param}' is not recognized for action '{action}'")
            # Continue anyway, just warn the user
    
    return params


def show_menu(role):
    """Show appropriate menu based on user role"""
    
    # Common menu items for all roles
    common_menu = f"""
{Colors.HEADER}SmartHome CLI Client - {role.upper()} ROLE{Colors.ENDC}

{Colors.BOLD}VIEWING COMMANDS (Available to all users):{Colors.ENDC}
  help                        → Show this help message
  house_status                → View full house state
  room_status <room_id>       → View specific room state
  device_status <room_id> <device_id> → View a specific device
  group_status <device_type>  → View status of all devices of a type
  
  list_devices                → List all devices in house (minimal info)
  list_room <room_id>         → List all devices in a room (minimal info)
  list_type <device_type>     → List all devices of a type (minimal info)
"""

    # Control menu items for regular and admin users
    control_menu = f"""
{Colors.BOLD}CONTROL COMMANDS (Regular and Admin only):{Colors.ENDC}
  action <action> <room_id> <device_id> [<param>=<value>] → Act on device
  group_action <device_type> <action> [<param>=<value>] → Act on all devices of type
  alarm <action> [alarm_id] → Control house alarm (arm, disarm, trigger, stop)
"""

    # Admin menu items
    admin_menu = f"""
{Colors.BOLD}ADMIN COMMANDS (Admin only):{Colors.ENDC}
  add_room <name>             → Add a new room to the house
  add_device <room_id> <type> [attr=value ...] → Add a device to a room
  del_room <room_id>          → Delete a room and all its devices
  del_device <room_id> <device_id> → Delete a specific device
"""

    # Other commands for all roles
    other_menu = f"""
{Colors.BOLD}OTHER COMMANDS:{Colors.ENDC}
  raw                         → Send raw JSON
  exit                        → Exit

Type 'help' for more detailed information.
"""

    # Display appropriate menu based on role
    print(common_menu)
    if role in ["regular", "admin"]:
        print(control_menu)
    if role == "admin":
        print(admin_menu)
    print(other_menu)


def get_detailed_help(role):
    """Return detailed help text based on user role"""
    
    # Common help for all roles
    common_help = f"""
{Colors.HEADER}SmartHome CLI Client Help - {role.upper()} ROLE{Colors.ENDC}

{Colors.BOLD}VIEWING COMMANDS (Available to all users):{Colors.ENDC}
  help                         → Display this help message
  house_status                → View full house state
  room_status <room_id>       → View specific room state
  device_status <room_id> <device_id> → View a specific device
  group_status <device_type>  → View status of all devices of a type
  
  list_devices                → List all devices in house (minimal info)
  list_room <room_id>         → List all devices in a room (minimal info)
  list_type <device_type>     → List all devices of a type (minimal info)
"""

    # Control commands for regular and admin
    control_help = f"""
{Colors.BOLD}CONTROL COMMANDS (Regular and Admin only):{Colors.ENDC}
  action <action> <room_id> <device_id> [<param>=<value>] → Act on device
  group_action <device_type> <action> [<param>=<value>] → Act on all devices of type
  alarm <action> [alarm_id] → Control house alarm (arm, disarm, trigger, stop)
                            If alarm_id is omitted, finds the house alarm automatically
"""

    # Admin commands
    admin_help = f"""
{Colors.BOLD}ADMIN COMMANDS (Admin only):{Colors.ENDC}
  add_room <name>               → Add a new room to the house
  add_device <room_id> <type> [attr=value ...] → Add a device to a room
  del_room <room_id>           → Delete a room and all its devices
  del_device <room_id> <device_id> → Delete a specific device
"""

    # Device types and actions
    devices_help = f"""
{Colors.BOLD}Device Types:{Colors.ENDC}
  Lamp, CeilingLight, Lock, Blinds, Alarm

{Colors.BOLD}Available Actions by Device Type:{Colors.ENDC}
  Lamp/CeilingLight:
    - toggle    : Toggle light on/off
    - on        : Turn light on
    - off       : Turn light off
    - dim       : Set brightness (requires level=0-100)
    - color     : Change color (requires color=<color_name>)
                  Valid colors: red, green, blue, white, yellow, purple, orange
  
  Lock:
    - lock      : Lock the door
    - unlock    : Unlock the door (requires code=<unlock_code>)
  
  Blinds:
    - toggle    : Toggle between up and down positions
    - up        : Raise the blinds to up position
    - down      : Lower the blinds to down position
    - shutter   : Toggle between open and closed states
    - open      : Open the blinds
    - close     : Close the blinds
  
  Alarm:
    - arm       : Arm the alarm
    - disarm    : Disarm the alarm
    - trigger   : Trigger the alarm manually
    - stop      : Stop the alarm
"""

    # Device types for adding (admin only)
    admin_devices_help = f"""
{Colors.BOLD}Device Types for Adding:{Colors.ENDC}
  lamp, ceiling_light, lock, blinds

{Colors.BOLD}Device Attributes:{Colors.ENDC}
  lamp/ceiling_light: on=true/false shade=0-100 color=red/blue/etc.
  lock: code=1234,5678 is_unlocked=true/false
  blinds: is_up=true/false is_open=true/false
"""

    # Examples
    examples_help = f"""
{Colors.BOLD}Examples:{Colors.ENDC}
  list_devices
  room_status 1
  device_status 1 2
"""

    # Control examples (for regular and admin)
    control_examples = f"""
  action toggle 1 2
  action on 1 2
  action off 1 2
  action dim 1 2 level=75
  action color 1 2 color=blue
  action unlock 1 4 code=1234
  action up 1 3
  action open 1 3
  group_status Lamp
  group_action Lamp off
  alarm arm        # Arms the house alarm
  alarm disarm     # Disarms the house alarm
  alarm trigger    # Manually triggers the alarm
"""

    # Admin examples
    admin_examples = f"""
  add_room Living Room
  add_device 1 lamp on=true color=white
  add_device 1 ceiling_light shade=80
  add_device 1 lock code=1234,5678,9012
  add_device 1 blinds is_up=true
  del_device 1 3
  del_room 2
"""

    # Build help text based on role
    help_text = common_help
    
    if role in ["regular", "admin"]:
        help_text += control_help
    
    if role == "admin":
        help_text += admin_help
    
    help_text += devices_help
    
    if role == "admin":
        help_text += admin_devices_help
    
    help_text += examples_help
    
    if role in ["regular", "admin"]:
        help_text += control_examples
    
    if role == "admin":
        help_text += admin_examples
    
    return help_text

def command_loop(ws, house_id, role):
    # Show the appropriate menu based on user role
    show_menu(role)
    
    while True:
        try:
            parts = input(f"\n{Colors.BOLD}> {Colors.ENDC}").strip().split()
            if not parts:
                continue
            cmd = parts[0].lower()

            if cmd == "exit":
                break
            elif cmd == "help":
                print(get_detailed_help(role))
            elif cmd == "house_status":
                send_and_print(ws, {"command": "query_house", "house_id": house_id})
            elif cmd == "room_status" and len(parts) == 2:
                try:
                    room_id = int(parts[1])
                    send_and_print(ws, {"command": "query_room", "house_id": house_id, "room_id": room_id})
                except ValueError:
                    print_error("Room ID must be a number")
            elif cmd == "device_status" and len(parts) == 3:
                try:
                    room_id = int(parts[1])
                    device_id = int(parts[2])
                    send_and_print(ws, {
                        "command": "device_status",
                        "house_id": house_id,
                        "room_id": room_id,
                        "device_id": device_id
                    })
                except ValueError:
                    print_error("Room ID and Device ID must be numbers")
            elif cmd == "group_status" and len(parts) == 2:
                device_type = parts[1].capitalize()
                send_and_print(ws, {
                    "command": "device_group_status",
                    "house_id": house_id,
                    "device_type": device_type
                })
            elif cmd == "list_devices":
                send_and_print(ws, {
                    "command": "list_house_devices",
                    "house_id": house_id
                })
            elif cmd == "list_room" and len(parts) == 2:
                try:
                    room_id = int(parts[1])
                    send_and_print(ws, {
                        "command": "list_room_devices",
                        "house_id": house_id,
                        "room_id": room_id
                    })
                except ValueError:
                    print_error("Room ID must be a number")
            elif cmd == "list_type" and len(parts) == 2:
                device_type = parts[1].capitalize()
                send_and_print(ws, {
                    "command": "list_group_devices",
                    "house_id": house_id,
                    "device_type": device_type
                })
            elif cmd == "action" and len(parts) >= 4:
                # Check permission for device control
                if role == "guest":
                    print_error("Permission denied: This action requires 'regular' or 'admin' role")
                    continue
                
                try:
                    action = parts[1]
                    room_id = int(parts[2])
                    device_id = int(parts[3])
                    
                    # Validate and get parameters
                    if len(parts) > 4:
                        params = get_action_params(action, parts[4:])
                        if params is None:
                            # Validation failed, skip sending the command
                            continue
                    else:
                        params = {}
                        
                    action_cmd = {
                        "command": "device_action",
                        "house_id": house_id,
                        "room_id": room_id,
                        "device_id": device_id,
                        "action": action
                    }
                    
                    if params:
                        action_cmd["params"] = params
                        
                    send_and_print(ws, action_cmd)
                except ValueError:
                    print_error("Room ID and Device ID must be numbers")
            elif cmd == "alarm" and len(parts) >= 2:
                # Check permission for device control
                if role == "guest":
                    print_error("Permission denied: This action requires 'regular' or 'admin' role")
                    continue
                
                try:
                    action = parts[1]  # arm, disarm, trigger, or stop
                    
                    # Validate alarm action
                    valid_actions = ["arm", "disarm", "trigger", "stop"]
                    if action not in valid_actions:
                        print_error(f"Invalid alarm action. Use: {', '.join(valid_actions)}")
                        continue
                    
                    # Get alarm device ID - if provided use it, otherwise find it
                    alarm_id = None
                    if len(parts) > 2:
                        try:
                            alarm_id = int(parts[2])
                        except ValueError:
                            print_error("Alarm ID must be a number")
                            continue
                    else:
                        # Send request to get alarm info
                        result = send_and_print(ws, {
                            "command": "list_group_devices",
                            "house_id": house_id,
                            "device_type": "Alarm"
                        })
                        
                        # Extract alarm ID from response
                        if result.get("status") != "error" and "devices" in result:
                            if len(result["devices"]) > 0:
                                alarm_id = result["devices"][0].get("device_id")
                                print_info(f"Using alarm device ID: {alarm_id}")
                            else:
                                print_error("No alarm found in this house")
                                continue
                        else:
                            print_error("Failed to retrieve alarm information")
                            continue
                    
                    # Now create and send the special JSON format for house-level devices
                    action_cmd = {
                        "command": "device_action",
                        "house_id": house_id,
                        "device_id": alarm_id,
                        "action": action
                    }

                    # Convert to string and send
                    raw_json = json.dumps(action_cmd)
                    print_info(f"Sending command: {raw_json}")
                    ws.send(raw_json)

                    # Wait for response with timeout
                    try:
                        response = response_queue.get(timeout=5)
                        parsed_response = response if isinstance(response, dict) else json.loads(response)
                        
                        if parsed_response.get("status") == "success":
                            print_success(f"Alarm {action} command successful")
                            # Display alarm state if available
                            if "device_state" in parsed_response:
                                device_state = parsed_response["device_state"]
                                print_info(f"Alarm state:")
                                for key, value in device_state.items():
                                    if key != "device_id":
                                        print(f"  {key}: {value}")
                        else:
                            print_error(f"Error: {parsed_response.get('message', 'Unknown error')}")
                    except queue.Empty:
                        print_error("Timeout waiting for server response")


                except Exception as e:
                    print_error(f"Error processing alarm command: {str(e)}")
            elif cmd == "group_action" and len(parts) >= 3:
                # Check permission for device control
                if role == "guest":
                    print_error("Permission denied: This action requires 'regular' or 'admin' role")
                    continue
                
                try:
                    device_type = parts[1].capitalize()
                    action = parts[2]
                    
                    # Validate and get parameters
                    if len(parts) > 3:
                        params = get_action_params(action, parts[3:])
                        if params is None:
                            # Validation failed, skip sending the command
                            continue
                    else:
                        params = {}
                        
                    action_cmd = {
                        "command": "device_group_action",
                        "house_id": house_id,
                        "device_type": device_type,
                        "action": action
                    }
                    
                    if params:
                        action_cmd["params"] = params
                        
                    send_and_print(ws, action_cmd)
                except ValueError:
                    print_error("Invalid input format")
            elif cmd == "add_room" and len(parts) >= 2:
                # Check permission for admin actions
                if role != "admin":
                    print_error("Permission denied: This action requires 'admin' role")
                    continue
                
                # Join all parts after the command to form the room name
                room_name = " ".join(parts[1:])
                send_and_print(ws, {
                    "command": "add_room",
                    "room_name": room_name
                })
            elif cmd == "add_device" and len(parts) >= 3:
                # Check permission for admin actions
                if role != "admin":
                    print_error("Permission denied: This action requires 'admin' role")
                    continue
                
                try:
                    room_id = int(parts[1])
                    device_type = parts[2].lower()
                    
                    # Process optional attributes
                    attributes = {}
                    for i in range(3, len(parts)):
                        if '=' in parts[i]:
                            key, value = parts[i].split('=', 1)
                            # Convert values to appropriate types
                            if value.lower() in ('true', 'false'):
                                # Convert to boolean
                                attributes[key] = (value.lower() == 'true')
                            elif value.isdigit():
                                # Convert to integer
                                attributes[key] = int(value)
                            else:
                                # Keep as string
                                attributes[key] = value
                    
                    send_and_print(ws, {
                        "command": "add_device",
                        "room_id": room_id,
                        "device_type": device_type,
                        "attributes": attributes
                    })
                except ValueError:
                    print_error("Room ID must be a number")
            elif cmd == "del_room" and len(parts) == 2:
                # Check permission for admin actions
                if role != "admin":
                    print_error("Permission denied: This action requires 'admin' role")
                    continue
                
                try:
                    room_id = int(parts[1])
                    send_and_print(ws, {
                        "command": "remove_room",
                        "room_id": room_id
                    })
                except ValueError:
                    print_error("Room ID must be a number")
            elif cmd == "del_device" and len(parts) == 3:
                # Check permission for admin actions
                if role != "admin":
                    print_error("Permission denied: This action requires 'admin' role")
                    continue
                
                try:
                    room_id = int(parts[1])
                    device_id = int(parts[2])
                    send_and_print(ws, {
                        "command": "remove_device",
                        "room_id": room_id,
                        "device_id": device_id
                    })
                except ValueError:
                    print_error("Room ID and Device ID must be numbers")
            elif cmd == "del_device" and len(parts) == 3:
                # Check permission for admin actions
                if role != "admin":
                    print_error("Permission denied: This action requires 'admin' role")
                    continue
                
                try:
                    room_id = int(parts[1])
                    device_id = int(parts[2])
                    send_and_print(ws, {
                        "command": "remove_device",
                        "room_id": room_id,
                        "device_id": device_id
                    })
                except ValueError:
                    print_error("Room ID and Device ID must be numbers")
            elif cmd == "raw":
                raw = input("Enter raw JSON: ")
                ws.send(raw)
                response = ws.recv()
                print(f"[RECEIVED] {response}")
            else:
                print_error("Unknown or malformed command. Type 'help' for available commands.")
        except Exception as e:
            print_error(f"An error occurred: {e}")

def main():
    try:
        print_info(f"Connecting to server at {HOST}:{PORT}...")
        ws = websocket.create_connection(f"ws://{HOST}:{PORT}")
        print_success("Connected to server")
        
        # Start message listener thread
        listener = threading.Thread(target=message_listener, args=(ws,), daemon=True)
        listener.start()
        
        # Continue with login and command loop
        login_response = login(ws)
        house_id, role = join_house(ws, login_response.get("houses", []))
        command_loop(ws, house_id, role)
        ws.close()
        print_info("Disconnected from server")
    except ConnectionRefusedError:
        print_error(f"Could not connect to server at {HOST}:{PORT}")
        sys.exit(1)
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()