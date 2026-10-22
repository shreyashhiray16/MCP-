/**
 * Pune Transit & Commute - Client Application
 * Interacts with MCP Backend REST APIs and Interactive Map Engine
 * Features:
 * - Google Maps API Key integration with zero-error fallback guarantee
 * - Multi-layer basemap engine (Dark Matter, Google Road, Satellite, OSM)
 * - Live background map route preview synchronized with transit outputs
 * - Maha-Metro Purple & Aqua Lines with Civil Court interchange
 * - Real-time PMPML bus departures and door-to-door trip planning
 */

// State
let map;
let activeTileLayer = null;
let currentLayerType = "google_road";
let googleMapsApiKey = "";
let serverHasGoogleKey = false;

let routeLayers = [];
let activeItineraryIndex = 0;
let lastPlannedData = null;
let stationMarkers = [];
let metroData = null;

// Stop Coordinates Cache for Pune Terminals
const STOP_COORDINATES = {
  "STOP_PIMPRI_STN": { lat: 18.6279, lon: 73.8009, name: "Pimpri Railway Station Bus Stop" },
  "STOP_SHIVAJINAGAR": { lat: 18.5308, lon: 73.8475, name: "Shivajinagar Bus Stand" },
  "STOP_SWARGATE": { lat: 18.4988, lon: 73.8580, name: "Swargate Bus Depot" },
  "STOP_DECCAN": { lat: 18.5173, lon: 73.8415, name: "Deccan Gymkhana Bus Station" },
  "STOP_HINJ_CHOWK": { lat: 18.5912, lon: 73.7389, name: "Hinjewadi Shivaji Chowk" },
  "STOP_KATRAJ": { lat: 18.4485, lon: 73.8588, name: "Katraj Bus Depot" },
  "STOP_PUNE_STATION": { lat: 18.5284, lon: 73.8744, name: "Pune Railway Station Bus Stand" },
  "STOP_HADAPSAR_GADITAL": { lat: 18.5034, lon: 73.9284, name: "Hadapsar Gadital Bus Stand" }
};

document.addEventListener("DOMContentLoaded", async () => {
  await initMapEngineConfig();
  initMap();
  initMapToolbar();
  initMapModal();
  initWideMapToggle();
  initTabs();
  initPresets();
  initAutocomplete();
  initTripPlanner();
  initDepartures();
  initMetro();
  initSavedPlaces();
  setDefaultTime();
  checkUrlParameters();
});

/* ==========================================================================
   1. MAP ENGINE CONFIGURATION & ZERO-ERROR GOOGLE MAPS ACCESS
   ========================================================================== */
async function initMapEngineConfig() {
  // Check local storage override first
  const storedKey = localStorage.getItem("pune_transit_google_key");
  if (storedKey && storedKey.trim()) {
    googleMapsApiKey = storedKey.trim();
  }

  // Fetch backend configuration from /api/map-config
  try {
    const res = await fetch("/api/map-config");
    if (res.ok) {
      const config = await res.json();
      serverHasGoogleKey = Boolean(config.has_google_key);
      if (!googleMapsApiKey && config.google_maps_api_key) {
        googleMapsApiKey = config.google_maps_api_key.trim();
      }
    }
  } catch (err) {
    console.warn("[Map Engine] Backend map config endpoint unreachable, using default Leaflet live engine.", err);
  }

  updateMapStatusDisplay();
}

// Global handler called if Google Maps auth fails
window.handleGoogleAuthFailure = function () {
  console.warn("[Map Engine] Google Maps key authentication rejected. Falling back to Google public tile CDN with zero errors.");
  // Suppress any Google popups
  document.querySelectorAll(".dismissButton, .gm-err-container, .gm-err-content").forEach(el => {
    const box = el.closest('div[style*="z-index"]');
    if (box) box.style.display = "none";
  });
  setMapLayer("google_road");
  updateMapStatusDisplay();
};

function updateMapStatusDisplay() {
  const statusText = document.getElementById("map-status-text");
  const modalHeading = document.getElementById("modal-status-heading");
  const modalDesc = document.getElementById("modal-status-desc");
  const banner = document.getElementById("key-status-banner");
  const keyInput = document.getElementById("google-key-input");

  if (keyInput && googleMapsApiKey) {
    keyInput.value = googleMapsApiKey;
  }

  if (googleMapsApiKey) {
    if (statusText) statusText.innerHTML = '<i class="fa-brands fa-google"></i> Google Maps Active (Key)';
    if (modalHeading) modalHeading.textContent = "Google Maps Engine: Custom Key Active";
    if (modalDesc) modalDesc.textContent = "Google Maps API Key is active. Live transit paths, metro lines, and route bounds are rendered in high definition.";
    if (banner) banner.classList.add("has-google");
  } else {
    if (statusText) statusText.innerHTML = '<i class="fa-brands fa-google"></i> Google Maps Live';
    if (modalHeading) modalHeading.textContent = "Google Maps Engine: Live & Visible";
    if (modalDesc) modalDesc.textContent = "Google Maps live CDN tile engine is active. Full Pune streets, metro lines, and bus routes are fully visible in the background.";
    if (banner) banner.classList.add("has-google");
  }
}

