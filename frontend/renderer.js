/**
 * StintLab — Renderer Process
 * Handles: navigation, WebSocket connection to backend, live telemetry rendering.
 */

"use strict";

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  ws: null,
  connected: false,
  lastFrame: null,
  lastFuelPct: null,
  fuelPerLap: 0,
  prevLapMs: null,
  prevPosition: null,
};

const PW_MAX_EVENTS = 12;
const PW_RPM_MAX = 9000;
const PW_SPEED_MAX = 320; // km/h, just for the bar scale

// ─── LED strip setup ──────────────────────────────────────────────────────────
const LED_COUNT = 18;
const ledStrip = document.getElementById("led-strip");
const leds = [];

for (let i = 0; i < LED_COUNT; i++) {
  const el = document.createElement("div");
  el.className = "led";
  ledStrip.appendChild(el);
  leds.push(el);
}

function updateLEDs(rpm, maxRpm = 8500) {
  const ratio = Math.min(1, rpm / maxRpm);
  const lit = Math.round(ratio * LED_COUNT);

  leds.forEach((led, i) => {
    led.className = "led";
    if (i < lit) {
      const pos = i / LED_COUNT;
      if (pos < 0.5)       led.classList.add("active-green");
      else if (pos < 0.78) led.classList.add("active-yellow");
      else                 led.classList.add("active-red");
    }
  });
}

// Idle pulse animation when not connected
let idleLedPhase = 0;
function idleLedTick() {
  if (state.connected) return;
  leds.forEach((led, i) => {
    led.className = "led";
    const wave = Math.sin((i / LED_COUNT) * Math.PI * 2 - idleLedPhase);
    if (wave > 0.6) led.classList.add("active-cyan");
  });
  idleLedPhase += 0.12;
  requestAnimationFrame(idleLedTick);
}
idleLedTick();

// ─── Navigation ───────────────────────────────────────────────────────────────
// Single navigation function: used by toolbar clicks AND keyboard shortcuts.
function navigateTo(page) {
  const tab = document.querySelector(`.nav-tab[data-page="${page}"]`);
  const pageEl = document.getElementById("page-" + page);
  if (!tab || !pageEl || tab.disabled) return;

  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  tab.classList.add("active");
  pageEl.classList.add("active");
}

// Navigable pages = enabled toolbar tabs, in toolbar (DOM) order.
// "Coming soon" tabs are disabled and have no data-page, so they are skipped.
const getNavTabs = () =>
  Array.from(document.querySelectorAll(".nav-tab[data-page]:not(:disabled)"));

function navigateToIndex(i) {
  const tab = getNavTabs()[i];
  if (tab) navigateTo(tab.dataset.page);
}

function navigateRelative(step) {
  const tabs = getNavTabs();
  if (tabs.length === 0) return;
  const current = tabs.findIndex(t => t.classList.contains("active"));
  const next = (current + step + tabs.length) % tabs.length; // wraps around
  navigateTo(tabs[next].dataset.page);
}

document.querySelectorAll(".nav-tab[data-page]").forEach(tab => {
  tab.addEventListener("click", () => navigateTo(tab.dataset.page));
});

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────
// ⌘ on macOS (metaKey), Ctrl on Windows/Linux (ctrlKey).
const IS_MAC = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
const modLabel = (key) => (IS_MAC ? `⌘${key}` : `Ctrl+${key}`);

// To add a shortcut: append an entry here. `match` receives the KeyboardEvent
// (the Cmd/Ctrl modifier is already verified); `run` performs the action.
const SHORTCUTS = [
  // Mod+1..9 → nth toolbar page (uses e.code so it is layout-independent)
  {
    match: (e) => /^Digit[1-9]$/.test(e.code) && !e.shiftKey && !e.altKey,
    run:   (e) => navigateToIndex(Number(e.code.slice(5)) - 1),
  },
  // Mod+[ / Mod+] → previous / next page (uses e.key so AltGr layouts work)
  { match: (e) => e.key === "[", run: () => navigateRelative(-1) },
  { match: (e) => e.key === "]", run: () => navigateRelative(1) },
];

function isTypingTarget(target) {
  return target instanceof Element &&
    (target.closest("input, textarea") !== null || target.isContentEditable);
}

