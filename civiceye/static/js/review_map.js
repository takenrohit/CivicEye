(function () {
  "use strict";
  const el = document.getElementById("map");
  if (!el || typeof L === "undefined") return;
  const p = [parseFloat(el.dataset.lat), parseFloat(el.dataset.lon)];
  const map = L.map(el).setView(p, 18);
  L.tileLayer(el.dataset.tiles, { maxZoom: 19, attribution: el.dataset.attribution }).addTo(map);
  L.marker(p, { title: "Complaint location" }).addTo(map);
  L.circle(p, { radius: parseFloat(el.dataset.radius), color: "#fd7e14", fill: false, dashArray: "4" }).addTo(map);
})();
