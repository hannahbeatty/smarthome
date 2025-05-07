from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy import UniqueConstraint


Base = declarative_base()

# Association Table for Many-to-Many with roles
class HouseUserRole(Base):
    __tablename__ = 'house_user_roles'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    house_id = Column(Integer, ForeignKey('houses.id'), primary_key=True)
    role = Column(String, nullable=False)  # 'admin', 'regular', 'guest'

    user = relationship("User", back_populates="house_links")
    house = relationship("House", back_populates="user_links")

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    house_links = relationship("HouseUserRole", back_populates="user")

class House(Base):
    __tablename__ = 'houses'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    next_device_id = Column(Integer, default=1)

    rooms = relationship("Room", back_populates="house")
    user_links = relationship("HouseUserRole", back_populates="house")
    alarm = relationship("Alarm", back_populates="house", uselist=False)

class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(Integer, primary_key=True)                 # Global DB ID (for joins)              # Per-house ID
    name = Column(String, nullable=True)                   # Optional display name
    house_id = Column(Integer, ForeignKey("houses.id"))

    __table_args__ = (
        UniqueConstraint("house_id", "id", name="uq_room_in_house"),
    )
    
    house = relationship("House", back_populates="rooms")
    lamps = relationship("Lamp", back_populates="room", cascade="all, delete-orphan")
    locks = relationship("Lock", back_populates="room", cascade="all, delete-orphan")
    ceiling_light = relationship("CeilingLight", back_populates="room", uselist=False, cascade="all, delete-orphan")
    blinds = relationship("Blinds", back_populates="room", uselist=False, cascade="all, delete-orphan")

class Lamp(Base):
    __tablename__ = 'lamps'
    id = Column(Integer, primary_key=True)
    on = Column(Boolean, default=False)
    shade = Column(Integer, default=100)
    color = Column(String, default="white")
    room_id = Column(Integer, ForeignKey('rooms.id', ondelete="CASCADE"))
    room = relationship("Room", back_populates="lamps")

class CeilingLight(Base):
    __tablename__ = 'ceiling_lights'
    id = Column(Integer, primary_key=True)
    on = Column(Boolean, default=False)
    shade = Column(Integer, default=100)
    color = Column(String, default="white")
    room_id = Column(Integer, ForeignKey('rooms.id', ondelete="CASCADE"), unique=True)
    room = relationship("Room", back_populates="ceiling_light")

class Lock(Base):
    __tablename__ = 'locks'
    id = Column(Integer, primary_key=True)
    is_unlocked = Column(Boolean, default=False)
    failed_attempts = Column(Integer, default=0)
    code = Column(String)  # e.g. JSON-encoded list of codes
    room_id = Column(Integer, ForeignKey('rooms.id', ondelete="CASCADE"))
    room = relationship("Room", back_populates="locks")

class Blinds(Base):
    __tablename__ = 'blinds'
    id = Column(Integer, primary_key=True)
    is_up = Column(Boolean, default=True)
    is_open = Column(Boolean, default=False)
    room_id = Column(Integer, ForeignKey('rooms.id', ondelete="CASCADE"), unique=True)
    room = relationship("Room", back_populates="blinds")

class Alarm(Base):
    __tablename__ = 'alarms'
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    is_armed = Column(Boolean, default=False)
    is_alarm = Column(Boolean, default=False)
    house_id = Column(Integer, ForeignKey('houses.id'), unique=True)
    house = relationship("House", back_populates="alarm")
    threshold = Column(Integer, default=3)

# i dont think alarm should cascade delete, but maybe it should
# later i will figure out cascade delete for deleting a house (sudo user does it)