document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented || e.repeat || e.isComposing) return;

  const modOk = IS_MAC ? (e.metaKey && !e.ctrlKey) : (e.ctrlKey && !e.metaKey);
  if (!modOk || isTypingTarget(e.target)) return;

  const shortcut = SHORTCUTS.find(s => s.match(e));
  if (!shortcut) return;

  e.preventDefault();
  shortcut.run(e);
});

// Toolbar tooltips: "Dashboard (⌘2)" / "Dashboard (Ctrl+2)".
// Built from the existing button label — no locale file needed.
getNavTabs().slice(0, 9).forEach((tab, i) => {
  const label = tab.textContent.trim() || tab.dataset.page;
  tab.title = `${label} (${modLabel(i + 1)})`;
  tab.setAttribute("aria-keyshortcuts", `${IS_MAC ? "Meta" : "Control"}+${i + 1}`);
});

// ─── Game selection ───────────────────────────────────────────────────────────
window.selectGame = function(game) {
  document.getElementById("card-gt7").style.boxShadow =
    game === "gt7" ? "0 0 24px rgba(0, 229, 255, 0.4)" : "";
};

// ─── WebSocket connection ─────────────────────────────────────────────────────
window.connectBackend = function() {
  const host = document.getElementById("ws-host").value.trim() || "127.0.0.1";
  const port = document.getElementById("ws-port").value.trim() || "8765";
  const ps5Ip = document.getElementById("ps5-ip").value.trim();
  const url = `ws://${host}:${port}`;

  setStatus("connecting", `Connecting to ${url}…`);

  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }

  try {
    state.ws = new WebSocket(url);
  } catch (e) {
    setStatus("error", `Invalid address: ${e.message}`);
    return;
  }

  state.ws.onopen = () => {
    state.connected = true;
    setStatus("connected", `Connected to backend at <span>${url}</span>`);

    // Send PS5 IP if provided
    if (ps5Ip) {
      state.ws.send(JSON.stringify({ action: "set_ps5_ip", ip: ps5Ip }));
    }

    // Start pinging
    state._pingInterval = setInterval(() => {
      if (state.ws?.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ action: "ping" }));
      }
    }, 5000);
  };

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (e) {
      console.warn("Bad WS message:", e);
    }
  };

  state.ws.onerror = () => {
    setStatus("error", "Connection error — is the backend running?");
  };

  state.ws.onclose = () => {
    state.connected = false;
    clearInterval(state._pingInterval);
    setStatus("error", "Disconnected from backend.");
    document.getElementById("disconnected-overlay").classList.remove("hidden");
  };
};

function handleMessage(msg) {
  switch (msg.type) {
    case "telemetry":
      handleTelemetry(msg.data);
      break;
    case "status":
      handleBackendStatus(msg.data);
      break;
    case "strategy":
      handleStrategy(msg.data);
      break;
    case "event":
      handleLiveEvent(msg.data);
      break;
    case "pong":
      break;
    case "ack":
      if (msg.action === "set_ps5_ip") {
        setStatus("connected", `PS5 set to <span>${msg.ip}</span> — waiting for packets…`);
      }
      break;
  }
}

function handleBackendStatus(data) {
  if (data.connected) {
    setStatus("connected", `GT7 telemetry active — <span>${data.frames_received} frames</span> from <span>${data.source_ip}</span>`);
  }
}

// ─── Status UI helpers ────────────────────────────────────────────────────────
function setStatus(type, html) {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");

  dot.className = "status-dot";
  if (type === "connected")  dot.classList.add("connected");
  if (type === "connecting") dot.classList.add("connecting");
  if (type === "error")      dot.classList.add("error");

  text.innerHTML = html;
}

