/* Sprint 2 frontend: accessible mode selectors, address autocomplete and maps. */
(() => {
  "use strict";

  const DRAFT_KEY = "group3-travel-aggregator-form-draft-v1";
  const form = document.getElementById("route-search-form");
  if (form) {
    const checkboxes = [...form.querySelectorAll('input[name="modes"]')];
    const allButton = document.querySelector('[data-mode="all"]');
    const modeError = document.getElementById("mode-error");
    const refreshModes = () => {
      for (const checkbox of checkboxes) {
        const chip = checkbox.closest(".mode-button");
        chip.classList.toggle("is-enabled", checkbox.checked);
        chip.setAttribute(
          "aria-label",
          `${chip.dataset.mode.replace("_", " ")} ${checkbox.checked ? "included" : "excluded"}`,
        );
      }
      const allChecked = checkboxes.every((input) => input.checked);
      allButton.classList.toggle("is-enabled", allChecked);
      allButton.setAttribute("aria-pressed", String(allChecked));
      if (modeError)
        modeError.hidden = checkboxes.some((input) => input.checked);
    };
    checkboxes.forEach((input) =>
      input.addEventListener("change", refreshModes),
    );
    allButton.addEventListener("click", () => {
      const enable = !checkboxes.every((input) => input.checked);
      checkboxes.forEach((input) => {
        input.checked = enable;
      });
      refreshModes();
    });
    refreshModes();
    // Preserve unfinished inputs in this browser when connectivity is lost.
    // The completed search and full algorithm JSON are also saved server-side.
    const saveDraft = () => {
      try {
        const values = Object.fromEntries(new FormData(form).entries());
        values.modes = checkboxes
          .filter((el) => el.checked)
          .map((el) => el.value);
        localStorage.setItem(DRAFT_KEY, JSON.stringify(values));
      } catch (_) {
        /* Storage can be disabled by browser privacy settings. */
      }
    };
    try {
      const old = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      if (old && typeof old === "object") {
        for (const name of [
          "origin",
          "destination",
          "travel_date",
          "adults",
          "objective",
          "start_time",
          "origin_lat",
          "origin_lon",
          "destination_lat",
          "destination_lon",
        ]) {
          const input = form.elements.namedItem(name);
          if (input && old[name] !== undefined) input.value = old[name];
        }
        if (Array.isArray(old.modes))
          checkboxes.forEach((el) => {
            el.checked = old.modes.includes(el.value);
          });
        refreshModes();
      }
    } catch (_) {
      /* Ignore stale or invalid browser storage. */
    }
    form.addEventListener("input", saveDraft);
    form.addEventListener("change", saveDraft);

    const dateInput = document.getElementById("travel_date");
    if (dateInput) {
      const todayLocal = new Date(
        Date.now() - new Date().getTimezoneOffset() * 60000,
      )
        .toISOString()
        .slice(0, 10);
      dateInput.min = todayLocal;
      if (!dateInput.value) dateInput.value = todayLocal;
    }

    const inputFor = (name) => document.getElementById(name);
    const coordsFor = (name) => [
      inputFor(name + "_lat"),
      inputFor(name + "_lon"),
    ];
    const setCoords = (name, lat, lon) => {
      const [latInput, lonInput] = coordsFor(name);
      latInput.value = lat ?? "";
      lonInput.value = lon ?? "";
    };

    for (const name of ["origin", "destination"]) {
      const input = inputFor(name);
      const suggestions = document.getElementById(name + "-suggestions");
      let debounceTimer;
      let controller;
      let requestNumber = 0;
      const close = () => {
        suggestions.hidden = true;
        suggestions.innerHTML = "";
        input.setAttribute("aria-expanded", "false");
      };
      const display = (rows) => {
        suggestions.replaceChildren();
        if (!rows.length) {
          close();
          return;
        }
        rows.forEach((row, index) => {
          const option = document.createElement("button");
          option.type = "button";
          option.className = "suggestion-item";
          option.textContent = "⌖  " + row.label;
          option.setAttribute("role", "option");
          option.id = `${name}-suggestion-${index}`;
          option.addEventListener("click", () => {
            input.value = row.label;
            setCoords(name, row.lat, row.lon);
            form.dispatchEvent(new Event("change", { bubbles: true }));
            close();
          });
          suggestions.append(option);
        });
        suggestions.hidden = false;
        input.setAttribute("aria-expanded", "true");
      };
      input.addEventListener("input", () => {
        setCoords(name, null, null); // Don't reuse stale coordinates after manual edits.
        clearTimeout(debounceTimer);
        if (controller) controller.abort();
        close();
        const query = input.value.trim();
        const current = ++requestNumber;
        if (query.length < 3) return;
        debounceTimer = setTimeout(async () => {
          controller = new AbortController();
          try {
            const response = await fetch(
              "/api/addresses/?q=" + encodeURIComponent(query),
              { signal: controller.signal },
            );
            if (!response.ok) throw new Error("Autocomplete unavailable");
            const data = await response.json();
            if (current === requestNumber && document.activeElement === input)
              display(data.suggestions || []);
          } catch (error) {
            if (error.name !== "AbortError") close();
          }
        }, 500);
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") close();
        if (event.key === "ArrowDown" && !suggestions.hidden) {
          event.preventDefault();
          suggestions.querySelector("button")?.focus();
        }
      });
      document.addEventListener("click", (event) => {
        if (!input.closest("[data-address-field]").contains(event.target))
          close();
      });
    }
    document.getElementById("swap-addresses").addEventListener("click", () => {
      const a = inputFor("origin"),
        b = inputFor("destination");
      const old = a.value;
      const [aLat, aLon] = coordsFor("origin").map((el) => el.value);
      a.value = b.value;
      b.value = old;
      const [bLat, bLon] = coordsFor("destination").map((el) => el.value);
      setCoords("origin", bLat, bLon);
      setCoords("destination", aLat, aLon);
      a.dispatchEvent(new Event("change"));
      saveDraft();
    });
    form.addEventListener("submit", (event) => {
      const checked = checkboxes.some((box) => box.checked);
      if (!checked) {
        event.preventDefault();
        modeError.hidden = false;
        allButton.focus();
      }
      // Let HTML5 native validation handle required address and date fields.
      if (checked && !form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
      }
    });
  }

  const clearSaved = document.getElementById("clear-planner-form");
  if (clearSaved)
    clearSaved.addEventListener("submit", () => {
      try {
        localStorage.removeItem(DRAFT_KEY);
      } catch (_) {}
    });

  function validGeometry(geometry) {
    return (
      Array.isArray(geometry) &&
      geometry.length >= 2 &&
      geometry.every(
        (point) =>
          Array.isArray(point) &&
          Number.isFinite(point[0]) &&
          Number.isFinite(point[1]) &&
          Math.abs(point[0]) <= 180 &&
          Math.abs(point[1]) <= 90,
      )
    );
  }

  function validPlace(place) {
    return (
      place &&
      Number.isFinite(place.lat) &&
      Number.isFinite(place.lon) &&
      Math.abs(place.lat) <= 90 &&
      Math.abs(place.lon) <= 180
    );
  }

  // These are driving estimates, never verified bus itineraries.
  // Fetch only on selection and reuse successful results for this page.
  const roadEstimates = new Map();
  function roadEstimate(origin, destination) {
    const coordinates = `${origin.lon},${origin.lat};${destination.lon},${destination.lat}`;
    if (roadEstimates.has(coordinates)) return roadEstimates.get(coordinates);
    const pending = (async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 12000);
      try {
        const response = await fetch(
          "https://router.project-osrm.org/route/v1/driving/" +
            coordinates +
            "?overview=full&geometries=geojson&steps=false",
          { signal: controller.signal, credentials: "omit" },
        );
        if (!response.ok) throw new Error("Road routing unavailable");
        const data = await response.json();
        const geometry = data.routes?.[0]?.geometry;
        if (
          data.code !== "Ok" ||
          geometry?.type !== "LineString" ||
          !validGeometry(geometry.coordinates)
        ) {
          throw new Error("No valid road estimate returned");
        }
        return geometry.coordinates;
      } finally {
        clearTimeout(timer);
      }
    })();
    roadEstimates.set(coordinates, pending);
    pending.catch(() => roadEstimates.delete(coordinates));
    return pending;
  }

  function initializeMap(element, data) {
    if (!element || typeof window.L === "undefined") return;
    const map = L.map(element, { scrollWheelZoom: false });
    L.maplibreGL({
      style: "https://tiles.openfreemap.org/styles/liberty",
    }).addTo(map);
    element.querySelector(".map-fallback")?.remove();
    map.setView([39.2, -97.5], 4);
    if (!validPlace(data?.origin) || !validPlace(data?.destination)) return;
    const overlay = L.layerGroup().addTo(map);

    function draw(origin, destination, geometry, estimated = false, legs = null) {
      if (!validPlace(origin) || !validPlace(destination)) return false;
      overlay.clearLayers();
      const segments = legs || [{ origin, destination, geometry, estimated }];
      const allPoints = [];
      const markers = new Set();
      segments.forEach((segment) => {
        const endpoints = [segment.origin, segment.destination];
        if (!endpoints.every(validPlace)) return;
        endpoints.forEach((place, i) => {
          const key = `${place.lat},${place.lon},${place.label}`;
          if (markers.has(key)) return;
          markers.add(key);
          L.circleMarker([place.lat, place.lon], {
            radius: 9, color: "#fff", weight: 3,
            fillColor: i === 0 ? "#655dc8" : "#fa7455", fillOpacity: 1,
          }).bindPopup((i === 0 ? "Departure: " : "Arrival: ") + escapeHtml(place.label))
            .addTo(overlay);
        });
        const hasPath = validGeometry(segment.geometry);
        const line = hasPath
          ? segment.geometry.map(([lon, lat]) => [lat, lon])
          : endpoints.map((place) => [place.lat, place.lon]);
        allPoints.push(...line, ...endpoints.map((place) => [place.lat, place.lon]));
        L.polyline(line, {
          color: segment.estimated ? "#b66b13" : "#665dc6", weight: 3, opacity: 0.9,
          dashArray: hasPath ? (segment.estimated ? "10 5" : undefined) : "8 9",
        }).addTo(overlay);
      });
      // No leg with usable GPS: retain the search endpoints as an explicit fallback.
      if (!allPoints.length) return draw(origin, destination, null);
      map.invalidateSize();
      map.fitBounds(L.latLngBounds(allPoints).pad(0.2), {
        maxZoom: 8,
      });
      return validGeometry(geometry);
    }

    draw(data.origin, data.destination, data.geometry);
    setTimeout(() => map.invalidateSize(), 100);
    return draw;
  }

  function escapeHtml(s) {
    const el = document.createElement("span");
    el.textContent = String(s || "");
    return el.innerHTML;
  }

  function whenMapReady() {
    initializeMap(document.getElementById("home-map"), null);
    const resultsMap = document.getElementById("results-map");
    const json = document.getElementById("route-map-data");
    if (!resultsMap || !json) return;
    try {
      const overview = JSON.parse(json.textContent);
      const draw = initializeMap(resultsMap, overview);
      const optionsJson = document.getElementById("map-route-options");
      const caption = document.getElementById("route-map-caption");
      if (!draw || !optionsJson || !caption) return;
      const options = JSON.parse(optionsJson.textContent);
      const buttons = [...document.querySelectorAll("[data-map-route]")];
      let selection = 0;
      buttons.forEach((button) => {
        const index = Number(button.dataset.mapRoute);
        const option = options[index];
        if (!option) return;
        button.hidden = false;
        button.addEventListener("click", async () => {
          const current = ++selection;
          const label = "Option " + (index + 1) + ": ";
          buttons.forEach((other) =>
            other.setAttribute("aria-pressed", String(other === button)),
          );
          const allLegs = Array.isArray(option.legs) ? option.legs : [];
          const legs = allLegs.filter((leg) => validPlace(leg.origin) && validPlace(leg.destination))
            .map((leg) => ({ ...leg }));
          const missing = legs.length !== allLegs.length || !legs.length;
          const origin = overview.origin;
          const destination = overview.destination;
          draw(origin, destination, null, false, legs);
          const detail = missing
            ? " Some leg coordinates are unavailable; those legs are omitted. Search endpoints are shown if no leg has GPS."
            : "";
          caption.textContent = label + "Dashed lines join itinerary leg endpoints, not actual paths or stops." + detail;
          resultsMap.scrollIntoView({ block: "nearest" });
          const buses = legs.filter((leg) => leg.mode === "bus");
          if (!buses.length) return;
          caption.textContent = label + "Loading estimated driving paths for bus legs." + detail;
          await Promise.all(buses.map(async (leg) => {
            try {
              leg.geometry = await roadEstimate(leg.origin, leg.destination);
              leg.estimated = true;
            } catch (_) {
              // Keep this leg's straight endpoint connector when routing fails.
            }
          }));
          if (current !== selection) return;
          draw(origin, destination, null, false, legs);
          const estimates = buses.filter((leg) => leg.estimated).length;
          caption.textContent = label + (estimates
            ? "Orange lines: estimated driving paths for bus legs (OSRM / OpenStreetMap), not the operator’s actual paths or stops. Other dashed lines connect leg endpoints only."
            : "Road estimates unavailable. Dashed lines connect itinerary leg endpoints only.") + detail;

        });
      });
    } catch (_) {
      /* Keep the map fallback if setup fails. */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", whenMapReady);
  } else {
    whenMapReady();
  }
})();
