# projekt-wirtualizacja

Topic 38: IoT event monitoring. A noise sensor on an ESP32 and a map of Poznań.

Course project for *Virtualization Methods* (Poznań University of Technology, Cybersecurity, 3rd semester, 2026/2027).

## Idea

An ESP32 with a microphone measures the noise level and sends a reading to the backend about every 10 seconds.
The backend stores the readings in a database and detects events: noise above a threshold for too long,
and a sensor going offline or coming back online.
The frontend shows a map of Poznań with sensors coloured by their latest reading, plus reading history and a list of events.
A simulator adds a few virtual sensors around the city, so the map has more than one point
and the demo does not depend on the hardware.

The sensor never records or sends audio. It only sends sound levels in decibels.

## Architecture

```
ESP32 + microphone --.
                     |  HTTP POST /api/readings (JSON)
simulator -----------+
                     v
               +---------+   SQL   +------------+
               | backend | ------> |     db     |
               +---------+         | PostgreSQL |
                     ^             +------------+
                     |  HTTP /api (JSON)
               +----------+
browser -----> | frontend |
               | (nginx)  |
               +----------+
```

Each part runs in its own container, managed with Docker Compose.
The frontend talks only to the backend, and the database is reachable only inside the Compose network.

## Repository layout

```
backend/     REST API (container)
frontend/    web app with the map (container, nginx)
firmware/    ESP32 sensor code
simulator/   virtual sensors for testing and demos
```

## Running

Instructions will be added together with `docker-compose.yml`.
Configuration lives in environment variables: copy `.env.example` to `.env` and fill in the passwords.

## Team

| Name | GitHub |
|---|---|
| Igor Komar | [0xKomar](https://github.com/0xKomar) |
| Michał Jasiński | [DontAskForAnything](https://github.com/DontAskForAnything) |
