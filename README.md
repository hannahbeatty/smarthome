Smart Home Management System
A comprehensive multi-user, multi-house IoT platform for home automation with role-based access control and real-time synchronization.
Overview
This Smart Home Management System is a three-tier application that allows multiple users to control various devices across multiple houses based on their assigned permissions. The system features real-time synchronization, security integration, and persistent storage.
Features

Multi-User Support: Multiple users can connect simultaneously with isolated sessions
Multi-House Management: Control multiple homes from a single system
Role-Based Access Control: Three permission levels (admin, regular, guest)
Device Management: Add, control, and remove smart devices
Room Management: Add and remove rooms with cascading device management
Security Integration: Lock and alarm system with automatic threat response
Real-Time Updates: WebSocket-based broadcasting of state changes
Persistent Storage: SQLite database with SQLAlchemy ORM

Architecture
The system is built on a three-tier architecture:

Client Tier: Command-line interface with WebSocket communication
Server Tier: Multi-threaded WebSocket server with business logic
Data Tier: SQLAlchemy ORM with SQLite backend

Device Types
The system supports the following device types:

Lamps: On/off toggle, brightness adjustment, color change
Ceiling Lights: Same capabilities as lamps but with room-level uniqueness
Locks: Lock/unlock with code validation and failed attempt tracking
Blinds: Position control (up/down) and shutter control (open/close)
Alarm: House-level security system with arm/disarm and automatic triggering

Installation
Prerequisites

Python 3.8+
Required packages: websocket-client, SQLAlchemy

Setup

Clone the repository:
git clone https://github.com/yourusername/smart-home-system.git
cd smart-home-system

Install dependencies:
pip install -r requirements.txt

Initialize the database:
python -m db.setup

Seed the database with demo data:
python bootstrap.py


Usage
Starting the Server
python main.py
Starting Client(s)
In a separate terminal:
python cli_client.py
You can start multiple client instances in different terminals to simulate multiple users.
Login Credentials
The system is seeded with three demo users with different permissions:

user1/password1: Admin access to Suburban Home, regular access to Beach House, guest access to Apartment
user2/password2: Regular access to Apartment and Suburban Home, no access to Beach House
user3/password3: Admin access to Apartment, guest access to Beach House, no access to Suburban Home

Client Commands
Authentication

login: Log in with username and password
logout: Log out of the current session
join_house <house_id>: Join a specific house

Viewing Commands (Available to all roles)

help: Display help message
house_status: View full house state
room_status <room_id>: View specific room state
device_status <room_id> <device_id>: View a specific device
group_status <device_type>: View status of all devices of a type
list_devices: List all devices in house
list_room <room_id>: List all devices in a room
list_type <device_type>: List all devices of a type

Control Commands (Regular and Admin only)

action <action> <room_id> <device_id> [param=value]: Act on device
group_action <device_type> <action> [param=value]: Act on all devices of type
alarm <action>: Control house alarm (arm, disarm, trigger, stop)

Admin Commands (Admin only)

add_room <name>: Add a new room to the house
add_device <room_id> <type> [attr=value]: Add a device to a room
del_room <room_id>: Delete a room and all its devices
del_device <room_id> <device_id>: Delete a specific device

Architecture Details
Threading Model
The system uses a threaded architecture for concurrency:

Each client connection operates in its own thread
Thread-safe mechanisms protect shared resources
Broadcast messages are routed to appropriate clients

Database Schema
The database implements the following entity relationships:

Users have many-to-many relationships with houses through roles
Houses contain multiple rooms
Rooms contain multiple devices
Different device types have specialized tables

Security Model
The security model implements:

Role-based access control (admin, regular, guest)
Lock-alarm integration for security monitoring
Failed attempt counting and threshold-based alarm triggering
Automatic restriction of operations during alarm conditions

Project Structure
smart-home-system/
├── app/                      # Application code
│   ├── __init__.py
│   ├── main.py               # Main application entry point
│   └── config.py             # Application configuration
├── client/                   # Client implementation
│   ├── cli_client.py         # Command-line client interface
│   └── utils.py              # Client utilities
├── db/                       # Database layer
│   ├── setup.py              # Database initialization
│   └── models/               # Database models
├── model/                    # Domain models
│   ├── domain.py             # Domain entities
│   ├── db.py                 # ORM models
│   └── bridge.py             # ORM-domain bridge
├── server/                   # Server implementation
│   ├── full_server.py        # WebSocket server
│   ├── handlers.py           # Request handlers
│   ├── broadcast.py          # Broadcast management
│   └── shared_state.py       # Shared state manager
├── bootstrap.py              # Demo data initialization
└── README.md                 # This file
Implementation Notes

The system uses a bridge pattern to translate between ORM entities and domain objects
Device IDs are unique within each room using a next_device_id counter
WebSockets provide real-time updates across all connected clients
The alarm system maintains a configurable threshold for failed unlock attempts
Thread-safe locks prevent race conditions in the shared state

Troubleshooting

Server won't start: Check if the port is already in use
Client connection error: Ensure the server is running
Database errors: Try reinitializing the database with python bootstrap.py
Permission errors: Verify you have the correct role for the requested operation


Acknowledgments

Dr. Nigel John for project guidance
ECE470 Spring 2025 class for feedback and suggestions