// ─── Telemetry rendering ──────────────────────────────────────────────────────
function handleTelemetry(d) {
  state.lastFrame = d;

  // Show dashboard, hide overlay
  document.getElementById("disconnected-overlay").classList.add("hidden");

  // Gear & Speed
  const gear = d.gear === 0 ? "N" : d.gear === -1 ? "R" : String(d.gear);
  document.getElementById("gear-display").textContent = gear;
  document.getElementById("speed-display").textContent = `${Math.round(d.speed)} KM/H`;

  // Position / Lap / Paused
  document.getElementById("d-position").textContent = d.position > 0 ? d.position : "—";
  document.getElementById("d-lap").textContent = d.lap_number > 0 ? d.lap_number : "—";
  document.getElementById("d-paused").textContent = d.paused ? "Y" : "N";

  // Lap times
  document.getElementById("d-lap-current").textContent = fmtTime(d.lap_time_ms);
  document.getElementById("d-lap-last").textContent    = fmtTime(d.last_lap_ms);
  document.getElementById("d-lap-best").textContent    = fmtTime(d.best_lap_ms);

  // RPM bar
  updateRPMBar(d.rpm);

  // Tyre temps
  document.getElementById("t-fl").textContent = Math.round(d.tyre_temp_fl) || "—";
  document.getElementById("t-fr").textContent = Math.round(d.tyre_temp_fr) || "—";
  document.getElementById("t-rl").textContent = Math.round(d.tyre_temp_rl) || "—";
  document.getElementById("t-rr").textContent = Math.round(d.tyre_temp_rr) || "—";

  // Inputs (0–100)
  document.getElementById("d-brake").textContent    = Math.round(d.brake * 100);
  document.getElementById("d-throttle").textContent = Math.round(d.throttle * 100);

  // Fuel
  document.getElementById("d-fuel-pct").innerHTML =
    `${d.fuel_level.toFixed(1)}<span class="fuel-stat-unit">%</span>`;

  // Estimate fuel per lap from delta between laps
  if (state.lastFuelPct !== null && d.lap_number !== state.prevLap) {
    const delta = state.lastFuelPct - d.fuel_level;
    if (delta > 0 && delta < 30) state.fuelPerLap = delta;
    state.prevLap = d.lap_number;
  }
  state.lastFuelPct = d.fuel_level;

  const fpl = state.fuelPerLap || d.fuel_per_lap || 0;
  const lapsLeft = fpl > 0 ? (d.fuel_level / fpl).toFixed(1) : "—";

  document.getElementById("d-fuel-per-lap").innerHTML =
    `${fpl.toFixed(1)}<span class="fuel-stat-unit">%</span>`;
  document.getElementById("d-laps-left").textContent = lapsLeft;

  // Total laps
  document.getElementById("d-total-laps").textContent = d.total_laps > 0 ? d.total_laps : "—";
  document.getElementById("d-car-id").textContent = d.car_id || "—";

  // LED strip
  updateLEDs(d.rpm);

  // Pitwall (own page, safe to update even while not visible)
  updatePitwall(d);

  // Clock
  const now = new Date();
  document.getElementById("d-time").textContent = now.toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

// ─── RPM bar renderer ─────────────────────────────────────────────────────────
function updateRPMBar(rpm) {
  const container = document.getElementById("rpm-bar");
  const SEG = 20;
  const MAX = 9000;

  if (container.children.length !== SEG) {
    container.innerHTML = "";
    for (let i = 0; i < SEG; i++) {
      const seg = document.createElement("div");
      seg.className = "rpm-seg";
      container.appendChild(seg);
    }
  }

  const ratio = Math.min(1, rpm / MAX);
  const lit = Math.round(ratio * SEG);
  const segs = container.querySelectorAll(".rpm-seg");

  segs.forEach((seg, i) => {
    seg.className = "rpm-seg";
    if (i < lit) {
      const pos = i / SEG;
      const h = 20 + (i / SEG) * 80;
      seg.style.height = h + "%";
      if (pos < 0.55)      seg.classList.add("lit-green");
      else if (pos < 0.80) seg.classList.add("lit-yellow");
      else                 seg.classList.add("lit-red");
    } else {
      seg.style.height = "10%";
    }
  });

  document.getElementById("d-rpm").textContent = Math.round(rpm).toLocaleString();
}

// ─── Pitwall ───────────────────────────────────────────────────────────────
function updatePitwall(d) {
  // Race control
  const posEl = document.getElementById("pw-position");
  const deltaEl = document.getElementById("pw-position-delta");
  if (posEl) posEl.textContent = d.position > 0 ? "P" + d.position : "—";

  if (deltaEl) {
    if (state.prevPosition !== null && d.position > 0 && d.position !== state.prevPosition) {
      const gained = state.prevPosition - d.position; // fewer = better
      deltaEl.textContent = (gained > 0 ? "▲ +" : "▼ ") + Math.abs(gained);
      deltaEl.className = "pw-position-delta " + (gained > 0 ? "up" : "down");
    } else if (state.prevPosition === null) {
      deltaEl.textContent = "";
      deltaEl.className = "pw-position-delta";
    }
  }
  if (d.position > 0) state.prevPosition = d.position;

  const lapEl = document.getElementById("pw-lap");
  if (lapEl) lapEl.textContent = d.lap_number > 0 ? d.lap_number : "—";
  const lastLapEl = document.getElementById("pw-last-lap");
  if (lastLapEl) lastLapEl.textContent = fmtTime(d.last_lap_ms);

  // Tyres — temp always available; slip only meaningful once the backend
  // sends it (falls back to "—" on older frames without the field).
  const tyreMap = { fl: "fl", fr: "fr", rl: "rl", rr: "rr" };
  for (const corner of Object.keys(tyreMap)) {
    const tEl = document.getElementById(`pw-t-${corner}`);
    const sEl = document.getElementById(`pw-s-${corner}`);
    const temp = d[`tyre_temp_${corner}`];
    const slip = d[`slip_${corner}`];
    if (tEl) tEl.textContent = (temp !== undefined ? Math.round(temp) : "—") + "°";
    if (sEl) sEl.textContent = "slip " + (slip !== undefined ? slip.toFixed(2) : "—");
  }

  // Telemetry bars
  setPwBar("speed", d.speed, PW_SPEED_MAX, Math.round(d.speed) + " km/h");
  setPwBar("rpm", d.rpm, PW_RPM_MAX, Math.round(d.rpm).toLocaleString());
  setPwBar("throttle", d.throttle * 100, 100, Math.round(d.throttle * 100) + "%");
  setPwBar("brake", d.brake * 100, 100, Math.round(d.brake * 100) + "%");
}

function setPwBar(key, value, max, label) {
  const fill = document.getElementById(`pw-b-${key}`);
  const val = document.getElementById(`pw-v-${key}`);
  if (fill) fill.style.width = Math.max(0, Math.min(100, (value / max) * 100)) + "%";
  if (val) val.textContent = label;
}

function handleStrategy(s) {
  const fuelEl = document.getElementById("pw-fuel");
  if (fuelEl && state.lastFrame) fuelEl.textContent = state.lastFrame.fuel_level.toFixed(1) + "%";

  const avgEl = document.getElementById("pw-avg-fuel");
  if (avgEl) avgEl.textContent = s.avg_fuel_per_lap != null ? s.avg_fuel_per_lap.toFixed(1) + "%" : "—";

  const lapsEl = document.getElementById("pw-laps-to-empty");
  if (lapsEl) {
    lapsEl.textContent = s.laps_to_empty != null ? s.laps_to_empty.toFixed(1) : "—";
    lapsEl.className = "pw-stat-value" +
      (s.warning === "red" ? " warn-red" : s.warning === "amber" ? " warn-amber" : "");
  }

  const pitEl = document.getElementById("pw-pit-window");
  if (pitEl) {
    if (s.pit_before_lap != null) {
      let txt = "by lap " + s.pit_before_lap;
      if (s.fuel_ok_for_race === false && s.fuel_shortfall_pct != null) {
        txt += ` (${s.fuel_shortfall_pct.toFixed(1)}% short)`;
      }
      pitEl.textContent = txt;
    } else {
      pitEl.textContent = "—";
    }
  }
}

function handleLiveEvent(ev) {
  const list = document.getElementById("pw-events-list");
  if (!list) return;

  const empty = list.querySelector(".pw-events-empty");
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = "pw-event-item sev-" + (ev.severity || "info");
  item.innerHTML = `<span class="pw-event-lap">L${ev.lap}</span><span>${ev.message}</span>`;
  list.appendChild(item);

  while (list.children.length > PW_MAX_EVENTS) {
    list.removeChild(list.firstChild);
  }
}

// ─── Time formatter ───────────────────────────────────────────────────────────
function fmtTime(ms) {
  if (!ms || ms <= 0) return "--:--.---";
  const totalSec = Math.floor(ms / 1000);
  const min  = Math.floor(totalSec / 60);
  const sec  = totalSec % 60;
  const milli = ms % 1000;
  return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}.${String(milli).padStart(3, "0")}`;
}

// ─── Clock tick (even without telemetry) ─────────────────────────────────────
setInterval(() => {
  const now = new Date();
  document.getElementById("d-time").textContent = now.toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", hour12: true,
  });
}, 1000);