import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.setup import init_db, SessionLocal
from model.db import Base, User, House, Room, Lamp, CeilingLight, Blinds, Lock, Alarm, HouseUserRole

def seed():
    """Create a rich demo environment with multiple users, houses, and devices."""
    init_db()
    session = SessionLocal()

    try:
        print("[SEED] Starting database seeding for smart home demo...")
        
        # Create multiple users with different roles
        user1 = User(username="user1", password_hash="password1")
        user2 = User(username="user2", password_hash="password2")
        user3 = User(username="user3", password_hash="password3")
        
        session.add_all([user1, user2, user3])
        session.flush()
        print("[SEED] Created 3 users: user1, user2, and user3")

        # Create multiple houses to demonstrate multi-house capability
        suburban_house = House(name="Suburban Home")
        beach_house = House(name="Beach House")
        apartment = House(name="City Apartment")
        
        session.add_all([suburban_house, beach_house, apartment])
        session.flush()
        print("[SEED] Created 3 houses: Suburban Home, Beach House, and City Apartment")

        # SUBURBAN HOME SETUP
        # ------------------------------
        # Create various rooms for the suburban house
        living_room = Room(name="Living Room", house_id=suburban_house.id, next_device_id=1)
        kitchen = Room(name="Kitchen", house_id=suburban_house.id, next_device_id=1)
        master_bedroom = Room(name="Master Bedroom", house_id=suburban_house.id, next_device_id=1)
        
        session.add_all([living_room, kitchen, master_bedroom])
        session.flush()
        print("[SEED] Created rooms for Suburban Home")

        # Add devices to Living Room
        living_room_lamp1 = Lamp(id=1, room_id=living_room.id, on=False, shade=70, color="warm white")
        living_room_lamp2 = Lamp(id=2, room_id=living_room.id, on=True, shade=50, color="blue")
        living_room_blinds = Blinds(id=3, room_id=living_room.id, is_up=True, is_open=False)
        
        # Add devices to Kitchen
        kitchen_ceiling = CeilingLight(id=1, room_id=kitchen.id, on=True, shade=100, color="white")
        kitchen_lock = Lock(id=2, room_id=kitchen.id, code="1234,5678", is_unlocked=True)
        
        # Add devices to Master Bedroom
        bedroom_lamp = Lamp(id=1, room_id=master_bedroom.id, on=False, shade=30, color="purple")
        bedroom_ceiling = CeilingLight(id=2, room_id=master_bedroom.id, on=False, shade=100, color="warm")
        bedroom_blinds = Blinds(id=3, room_id=master_bedroom.id, is_up=False, is_open=False)
        bedroom_lock = Lock(id=4, room_id=master_bedroom.id, code="9876", is_unlocked=False)
        
        session.add_all([
            living_room_lamp1, living_room_lamp2, living_room_blinds,
            kitchen_ceiling, kitchen_lock,
            bedroom_lamp, bedroom_ceiling, bedroom_blinds, bedroom_lock
        ])
        
        # Update next_device_id for each room
        living_room.next_device_id = 4
        kitchen.next_device_id = 3
        master_bedroom.next_device_id = 5
        
        # Add alarm to suburban house
        suburban_alarm = Alarm(code=1234, is_armed=True, is_alarm=False, house_id=suburban_house.id, threshold=3)
        session.add(suburban_alarm)
        
        print("[SEED] Added devices to Suburban Home")

        # BEACH HOUSE SETUP
        # ------------------------------
        # Create rooms for beach house
        beach_living = Room(name="Living Area", house_id=beach_house.id, next_device_id=1)
        beach_kitchen = Room(name="Kitchen", house_id=beach_house.id, next_device_id=1)
        beach_deck = Room(name="Deck", house_id=beach_house.id, next_device_id=1)
        
        session.add_all([beach_living, beach_kitchen, beach_deck])
        session.flush()
        print("[SEED] Created rooms for Beach House")
        
        # Add devices to Beach House Living Area
        beach_living_ceiling = CeilingLight(id=1, room_id=beach_living.id, on=False, shade=90, color="white")
        beach_living_lamp = Lamp(id=2, room_id=beach_living.id, on=True, shade=60, color="yellow")
        
        # Add devices to Beach House Kitchen
        beach_kitchen_ceiling = CeilingLight(id=1, room_id=beach_kitchen.id, on=False, shade=100, color="white")
        
        # Add devices to Beach House Deck
        beach_deck_lamp1 = Lamp(id=1, room_id=beach_deck.id, on=False, shade=100, color="warm white")
        beach_deck_lamp2 = Lamp(id=2, room_id=beach_deck.id, on=False, shade=100, color="warm white")
        
        session.add_all([
            beach_living_ceiling, beach_living_lamp,
            beach_kitchen_ceiling,
            beach_deck_lamp1, beach_deck_lamp2
        ])
        
        # Update next_device_id for each room
        beach_living.next_device_id = 3
        beach_kitchen.next_device_id = 2
        beach_deck.next_device_id = 3
        
        # Add alarm to beach house (disarmed)
        beach_alarm = Alarm(code=5678, is_armed=False, is_alarm=False, house_id=beach_house.id, threshold=2)
        session.add(beach_alarm)
        
        print("[SEED] Added devices to Beach House")

        # APARTMENT SETUP
        # ------------------------------
        # Create rooms for apartment
        apt_living = Room(name="Living Room", house_id=apartment.id, next_device_id=1)
        apt_bedroom = Room(name="Bedroom", house_id=apartment.id, next_device_id=1)
        
        session.add_all([apt_living, apt_bedroom])
        session.flush()
        print("[SEED] Created rooms for City Apartment")
        
        # Add devices to Apartment Living Room
        apt_living_ceiling = CeilingLight(id=1, room_id=apt_living.id, on=True, shade=75, color="white")
        apt_living_lamp = Lamp(id=2, room_id=apt_living.id, on=False, shade=50, color="red")
        apt_living_blinds = Blinds(id=3, room_id=apt_living.id, is_up=True, is_open=True)
        
        # Add devices to Apartment Bedroom
        apt_bedroom_lamp = Lamp(id=1, room_id=apt_bedroom.id, on=False, shade=30, color="blue")
        apt_bedroom_lock = Lock(id=2, room_id=apt_bedroom.id, code="1111", is_unlocked=True)
        
        session.add_all([
            apt_living_ceiling, apt_living_lamp, apt_living_blinds,
            apt_bedroom_lamp, apt_bedroom_lock
        ])
        
        # Update next_device_id for each room
        apt_living.next_device_id = 4
        apt_bedroom.next_device_id = 3
        
        # Add alarm to apartment
        apt_alarm = Alarm(code=9999, is_armed=False, is_alarm=False, house_id=apartment.id, threshold=3)
        session.add(apt_alarm)
        
        print("[SEED] Added devices to City Apartment")

        # ASSIGN USER ROLES TO DEMONSTRATE DIFFERENT ACCESS LEVELS
        # -------------------------------------------------------
        # User1 has admin access to Suburban House, regular access to Beach House, and guest access to Apartment
        session.add(HouseUserRole(user_id=user1.id, house_id=suburban_house.id, role="admin"))
        session.add(HouseUserRole(user_id=user1.id, house_id=beach_house.id, role="regular"))
        session.add(HouseUserRole(user_id=user1.id, house_id=apartment.id, role="guest"))

        # User2 has admin access to Apartment, regular access to Suburban House, no access to Beach House
        session.add(HouseUserRole(user_id=user2.id, house_id=apartment.id, role="regular"))
        session.add(HouseUserRole(user_id=user2.id, house_id=suburban_house.id, role="regular"))
        # Note: no role for beach house - demonstrating that some users don't have access to all houses

        # User3 has guest access to Beach House and admin access to Apartment (showing mixed privileges)
        session.add(HouseUserRole(user_id=user3.id, house_id=beach_house.id, role="guest"))
        session.add(HouseUserRole(user_id=user3.id, house_id=apartment.id, role="admin"))
        
        print("[SEED] Assigned user roles to houses")

        session.commit()
        print("[SEED] Database seeding completed successfully!")
        print("\n[DEMO] Ready for multi-user, multi-house demonstration")
        print("[DEMO] Login credentials:")
        print("       user1/password1 - admin (Suburban), regular (Beach), guest (Apartment)")
        print("       user2/password2 - admin (Apartment), regular (Suburban), no access to Beach House")
        print("       user3/password3 - admin (Apartment), guest (Beach House), no access to Suburban")

    except Exception as e:
        session.rollback()
        print(f"[SEED ERROR] {e}")
        raise
    finally:
        session.close()
        
if __name__ == "__main__":
    seed()
