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
demo/        curl walkthrough of the API
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

## Deploy on a server

The same steps work on a server with Docker:

```sh
git clone https://github.com/0xKomar/projekt-wirtualizacja.git
cd projekt-wirtualizacja
cp .env.example .env    # strong POSTGRES_PASSWORD, FRONTEND_PORT = the public port
docker compose up -d --build
```

- Open only `FRONTEND_PORT` in the firewall. The backend listens on localhost only and the database has no port,
  so everything from outside goes through nginx and `/api/`.
- A device sends its readings to `http://<server>:<FRONTEND_PORT>/api/readings` with its `X-Device-Key`.
- `db`, `backend` and `frontend` come back on their own after a crash or a server reboot.
- Update to the latest version: `git pull`, then `docker compose up -d --build`.
- For demo data add `--profile sim` to the `up` command. The simulator is not restarted on its own.

## API demo

`demo/api.sh` walks through every endpoint with curl: health check, locations and devices
(add, list, change, delete), sending a reading and its history, and the errors for a wrong key (401),
bad data (400), an unknown device (404) and deleting something still in use (409).
Each step prints the command, the HTTP code and the answer.

```sh
demo/api.sh                                   # local stack, http://localhost:8080
demo/api.sh http://<server>:<FRONTEND_PORT>   # deployed app
```

It needs only bash and curl and ends with an error when a code differs from the expected one,
so it also works as a quick check after a deploy. The demo location and device it adds stay in the database
and show up on the map.

## Team

| Name | GitHub |
|---|---|
| Igor Komar | [0xKomar](https://github.com/0xKomar) |
| Michał Jasiński | [DontAskForAnything](https://github.com/DontAskForAnything) |
