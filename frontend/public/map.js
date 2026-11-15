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

// Names come from the API, so never put them into HTML as they are.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function showSensor(device) {
  const position = [device.location.lat, device.location.lon];
  let marker = markers[device.id];
  if (!marker) {
    marker = L.circleMarker(position, {
      radius: 10,
      color: "white",
      weight: 2,
      fillColor: "#3388ff",
      fillOpacity: 0.9,
    }).addTo(map);
    marker.bindTooltip(escapeHtml(device.name));
    markers[device.id] = marker;
  }
  marker.setLatLng(position);
}

async function loadSensors() {
  try {
    const res = await fetch("/api/devices", { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const devices = await res.json();
    for (const device of devices) {
      showSensor(device);
    }
  } catch {
    // Backend down: keep the last markers, the status line shows the problem.
  }
}

loadSensors();
