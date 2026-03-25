const BOOT_LINES = [
  { level: "info", text: "Powering S3M NAC terminal..." },
  { level: "ok", text: "FastAPI policy engine link established" },
  { level: "ok", text: "FreeRADIUS AAA transport online" },
  { level: "ok", text: "PostgreSQL source of truth mounted" },
  { level: "ok", text: "Redis session cache synchronized" },
  { level: "dim", text: "Cookie-backed dashboard session enabled" },
  { level: "warn", text: "Live backend mode active. Demo fallbacks disabled." },
];

const QUICK_LOGINS = {
  admin: {
    username: "admin01",
    password: "admin123",
    callingStationId: "",
  },
  employee: {
    username: "employee01",
    password: "employee123",
    callingStationId: "",
  },
  guest: {
    username: "guest01",
    password: "guest123",
    callingStationId: "",
  },
  mab: {
    username: "aa:bb:cc:dd:ee:ff",
    password: "aa:bb:cc:dd:ee:ff",
    callingStationId: "aa:bb:cc:dd:ee:ff",
  },
};

const ROLE_THEMES = {
  admin: {
    color: "#ff7a18",
    background: "#261003",
    glow: "rgba(255, 122, 24, 0.26)",
  },
  employee: {
    color: "#00e5ff",
    background: "#031a24",
    glow: "rgba(0, 229, 255, 0.24)",
  },
  guest: {
    color: "#ffd84d",
    background: "#221b06",
    glow: "rgba(255, 216, 77, 0.24)",
  },
  mab: {
    color: "#6cff8a",
    background: "#071d0d",
    glow: "rgba(108, 255, 138, 0.24)",
  },
};

const ROLE_PERMISSIONS = {
  admin: [
    { label: "Global session visibility", allow: true },
    { label: "Provision new identities", allow: true },
    { label: "Inspect VLAN policy map", allow: true },
    { label: "Restricted to guest internet only", allow: false },
  ],
  employee: [
    { label: "Corporate access VLAN", allow: true },
    { label: "Own session telemetry", allow: true },
    { label: "Provision identities", allow: false },
    { label: "Global network visibility", allow: false },
  ],
  guest: [
    { label: "Guest internet VLAN", allow: true },
    { label: "Temporary access posture", allow: true },
    { label: "Corporate admin tools", allow: false },
    { label: "All-session visibility", allow: false },
  ],
  mab: [
    { label: "Device-based network admission", allow: true },
    { label: "Automated endpoint profiling", allow: true },
    { label: "Human dashboard admin rights", allow: false },
    { label: "Manual policy override", allow: false },
  ],
};

const HANDSHAKE_STEPS = [
  "Client prepared access-request packet",
  "FreeRADIUS received credentials over AAA transport",
  "RADIUS authorize stage queried FastAPI policy engine",
  "FastAPI validated credentials and policy",
  "Accounting start prepared for dashboard session",
];

const PULSE_INTERVAL_MS = 10000;
const CLOCK_INTERVAL_MS = 1000;

const state = {
  viewer: null,
  overview: null,
  clockTimer: null,
  pulseTimer: null,
  toastTimer: null,
  packetLog: [],
  traffic: {
    inputOctets: 0,
    outputOctets: 0,
  },
};

