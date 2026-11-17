// Map of Poznań, centred on the old town.
const map = L.map("map").setView([52.4064, 16.9252], 13);

// OpenStreetMap tiles, shown in gray so the colored sensors stand out.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
  className: "gray-tiles",
}).addTo(map);

// One marker per device id, so a refresh can update it in place.
const markers = {};

const COLORS = {
  quiet: "#2e9e44",
  medium: "#f0b400",
  loud: "#d7301f",
  offline: "#9e9e9e",
};

// Color from the latest average: below 55 green, 55-70 yellow, above 70 red.
function levelColor(device) {
  if (!device.online || !device.last_reading) {
    return COLORS.offline;
  }
  const level = device.last_reading.db_avg;
  if (level < 55) {
    return COLORS.quiet;
  }
  if (level <= 70) {
    return COLORS.medium;
  }
  return COLORS.loud;
}

// Names come from the API, so never put them into HTML as they are.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Name, latest reading and when it was measured.
function popupText(device) {
  const reading = device.last_reading;
  let text = `<strong>${escapeHtml(device.name)}</strong><br>`;
  if (!reading) {
    return text + "No readings yet";
  }
  text += `${reading.db_avg} dB (min ${reading.db_min}, max ${reading.db_max})<br>`;
  text += new Date(reading.measured_at).toLocaleString();
  if (!device.online) {
    text += "<br>Offline";
  }
  return text;
}

function showSensor(device) {
  const position = [device.location.lat, device.location.lon];
  let marker = markers[device.id];
  if (!marker) {
    marker = L.circleMarker(position, {
      radius: 10,
      color: "white",
      weight: 2,
      fillOpacity: 0.9,
    }).addTo(map);
    marker.bindTooltip(escapeHtml(device.name));
    marker.bindPopup("");
    markers[device.id] = marker;
  }
  marker.setLatLng(position);
  marker.setStyle({ fillColor: levelColor(device) });
  marker.setPopupContent(popupText(device));
}

async function loadSensors() {
  try {
    const res = await fetch("/api/devices", { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const devices = await res.json();
    for (const device of devices) {
      showSensor(device);
    }
    // Remove markers of devices the backend no longer has.
    const ids = devices.map((device) => String(device.id));
    for (const id of Object.keys(markers)) {
      if (!ids.includes(id)) {
        markers[id].remove();
        delete markers[id];
      }
    }
  } catch {
    // Backend down: keep the last markers, the status line shows the problem.
  }
}

loadSensors();
setInterval(loadSensors, 10000);
