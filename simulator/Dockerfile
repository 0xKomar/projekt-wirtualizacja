FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Sensors are in Poznań, so the day rhythm follows Polish time.
ENV TZ=Europe/Warsaw

# Device keys go to a volume mounted here.
ENV SIM_STATE_FILE=/data/devices.json

WORKDIR /app
RUN useradd --create-home --uid 10001 app \
    && mkdir /data && chown app /data

COPY noise.py main.py ./
USER app
CMD ["python", "main.py"]
