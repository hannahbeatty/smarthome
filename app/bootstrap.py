import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.setup import init_db, SessionLocal
from model.db import Base, User, House, Room, Lamp, CeilingLight, Blinds, Lock, Alarm, HouseUserRole

def seed():
    init_db()
    session = SessionLocal()

    try:
        # Create users
        admin = User(username="admin", password_hash="admin123")
        guest = User(username="guest", password_hash="guest123")
        session.add_all([admin, guest])
        session.flush()
        print("[SEED] Users created.")

        # Create a house
        house = House(name="Test House")
        session.add(house)
        session.flush()
        print("[SEED] House created.")

        # Create a room
        room = Room(name="Test Room", house_id=house.id)
        session.add(room)
        session.flush()
        print("[SEED] Room created.")

        # Add devices to room
        # Add devices to room with explicit unique IDs
        lamp = Lamp(id=1, on=False, shade=70, color="blue", room_id=room.id)
        ceiling_light = CeilingLight(id=2, on=True, shade=80, color="warm", room_id=room.id)
        blinds = Blinds(id=3, is_up=True, is_open=False, room_id=room.id)
        lock = Lock(id=4, code="1234,4321,0000,1111,9999", is_unlocked=False, room_id=room.id)

        session.add_all([lamp, ceiling_light, blinds, lock])
        print("[SEED] Devices added.")

        # Add alarm to house (with threshold)
        alarm = Alarm(code=4321, is_armed=True, is_alarm=False, house_id=house.id)
        alarm.threshold = 3
        session.add(alarm)
        print("[SEED] Alarm added.")

        # Assign user roles
        session.add(HouseUserRole(user_id=admin.id, house_id=house.id, role="admin"))
        session.add(HouseUserRole(user_id=guest.id, house_id=house.id, role="guest"))
        print("[SEED] User roles assigned.")

        session.commit()
        print("[SEED] Test house created successfully.")

    except Exception as e:
        session.rollback()
        print(f"[SEED ERROR] {e}")
    finally:
        session.close()

        
if __name__ == "__main__":
    seed()
