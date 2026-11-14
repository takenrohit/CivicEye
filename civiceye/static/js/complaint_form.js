(function () {
  "use strict";
  const form = document.getElementById("complaint-form");
  if (!form) return;
  const csrf = form.querySelector("input[name=csrf_token]").value;
  const latEl = document.getElementById("latitude");
  const lonEl = document.getElementById("longitude");
  const srcEl = document.getElementById("location_source");
  const geoStatus = document.getElementById("geo-status");
  const nearbyEl = document.getElementById("nearby");
  const catEl = document.getElementById("category");
  const descEl = document.getElementById("description");
  const suggEl = document.getElementById("text-suggestion");
  const obsEl = document.getElementById("observed_at");

  // Default observation time = now (local)
  if (!obsEl.value) {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    obsEl.value = d.toISOString().slice(0, 16);
  }

  // ---- Map ----
  const mapEl = document.getElementById("map");
  const center = [parseFloat(mapEl.dataset.centerLat), parseFloat(mapEl.dataset.centerLon)];
  const map = L.map(mapEl).setView(center, parseInt(mapEl.dataset.zoom, 10));
  L.tileLayer(mapEl.dataset.tiles, { maxZoom: 19, attribution: mapEl.dataset.attribution }).addTo(map);
  let marker = null;

  function setPoint(lat, lon, source, pan) {
    lat = Math.round(lat * 1e6) / 1e6;
    lon = Math.round(lon * 1e6) / 1e6;
    latEl.value = lat;
    lonEl.value = lon;
    srcEl.value = source;
    if (!marker) {
      marker = L.marker([lat, lon], { draggable: true, keyboard: true, title: "Issue location" }).addTo(map);
      marker.on("dragend", function () {
        const p = marker.getLatLng();
        setPoint(p.lat, p.lng, "manual", false);
      });
    } else {
      marker.setLatLng([lat, lon]);
    }
    if (pan) map.setView([lat, lon], Math.max(map.getZoom(), 17));
    checkNearby();
  }

  map.on("click", function (e) { setPoint(e.latlng.lat, e.latlng.lng, "manual", false); });

  function fromInputs() {
    const lat = parseFloat(latEl.value), lon = parseFloat(lonEl.value);
    if (isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) setPoint(lat, lon, "manual", true);
  }
  latEl.addEventListener("change", fromInputs);
  lonEl.addEventListener("change", fromInputs);
  if (latEl.value && lonEl.value) fromInputs();

  document.getElementById("use-location").addEventListener("click", function () {
    if (!("geolocation" in navigator)) {
      geoStatus.textContent = "Location is not available in this browser. Please click the map instead.";
      return;
    }
    geoStatus.textContent = "Requesting your location…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      setPoint(pos.coords.latitude, pos.coords.longitude, "geolocation", true);
      const acc = Math.round(pos.coords.accuracy);
      geoStatus.textContent = "Location set (accuracy about " + acc + " m)." +
        (acc > 50 ? " This is not very precise: drag the pin to the exact spot." : " Drag the pin if it is wrong.");
    }, function (err) {
      geoStatus.textContent = (err.code === 1 ? "Location permission denied." : "Could not get your location.") +
        " Please click the map to set the location.";
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });

  // ---- Nearby reports (no personal data returned) ----
  let nearbyTimer = null;
  function checkNearby() {
    clearTimeout(nearbyTimer);
    nearbyTimer = setTimeout(function () {
      if (!latEl.value || !lonEl.value) return;
      const u = new URL(form.dataset.nearbyUrl, window.location.origin);
      u.searchParams.set("lat", latEl.value);
      u.searchParams.set("lon", lonEl.value);
      if (catEl.value) u.searchParams.set("category", catEl.value);
      fetch(u, { credentials: "same-origin" }).then(r => r.json()).then(function (data) {
        nearbyEl.replaceChildren();
        if (!data.results || data.results.length === 0) {
          nearbyEl.textContent = "No reports found within " + data.radius_m + " m in the last " + data.window_days + " days.";
          return;
        }
        const ul = document.createElement("ul");
        ul.className = "mb-0";
        data.results.forEach(function (r) {
          const li = document.createElement("li");
          li.textContent = r.category + ", about " + r.distance_m + " m away, status: " + r.status +
            (r.same_category ? "" : " (different category)");
          ul.appendChild(li);
        });
        nearbyEl.appendChild(ul);
      }).catch(function () { nearbyEl.textContent = "Could not check nearby reports."; });
    }, 300);
  }
  catEl.addEventListener("change", checkNearby);

  // ---- Text suggestion (keyword rule) ----
  const counter = document.getElementById("desc-count");
  let suggTimer = null;
  descEl.addEventListener("input", function () {
    counter.textContent = descEl.value.length + " characters.";
    clearTimeout(suggTimer);
    suggTimer = setTimeout(function () {
      if (descEl.value.trim().length < 5) return;
      fetch(form.dataset.suggestUrl, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ text: descEl.value })
      }).then(r => r.json()).then(function (s) {
        suggEl.replaceChildren();
        if (!s.category) {
          suggEl.textContent = "No clear suggestion. Please choose manually.";
          return;
        }
        const span = document.createElement("span");
        span.textContent = s.category_label + " (keyword score " + s.score + ", matched: " + s.matched.join(", ") + ") ";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-sm btn-outline-secondary py-0";
        btn.textContent = "Use this";
        btn.addEventListener("click", function () { catEl.value = s.category; checkNearby(); catEl.focus(); });
        suggEl.append(span, btn);
      }).catch(function () { suggEl.textContent = "Suggestion unavailable."; });
    }, 400);
  });

  // ---- Image preview ----
  const imgEl = document.getElementById("image");
  const prev = document.getElementById("image-preview");
  imgEl.addEventListener("change", function () {
    const f = imgEl.files && imgEl.files[0];
    if (!f) { prev.classList.add("d-none"); return; }
    prev.src = URL.createObjectURL(f);
    prev.classList.remove("d-none");
  });
})();
