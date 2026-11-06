/* Sprint 2 frontend: accessible mode selectors, address autocomplete and maps. */
(() => {
  'use strict';

  const DRAFT_KEY = 'group3-travel-aggregator-form-draft-v1';
  const form = document.getElementById('route-search-form');
  if (form) {
    const checkboxes = [...form.querySelectorAll('input[name="modes"]')];
    const allButton = document.querySelector('[data-mode="all"]');
    const modeError = document.getElementById('mode-error');
    const refreshModes = () => {
      for (const checkbox of checkboxes) {
        const chip = checkbox.closest('.mode-button');
        chip.classList.toggle('is-enabled', checkbox.checked);
        chip.setAttribute('aria-label', `${chip.dataset.mode.replace('_', ' ')} ${checkbox.checked ? 'included' : 'excluded'}`);
      }
      const allChecked = checkboxes.every(input => input.checked);
      allButton.classList.toggle('is-enabled', allChecked);
      allButton.setAttribute('aria-pressed', String(allChecked));
      if (modeError) modeError.hidden = checkboxes.some(input => input.checked);
    };
    checkboxes.forEach(input => input.addEventListener('change', refreshModes));
    allButton.addEventListener('click', () => {
      const enable = !checkboxes.every(input => input.checked);
      checkboxes.forEach(input => { input.checked = enable; });
      refreshModes();
    });
    refreshModes();
    // Preserve unfinished inputs in this browser when connectivity is lost.
    // The completed search and original provider JSON are also saved server-side.
    const saveDraft = () => {
      try {
        const values = Object.fromEntries(new FormData(form).entries());
        values.modes = checkboxes.filter(el => el.checked).map(el => el.value);
        localStorage.setItem(DRAFT_KEY, JSON.stringify(values));
      } catch (_) { /* Storage can be disabled by browser privacy settings. */ }
    };
    try {
      const old = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
      if (old && typeof old === 'object') {
        for (const name of ['origin','destination','travel_date','adults','objective',
                            'origin_lat','origin_lon','destination_lat','destination_lon']) {
          const input = form.elements.namedItem(name);
          if (input && old[name] !== undefined) input.value = old[name];
        }
        if (Array.isArray(old.modes)) checkboxes.forEach(el => {el.checked = old.modes.includes(el.value);});
        refreshModes();
      }
    } catch (_) { /* Ignore stale or invalid browser storage. */ }
    form.addEventListener('input', saveDraft);
    form.addEventListener('change', saveDraft);

    const dateInput = document.getElementById('travel_date');
    if (dateInput) {
      const todayLocal = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0,10);
      dateInput.min = todayLocal;
      if (!dateInput.value) dateInput.value = todayLocal;
    }

    const inputFor = name => document.getElementById(name);
    const coordsFor = name => [inputFor(name + '_lat'), inputFor(name + '_lon')];
    const setCoords = (name, lat, lon) => {
      const [latInput, lonInput] = coordsFor(name);
      latInput.value = lat ?? '';
      lonInput.value = lon ?? '';
    };

    for (const name of ['origin', 'destination']) {
      const input = inputFor(name);
      const suggestions = document.getElementById(name + '-suggestions');
      let debounceTimer;
      let controller;
      let requestNumber = 0;
      const close = () => { suggestions.hidden = true; suggestions.innerHTML = ''; input.setAttribute('aria-expanded','false'); };
      const display = rows => {
        suggestions.replaceChildren();
        if (!rows.length) { close(); return; }
        rows.forEach((row, index) => {
          const option = document.createElement('button');
          option.type = 'button';
          option.className = 'suggestion-item';
          option.textContent = '⌖  ' + row.label;
          option.setAttribute('role','option');
          option.id = `${name}-suggestion-${index}`;
          option.addEventListener('click', () => {
            input.value = row.label;
            setCoords(name, row.lat, row.lon);
            form.dispatchEvent(new Event('change', {bubbles: true}));
            close();
          });
          suggestions.append(option);
        });
        suggestions.hidden = false;
        input.setAttribute('aria-expanded','true');
      };
      input.addEventListener('input', () => {
        setCoords(name, null, null);  // Don't reuse stale coordinates after manual edits.
        clearTimeout(debounceTimer);
        if (controller) controller.abort();
        close();
        const query = input.value.trim();
        const current = ++requestNumber;
        if (query.length < 3) return;
        debounceTimer = setTimeout(async () => {
          controller = new AbortController();
          try {
            const response = await fetch('/api/addresses/?q=' + encodeURIComponent(query), {signal: controller.signal});
            if (!response.ok) throw new Error('Autocomplete unavailable');
            const data = await response.json();
            if (current === requestNumber && document.activeElement === input) display(data.suggestions || []);
          } catch (error) {
            if (error.name !== 'AbortError') close();
          }
        }, 500);
      });
      input.addEventListener('keydown', event => {
        if (event.key === 'Escape') close();
        if (event.key === 'ArrowDown' && !suggestions.hidden) {
          event.preventDefault();
          suggestions.querySelector('button')?.focus();
        }
      });
      document.addEventListener('click', event => {
        if (!input.closest('[data-address-field]').contains(event.target)) close();
      });
    }
    document.getElementById('swap-addresses').addEventListener('click', () => {
      const a = inputFor('origin'), b = inputFor('destination');
      const old = a.value;
      const [aLat, aLon] = coordsFor('origin').map(el => el.value);
      a.value = b.value; b.value = old;
      const [bLat, bLon] = coordsFor('destination').map(el => el.value);
      setCoords('origin', bLat, bLon);
      setCoords('destination', aLat, aLon);
      a.dispatchEvent(new Event('change'));
      saveDraft();
    });
    form.addEventListener('submit', event => {
      const checked = checkboxes.some(box => box.checked);
      if (!checked) {
        event.preventDefault();
        modeError.hidden = false;
        allButton.focus();
      }
      // Let HTML5 native validation handle required address and date fields.
      if (checked && !form.checkValidity()) { event.preventDefault(); form.reportValidity(); }
    });
  }

  const clearSaved = document.getElementById('clear-planner-form');
  if (clearSaved) clearSaved.addEventListener('submit', () => {
    try { localStorage.removeItem(DRAFT_KEY); } catch (_) {}
  });

  function initializeMap(element, data) {
    if (!element || typeof window.L === 'undefined') return;
    element.querySelector('.map-fallback')?.remove();
    const map = L.map(element, {scrollWheelZoom: false});
    L.maplibreGL({
      style: 'https://tiles.openfreemap.org/styles/liberty'
    }).addTo(map);
    
    if (!data || !data.origin || !data.destination) {
      map.setView([39.2, -97.5], 4);
      return;
    }
    const points = [data.origin, data.destination];
    points.forEach((place, i) => {
      L.circleMarker([place.lat, place.lon], {
        radius: 9, color: '#fff', weight: 3, fillColor: i === 0 ? '#655dc8' : '#fa7455', fillOpacity: 1,
      }).bindPopup((i === 0 ? 'Address A: ' : 'Address B: ') + escapeHtml(place.label)).addTo(map);
    });
    const line = Array.isArray(data.geometry) && data.geometry.length >= 2
      ? data.geometry.map(coordinate => [coordinate[1], coordinate[0]])
      : points.map(place => [place.lat, place.lon]);
    L.polyline(line, {color: '#665dc6', weight: 3, opacity: .83, dashArray: data.geometry ? undefined : '8 9'}).addTo(map);
    const bounds = L.latLngBounds(line);
    map.fitBounds(bounds.pad(.2), {maxZoom: 8});
    if (bounds.getNorthEast().equals(bounds.getSouthWest())) map.setZoom(9);
    setTimeout(() => map.invalidateSize(), 100);
  }
  function escapeHtml(s) {
    const el = document.createElement('span'); el.textContent = String(s || ''); return el.innerHTML;
  }
  function whenMapReady() {
    initializeMap(document.getElementById('home-map'), null);
    const resultsMap = document.getElementById('results-map');
    const json = document.getElementById('route-map-data');
    if (resultsMap && json) {
      try { initializeMap(resultsMap, JSON.parse(json.textContent)); } catch (_) { /* Keep fallback */ }
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', whenMapReady);
  else whenMapReady();
})();
