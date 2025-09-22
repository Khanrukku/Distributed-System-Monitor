# Distributed System Monitor

A real-time distributed system monitoring application built with Flask, Redis, and WebSocket connections.

## Features
- Real-time system metrics monitoring
- Publisher-Subscriber pattern for distributed communication
- Alert system for threshold breaches
- Interactive web dashboard
- Fault tolerance and high availability

## Quick Start
1. Install Redis
2. Clone this repository
3. Install dependencies: `pip install -r requirements.txt`
4. Start Redis server
5. Run: `python app.py`
6. Open: `http://localhost:5000`

## Architecture
- **Publisher**: Collects and publishes system metrics
- **Subscriber**: Receives and processes messages
- **Redis**: Message broker and data storage
- **Flask**: Web framework and API
- **WebSocket**: Real-time frontend updates