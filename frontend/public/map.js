// Map of Poznań, centred on the old town.
const map = L.map("map").setView([52.4064, 16.9252], 13);

// OpenStreetMap tiles, shown in gray so the colored sensors stand out.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
  className: "gray-tiles",
}).addTo(map);