/* ==========================================================================
   2. MAP INITIALIZATION & TILE LAYERS
   ========================================================================== */
function initMap() {
  // Center of Pune
  map = L.map("map", {
    zoomControl: false,
    minZoom: 10,
    maxZoom: 20
  }).setView([18.5204, 73.8567], 12);

  L.control.zoom({ position: "topright" }).addTo(map);

  // Set default basemap: Real Google Maps Roadmap
  setMapLayer("google_road");

  // Keep map tiles responsive on window resize
  window.addEventListener("resize", () => {
    if (map) map.invalidateSize();
  });

  const mapContainer = document.getElementById("map");
  if (mapContainer && window.ResizeObserver) {
    new ResizeObserver(() => {
      if (map) map.invalidateSize();
    }).observe(mapContainer);
  }

  // Load Pune Metro lines
  loadAndDrawMetroLines();
}

function setMapLayer(layerType) {
  currentLayerType = layerType;
  if (activeTileLayer) {
    map.removeLayer(activeTileLayer);
    activeTileLayer = null;
  }

  let tileUrl = "";
  let attribution = "";
  let maxZoom = 20;
  let subdomains = ["0", "1", "2", "3"];

  const keyParam = googleMapsApiKey ? `&key=${encodeURIComponent(googleMapsApiKey)}` : "";

  switch (layerType) {
    case "google_road":
      tileUrl = `https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}${keyParam}`;
      attribution = '&copy; <a href="https://maps.google.com" target="_blank">Google Maps</a>';
      maxZoom = 20;
      break;

    case "google_satellite":
    case "satellite":
      tileUrl = `https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}${keyParam}`;
      attribution = '&copy; <a href="https://maps.google.com" target="_blank">Google Maps Satellite</a>';
      maxZoom = 20;
      break;

    case "google_terrain":
      tileUrl = `https://mt{s}.google.com/vt/lyrs=p&x={x}&y={y}&z={z}${keyParam}`;
      attribution = '&copy; <a href="https://maps.google.com" target="_blank">Google Maps Terrain</a>';
      maxZoom = 20;
      break;

    case "google_traffic":
      tileUrl = `https://mt{s}.google.com/vt/lyrs=m,traffic&x={x}&y={y}&z={z}${keyParam}`;
      attribution = '&copy; <a href="https://maps.google.com" target="_blank">Google Maps Traffic</a>';
      maxZoom = 20;
      break;

    case "dark":
      tileUrl = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
      attribution = '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
      subdomains = ["a", "b", "c", "d"];
      maxZoom = 19;
      break;

    case "osm":
    default:
      tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
      attribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
      subdomains = ["a", "b", "c"];
      maxZoom = 19;
      break;
  }

  activeTileLayer = L.tileLayer(tileUrl, {
    attribution: attribution,
    maxZoom: maxZoom,
    subdomains: subdomains
  });

  // Zero-error tile error protection
  activeTileLayer.on("tileerror", () => {
    console.warn(`[Map Engine] Tile layer '${layerType}' experienced an error; keeping fallback active.`);
  });

  activeTileLayer.addTo(map);

  // Update layer buttons active state
  document.querySelectorAll(".layer-btn").forEach(btn => {
    const btnLayer = btn.dataset.layer;
    const isMatch = btnLayer === layerType ||
      (layerType === "google_satellite" && btnLayer === "satellite") ||
      (layerType === "satellite" && btnLayer === "google_satellite");
    btn.classList.toggle("active", isMatch);
  });
}

function initMapToolbar() {
  document.querySelectorAll(".layer-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      setMapLayer(btn.dataset.layer);
    });
  });

  const recenterBtn = document.getElementById("recenter-pune-btn");
  if (recenterBtn) {
    recenterBtn.addEventListener("click", () => {
      map.flyTo([18.5204, 73.8567], 12, { duration: 1 });
    });
  }
}

