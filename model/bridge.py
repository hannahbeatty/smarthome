# act as a bridge between the model and the ORM

from model.domain import User, SmartHouse, Room, Lamp, Lock, Blinds, CeilingLight, Alarm
from model.db import User as UserORM, House as HouseORM, Room as RoomORM, Lamp as LampORM, Lock as LockORM
from model.db import Blinds as BlindsORM, CeilingLight as CeilingLightORM, Alarm as AlarmORM


# Translate ORM user + role into domain user
def domain_user_from_orm(user_row, role):
    return User(user_id=user_row.id, username=user_row.username, role=role)

# Translate ORM lamp into domain lamp
def domain_lamp_from_orm(lamp_row):
    return Lamp(
        device_id=lamp_row.id,
        on=lamp_row.on,
        shade=lamp_row.shade,
        color=lamp_row.color
    )

def domain_lock_from_orm(lock_row):
    return Lock(
        device_id=lock_row.id,
        code=lock_row.code.split(","),  # assume comma-separated list
        is_unlocked=lock_row.is_unlocked
    )

def domain_blinds_from_orm(blinds_row):
    return Blinds(
        device_id=blinds_row.id,
        is_up=blinds_row.is_up,
        is_open=blinds_row.is_open
    )

def domain_ceiling_light_from_orm(cl_row):
    return CeilingLight(
        device_id=cl_row.id,
        on=cl_row.on,
        shade=cl_row.shade,
        color=cl_row.color
    )

def domain_room_from_orm(room_row):
    print(f"Creating domain room: id={room_row.id}, name={room_row.name}")
    room = Room(room_id=room_row.id, name=room_row.name)

    # Set the next_device_id from the database
    if hasattr(room_row, 'next_device_id'):
        room.next_device_id = room_row.next_device_id
    else:
        # If not in database, calculate the next ID by finding the highest device ID + 1
        max_id = 0
        for device_collection in [room_row.lamps, room_row.locks]:
            for device in device_collection:
                max_id = max(max_id, device.id)
        if room_row.ceiling_light:
            max_id = max(max_id, room_row.ceiling_light.id)
        if room_row.blinds:
            max_id = max(max_id, room_row.blinds.id)
        room.next_device_id = max_id + 1

    print(f"Room {room_row.id} has {len(room_row.lamps)} lamps, {len(room_row.locks)} locks, "
          f"ceiling_light={room_row.ceiling_light is not None}, "
          f"blinds={room_row.blinds is not None}")

    for lamp in room_row.lamps:
        print(f"  Adding lamp {lamp.id}: on={lamp.on}, shade={lamp.shade}, color={lamp.color}")
        room.add_lamp(domain_lamp_from_orm(lamp))
    
    for lock in room_row.locks:
        print(f"  Adding lock {lock.id}: is_unlocked={lock.is_unlocked}, code={lock.code}")
        room.add_lock(domain_lock_from_orm(lock))
    
    if room_row.blinds:
        print(f"  Adding blinds {room_row.blinds.id}: is_up={room_row.blinds.is_up}")
        room.add_blinds(domain_blinds_from_orm(room_row.blinds))
    
    if room_row.ceiling_light:
        print(f"  Adding ceiling_light {room_row.ceiling_light.id}: on={room_row.ceiling_light.on}")
        room.add_ceiling_light(domain_ceiling_light_from_orm(room_row.ceiling_light))

    print("  Building device cache...")
    room.build_device_cache()
    print(f"  Device cache built with {len(room.device_map)} devices")
    for device_id, device in room.device_map.items():
        print(f"    Device {device_id}: type={type(device).__name__}")
    
    return room


def domain_alarm_from_orm(alarm_row):
    alarm = Alarm(code=alarm_row.code, threshold=alarm_row.threshold if hasattr(alarm_row, "threshold") else 3)
    alarm.is_armed = alarm_row.is_armed
    alarm.is_alarm = alarm_row.is_alarm
    alarm.device_id = alarm_row.id  
    return alarm


def domain_house_from_orm(house_row):
    house = SmartHouse(house_id=house_row.id, name=house_row.name)
    
    # Set the next_device_id from the database
    if hasattr(house_row, 'next_device_id'):
        house.next_device_id = house_row.next_device_id
    else:
        # If not in database, calculate the next ID by finding the highest device ID + 1
        max_id = 0
        for room_row in house_row.rooms:
            for device_collection in [room_row.lamps, room_row.locks]:
                for device in device_collection:
                    max_id = max(max_id, device.id)
            if room_row.ceiling_light:
                max_id = max(max_id, room_row.ceiling_light.id)
            if room_row.blinds:
                max_id = max(max_id, room_row.blinds.id)
        house.next_device_id = max_id + 1

    for room_row in house_row.rooms:
        room = domain_room_from_orm(room_row)
        room.build_device_cache()  # ✅ This populates room.device_map
        house.add_room(room)

    if house_row.alarm:
        alarm = domain_alarm_from_orm(house_row.alarm)
        house.alarm = alarm
        alarm.link_house(house)

    return house

# === Reverse Bridges ===

def update_orm_lamp_from_domain(lamp_domain: Lamp, lamp_orm: LampORM):
    lamp_orm.on = lamp_domain.on
    lamp_orm.shade = lamp_domain.shade
    lamp_orm.color = lamp_domain.color

def update_orm_lock_from_domain(lock_domain: Lock, lock_orm: LockORM):
    lock_orm.is_unlocked = lock_domain.is_unlocked
    lock_orm.failed_attempts = lock_domain.failed_attempts
    lock_orm.code = ",".join(lock_domain._code)  # re-encode list as CSV string

def update_orm_blinds_from_domain(blinds_domain: Blinds, blinds_orm: BlindsORM):
    blinds_orm.is_up = blinds_domain.is_up
    blinds_orm.is_open = blinds_domain.is_open

def update_orm_ceiling_light_from_domain(cl_domain: CeilingLight, cl_orm: CeilingLightORM):
    cl_orm.on = cl_domain.on
    cl_orm.shade = cl_domain.shade
    cl_orm.color = cl_domain.color

def update_orm_alarm_from_domain(alarm_domain: Alarm, alarm_orm: AlarmORM):
    alarm_orm.is_armed = alarm_domain.is_armed
    alarm_orm.is_alarm = alarm_domain.is_alarm