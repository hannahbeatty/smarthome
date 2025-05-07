# for holding domain classes, formerly home_model.py

'''
Created on April 25, 2025

@author: hannahbeatty

'''

class User:
    def __init__(self, user_id: int, username: str, role: str = "guest"):
        self.user_id = user_id
        self.username = username
        self.role = role  # 'admin', 'regular', 'guest'

    def can_control(self):
        return self.role in ("admin", "regular")

    def can_modify_structure(self):
        return self.role == "admin"

    def __str__(self):
        return f"User {self.username} with role {self.role}"


class Room:
    def __init__(self, room_id: int, name: str):
        self.room_id = room_id
        self.name = name
        self.house = None  # set by SmartHouse.add_room

        self.ceiling_light = None
        self.blinds = None
        self.lamps = {}
        self.locks = {}

    def set_house(self, house):
        self.house = house

    def add_ceiling_light(self, ceiling_light):
        if self.ceiling_light is not None:
            raise ValueError("Ceiling light already exists.")
        self.ceiling_light = ceiling_light

    def add_blinds(self, blinds):
        if self.blinds is not None:
            raise ValueError("Blinds already exist.")
        self.blinds = blinds

    def add_lamp(self, lamp):
        self.lamps[lamp.device_id] = lamp

    def add_lock(self, lock):
        self.locks[lock.device_id] = lock

    def check_status(self):
        status = {
            "lamps": {id: lamp.check_status() for id, lamp in self.lamps.items()},
            "locks": {id: lock.check_status() for id, lock in self.locks.items()},
        }
        if self.ceiling_light:
            status["ceiling_light"] = self.ceiling_light.check_status()
        if self.blinds:
            status["blinds"] = self.blinds.check_status()
        return status
    
    def __str__(self):
        return f"Room {self.room_id} - {self.name}"
    

class SmartHouse:
    def __init__(self, house_id: int, name: str):
        self.house_id = house_id
        self.name = name
        self.rooms = {}
        self.alarm = None
        self.next_device_id = 1

    def get_next_device_id(self):
        device_id = self.next_device_id
        self.next_device_id += 1
        return device_id

    def add_room(self, room):
        if room.room_id in self.rooms:
            raise ValueError(f"Room ID {room.room_id} already exists.")
        room.set_house(self)
        self.rooms[room.room_id] = room

    def __str__(self):
        return f"SmartHouse {self.house_id} - {self.name}, Rooms: {list(self.rooms.keys())}"


class Alarm:
    def __init__(self, code: int):
        self.code = code
        self.is_armed = False
        self.is_alarm = False
        self.house = None  # set when assigned
        self.failed_attempts_by_lock = {}

    def link_house(self, house):
        self.house = house

    def notify_wrong_code(self, lock_id):
        self.failed_attempts_by_lock[lock_id] = self.failed_attempts_by_lock.get(lock_id, 0) + 1
        if self.failed_attempts_by_lock[lock_id] >= 3:
            self.trigger_alarm()

    def trigger_alarm(self):
        if self.is_armed:
            self.is_alarm = True
            print("[ALARM TRIGGERED] Excessive failed attempts on lock!")

    def disarm(self):
        self.is_armed = False
        self.is_alarm = False
        self.failed_attempts_by_lock.clear()


class Lamp:
    def __init__(self, device_id: int, on: bool = False, shade: int = 100, color: str = "white"):
        """
        Initialize a Lamp.
        :param device_id: Unique identifier for the lamp
        :param on: Whether the lamp is on or off (default: False)
        :param shade: Brightness level (0-100, default: 100)
        :param color: Lamp color (default: white)
        """
        self.device_id = device_id
        self.on = on
        self.shade = max(0, min(100, shade))  # Ensure brightness is within range
        self.color = color.lower()  # Store color in lowercase for consistency

    def flip_switch(self):
        """Toggle the lamp on/off."""
        self.on = not self.on

    def set_shade(self, level: int):
        """Set the brightness of the lamp."""
        if 0 <= level <= 100:
            self.shade = level
        else:
            raise ValueError("Shade level must be between 0 and 100.")

    def change_color(self, new_color: str):
        """Change the color of the lamp."""
        valid_colors = ["red", "green", "blue", "white", "yellow", "purple", "orange"]
        if new_color.lower() in valid_colors:
            self.color = new_color.lower()
        else:
            raise ValueError(f"Invalid color '{new_color}'. Supported colors: {', '.join(valid_colors)}.")

    def check_status(self):
        """Returns the current status of the lamp."""
        return {
            "device_id": self.device_id,
            "on": self.on,
            "shade": self.shade,
            "color": self.color
        }

    def __str__(self):
        """Returns a string representation of the lamp."""
        return f"Lamp {self.device_id}: {'On' if self.on else 'Off'}, Shade: {self.shade}, Color: {self.color}"