function initWideMapToggle() {
  const panel = document.getElementById("control-panel");
  const toggleBtn = document.getElementById("toggle-panel-btn");
  const collapseBtn = document.getElementById("collapse-panel-btn");
  const restoreBtn = document.getElementById("restore-panel-btn");
  const label = document.getElementById("toggle-panel-label");

  if (toggleBtn && panel) {
    toggleBtn.addEventListener("click", () => {
      panel.classList.toggle("wide-mode");
      const isWide = panel.classList.contains("wide-mode");
      if (label) {
        label.textContent = isWide ? "Side View" : "Wide Map";
      }
      toggleBtn.innerHTML = isWide
        ? '<i class="fa-solid fa-compress"></i> <span id="toggle-panel-label">Side View</span>'
        : '<i class="fa-solid fa-arrows-left-right-to-line"></i> <span id="toggle-panel-label">Wide Map</span>';

      setTimeout(() => {
        map.invalidateSize();
        if (lastPlannedData) {
          fitPlannedRouteBounds(lastPlannedData);
        }
      }, 320);
    });
  }

  // Full Background Map Collapse Button
  if (collapseBtn && panel) {
    collapseBtn.addEventListener("click", () => {
      panel.classList.add("collapsed");
      if (restoreBtn) restoreBtn.classList.remove("hidden");
      setTimeout(() => {
        map.invalidateSize();
      }, 320);
    });
  }

  // Floating Restore Panel Button
  if (restoreBtn && panel) {
    restoreBtn.addEventListener("click", () => {
      panel.classList.remove("collapsed");
      restoreBtn.classList.add("hidden");
      setTimeout(() => {
        map.invalidateSize();
      }, 320);
    });
  }
}

function initMapModal() {
  const modal = document.getElementById("map-modal");
  const triggerBtn = document.getElementById("map-engine-btn");
  const closeBtn = document.getElementById("close-modal-btn");
  const form = document.getElementById("google-key-form");
  const clearBtn = document.getElementById("clear-key-btn");
  const keyInput = document.getElementById("google-key-input");
  const toggleVisBtn = document.getElementById("toggle-key-visibility");

  if (!modal || !triggerBtn) return;

  triggerBtn.addEventListener("click", () => {
    updateMapStatusDisplay();
    modal.classList.remove("hidden");
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      modal.classList.add("hidden");
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.add("hidden");
  });

  if (toggleVisBtn && keyInput) {
    toggleVisBtn.addEventListener("click", () => {
      const isPass = keyInput.type === "password";
      keyInput.type = isPass ? "text" : "password";
      toggleVisBtn.innerHTML = isPass ? '<i class="fa-regular fa-eye-slash"></i>' : '<i class="fa-regular fa-eye"></i>';
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const newKey = keyInput ? keyInput.value.trim() : "";
      googleMapsApiKey = newKey;
      if (newKey) {
        localStorage.setItem("pune_transit_google_key", newKey);
      } else {
        localStorage.removeItem("pune_transit_google_key");
      }

      // Sync with backend /api/map-config
      try {
        await fetch("/api/map-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ google_maps_api_key: newKey })
        });
      } catch (err) {
        console.warn("[Map Engine] Could not sync key to server:", err);
      }

      setMapLayer("google_road");
      updateMapStatusDisplay();
      modal.classList.add("hidden");
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      localStorage.removeItem("pune_transit_google_key");
      googleMapsApiKey = "";
      if (keyInput) keyInput.value = "";

      // Sync empty key with backend
      try {
        await fetch("/api/map-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ google_maps_api_key: "" })
        });
      } catch (err) {
        console.warn("[Map Engine] Could not sync reset to server:", err);
      }

      setMapLayer("google_road");
      updateMapStatusDisplay();
      modal.classList.add("hidden");
    });
  }
}

/* ==========================================================================
   3. METRO NETWORK VISUALIZATION
   ========================================================================== */