const elements = {
  bootLog: document.getElementById("boot-log"),
  bootScreen: document.getElementById("boot-screen"),
  loginScreen: document.getElementById("login-screen"),
  handshakeScreen: document.getElementById("handshake-screen"),
  dashboardScreen: document.getElementById("dashboard-screen"),
  connectionStatus: document.getElementById("connection-status"),
  loginUsername: document.getElementById("login-username"),
  loginPassword: document.getElementById("login-password"),
  loginCallingStation: document.getElementById("login-calling-station"),
  loginButton: document.getElementById("login-button"),
  quickButtons: Array.from(document.querySelectorAll(".quick-btn")),
  handshakeUser: document.getElementById("handshake-user"),
  handshakePackets: document.getElementById("handshake-packets"),
  handshakeLog: document.getElementById("handshake-log"),
  viewerUsername: document.getElementById("viewer-username"),
  viewerRole: document.getElementById("viewer-role"),
  viewerSessionTimer: document.getElementById("viewer-session-timer"),
  networkDeviceLabel: document.getElementById("network-device-label"),
  networkVlanLabel: document.getElementById("network-vlan-label"),
  profileAvatar: document.getElementById("profile-avatar"),
  profileName: document.getElementById("profile-name"),
  profileRoleBadge: document.getElementById("profile-role-badge"),
  profileInfo: document.getElementById("profile-info"),
  packetLog: document.getElementById("packet-log"),
  vlanNumber: document.getElementById("vlan-number"),
  radiusAttrTable: document.getElementById("radius-attr-table"),
  permissionGrid: document.getElementById("permission-grid"),
  sessionInfo: document.getElementById("session-info"),
  adminShell: document.getElementById("admin-shell"),
  adminMeta: document.getElementById("admin-meta"),
  summaryTotalUsers: document.getElementById("summary-total-users"),
  summaryActiveUsers: document.getElementById("summary-active-users"),
  summaryBlockedUsers: document.getElementById("summary-blocked-users"),
  summaryActiveSessions: document.getElementById("summary-active-sessions"),
  createUserForm: document.getElementById("create-user-form"),
  createUsername: document.getElementById("create-username"),
  createPassword: document.getElementById("create-password"),
  createGroup: document.getElementById("create-group"),
  createAuthType: document.getElementById("create-auth-type"),
  groupPolicyFeed: document.getElementById("group-policy-feed"),
  usersTable: document.getElementById("users-table"),
  sessionsTable: document.getElementById("sessions-table"),
  activityFeed: document.getElementById("activity-feed"),
  logoutButton: document.getElementById("logout-button"),
  toast: document.getElementById("toast"),
};

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showScreen(screen) {
  [elements.bootScreen, elements.loginScreen, elements.handshakeScreen, elements.dashboardScreen].forEach(
    (node) => node.classList.remove("active")
  );
  screen.classList.add("active");
}

function formatTimestamp(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date);
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(Number(totalSeconds) || 0, 0);
  const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const secs = String(seconds % 60).padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
}

function formatTraffic(inputOctets, outputOctets) {
  return `${Number(inputOctets || 0)} in / ${Number(outputOctets || 0)} out`;
}

function inferThemeKey(viewer) {
  if (!viewer) return "mab";
  if (viewer.auth_method === "mab") return "mab";
  return viewer.groupname || "guest";
}

function applyTheme(viewer) {
  const theme = ROLE_THEMES[inferThemeKey(viewer)] || ROLE_THEMES.mab;
  const root = document.documentElement;
  root.style.setProperty("--role-c", theme.color);
  root.style.setProperty("--role-bg", theme.background);
  root.style.setProperty("--role-glow", theme.glow);
}

function addPacketLog(message, level = "info") {
  state.packetLog.unshift({
    level,
    message,
    time: new Date().toISOString(),
  });
  state.packetLog = state.packetLog.slice(0, 10);
  renderPacketLog();
}

function renderPacketLog() {
  if (!state.packetLog.length) {
    elements.packetLog.innerHTML = '<div class="packet-entry">No packet exchange recorded yet</div>';
    return;
  }

  elements.packetLog.innerHTML = state.packetLog
    .map(
      (entry) => `
        <div class="packet-entry ${escapeHtml(entry.level)}">
          <span class="time">${escapeHtml(formatTimestamp(entry.time))}</span>
          <span class="message">${escapeHtml(entry.message)}</span>
        </div>
      `
    )
    .join("");
}

function showToast(message, variant = "error") {
  elements.toast.textContent = message;
  elements.toast.style.borderColor = variant === "ok" ? "#00ff88" : "#ff6666";
  elements.toast.style.color = variant === "ok" ? "#8dffb0" : "#ff8888";
  elements.toast.classList.add("show");

  if (state.toastTimer) {
    window.clearTimeout(state.toastTimer);
  }

  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 3200);
}

async function fetchJson(url, { method = "GET", body } = {}) {
  const response = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });

  const text = await response.text();
  let payload = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload ? payload.detail : payload;
    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || {})
    );
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

async function bootSequence() {
  elements.bootLog.innerHTML = "";
  for (const line of BOOT_LINES) {
    const row = document.createElement("div");
    row.className = line.level;
    row.textContent = `[${line.level.toUpperCase()}] ${line.text}`;
    elements.bootLog.appendChild(row);
    await sleep(170);
  }
}

