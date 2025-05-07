import websocket
import json

HOST = 'localhost'
PORT = 8765

def send_and_print(ws, message):
    ws.send(json.dumps(message))
    response = ws.recv()
    print("[RECEIVED]", response)
    return json.loads(response)

def login(ws):
    while True:
        username = input("Username: ")
        password = input("Password: ")
        message = {"command": "login", "username": username, "password": password}
        response = send_and_print(ws, message)
        if response.get("status") == "success":
            print("Login successful.")
            return response
        print("Login failed. Try again.\n")

def join_house(ws, houses):
    print("\nAvailable Houses:")
    for h in houses:
        print(f"  ID {h['id']}: {h['name']} (Role: {h['role']})")
    while True:
        try:
            house_id = int(input("Enter house ID to join: "))
            response = send_and_print(ws, {"command": "join_house", "house_id": house_id})
            if response.get("status") == "success":
                print(f"Joined house {house_id}\n")
                return house_id
        except ValueError:
            print("Invalid input.")
        print("Failed to join house. Try again.\n")

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
            print(f"[ERROR] Parameter '{p}' is not in the format 'name=value'")
            return None
            
        k, v = p.split('=', 1)
        params[k] = int(v) if v.isdigit() else v
    
    # Check required parameters
    required_params = action_params[action]["required"]
    for param in required_params:
        if param not in params:
            print(f"[ERROR] Action '{action}' requires parameter '{param}'")
            print(f"Example: action {action} <room_id> <device_id> {param}=<value>")
            return None
    
    # Check for unknown parameters
    all_valid_params = required_params + action_params[action]["optional"]
    for param in params:
        if param not in all_valid_params:
            print(f"[WARNING] Parameter '{param}' is not recognized for action '{action}'")
            # Continue anyway, just warn the user
    
    return params


def command_loop(ws, house_id):
    HELP_TEXT = """
SmartHome CLI Client Help
=========================

Available Commands:
------------------

CORE COMMANDS:
  help                         → Display this help message
  house_status                → View full house state
  room_status <room_id>       → View specific room state
  device_status <room_id> <device_id> → View a specific device
  group_status <device_type>  → View status of all devices of a type
  
LISTING COMMANDS:
  list_devices                → List all devices in house (minimal info)
  list_room <room_id>         → List all devices in a room (minimal info)
  list_type <device_type>     → List all devices of a type (minimal info)
  
ACTION COMMANDS:
  action <action> <room_id> <device_id> [<param>=<value>] → Act on device
  group_action <device_type> <action> [<param>=<value>] → Act on all devices of type
  
OTHER COMMANDS:
  raw                         → Send raw JSON
  exit                        → Exit

Device Types:
------------
  Lamp, CeilingLight, Lock, Blinds, Alarm

Available Actions by Device Type:
-------------------------------
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

Examples:
--------
  list_devices
  room_status 1
  device_status 1 2
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
"""
    print("""
Available Commands:
  help                        → Show this help message
  house_status                → View full house state
  room_status <room_id>       → View specific room state
  device_status <room_id> <device_id> → View a specific device
  group_status <device_type>  → View status of all devices of a type
  
  list_devices                → List all devices in house (minimal info)
  list_room <room_id>         → List all devices in a room (minimal info)
  list_type <device_type>     → List all devices of a type (minimal info)
  
  action <action> <room_id> <device_id> [<param>=<value>] → Act on device
  group_action <device_type> <action> [<param>=<value>] → Act on all devices of type
  raw                         → Send raw JSON
  exit                        → Exit

Action Parameters Guide:
  dim: requires level=<0-100>
  color: requires color=<color_name> (valid: red, green, blue, white, yellow, purple, orange)
  unlock: requires code=<unlock_code>
""")
    while True:
        try:
            parts = input("\n> ").strip().split()
            if not parts:
                continue
            cmd = parts[0].lower()

            if cmd == "exit":
                break
            elif cmd == "help":
                print(HELP_TEXT)
            elif cmd == "house_status":
                send_and_print(ws, {"command": "query_house", "house_id": house_id})
            elif cmd == "room_status" and len(parts) == 2:
                try:
                    room_id = int(parts[1])
                    send_and_print(ws, {"command": "query_room", "house_id": house_id, "room_id": room_id})
                except ValueError:
                    print("[ERROR] Room ID must be a number")
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
                    print("[ERROR] Room ID and Device ID must be numbers")
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
                    print("[ERROR] Room ID must be a number")
            elif cmd == "list_type" and len(parts) == 2:
                device_type = parts[1].capitalize()
                send_and_print(ws, {
                    "command": "list_group_devices",
                    "house_id": house_id,
                    "device_type": device_type
                })
            elif cmd == "action" and len(parts) >= 4:
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
                    print("[ERROR] Room ID and Device ID must be numbers")
            elif cmd == "group_action" and len(parts) >= 3:
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
                    print("[ERROR] Invalid input format")
            elif cmd == "raw":
                raw = input("Enter raw JSON: ")
                ws.send(raw)
                print("[RECEIVED]", ws.recv())
            else:
                print("Unknown or malformed command.")
        except Exception as e:
            print("[ERROR]", e)

def main():
    ws = websocket.create_connection(f"ws://{HOST}:{PORT}")
    print("[CLIENT] Connected to server")

    login_response = login(ws)
    house_id = join_house(ws, login_response.get("houses", []))
    command_loop(ws, house_id)
    ws.close()

if __name__ == "__main__":
    main()