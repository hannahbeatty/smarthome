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
    room = Room(room_id=room_row.id, name=room_row.name)

    for lamp in room_row.lamps:
        room.add_lamp(domain_lamp_from_orm(lamp))
    for lock in room_row.locks:
        room.add_lock(domain_lock_from_orm(lock))

    if room_row.blinds:
        room.add_blinds(domain_blinds_from_orm(room_row.blinds))
    if room_row.ceiling_light:
        room.add_ceiling_light(domain_ceiling_light_from_orm(room_row.ceiling_light))

    return room

def domain_alarm_from_orm(alarm_row):
    alarm = Alarm(code=alarm_row.code)
    alarm.is_armed = alarm_row.is_armed
    alarm.is_alarm = alarm_row.is_alarm
    return alarm

def domain_house_from_orm(house_row):
    house = SmartHouse(house_id=house_row.id, name=house_row.name)

    for room_row in house_row.rooms:
        room = domain_room_from_orm(room_row)
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