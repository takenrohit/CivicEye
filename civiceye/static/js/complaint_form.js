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
  // Declared before any code path that can call checkNearby() (e.g. restoring
  // coordinates after a failed submission), to avoid a temporal-dead-zone error.
  let nearbyTimer = null;
  let suggTimer = null;

  // Default observation time = now in IST. The server interprets this field as
  // Asia/Kolkata, so it must not depend on the browser's own time zone.
  function nowIST() {
    const parts = {};
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    }).formatToParts(new Date()).forEach(function (p) { parts[p.type] = p.value; });
    return parts.year + "-" + parts.month + "-" + parts.day + "T" + parts.hour + ":" + parts.minute;
  }
  obsEl.max = nowIST();
  if (!obsEl.value) obsEl.value = obsEl.max;

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

  function fromInputs(source) {
    const lat = parseFloat(latEl.value), lon = parseFloat(lonEl.value);
    if (isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) setPoint(lat, lon, source, true);
  }
  latEl.addEventListener("change", function () { fromInputs("manual"); });
  lonEl.addEventListener("change", function () { fromInputs("manual"); });
  // After a failed submission the server re-renders the form: restore the pin and keep its original source.
  if (latEl.value && lonEl.value) fromInputs(srcEl.value || "manual");

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
  descEl.addEventListener("input", refreshSuggestion);
  function refreshSuggestion() {
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
  }
  // Re-rendered after a failed submission: show the suggestion for the kept description.
  if (descEl.value.trim()) refreshSuggestion();

  // ---- Image preview ----
  const imgEl = document.getElementById("image");
  const extraEl = document.getElementById("extra_images");
  const prev = document.getElementById("image-preview");
  imgEl.addEventListener("change", function () {
    const f = imgEl.files && imgEl.files[0];
    if (prev.src) URL.revokeObjectURL(prev.src);
    if (!f) { prev.classList.add("d-none"); prev.removeAttribute("src"); return; }
    prev.src = URL.createObjectURL(f);
    prev.classList.remove("d-none");
  });

  // ---- Client-side size check (the server re-checks everything) ----
  // Without this, an oversized request is cut off by the server and the browser shows
  // a connection error instead of a helpful message.
  const maxImage = parseInt(form.dataset.maxImageBytes, 10);
  const maxRequest = parseInt(form.dataset.maxRequestBytes, 10);
  const maxExtra = parseInt(form.dataset.maxExtra, 10);
  // Round file sizes up and limits down so "21.0 MB; the limit is 20.0 MB" never reads as equal.
  const mb = function (n, down) {
    const v = n / 1048576;
    return (down ? Math.floor(v * 10) : Math.ceil(v * 10)) / 10 + " MB";
  };
  function setFileError(input, msg) {
    input.setCustomValidity(msg);
    input.classList.toggle("is-invalid", !!msg);
    let el = document.getElementById(input.id + "-client-error");
    if (!el) {
      el = document.createElement("div");
      el.id = input.id + "-client-error";
      el.className = "invalid-feedback d-block";
      el.setAttribute("aria-live", "polite");
      input.insertAdjacentElement("afterend", el);
    }
    el.textContent = msg;
  }
  function checkFiles() {
    const main = imgEl.files[0];
    const extras = Array.from(extraEl.files || []);
    let total = 0;
    setFileError(imgEl, main && main.size > maxImage ? "This photo is " + mb(main.size) + "; the limit is " + mb(maxImage, true) + "." : "");
    if (main) total += main.size;
    let extraMsg = extras.length > maxExtra ? "Choose at most " + maxExtra + " additional photos." : "";
    extras.forEach(function (f) {
      total += f.size;
      if (!extraMsg && f.size > maxImage) extraMsg = f.name + " is " + mb(f.size) + "; the limit is " + mb(maxImage, true) + " per photo.";
    });
    if (!extraMsg && total > maxRequest) extraMsg = "All photos together are " + mb(total) + "; the limit is " + mb(maxRequest, true) + ".";
    setFileError(extraEl, extraMsg);
    return !imgEl.validationMessage && !extraEl.validationMessage;
  }
  imgEl.addEventListener("change", checkFiles);
  extraEl.addEventListener("change", checkFiles);
  form.addEventListener("submit", function (e) {
    if (!checkFiles()) {
      e.preventDefault();
      (imgEl.validationMessage ? imgEl : extraEl).focus();
    }
  });
})();