async function updateConnectionStatus() {
  try {
    const health = await fetchJson("/health");
    elements.connectionStatus.textContent = `API STATUS // ${String(
      health.status || "ok"
    ).toUpperCase()}`;
    return true;
  } catch (error) {
    elements.connectionStatus.textContent = `API STATUS // OFFLINE (${error.message})`;
    return false;
  }
}

function populateQuickLogin(kind) {
  const preset = QUICK_LOGINS[kind];
  if (!preset) return;

  elements.loginUsername.value = preset.username;
  elements.loginPassword.value = preset.password;
  elements.loginCallingStation.value = preset.callingStationId;
}

function currentSession() {
  return state.overview?.current_session || null;
}

function currentUser() {
  return state.overview?.current_user || null;
}

function updateTrafficFromSession(session) {
  state.traffic.inputOctets = Number(session?.input_octets || 0);
  state.traffic.outputOctets = Number(session?.output_octets || 0);
}

function renderProfile() {
  const viewer = state.viewer;
  const session = currentSession();
  const user = currentUser();
  const authMethod = viewer?.auth_method === "mab" ? "MAB" : "PAP";

  elements.viewerUsername.textContent = viewer?.username || "-";
  elements.viewerRole.textContent = `${(viewer?.groupname || "unknown").toUpperCase()} / ${authMethod}`;
  elements.networkDeviceLabel.textContent = viewer?.calling_station_id || viewer?.username || "DEVICE";
  elements.networkVlanLabel.textContent = `VLAN ${viewer?.vlan || "-"}`;
  elements.profileAvatar.textContent = (viewer?.username || "?").slice(0, 2).toUpperCase();
  elements.profileName.textContent = viewer?.username || "-";
  elements.profileRoleBadge.textContent = `${(viewer?.groupname || "unknown").toUpperCase()} // ${authMethod}`;
  elements.vlanNumber.textContent = viewer?.vlan || "-";

  elements.profileInfo.innerHTML = [
    ["Auth Method", authMethod],
    ["Group", viewer?.groupname || "-"],
    ["NAS IP", viewer?.nas_ip || "-"],
    ["Framed IP", viewer?.framed_ip || "-"],
    ["Calling-Station", viewer?.calling_station_id || "-"],
    ["Status", user?.status || "active"],
  ]
    .map(
      ([key, value]) => `
        <div class="info-row">
          <span class="info-key">${escapeHtml(key)}</span>
          <span class="info-val">${escapeHtml(value)}</span>
        </div>
      `
    )
    .join("");

  const replyAttributes = viewer?.reply_attributes || {};
  const rows = Object.entries(replyAttributes);
  elements.radiusAttrTable.innerHTML = rows.length
    ? rows
        .map(
          ([key, value]) => `
            <tr>
              <td class="attr-key">${escapeHtml(key)}</td>
              <td class="attr-op">:=</td>
              <td class="attr-val">${escapeHtml(value)}</td>
            </tr>
          `
        )
        .join("")
    : '<tr><td class="attr-val">No RADIUS reply attributes</td></tr>';

  const permissionKey = viewer?.auth_method === "mab" ? "mab" : viewer?.groupname || "guest";
  const permissions = ROLE_PERMISSIONS[permissionKey] || [];
  elements.permissionGrid.innerHTML = permissions
    .map(
      (item) => `
        <div class="permission-item ${item.allow ? "allow" : "deny"}">
          <span class="permission-dot"></span>
          <span>${escapeHtml(item.label)}</span>
        </div>
      `
    )
    .join("");

  elements.sessionInfo.innerHTML = [
    ["Session ID", viewer?.session_id || "-"],
    ["Unique ID", viewer?.unique_id || "-"],
    ["Started At", formatTimestamp((viewer?.started_at || 0) * 1000)],
    ["Source", session?.source || "dashboard"],
    ["Session Time", formatDuration(session?.session_time || 0)],
    [
      "Traffic",
      formatTraffic(session?.input_octets || 0, session?.output_octets || 0),
    ],
  ]
    .map(
      ([key, value]) => `
        <div class="info-row">
          <span class="info-key">${escapeHtml(key)}</span>
          <span class="info-val">${escapeHtml(value)}</span>
        </div>
      `
    )
    .join("");
}