class CeilingLight:
    def __init__(self, device_id: int, on: bool = False, shade: int = 100, color: str = "white"):
        """
        Initialize a Ceiling Light.
        :param device_id: Unique identifier for the ceiling light
        :param on: Whether the light is on or off (default: False)
        :param shade: Brightness level (0-100, default: 100)
        :param color: Light color (default: white)
        """
        self.device_id = device_id
        self.on = on
        self.shade = max(0, min(100, shade))  # Ensure brightness is within range
        self.color = color.lower()

    def flip_switch(self):
        """Toggle the ceiling light on/off."""
        self.on = not self.on

    def set_shade(self, level: int):
        """Set the brightness of the ceiling light."""
        if 0 <= level <= 100:
            self.shade = level
        else:
            raise ValueError("Shade level must be between 0 and 100.")

    def change_color(self, new_color: str):
        """Change the color of the ceiling light."""
        valid_colors = ["red", "green", "blue", "white", "yellow", "purple", "orange"]
        if new_color.lower() in valid_colors:
            self.color = new_color.lower()
        else:
            raise ValueError(f"Invalid color '{new_color}'. Supported colors: {', '.join(valid_colors)}.")

    def check_status(self):
        """Returns the current status of the ceiling light."""
        return {
            "device_id": self.device_id,
            "on": self.on,
            "shade": self.shade,
            "color": self.color
        }

    def __str__(self):
        """Returns a string representation of the ceiling light."""
        return f"CeilingLight {self.device_id}: {'On' if self.on else 'Off'}, Shade: {self.shade}, Color: {self.color}"



class Lock:
    def __init__(self, device_id: int, code: list[int], is_unlocked: bool = False):
        """
        Initialize a Lock.
        :param device_id: Unique identifier for the lock
        :param code: Security code required to unlock
        :param is_unlocked: Whether the lock is initially unlocked (default: False)
        """
        self.device_id = device_id
        self._code = code  
        self.is_unlocked = is_unlocked
        self.failed_attempts = 0  # Track incorrect unlock attempts

    def lock(self):
        """Lock the door."""
        self.is_unlocked = False

    def unlock(self, user_code: str) -> bool:
        """
        Attempt to unlock the door.
        :param user_code: Code entered by the user
        :return: True if unlocked successfully, False otherwise
        """
        if user_code in self._code:
            self.is_unlocked = True
            self.failed_attempts = 0  # Reset failed attempts
            return True
        else:
            self.failed_attempts += 1
            return False

    def check_status(self):
        """Returns the current status of the lock."""
        return {
            "device_id": self.device_id,
            "is_unlocked": self.is_unlocked,
            "failed_attempts": self.failed_attempts
        }

    def __str__(self):
        """Returns a string representation of the lock."""
        return f"Lock {self.device_id}: {'Unlocked' if self.is_unlocked else 'Locked'}"

class Blinds:
    def __init__(self, device_id: int, is_up: bool = True, is_open: bool = False):
        """
        Initialize Blinds.
        :param device_id: Unique identifier for the blinds
        :param is_up: Whether the blinds are initially up (default: True)
        """
        self.device_id = device_id
        self.is_up = is_up  # True = Up, False = Down
        self.is_open = is_open # True = open, False = closed

    def toggle(self):
        """Toggle the blinds up/down."""
        self.is_up = not self.is_up

    def shutter(self):
        """Open or close the blinds"""
        self.is_open = not self.is_open


    def check_status(self):
        """Returns the current status of the blinds."""
        return {
            "device_id": self.device_id,
            "is_up": self.is_up,
            "is_open" : self.is_open
        }

    def __str__(self):
        """Returns a string representation of the blinds."""
        return f"Blinds {self.device_id}: {'Up' if self.is_up else 'Down'}"


    