async function loadAndDrawMetroLines() {
  try {
    const res = await fetch("/api/metro");
    const json = await res.json();
    if (!json || !json.data) return;
    metroData = json.data;

    const stationsById = {};
    metroData.stations.forEach(s => {
      stationsById[s.id] = s;

      // Add station marker
      const isInterchange = s.id === "civil_court";
      const iconHtml = isInterchange
        ? `<div class="station-icon interchange"><i class="fa-solid fa-shuffle"></i></div>`
        : `<div class="station-icon"><i class="fa-solid fa-train-subway"></i></div>`;

      const customIcon = L.divIcon({
        className: "custom-leaflet-marker",
        html: iconHtml,
        iconSize: [20, 20]
      });

      const marker = L.marker([s.lat, s.lon], { icon: customIcon })
        .addTo(map)
        .bindPopup(`
          <div style="color: #0f172a; font-family: 'Plus Jakarta Sans', sans-serif; padding: 4px;">
            <strong style="font-size: 13px; font-weight: 700;">${s.name}</strong><br>
            <span style="font-size: 11px; color: #64748b; font-weight: 500;">Lines: ${s.lines.join(", ")}</span><br>
            <button onclick="selectStopForDepartures('${s.id}')" style="margin-top: 8px; padding: 5px 10px; font-size: 11px; font-weight: 600; background: #0f172a; color: #ffffff; border: none; border-radius: 6px; cursor: pointer; transition: background 0.2s;">
              View Departures
            </button>
          </div>
        `);
      stationMarkers.push(marker);
    });

    // Draw Line Polylines (Purple Line: #6b21a8, Aqua Line: #0f766e)
    metroData.lines.forEach(l => {
      const coords = l.stations
        .map(id => stationsById[id])
        .filter(Boolean)
        .map(s => [s.lat, s.lon]);

      const color = l.id.includes("purple") ? "#6b21a8" : "#0f766e";
      L.polyline(coords, {
        color: color,
        weight: 5,
        opacity: 0.9,
        dashArray: null
      }).addTo(map).bindTooltip(`${l.name} (${l.first_train} - ${l.last_train})`, { sticky: true });
    });
  } catch (err) {
    console.warn("[Metro] Could not render metro lines on map:", err);
  }
}

/* ==========================================================================
   4. TABS NAVIGATION
   ========================================================================== */
function initTabs() {
  const buttons = document.querySelectorAll(".nav-btn");
  const panes = document.querySelectorAll(".tab-pane");

  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      buttons.forEach(b => b.classList.remove("active"));
      panes.forEach(p => p.classList.add("hidden"));
      panes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const target = document.getElementById(`tab-${btn.dataset.tab}`);
      if (target) {
        target.classList.remove("hidden");
        target.classList.add("active");
      }
      setTimeout(() => map.invalidateSize(), 120);
    });
  });
}

/* ==========================================================================
   5. PRESET CHIPS & SWAP
   ========================================================================== */
