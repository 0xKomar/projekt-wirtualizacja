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

## How to run

You need Docker with Docker Compose.

```sh
git clone https://github.com/0xKomar/projekt-wirtualizacja.git
cd projekt-wirtualizacja
cp .env.example .env    # then set POSTGRES_PASSWORD
docker compose up --build
```

Compose starts three containers: `db`, `backend` and `frontend`. The backend waits until the database is healthy.

- Web page: http://localhost:8080
- Backend health check: http://localhost:8000/api/health (published on localhost only)
- The database has no port on the host, only the backend can reach it.

To add the virtual sensors, start with the `sim` profile:

```sh
docker compose --profile sim up --build
```

Six sensors around Poznań then send a reading every 10 seconds (`SIM_INTERVAL` in `.env`).

Configuration lives in `.env`, which git ignores, so passwords never reach the repository.
If port 8080 is already in use, change `FRONTEND_PORT` in `.env`.
If you change `BACKEND_PORT`, change the port in `BACKEND_URL` too.

Stop everything with `docker compose down`. The database stays in the `postgres_data` volume.
`docker compose down -v` deletes it, which is also needed after changing the database password.

More details: [backend/README.md](backend/README.md), [frontend/README.md](frontend/README.md),
[simulator/README.md](simulator/README.md).

## Team

| Name | GitHub |
|---|---|
| Igor Komar | [0xKomar](https://github.com/0xKomar) |
| Michał Jasiński | [DontAskForAnything](https://github.com/DontAskForAnything) |
