"use strict";

(() => {
  const el = (id) => document.getElementById(id);
  const refs = Object.fromEntries([
    "scan-button", "scan-button-text", "mode-badge", "demo-banner", "error-banner", "error-title", "error-message", "error-remediation", "warning-banner", "warning-list", "total-count", "ssid-count", "strongest-signal", "strongest-name", "modern-count", "attention-count", "attention-detail", "scan-metadata", "scan-status", "status-text", "search-input", "band-filter", "sort-select", "results-count", "empty-state", "empty-title", "empty-copy", "table-wrap", "network-rows", "channel-chart", "location-status", "location-dot", "location-copy", "location-button", "insight-copy", "runtime-info", "live-announcement"
  ].map((id) => [id, el(id)]));

  let state = null;
  let sessionToken = null;
  let timer = null;
  let fetching = false;
  let actionPending = false;
  let offline = false;
  let requestError = null;
  let stopped = false;
  let lastAnnouncement = "";
  let lastResultsKey = null;
  const number = (value) => typeof value === "number" && Number.isFinite(value);
  const text = (value, fallback = "Unavailable") => value === null || value === undefined || value === "" ? fallback : String(value);
  const array = (value) => Array.isArray(value) ? value : [];
  const node = (tag, className, value) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (value !== undefined) element.textContent = String(value);
    return element;
  };
  const networks = () => array(state && state.last_result && state.last_result.networks);
  const bandKey = (band) => {
    const value = text(band, "").toLowerCase();
    if (value.includes("2.4")) return "2.4";
    if (/(^|[^0-9])6([^0-9]|$)/.test(value)) return "6";
    if (/(^|[^0-9])5([^0-9]|$)/.test(value)) return "5";
    return "unknown";
  };
  const bandName = (band) => bandKey(band) === "unknown" ? "Band unavailable" : `${bandKey(band)} GHz`;

  async function getToken() {
    if (!sessionToken) {
      const response = await fetch("/api/session", {cache: "no-store", credentials: "same-origin"});
      if (!response.ok) throw new Error("The agent session could not be initialized. Reload this page.");
      const result = await response.json();
      if (!result.token) throw new Error("The agent did not supply a session token. Reload this page.");
      sessionToken = result.token;
    }
    return sessionToken;
  }

  async function action(path) {
    if (actionPending) return;
    actionPending = true;
    requestError = null;
    updateControls();
    try {
      const token = await getToken();
      const response = await fetch(path, {method: "POST", credentials: "same-origin", headers: {"X-Jarvis-Token": token}, cache: "no-store"});
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 403) sessionToken = null;
        const detail = result.error || {};
        requestError = {message: detail.message || `The request was declined (${response.status}).`, remediation: detail.remediation || "Wait a moment and try again."};
        showError(requestError);
      }
      await refresh();
    } catch (error) {
      requestError = {message: error.message || "Could not contact the local agent.", remediation: "Check that the agent is still running, then reload this page."};
      showError(requestError);
    } finally {
      actionPending = false;
      updateControls();
      schedule(1000);
    }
  }

  function showError(error) {
    refs["error-banner"].hidden = !error;
    if (!error) return;
    refs["error-title"].textContent = state && state.last_result ? "The latest scan could not complete." : "The agent needs your attention.";
    refs["error-message"].textContent = text(error.message, "An unknown error occurred.");
    refs["error-remediation"].textContent = text(error.remediation, "");
  }

  function updateControls() {
    const busy = Boolean(state && state.scanning);
    const cooldown = state && number(state.cooldown_seconds) ? Math.ceil(Math.max(0, state.cooldown_seconds)) : 0;
    refs["scan-button"].disabled = !state || actionPending || busy || cooldown > 0 || offline;
    refs["scan-button"].classList.toggle("scanning", busy);
    refs["scan-button-text"].textContent = busy ? "Scanning nearby…" : actionPending ? "Starting…" : cooldown > 0 ? `Ready in ${cooldown}s` : "Scan nearby networks";
    const locationStatus = state && state.diagnostics && state.diagnostics.location && state.diagnostics.location.status;
    const authorized = /authorized|granted/i.test(text(locationStatus, "")) && !/not|un/i.test(text(locationStatus, ""));
    const cannotRequest = state && state.diagnostics && state.diagnostics.location && state.diagnostics.location.can_request === false;
    refs["location-button"].disabled = !state || state.mode === "demo" || actionPending || offline || authorized || cannotRequest;
    refs["location-button"].textContent = authorized ? "Permission granted" : cannotRequest && state.mode !== "demo" ? "Use Mac app to request access" : "Request location permission";
  }

  function renderLocation() {
    const location = (state.diagnostics && state.diagnostics.location) || {};
    const raw = text(location.status, "Unknown");
    const value = raw.replace(/[_-]/g, " ");
    refs["location-status"].textContent = state.mode === "demo" ? "Not used in demo mode" : value.charAt(0).toUpperCase() + value.slice(1);
    const lower = raw.toLowerCase();
    let copy = "macOS may require Location Services to reveal network names and BSSIDs. You can request permission here or review it in System Settings.";
    let color = "#f0c982";
    if (state.mode === "demo") {
      copy = "Sample data is shown. Run the agent in live mode to use Apple’s CoreWLAN API and your Mac’s Wi-Fi interface.";
      color = "#96a7b9";
    } else if (location.services_enabled === false) {
      copy = "Location Services are off. Enable them in System Settings, then allow this app to reveal the details macOS makes available.";
    } else if (/denied|restricted/.test(lower)) {
      copy = "Location access is denied or restricted. Review this app’s permission in System Settings; the agent cannot bypass that choice.";
    } else if (/authorized|granted/.test(lower) && !/not|un/.test(lower)) {
      copy = "Location access is allowed. macOS still controls which Wi-Fi fields are returned. The agent does not request or display geographic coordinates.";
      color = "#6fe2d5";
    } else if (/not.determined|pending|request/.test(lower)) {
      copy = "Choose “Request location permission” and respond to the macOS dialog. If no dialog appears, review the setup steps in the README.";
    }
    if (state.mode !== "demo" && location.can_request === false && location.message) copy = location.message;
    refs["location-copy"].textContent = copy;
    refs["location-dot"].style.backgroundColor = color;
  }

  function renderSummary() {
    const result = state.last_result;
    if (!result) return;
    const items = networks();
    const summary = result.summary || {};
    const total = number(summary.total) ? summary.total : items.length;
    const named = number(summary.visible_ssids) ? summary.visible_ssids : items.filter((item) => item.ssid !== null && item.ssid !== undefined && item.ssid !== "").length;
    refs["total-count"].textContent = String(total);
    refs["ssid-count"].textContent = `${named} named · ${Math.max(0, total - named)} name${total - named === 1 ? "" : "s"} unavailable`;
    const modern = number(summary.modern) ? summary.modern : items.filter((item) => item.security_assessment === "modern").length;
    const open = number(summary.open) ? summary.open : items.filter((item) => item.security_assessment === "open").length;
    const legacy = number(summary.legacy) ? summary.legacy : items.filter((item) => item.security_assessment === "legacy").length;
    const unknown = number(summary.unknown) ? summary.unknown : items.filter((item) => item.security_assessment === "unknown").length;
    refs["modern-count"].textContent = String(modern);
    refs["attention-count"].textContent = String(open + legacy);
    refs["attention-detail"].textContent = `${open} open · ${legacy} legacy · ${unknown} unknown`;
    const strongest = items.filter((item) => number(item.rssi_dbm)).sort((a, b) => b.rssi_dbm - a.rssi_dbm)[0];
    refs["strongest-signal"].replaceChildren();
    if (strongest) {
      refs["strongest-signal"].append(document.createTextNode(String(strongest.rssi_dbm)), node("span", "unit", "dBm"));
      refs["strongest-name"].textContent = text(strongest.ssid, "Network name unavailable");
      refs["strongest-name"].title = text(strongest.ssid, "Network name unavailable");
    } else {
      refs["strongest-signal"].textContent = "—";
      refs["strongest-name"].textContent = "Signal measurement unavailable";
    }
    refs["insight-copy"].textContent = open + legacy > 0 ? "This snapshot includes open or legacy security advertisements. Treat them as a reason to check your own router’s configuration; these labels do not test encryption, passwords, or network trust." : "Signal is a moment in time. A less negative RSSI is stronger; walls, distance, and radio conditions can change the next scan.";
  }

  function renderChannels() {
    refs["channel-chart"].replaceChildren();
    const result = state.last_result;
    const channels = array(result && result.summary && result.summary.channels).filter((item) => number(item.channel) && number(item.count) && item.count > 0);
    if (!channels.length) {
      refs["channel-chart"].append(node("p", "muted", result ? "No channel measurements were returned." : "Channel counts appear after your first scan."));
      return;
    }
    const maximum = Math.max(...channels.map((item) => item.count));
    const sorted = channels.slice().sort((a, b) => bandKey(a.band).localeCompare(bandKey(b.band), "en", {numeric: true}) || a.channel - b.channel);
    for (const item of sorted) {
      const row = node("div", "channel-row");
      const label = `${bandKey(item.band) === "unknown" ? "?" : bandKey(item.band)}G · Ch ${item.channel}`;
      row.setAttribute("aria-label", `${bandName(item.band)}, channel ${item.channel}: ${item.count} observed access point${item.count === 1 ? "" : "s"}`);
      const track = node("div", "channel-track");
      track.setAttribute("aria-hidden", "true");
      const fill = node("div", "channel-fill");
      fill.style.width = `${Math.max(0, Math.min(100, item.count / maximum * 100))}%`;
      track.append(fill);
      row.append(node("span", "channel-label", label), track, node("span", "channel-count", item.count));
      refs["channel-chart"].append(row);
    }
  }

  function renderTable() {
    const result = state && state.last_result;
    const all = networks();
    const query = refs["search-input"].value.trim().toLocaleLowerCase();
    const band = refs["band-filter"].value;
    const items = all.filter((item) => (band === "all" || bandKey(item.band) === band) && (!query || [item.ssid, item.bssid, ...array(item.security)].filter((value) => value !== null && value !== undefined).join(" ").toLocaleLowerCase().includes(query)));
    items.sort((a, b) => {
      if (refs["sort-select"].value === "name") return text(a.ssid, "\uffff").localeCompare(text(b.ssid, "\uffff"));
      if (refs["sort-select"].value === "channel") return (number(a.channel) ? a.channel : Infinity) - (number(b.channel) ? b.channel : Infinity) || bandKey(a.band).localeCompare(bandKey(b.band), "en", {numeric: true});
      return (number(b.rssi_dbm) ? b.rssi_dbm : -Infinity) - (number(a.rssi_dbm) ? a.rssi_dbm : -Infinity) || text(a.ssid).localeCompare(text(b.ssid));
    });
    refs["network-rows"].replaceChildren();
    refs["table-wrap"].hidden = !items.length;
    refs["empty-state"].hidden = items.length > 0;
    refs["results-count"].hidden = !result;
    refs["results-count"].textContent = `${items.length} of ${all.length} observed access point${all.length === 1 ? "" : "s"}`;
    if (!items.length) {
      refs["empty-title"].textContent = !result ? "Ready to discover." : all.length ? "No matching networks." : "No access points returned.";
      refs["empty-copy"].textContent = !result ? "Choose “Scan nearby networks” to take a snapshot. Your Mac’s existing connection stays under macOS control." : all.length ? "Try a different search or select all bands to see more of this snapshot." : "Check Wi-Fi power and the macOS permission status, then try again. An empty scan does not prove there are no networks nearby.";
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const row = node("tr");
      const nameCell = node("td");
      nameCell.append(node("span", `network-name${item.ssid ? "" : " unavailable"}`, text(item.ssid, "Name unavailable")));
      nameCell.append(node("span", "network-bssid", text(item.bssid, "BSSID unavailable")));
      if (array(item.notes).length) nameCell.append(node("div", "network-notes", array(item.notes).join(" · ")));
      const signalCell = node("td");
      const signalLine = node("div", "signal-line");
      const bars = node("span", "signal-bars");
      bars.setAttribute("aria-hidden", "true");
      const percent = number(item.signal_percent) ? Math.max(0, Math.min(100, item.signal_percent)) : null;
      const activeBars = percent === null ? 0 : Math.max(1, Math.ceil(percent / 25));
      for (let i = 0; i < 4; i++) bars.append(node("i", i < activeBars ? "active" : ""));
      signalLine.append(bars, node("span", "", number(item.rssi_dbm) ? `${item.rssi_dbm} dBm` : "Unavailable"));
      signalCell.append(signalLine, node("span", "signal-sub", text(item.signal_label, "Signal unavailable")));
      const noise = number(item.noise_dbm) ? `${item.noise_dbm} dBm` : "—";
      const snr = number(item.snr_db) ? `${item.snr_db} dB` : "—";
      signalCell.append(node("span", "signal-sub", `Noise ${noise} · SNR ${snr}`));
      const channelCell = node("td");
      channelCell.append(node("span", "channel-number", number(item.channel) ? `Ch ${item.channel}` : "Unavailable"), node("span", "channel-sub", bandName(item.band)));
      if (number(item.width_mhz)) channelCell.append(node("span", "channel-sub", `${item.width_mhz} MHz width`));
      const securityCell = node("td");
      const assessment = ["open", "legacy", "modern", "unknown"].includes(item.security_assessment) ? item.security_assessment : "unknown";
      const labels = array(item.security).map((value) => String(value));
      securityCell.append(node("span", `security-badge ${assessment}`, labels.length ? labels.join(" / ") : "Unknown"));
      const securityDescriptions = {open: "Advertised open access", legacy: "Legacy security advertised", modern: "Modern family advertised", unknown: "Not exposed by macOS"};
      securityCell.append(node("div", "security-detail", securityDescriptions[assessment]));
      row.append(nameCell, signalCell, channelCell, securityCell);
      fragment.append(row);
    }
    refs["network-rows"].append(fragment);
  }

  function render() {
    refs["mode-badge"].textContent = state.mode === "demo" ? "Demo · sample data" : "Live · CoreWLAN";
    refs["mode-badge"].classList.toggle("demo", state.mode === "demo");
    refs["demo-banner"].hidden = state.mode !== "demo";
    showError(state.error || requestError);
    const result = state.last_result;
    const warnings = state.mode === "demo" ? [] : [...new Set(array(result && result.warnings))];
    refs["warning-banner"].hidden = !warnings.length;
    refs["warning-list"].replaceChildren(...warnings.map((warning) => node("div", "", warning)));
    refs["scan-status"].classList.toggle("busy", Boolean(state.scanning));
    refs["scan-status"].classList.toggle("stale", Boolean(state.error && result));
    refs["status-text"].textContent = state.scanning ? "Scanning" : state.error && result ? "Previous results" : state.error ? "Needs attention" : result ? "Snapshot ready" : "Ready";
    if (result) {
      const date = new Date(result.timestamp);
      const stamp = Number.isNaN(date.getTime()) ? text(result.timestamp) : date.toLocaleString([], {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit"});
      const duration = number(result.duration_seconds) ? ` · ${result.duration_seconds.toFixed(1)}s` : "";
      refs["scan-metadata"].textContent = `${state.mode === "demo" ? "Sample snapshot" : "Last scan"} ${stamp} · ${text(result.interface, "Interface unavailable")}${duration}${state.error ? " · previous results retained" : ""}`;
    }
    const diagnostic = state.diagnostics || {};
    refs["runtime-info"].textContent = [diagnostic.platform, diagnostic.architecture, state.version ? `v${state.version}` : null].filter(Boolean).join(" · ") || "Local dashboard · no cloud services";
    renderLocation();
    renderSummary();
    const resultsKey = JSON.stringify(result);
    if (lastResultsKey !== resultsKey) {
      lastResultsKey = resultsKey;
      renderTable();
      renderChannels();
    }
    updateControls();
    const announcement = state.scanning ? "Scanning nearby Wi-Fi networks." : state.error ? text(state.error.message) : result ? `Scan complete. ${networks().length} access points observed.` : "Agent ready. Scanning starts when you choose.";
    if (announcement !== lastAnnouncement) {
      refs["live-announcement"].textContent = announcement;
      lastAnnouncement = announcement;
    }
  }

  function schedule(milliseconds) {
    clearTimeout(timer);
    if (stopped) return;
    timer = setTimeout(refresh, milliseconds === undefined ? state && (state.scanning || state.cooldown_seconds > 0) ? 1000 : 5000 : milliseconds);
  }

  async function refresh() {
    if (fetching || stopped) return;
    fetching = true;
    try {
      const response = await fetch("/api/state", {cache: "no-store", credentials: "same-origin"});
      if (!response.ok) throw new Error(`The local agent returned an error (${response.status}).`);
      const result = await response.json();
      if (!result || !["live", "demo"].includes(result.mode)) throw new Error("The agent returned an unexpected response.");
      state = result;
      offline = false;
      render();
    } catch (error) {
      offline = true;
      showError({message: error.message || "The local agent is unavailable.", remediation: "Keep the agent running in Terminal or its app, then reload this page. Any displayed scan is an older snapshot."});
      refs["status-text"].textContent = "Agent unavailable";
      refs["scan-status"].classList.add("stale");
      refs["scan-status"].classList.remove("busy");
      updateControls();
    } finally {
      fetching = false;
      schedule();
    }
  }

  refs["scan-button"].addEventListener("click", () => action("/api/scan"));
  refs["location-button"].addEventListener("click", () => action("/api/location/request"));
  refs["search-input"].addEventListener("input", renderTable);
  refs["band-filter"].addEventListener("change", renderTable);
  refs["sort-select"].addEventListener("change", renderTable);
  el("stop-button").addEventListener("click", async () => {
    try {
      const token = await getToken();
      const response = await fetch("/api/shutdown", {method: "POST", headers: {"X-Jarvis-Token": token}});
      if (!response.ok) throw new Error("Could not stop the agent. Reload and try again.");
      stopped = true;
      clearTimeout(timer);
      offline = true;
      updateControls();
      el("stop-button").disabled = true;
      el("stop-button").textContent = "Agent stopped";
      refs["status-text"].textContent = "Agent stopped";
      showError({message: "The local agent has stopped. You can close this page.", remediation: "Open the Mac app or Launch Jarvis.command to start it again."});
      refs["error-title"].textContent = "Session ended";
    } catch (error) {
      showError({message: error.message, remediation: "You can also stop the agent with Control-C in its Terminal window."});
    }
  });
  refresh();
})();