function statusBadge(status) {
  const normalized = String(status || "unknown").toLowerCase();
  const extraClass = normalized.includes("blocked")
    ? "warn"
    : normalized.includes("reject")
      ? "error"
      : "";

  return `<span class="status-badge ${extraClass}">${escapeHtml(status || "unknown")}</span>`;
}

function renderAdminOverview() {
  const overview = state.overview;
  if (!overview) return;

  const summary = overview.summary || {};
  elements.summaryTotalUsers.textContent = String(summary.total_users || 0);
  elements.summaryActiveUsers.textContent = String(summary.active_users || 0);
  elements.summaryBlockedUsers.textContent = String(summary.blocked_users || 0);
  elements.summaryActiveSessions.textContent = String(summary.active_sessions || 0);
  elements.adminMeta.textContent = `Source: ${summary.source_of_truth || "unknown"} / cache-only: ${
    summary.cache_only_sessions || 0
  }`;

  const groupPolicies = overview.group_policies || {};
  const policyGroups = Object.entries(groupPolicies);
  elements.groupPolicyFeed.innerHTML = policyGroups.length
    ? policyGroups
        .map(
          ([groupname, attrs]) => `
            <div class="policy-entry">
              <div><strong>${escapeHtml(groupname)}</strong></div>
              ${Object.entries(attrs)
                .map(
                  ([key, value]) =>
                    `<div class="info-row"><span class="info-key">${escapeHtml(
                      key
                    )}</span><span class="info-val">${escapeHtml(value)}</span></div>`
                )
                .join("")}
            </div>
          `
        )
        .join("")
    : '<div class="policy-entry">No group policy data</div>';

  const users = overview.users || [];
  elements.usersTable.innerHTML = users.length
    ? users
        .map(
          (user) => `
            <tr>
              <td>${escapeHtml(user.username)}</td>
              <td>${escapeHtml(user.groupname)}</td>
              <td>${statusBadge(user.status)}</td>
              <td>${escapeHtml(user.active_session_count || 0)}</td>
              <td>${escapeHtml(user.block_ttl ?? "-")}</td>
            </tr>
          `
        )
        .join("")
    : '<tr><td colspan="5" class="empty-cell">No users found</td></tr>';

  const sessions = overview.sessions || [];
  elements.sessionsTable.innerHTML = sessions.length
    ? sessions
        .map(
          (session) => `
            <tr>
              <td>${escapeHtml(session.session_id || "-")}</td>
              <td>${escapeHtml(session.username || "-")}</td>
              <td>${statusBadge(session.source || session.status)}</td>
              <td>${escapeHtml(session.nas_ip || "-")}</td>
              <td>${escapeHtml(session.framed_ip || "-")}</td>
              <td>${escapeHtml(
                formatTraffic(session.input_octets || 0, session.output_octets || 0)
              )}</td>
            </tr>
          `
        )
        .join("")
    : '<tr><td colspan="6" class="empty-cell">No active sessions</td></tr>';

  const activityItems = users
    .filter((user) => user.last_accounting)
    .sort((left, right) => {
      const leftTime = new Date(left.last_accounting.last_activity || 0).getTime();
      const rightTime = new Date(right.last_accounting.last_activity || 0).getTime();
      return rightTime - leftTime;
    });

  elements.activityFeed.innerHTML = activityItems.length
    ? activityItems
        .map(
          (user) => `
            <div class="activity-entry ok">
              <span class="time">${escapeHtml(
                formatTimestamp(user.last_accounting.last_activity)
              )}</span>
              <span class="message">${escapeHtml(user.username)} / ${escapeHtml(
                user.last_accounting.status_type || "n/a"
              )} / ${escapeHtml(user.last_accounting.session_id || "-")}</span>
            </div>
          `
        )
        .join("")
    : '<div class="activity-entry">No accounting history yet</div>';
}

function renderDashboard() {
  if (!state.viewer || !state.overview) return;

  applyTheme(state.viewer);
  renderProfile();
  renderAdminOverview();
  elements.adminShell.hidden = !state.overview.can_manage_users;
  showScreen(elements.dashboardScreen);
}

