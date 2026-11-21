// Map of Poznań, centred on the old town.
const map = L.map("map", { zoomControl: false }).setView([52.4064, 16.9252], 13);
L.control.zoom({ position: "bottomright" }).addTo(map);

// OpenStreetMap tiles, shown in gray so the colored sensors stand out.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
  className: "gray-tiles",
}).addTo(map);

// One marker per device id, so a refresh can update it in place.
const markers = {};

// Level from the latest average: below 55 quiet, 55-70 medium, above 70 loud.
// The name is also the CSS class that gives the color.
function noiseLevel(device) {
  if (!device.online || !device.last_reading) {
    return "offline";
  }
  const value = device.last_reading.db_avg;
  if (value < 55) {
    return "quiet";
  }
  if (value <= 70) {
    return "medium";
  }
  return "loud";
}

// Rounded value for the marker and the list, "-" without readings.
function shortValue(device) {
  return device.last_reading ? Math.round(device.last_reading.db_avg) : "-";
}

// Names come from the API, so never put them into HTML as they are.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// "12 s ago" or "3 min ago".
function timeAgo(isoTime) {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(isoTime)) / 1000));
  if (seconds < 60) {
    return `${seconds} s ago`;
  }
  return `${Math.round(seconds / 60)} min ago`;
}

// Name, latest reading and when it was measured.
function popupText(device) {
  const reading = device.last_reading;
  let text = `<strong>${escapeHtml(device.name)}</strong>`;
  if (!reading) {
    return text + '<span class="muted">No readings yet</span>';
  }
  text += `<span class="value ${noiseLevel(device)}">${reading.db_avg.toFixed(1)} <small>dB</small></span>`;
  text += `<span class="muted">min ${reading.db_min}, max ${reading.db_max}</span>`;
  text += `<span class="muted">${timeAgo(reading.measured_at)}</span>`;
  if (!device.online) {
    text += '<span class="muted">Offline</span>';
  }
  return text;
}

// Round marker with the value inside, colored by level.
function markerIcon(device) {
  return L.divIcon({
    className: "",
    html: `<div class="pin ${noiseLevel(device)}">${shortValue(device)}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });
}

function showSensor(device) {
  const position = [device.location.lat, device.location.lon];
  let marker = markers[device.id];
  if (!marker) {
    marker = L.marker(position).addTo(map);
    marker.bindTooltip(escapeHtml(device.name));
    marker.bindPopup("", { className: "sensor-popup" });
    markers[device.id] = marker;
  }
  marker.setLatLng(position);
  marker.setIcon(markerIcon(device));
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
    // Backend down: keep the last markers, the status badge shows the problem.
  }
}

loadSensors();
setInterval(loadSensors, 10000);
