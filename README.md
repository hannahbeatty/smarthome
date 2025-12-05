# Smart Home Management System

A comprehensive multi-user, multi-house IoT platform for home automation with role-based access control and real-time synchronization.

## Overview

This Smart Home Management System is a three-tier application that allows multiple users to control various devices across multiple houses based on their assigned permissions. The system features real-time synchronization, security integration, and persistent storage.

## Features

### Multi-User Support
Multiple users can connect simultaneously with isolated sessions.

### Multi-House Management
Control multiple homes from a single system.

### Role-Based Access Control
Three permission levels: admin, regular, guest.

### Device Management
Add, control, and remove smart devices.

### Room Management
Add and remove rooms with cascading device deletion.

### Security Integration
Lock and alarm system with automatic threat response.

### Real-Time Updates
WebSocket-based broadcasting of state changes.

### Persistent Storage
SQLite database with SQLAlchemy ORM.

---

## Architecture

The system uses a three-tier architecture:

### Client Tier
Command-line interface using WebSocket communication.

### Server Tier
Multi-threaded WebSocket server with business logic.

### Data Tier
SQLAlchemy ORM with SQLite backend.

---

## Device Types

### Lamps
On/off toggle, brightness adjustment, color change.

### Ceiling Lights
Same as lamps but unique per room.

### Locks
Lock/unlock with code validation and failed attempt tracking.

### Blinds
Position control (up/down) and shutter control (open/close).

### Alarm
House-level security system with arm/disarm and automatic triggering.

---

## Installation

### Prerequisites
- Python 3.8+
- websocket-client
- SQLAlchemy

### Setup

Clone the repository:

\`\`\`bash
git clone https://github.com/yourusername/smart-home-system.git
cd smart-home-system
\`\`\`

Install dependencies:

\`\`\`bash
pip install -r requirements.txt
\`\`\`

Initialize the database:

\`\`\`bash
python -m db.setup
\`\`\`

Seed the database with demo data:

\`\`\`bash
python bootstrap.py
\`\`\`

---

## Usage

### Starting the Server

\`\`\`bash
python main.py
\`\`\`

### Starting Client(s)

\`\`\`bash
python cli_client.py
\`\`\`

You can start multiple client instances to simulate multiple users.

---

## Login Credentials

### user1/password1
- Admin: Suburban Home  
- Regular: Beach House  
- Guest: Apartment  

### user2/password2
- Regular: Apartment, Suburban Home  
- No access: Beach House  

### user3/password3
- Admin: Apartment  
- Guest: Beach House  
- No access: Suburban Home  

---

## Client Commands

### Authentication
- \`login\`
- \`logout\`
- \`join_house <house_id>\`

### Viewing Commands (all roles)
- \`help\`
- \`house_status\`
- \`room_status <room_id>\`
- \`device_status <room_id> <device_id>\`
- \`group_status <device_type>\`
- \`list_devices\`
- \`list_room <room_id>\`
- \`list_type <device_type>\`

### Control Commands (regular + admin)
- \`action <action> <room_id> <device_id> [param=value]\`
- \`group_action <device_type> <action> [param=value]\`
- \`alarm <action>\` (arm, disarm, trigger, stop)

### Admin Commands
- \`add_room <name>\`
- \`add_device <room_id> <type> [attr=value]\`
- \`del_room <room_id>\`
- \`del_device <room_id> <device_id>\`

---

## Architecture Details

### Threading Model
- Each client connection operates in its own thread.
- Thread-safe mechanisms protect shared resources.
- Broadcast messages are routed to appropriate clients.

### Database Schema
- Users have many-to-many relationships with houses through roles.
- Houses contain multiple rooms.
- Rooms contain multiple devices.
- Device types have specialized tables.

### Security Model
- Role-based access control.
- Lock–alarm integration for monitoring.
- Failed attempt thresholds trigger alarms.
- Alarm restricts operations during active alerts.

---

## Project Structure

\`\`\`
smart-home-system/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── config.py
├── client/
│   ├── cli_client.py
│   └── utils.py
├── db/
│   ├── setup.py
│   └── models/
├── model/
│   ├── domain.py
│   ├── db.py
│   └── bridge.py
├── server/
│   ├── full_server.py
│   ├── handlers.py
│   ├── broadcast.py
│   └── shared_state.py
├── bootstrap.py
└── README.md
\`\`\`

---

## Implementation Notes

- Bridge pattern used to translate between ORM entities and domain objects.
- Device IDs are unique within each room via a next_device_id counter.
- WebSockets provide real-time updates across connected clients.
- Alarm integrates failed unlock tracking with automatic triggering.
- Thread-safe locks ensure consistent shared state.

---

## Troubleshooting

### Server won't start
Check if the port is already in use.

### Client connection error
Ensure the server is running.

### Database errors
Reinitialize the database:

\`\`\`bash
python bootstrap.py
\`\`\`

### Permission errors
Verify your user role supports the requested action.

---

## Acknowledgments
- Dr. Nigel John for project guidance  
- ECE470 Spring 2025 class for feedback and suggestions