function sessionSeconds() {
  if (!state.viewer) return 0;

  const startedAtMs = Number(state.viewer.started_at || 0) * 1000;
  const elapsed = startedAtMs ? Math.floor((Date.now() - startedAtMs) / 1000) : 0;
  return Math.max(elapsed, Number(currentSession()?.session_time || 0), 0);
}

function refreshSessionClock() {
  elements.viewerSessionTimer.textContent = formatDuration(sessionSeconds());
}

function resetTimers() {
  if (state.clockTimer) {
    window.clearInterval(state.clockTimer);
    state.clockTimer = null;
  }
  if (state.pulseTimer) {
    window.clearInterval(state.pulseTimer);
    state.pulseTimer = null;
  }
}

function pulseDelta() {
  const key = inferThemeKey(state.viewer);
  if (key === "admin") return { input: 3800, output: 5200 };
  if (key === "employee") return { input: 2600, output: 3400 };
  if (key === "guest") return { input: 900, output: 1500 };
  return { input: 1800, output: 1200 };
}

async function loadOverview() {
  state.overview = await fetchJson("/dashboard-api/overview");
  updateTrafficFromSession(currentSession());
}

async function sendPulse() {
  if (!state.viewer) return;

  const delta = pulseDelta();
  state.traffic.inputOctets += delta.input;
  state.traffic.outputOctets += delta.output;

  try {
    await fetchJson("/dashboard-api/pulse", {
      method: "POST",
      body: {
        session_time: sessionSeconds(),
        input_octets: state.traffic.inputOctets,
        output_octets: state.traffic.outputOctets,
      },
    });
    addPacketLog(
      `Accounting interim sent for ${state.viewer.session_id} (${formatTraffic(
        state.traffic.inputOctets,
        state.traffic.outputOctets
      )})`,
      "ok"
    );
    await loadOverview();
    renderDashboard();
  } catch (error) {
    if (error.status === 401) {
      showToast("Dashboard session expired. Please authenticate again.");
      await returnToLogin();
      return;
    }
    addPacketLog(`Pulse failed: ${error.message}`, "warn");
  }
}

function startLiveTimers() {
  resetTimers();
  refreshSessionClock();
  state.clockTimer = window.setInterval(refreshSessionClock, CLOCK_INTERVAL_MS);
  state.pulseTimer = window.setInterval(sendPulse, PULSE_INTERVAL_MS);
}

function updateCreateUserForm() {
  const authType = elements.createAuthType.value;
  const isMab = authType === "mab";

  elements.createPassword.disabled = isMab;
  elements.createPassword.placeholder = isMab ? "Auto-filled from MAC" : "";
  if (isMab) {
    elements.createUsername.value = elements.createUsername.value.trim().toLowerCase();
    elements.createPassword.value = elements.createUsername.value;
  }
}

async function runHandshake(payload, loginPromise) {
  elements.handshakeUser.textContent = payload.calling_station_id
    ? `${payload.username} // ${payload.calling_station_id}`
    : payload.username;
  elements.handshakePackets.innerHTML = "";
  elements.handshakeLog.innerHTML = "";
  showScreen(elements.handshakeScreen);

  for (const [index, step] of HANDSHAKE_STEPS.entries()) {
    const packet = document.createElement("div");
    packet.className = "packet-entry info";
    packet.innerHTML = `<span class="message">PKT-${index + 1} // ${escapeHtml(step)}</span>`;
    elements.handshakePackets.appendChild(packet);

    const line = document.createElement("div");
    line.className = "activity-entry info";
    line.innerHTML = `<span class="time">${escapeHtml(
      formatTimestamp(new Date().toISOString())
    )}</span><span class="message">${escapeHtml(step)}</span>`;
    elements.handshakeLog.appendChild(line);
    await sleep(280);
  }

  return loginPromise;
}

