(function () {
  "use strict";
  const el = document.getElementById("map");
  if (!el || typeof L === "undefined") return;
  const points = JSON.parse(document.getElementById("points").textContent);
  const map = L.map(el).setView([parseFloat(el.dataset.centerLat), parseFloat(el.dataset.centerLon)],
    parseInt(el.dataset.zoom, 10));
  L.tileLayer(el.dataset.tiles, { maxZoom: 19, attribution: el.dataset.attribution }).addTo(map);
  const color = { pothole: "#495057", garbage: "#8a5a00", waterlogging: "#0b5ed7", streetlight: "#6f42c1", other: "#198754" };
  const letter = { pothole: "P", garbage: "G", waterlogging: "W", streetlight: "S", other: "O" };
  const bounds = [];
  points.forEach(function (p) {
    let border = "2px solid #000";
    if (p.provisional) border = "3px dashed #000";
    else if (p.band === "High") border = "4px solid #dc3545";
    else if (p.band === "Medium") border = "3px solid #000";
    const icon = L.divIcon({
      className: "",
      html: '<div style="width:26px;height:26px;border-radius:50%;background:' + (color[p.category] || "#333") +
        ';border:' + border + ';color:#fff;font:700 13px/20px sans-serif;text-align:center">' +
        (letter[p.category] || "?") + "</div>",
      iconSize: [26, 26], iconAnchor: [13, 13]
    });
    const m = L.marker([p.lat, p.lon], { icon: icon, title: p.id + " " + p.category_label, keyboard: true }).addTo(map);
    const div = document.createElement("div");
    const a = document.createElement("a");
    a.href = p.url; a.textContent = p.id;
    div.appendChild(a);
    div.appendChild(document.createElement("br"));
    div.appendChild(document.createTextNode(p.category_label + " · " + p.status + " · priority " +
      p.priority.toFixed(2) + (p.provisional ? " (provisional)" : " (" + p.band + ")") + (p.demo ? " · DEMO" : "")));
    m.bindPopup(div);
    bounds.push([p.lat, p.lon]);
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 17 });
})();