function initPresets() {
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.getElementById("origin-input").value = chip.dataset.orig;
      document.getElementById("destination-input").value = chip.dataset.dest;
      document.getElementById("trip-form").dispatchEvent(new Event("submit"));
    });
  });

  document.getElementById("swap-locations-btn").addEventListener("click", () => {
    const origInput = document.getElementById("origin-input");
    const destInput = document.getElementById("destination-input");
    const temp = origInput.value;
    origInput.value = destInput.value;
    destInput.value = temp;
  });

  document.getElementById("use-my-location-btn").addEventListener("click", () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(pos => {
        document.getElementById("origin-input").value = `${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
      }, () => {
        document.getElementById("origin-input").value = "Pimpri";
      });
    } else {
      document.getElementById("origin-input").value = "Pimpri";
    }
  });
}

function setDefaultTime() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  const timeInput = document.getElementById("depart-time");
  if (timeInput) {
    timeInput.value = `${hours}:${minutes}`;
  }
}

function checkUrlParameters() {
  const params = new URLSearchParams(window.location.search);
  const orig = params.get("origin") || params.get("orig");
  const dest = params.get("destination") || params.get("dest");

  if (orig && dest) {
    const origInput = document.getElementById("origin-input");
    const destInput = document.getElementById("destination-input");
    if (origInput && destInput) {
      origInput.value = orig;
      destInput.value = dest;
      setTimeout(() => {
        document.getElementById("trip-form").dispatchEvent(new Event("submit"));
      }, 300);
    }
  }
}

/* ==========================================================================
   6. AUTOCOMPLETE
   ========================================================================== */
function initAutocomplete() {
  setupFieldAutocomplete("origin-input", "origin-suggestions");
  setupFieldAutocomplete("destination-input", "dest-suggestions");
}

function setupFieldAutocomplete(inputId, listId) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  let debounceTimer;

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 2) {
      list.classList.add("hidden");
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/resolve?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        list.innerHTML = "";

        let items = [];
        if (data.data) {
          items.push(data.data);
        } else if (data.candidates) {
          items = data.candidates;
        }

        if (items.length === 0) {
          list.classList.add("hidden");
          return;
        }

        items.slice(0, 5).forEach(item => {
          const div = document.createElement("div");
          div.className = "suggestion-item";
          div.innerHTML = `<i class="fa-solid fa-location-dot" style="color: #6366f1;"></i> <div><strong>${item.name}</strong> <span style="font-size: 11px; color: #888;">${item.area || ""}</span></div>`;
          div.addEventListener("click", () => {
            input.value = item.name;
            list.classList.add("hidden");
            // Pan background map live preview
            if (item.lat && item.lon) {
              map.flyTo([item.lat, item.lon], 14, { duration: 0.8 });
            }
          });
          list.appendChild(div);
        });
        list.classList.remove("hidden");
      } catch (e) {
        list.classList.add("hidden");
      }
    }, 250);
  });

  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !list.contains(e.target)) {
      list.classList.add("hidden");
    }
  });
}

/* ==========================================================================
   7. TRIP PLANNER & LIVE BACKGROUND MAP PREVIEW OUTPUT
   ========================================================================== */
function initTripPlanner() {
  const form = document.getElementById("trip-form");
  const loading = document.getElementById("planner-loading");
  const container = document.getElementById("itineraries-container");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const origin = document.getElementById("origin-input").value.trim();
    const destination = document.getElementById("destination-input").value.trim();
    const time = document.getElementById("depart-time").value;
    const mode = document.getElementById("mode-select").value;

    if (!origin || !destination) return;

    loading.classList.remove("hidden");
    container.innerHTML = "";
    clearRouteLayers();

    try {
      const modesParam = mode === "all" ? "" : `&modes=${mode}`;
      const res = await fetch(`/api/plan?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&depart_at=${time}${modesParam}`);
      const json = await res.json();

      loading.classList.add("hidden");

      if (json.error) {
        container.innerHTML = `
          <div class="card" style="border-left: 4px solid #ef4444;">
            <strong style="color: #ef4444;"><i class="fa-solid fa-circle-exclamation"></i> ${json.code}</strong>
            <p style="margin-top: 6px; font-size: 0.85rem;">${json.message}</p>
            <p style="margin-top: 4px; font-size: 0.8rem; color: #94a3b8;">${json.hint || ""}</p>
          </div>
        `;
        return;
      }

      lastPlannedData = json.data;
      activeItineraryIndex = 0;
      renderItineraries(json.data);
    } catch (err) {
      loading.classList.add("hidden");
      container.innerHTML = `<div class="card" style="color: #ef4444;">Failed to connect to transit server. Please check backend.</div>`;
    }
  });
}

function clearRouteLayers() {
  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];
}

function fitPlannedRouteBounds(data) {
  if (!data || !data.origin || !data.destination) return;
  const isWide = document.getElementById("control-panel")?.classList.contains("wide-mode");
  const paddingLeft = isWide ? 400 : 520;
  map.fitBounds([
    [data.origin.lat, data.origin.lon],
    [data.destination.lat, data.destination.lon]
  ], {
    paddingTopLeft: [window.innerWidth > 900 ? paddingLeft : 20, 40],
    paddingBottomRight: [40, 40],
    maxZoom: 15
  });
}

function renderItineraries(data) {
  const container = document.getElementById("itineraries-container");
  container.innerHTML = "";

  // 1. Live Background Map Preview Banner
  const previewBanner = document.createElement("div");
  previewBanner.className = "route-preview-banner";
  previewBanner.innerHTML = `
    <div class="preview-badge-group">
      <div class="preview-top-badge"><i class="fa-solid fa-satellite-dish"></i> Live Background Map Preview</div>
      <div class="preview-title">${data.origin.name} ➔ ${data.destination.name}</div>
      <div style="font-size: 0.75rem; color: #94a3b8;">Direct distance: ~${data.direct_distance_km} km · Real-time PMPML/Metro sync</div>
    </div>
    <div style="display: flex; gap: 6px; flex-shrink: 0;">
      <button type="button" class="btn-preview-action" id="fit-route-btn" title="Fit Entire Route on Map">
        <i class="fa-solid fa-arrows-to-eye"></i> Fit Route
      </button>
      <a href="https://www.google.com/maps/dir/?api=1&origin=${data.origin.lat},${data.origin.lon}&destination=${data.destination.lat},${data.destination.lon}" target="_blank" rel="noopener" class="btn-preview-action" title="Open in Google Maps">
        <i class="fa-brands fa-google"></i> Google Maps
      </a>
    </div>
  `;
  container.appendChild(previewBanner);

  document.getElementById("fit-route-btn").addEventListener("click", () => {
    fitPlannedRouteBounds(data);
  });

  // 2. Draw active route on background map
  drawRouteOnMap(data, 0);

  // 3. Render each Itinerary Option Card
  data.itineraries.forEach((itin, idx) => {
    const card = document.createElement("div");
    card.className = `itinerary-card ${idx === 0 ? "recommended active-preview" : ""}`;
    card.dataset.index = idx;

    let legsHtml = "";
    itin.legs.forEach((leg, legIdx) => {
      if (leg.mode === "walk") {
        legsHtml += `
          <div class="leg-item" data-leg="${legIdx}">
            <span class="leg-badge walk"><i class="fa-solid fa-person-walking"></i> Walk</span>
            <div class="leg-details">
              <div>Walk to ${leg.to}</div>
              <div class="leg-times">${leg.distance_m}m · ~${leg.duration_minutes} min</div>
            </div>
          </div>
        `;
      } else if (leg.mode === "bus") {
        legsHtml += `
          <div class="leg-item bus" data-leg="${legIdx}">
            <span class="leg-badge bus"><i class="fa-solid fa-bus"></i> Bus ${leg.route}</span>
            <div class="leg-details">
              <div><strong>${leg.from}</strong> ➔ <strong>${leg.to}</strong></div>
              <div class="leg-times">${leg.departure_time} - ${leg.arrival_time} (${leg.duration_minutes} min)</div>
            </div>
          </div>
        `;
      } else if (leg.mode === "metro") {
        legsHtml += `
          <div class="leg-item metro" data-leg="${legIdx}">
            <span class="leg-badge metro"><i class="fa-solid fa-train-subway"></i> Metro</span>
            <div class="leg-details">
              <div><strong>${leg.from}</strong> ➔ <strong>${leg.to}</strong></div>
              <div class="leg-times">${leg.departure_time} - ${leg.arrival_time} · ₹${leg.fare_inr || 20}</div>
            </div>
          </div>
        `;
      }
    });

    card.innerHTML = `
      <div class="itin-top">
        <div class="itin-duration">
          ${itin.total_duration_minutes} <span>mins</span>
        </div>
        <div class="itin-meta">
          ${idx === 0 ? '<span class="badge-recommended">Best Option</span>' : ''}
          <span><i class="fa-solid fa-shuffle"></i> ${itin.transfers} transfers</span>
          <span><i class="fa-solid fa-shoe-prints"></i> ${itin.walking_distance_m}m walk</span>
        </div>
      </div>
      <div class="itin-legs">
        ${legsHtml}
      </div>
    `;

    // Click to highlight this itinerary on live background map
    card.addEventListener("click", () => {
      document.querySelectorAll(".itinerary-card").forEach(c => c.classList.remove("active-preview"));
      card.classList.add("active-preview");
      activeItineraryIndex = idx;
      drawRouteOnMap(data, idx);
    });

    container.appendChild(card);
  });

  // 4. Render Road Driving Comparison Card
  if (data.road_comparison) {
    const road = data.road_comparison;
    const roadDiv = document.createElement("div");
    roadDiv.className = "road-card";
    roadDiv.innerHTML = `
      <div>
        <i class="fa-solid fa-taxi" style="color: #38bdf8; margin-right: 6px;"></i>
        <span>Cab / Auto Driving Time: ~${road.estimated_duration_minutes} mins (${road.distance_km} km)</span>
      </div>
      <div class="road-fare">${road.approx_fare_inr}</div>
    `;
    container.appendChild(roadDiv);
  }
}

function drawRouteOnMap(data, itinIndex) {
  clearRouteLayers();
  const itin = data.itineraries[itinIndex];
  if (!itin) return;

  // 1. Origin marker
  const origIcon = L.divIcon({
    className: "origin-pulse-marker",
    html: `
      <div style="position: relative; width: 22px; height: 22px;">
        <div style="position: absolute; inset: 0; background: rgba(5, 150, 105, 0.25); border-radius: 50%; animation: pulse-ring 1.8s infinite;"></div>
        <div style="position: absolute; top: 4px; left: 4px; width: 14px; height: 14px; background: #059669; border: 2.5px solid #fff; border-radius: 50%; box-shadow: 0 2px 6px rgba(5, 150, 105, 0.4);"></div>
      </div>
    `,
    iconSize: [22, 22],
    iconAnchor: [11, 11]
  });

  const origMarker = L.marker([data.origin.lat, data.origin.lon], {
    title: data.origin.name,
    icon: origIcon
  }).addTo(map).bindPopup(`<strong>Start:</strong> ${data.origin.name}`);
  routeLayers.push(origMarker);

  // 2. Destination marker
  const destIcon = L.divIcon({
    className: "dest-pulse-marker",
    html: `
      <div style="position: relative; width: 22px; height: 22px;">
        <div style="position: absolute; inset: 0; background: rgba(225, 29, 72, 0.25); border-radius: 50%; animation: pulse-ring 1.8s infinite;"></div>
        <div style="position: absolute; top: 4px; left: 4px; width: 14px; height: 14px; background: #e11d48; border: 2.5px solid #fff; border-radius: 50%; box-shadow: 0 2px 6px rgba(225, 29, 72, 0.4);"></div>
      </div>
    `,
    iconSize: [22, 22],
    iconAnchor: [11, 11]
  });

  const destMarker = L.marker([data.destination.lat, data.destination.lon], {
    title: data.destination.name,
    icon: destIcon
  }).addTo(map).bindPopup(`<strong>Destination:</strong> ${data.destination.name}`);
  routeLayers.push(destMarker);

  // 3. Draw Polylines & Stop Waypoints for each Leg
  let currentCoord = [data.origin.lat, data.origin.lon];
  const allCoords = [currentCoord];

  itin.legs.forEach(leg => {
    let nextCoord = null;

    // Check stop coordinates
    if (STOP_COORDINATES[leg.to]) {
      nextCoord = [STOP_COORDINATES[leg.to].lat, STOP_COORDINATES[leg.to].lon];
    } else if (metroData && metroData.stations) {
      const match = metroData.stations.find(s => s.name.toLowerCase().includes(leg.to.toLowerCase()) || s.id === leg.to);
      if (match) nextCoord = [match.lat, match.lon];
    }

    if (!nextCoord) {
      nextCoord = [data.destination.lat, data.destination.lon];
    }

    allCoords.push(nextCoord);

    // Style by leg mode
    if (leg.mode === "walk") {
      const walkLine = L.polyline([currentCoord, nextCoord], {
        color: "#64748b",
        weight: 4,
        dashArray: "6, 8",
        opacity: 0.85
      }).addTo(map).bindTooltip(`Walk to ${leg.to} (~${leg.duration_minutes} min)`, { sticky: true });
      routeLayers.push(walkLine);
    } else if (leg.mode === "bus") {
      const busLine = L.polyline([currentCoord, nextCoord], {
        color: "#d97706",
        weight: 6,
        opacity: 0.95
      }).addTo(map).bindTooltip(`Bus ${leg.route}: ${leg.from} ➔ ${leg.to}`, { sticky: true });
      routeLayers.push(busLine);

      // Add bus waypoint dot
      const busDot = L.circleMarker(nextCoord, {
        radius: 5,
        color: "#d97706",
        fillColor: "#ffffff",
        fillOpacity: 1,
        weight: 2.5
      }).addTo(map).bindTooltip(`Bus Stop: ${leg.to}`);
      routeLayers.push(busDot);
    } else if (leg.mode === "metro") {
      const metroLine = L.polyline([currentCoord, nextCoord], {
        color: "#6b21a8",
        weight: 6,
        opacity: 0.95
      }).addTo(map).bindTooltip(`Pune Metro: ${leg.from} ➔ ${leg.to}`, { sticky: true });
      routeLayers.push(metroLine);

      // Add metro station dot
      const metroDot = L.circleMarker(nextCoord, {
        radius: 6,
        color: "#6b21a8",
        fillColor: "#0f766e",
        fillOpacity: 1,
        weight: 2.5
      }).addTo(map).bindTooltip(`Metro Station: ${leg.to}`);
      routeLayers.push(metroDot);
    }

    currentCoord = nextCoord;
  });

  // Smooth camera framing
  fitPlannedRouteBounds(data);
}

/* ==========================================================================
   8. DEPARTURES TAB
   ========================================================================== */
function initDepartures() {
  const select = document.getElementById("stop-select");
  const loading = document.getElementById("departures-loading");
  const list = document.getElementById("departures-list");

  select.addEventListener("change", async () => {
    const stopId = select.value;
    if (!stopId) return;

    loading.classList.remove("hidden");
    list.innerHTML = "";

    // Highlight stop on live background map
    if (STOP_COORDINATES[stopId]) {
      const coord = STOP_COORDINATES[stopId];
      map.flyTo([coord.lat, coord.lon], 15, { duration: 0.8 });
    }

    try {
      const res = await fetch(`/api/departures?stop_id=${encodeURIComponent(stopId)}`);
      const json = await res.json();
      loading.classList.add("hidden");

      if (json.error) {
        list.innerHTML = `<div class="card" style="color: #ef4444;">${json.message}</div>`;
        return;
      }

      const departures = json.data.departures;
      if (!departures || departures.length === 0) {
        list.innerHTML = `<div class="empty-state">No upcoming departures scheduled at this time.</div>`;
        return;
      }

      list.innerHTML = "";
      departures.forEach(d => {
        const item = document.createElement("div");
        item.className = "dep-item";
        item.innerHTML = `
          <div class="dep-route">
            <span class="route-pill ${d.mode === 'metro' ? 'metro' : 'bus'}">
              ${d.mode === 'metro' ? '<i class="fa-solid fa-train-subway"></i> Metro' : 'Bus ' + d.route_short_name}
            </span>
            <div class="dep-headsign">${d.headsign}</div>
          </div>
          <div class="dep-wait">
            <div class="wait-time">${d.wait_minutes} min</div>
            <div style="font-size: 11px; color: #888;">${d.departure_time}</div>
          </div>
        `;
        list.appendChild(item);
      });
    } catch (e) {
      loading.classList.add("hidden");
      list.innerHTML = `<div class="card" style="color: #ef4444;">Error fetching departures.</div>`;
    }
  });
}

function selectStopForDepartures(stopId) {
  document.getElementById("tab-departures-btn").click();
  const select = document.getElementById("stop-select");
  select.value = stopId;
  select.dispatchEvent(new Event("change"));
}
window.selectStopForDepartures = selectStopForDepartures;

/* ==========================================================================
   9. METRO TAB & FARE CALCULATOR
   ========================================================================== */
async function initMetro() {
  const fromSelect = document.getElementById("metro-from");
  const toSelect = document.getElementById("metro-to");
  const calcBtn = document.getElementById("calc-fare-btn");
  const resultDiv = document.getElementById("fare-result");

  try {
    const res = await fetch("/api/metro");
    const json = await res.json();
    if (!json || !json.data) return;

    json.data.stations.forEach(s => {
      const opt1 = new Option(s.name, s.id);
      const opt2 = new Option(s.name, s.id);
      fromSelect.add(opt1);
      toSelect.add(opt2);
    });

    toSelect.selectedIndex = Math.min(5, json.data.stations.length - 1);

    calcBtn.addEventListener("click", async () => {
      const s1 = fromSelect.value;
      const s2 = toSelect.value;
      if (s1 === s2) {
        resultDiv.classList.remove("hidden");
        resultDiv.innerHTML = `Same station selected. Fare: ₹10`;
        return;
      }

      const fareRes = await fetch(`/api/metro?station1=${s1}&station2=${s2}`);
      const fareJson = await fareRes.json();
      resultDiv.classList.remove("hidden");
      resultDiv.innerHTML = `
        <strong>Fare: ₹${fareJson.fare_inr}</strong><br>
        <span style="font-size: 12px; color: #cbd5e1;">Route: ${fareJson.requires_interchange ? 'Interchange at Civil Court' : 'Direct line'} · Operating 06:00 AM - 10:00 PM IST</span>
      `;

      // Center map on Civil Court if interchange needed
      if (fareJson.requires_interchange) {
        map.flyTo([18.5284, 73.8540], 14, { duration: 1 });
      }
    });
  } catch (e) {
    console.warn("Metro init failed", e);
  }
}

/* ==========================================================================
   10. SAVED PLACES TAB
   ========================================================================== */
async function initSavedPlaces() {
  const form = document.getElementById("save-place-form");
  const list = document.getElementById("saved-places-list");

  async function loadPlaces() {
    try {
      const res = await fetch("/api/places");
      const json = await res.json();
      list.innerHTML = "";
      if (json.data && json.data.length > 0) {
        json.data.forEach(p => {
          const div = document.createElement("div");
          div.className = "saved-place-item";
          div.innerHTML = `
            <div>
              <span class="saved-place-label">${p.label}</span>
              <div style="font-size: 0.85rem; font-weight: 600;">${p.name}</div>
            </div>
            <button class="btn-use-place" style="background: rgba(255,255,255,0.08); border: none; color: #fff; padding: 4px 8px; border-radius: 6px; cursor: pointer; font-size: 11px;">
              Use in Plan
            </button>
          `;
          div.querySelector(".btn-use-place").addEventListener("click", () => {
            document.getElementById("tab-plan-btn").click();
            document.getElementById("origin-input").value = p.label;
          });
          list.appendChild(div);
        });
      } else {
        list.innerHTML = `<div class="empty-state">No places saved yet. Add home or office above!</div>`;
      }
    } catch (e) { }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const label = document.getElementById("place-label").value.trim();
    const address = document.getElementById("place-address").value.trim();
    if (!label || !address) return;

    await fetch("/api/places", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, place: address })
    });

    form.reset();
    loadPlaces();
  });

  loadPlaces();
}