async function login() {
  const username = elements.loginUsername.value.trim();
  const password = elements.loginPassword.value;
  const callingStationId = elements.loginCallingStation.value.trim();

  if (!username || !password) {
    showToast("Username and password are required.");
    return;
  }

  elements.loginButton.disabled = true;
  const payload = {
    username,
    password,
    calling_station_id: callingStationId,
  };

  try {
    const loginPromise = fetchJson("/dashboard-api/login", {
      method: "POST",
      body: payload,
    });
    const loginData = await runHandshake(payload, loginPromise);
    state.viewer = loginData.viewer;
    addPacketLog(
      `Access-Accept issued for ${state.viewer.username} on VLAN ${state.viewer.vlan}`,
      "ok"
    );
    await loadOverview();
    renderDashboard();
    startLiveTimers();
  } catch (error) {
    const details =
      error.payload && typeof error.payload === "object" ? error.payload.detail : null;
    const reason =
      details && typeof details === "object" && details.reason
        ? details.reason
        : error.message;

    elements.handshakeLog.innerHTML += `
      <div class="activity-entry">
        <span class="time">${escapeHtml(formatTimestamp(new Date().toISOString()))}</span>
        <span class="message">Authentication failed: ${escapeHtml(reason)}</span>
      </div>
    `;
    showToast(`Authentication failed: ${reason}`);
    await sleep(900);
    showScreen(elements.loginScreen);
  } finally {
    elements.loginButton.disabled = false;
  }
}

async function restoreExistingSession() {
  try {
    const data = await fetchJson("/dashboard-api/me");
    state.viewer = data.viewer;
    addPacketLog(`Dashboard session restored for ${state.viewer.username}`, "ok");
    await loadOverview();
    renderDashboard();
    startLiveTimers();
    return true;
  } catch (error) {
    if (error.status !== 401) {
      showToast(`Session restore failed: ${error.message}`);
    }
    return false;
  }
}

async function returnToLogin() {
  resetTimers();
  state.viewer = null;
  state.overview = null;
  state.traffic.inputOctets = 0;
  state.traffic.outputOctets = 0;
  showScreen(elements.loginScreen);
}

async function logout() {
  try {
    await fetchJson("/dashboard-api/logout", { method: "POST" });
  } catch (error) {
    showToast(`Logout warning: ${error.message}`);
  }
  addPacketLog("Dashboard session closed", "warn");
  await returnToLogin();
}

async function createUser(event) {
  event.preventDefault();

  const authType = elements.createAuthType.value;
  const username =
    authType === "mab"
      ? elements.createUsername.value.trim().toLowerCase()
      : elements.createUsername.value.trim();
  const payload = {
    username,
    password: authType === "pap" ? elements.createPassword.value : undefined,
    groupname: elements.createGroup.value,
    auth_type: authType,
  };

  if (!payload.username) {
    showToast("Username is required.");
    return;
  }

  if (authType === "pap" && !payload.password) {
    showToast("Password is required for PAP users.");
    return;
  }

  try {
    const data = await fetchJson("/dashboard-api/users", {
      method: "POST",
      body: payload,
    });
    showToast(
      `User created: ${data.user.username} -> VLAN ${data.vlan || "-"}`,
      "ok"
    );
    elements.createUserForm.reset();
    elements.createGroup.value = "employee";
    elements.createAuthType.value = "pap";
    updateCreateUserForm();
    await loadOverview();
    renderDashboard();
  } catch (error) {
    showToast(`Create user failed: ${error.message}`);
  }
}

function bindEvents() {
  elements.quickButtons.forEach((button) => {
    button.addEventListener("click", () => populateQuickLogin(button.dataset.quick));
  });

  elements.loginButton.addEventListener("click", login);
  [elements.loginUsername, elements.loginPassword, elements.loginCallingStation].forEach(
    (field) => {
      field.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          login();
        }
      });
    }
  );
  elements.logoutButton.addEventListener("click", logout);
  elements.createAuthType.addEventListener("change", updateCreateUserForm);
  elements.createUsername.addEventListener("input", updateCreateUserForm);
  elements.createUserForm.addEventListener("submit", createUser);
}

async function init() {
  bindEvents();
  updateCreateUserForm();
  await bootSequence();
  const apiOnline = await updateConnectionStatus();
  if (!apiOnline) {
    showToast("API is offline. Dashboard cannot authenticate.");
  }

  const restored = apiOnline ? await restoreExistingSession() : false;
  if (!restored) {
    populateQuickLogin("admin");
    showScreen(elements.loginScreen);
  }
}

void init();
