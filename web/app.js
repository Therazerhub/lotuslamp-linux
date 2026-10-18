/* LotusLamp Linux — vanilla JS control logic. Works offline, no CDN. */
const $ = (id) => document.getElementById(id);

let connected = false;
let powerOn = false;
let scanning = false;

const connDot = $("connDot"), connText = $("connText"),
      connStatus = $("connStatus"), devList = $("devList");

const PRESETS = [
  ["#ff0000","#ff5a00","#ffee00","#00ff00","#00c8ff","#0066ff","#a200ff","#ff00c8","#ffffff"]
];

function setConn(on, label) {
  connText.textContent = label;
  connDot.classList.toggle("on", on);
  $("previewSwatch").classList.toggle("on", on && powerOn);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json().catch(() => ({}));
}

// ---- connect flow ----
async function scan() {
  if (scanning) return;
  scanning = true;
  devList.value = "scanning…";
  const j = await api("/api/scan?timeout=7");
  const d = (j.devices || [])[0];
  if (d) { devList.value = `${d.name}  ·  ${d.address}`; connStatus.textContent = "found — hit connect"; }
  else { devList.value = "no lamp found"; connStatus.textContent = "power strip on + bluetooth on"; }
  scanning = false;
}

async function connect() {
  connStatus.textContent = "connecting…";
  const j = await api("/api/connect", { method: "POST" });
  if (j.ok) {
    connected = true; setConn(true, "connected");
    connStatus.textContent = `→ ${j.device || "device"}`;
  } else {
    connected = false; setConn(false, "offline");
    connStatus.textContent = "connect failed — is the strip awake & phone disconnected?";
  }
}

async function disconnect() {
  await api("/api/disconnect", { method: "POST" });
  connected = false; powerOn = false;
  setConn(false, "offline"); connStatus.textContent = "disconnected";
}

$("scanBtn").onclick = scan;
$("connBtn").onclick = connect;
$("discBtn").onclick = disconnect;

// ---- power ----
$("powerBtn").onclick = async () => {
  powerOn = !powerOn;
  await api(`/api/power/${powerOn ? "on" : "off"}`, { method: "POST" });
  $("previewSwatch").classList.toggle("on", powerOn && connected);
  await api("/api/music/off", { method: "POST" });
  $("powerBtn").textContent = powerOn ? "ON" : "OFF";
};

// ---- color ----
$("colorInput").addEventListener("input", (e) => {
  const str = e.target.value.replace("#", "");
  const [r, g, b] = [0,2,4].map(i => parseInt(str.substr(i,2),16));
  $("previewSwatch").style.background = `rgb(${r},${g},${b})`;
  $("previewSwatch").style.color = `rgb(${r},${g},${b})`;
  api(`/api/color?r=${r}&g=${g}&b=${b}`, { method: "POST" });
});
$("colorInput").addEventListener("change", (e) => {
  const str = e.target.value.replace("#", "");
  const [r, g, b] = [0,2,4].map(i => parseInt(str.substr(i,2),16));
  api(`/api/color?r=${r}&g=${g}&b=${b}`, { method: "POST" });
});

// presets
for (const col of PRESETS[0]) {
  const s = document.createElement("span");
  s.className = "preset"; s.style.background = col; s.style.color = col;
  s.onclick = () => {
    $("colorInput").value = col;
    const [r,g,b] = [1,3,5].map(i => parseInt(col.substr(i,2),16));
    $("previewSwatch").style.background = col; $("previewSwatch").style.color = col;
    api(`/api/color?r=${r}&g=${g}&b=${b}`, { method: "POST" });
  };
  $("palettes").appendChild(s);
}

// ---- brightness / speed ----
let brTimer, spTimer;
$("brightness").addEventListener("input", (e) => {
  $("brVal").textContent = e.target.value;
  clearTimeout(brTimer);
  brTimer = setTimeout(() => api(`/api/brightness?level=${e.target.value}`, { method: "POST" }), 60);
});
$("speed").addEventListener("input", (e) => {
  $("spdVal").textContent = e.target.value;
  clearTimeout(spTimer);
  spTimer = setTimeout(() => api(`/api/speed?value=${e.target.value}`, { method: "POST" }), 60);
});

// ---- modes ----
(async function loadModes() {
  const j = await api("/api/modes");
  const sel = $("modeSelect");
  (j.modes || []).forEach((m, i) => {
    const o = document.createElement("option");
    o.value = i; o.textContent = `${i} · ${m}`;
    sel.appendChild(o);
  });
  sel.onchange = () => api(`/api/mode?index=${sel.value}`, { method: "POST" });
})();

// ---- music sync ----
document.querySelectorAll(".mbtn").forEach(b => {
  b.onclick = async () => {
    document.querySelectorAll(".mbtn").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    const mode = b.dataset.m;
    $("musicControls").style.display = mode === "off" ? "none" : "block";
    $("musicTag").textContent = mode;
    $("musicTag").classList.toggle("on", mode !== "off");
    await api(`/api/music/${mode}?sensitivity=${$("sensitivity").value}&palette=${$("palette").value}`, { method: "POST" });
  };
});

let palTimer;
$("palette").addEventListener("change", () => {
  clearTimeout(palTimer);
  palTimer = setTimeout(() =>
    api(`/api/music/config?palette=${$("palette").value}`, { method: "POST" }), 150);
});
$("sensitivity").addEventListener("input", (e) => {
  $("sensVal").textContent = e.target.value;
  clearTimeout(palTimer);
  palTimer = setTimeout(() =>
    api(`/api/music/config?sensitivity=${e.target.value}`, { method: "POST" }), 150);
});

// ---- live spectrum over ws ----
const bars = [];
for (let i = 0; i < 8; i++) {
  const b = document.createElement("div");
  b.className = "bar"; $("bars").appendChild(b); bars.push(b);
}
let ws;
function openWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data);
    const bands = (d.music && d.music.bands) || [0,0,0,0];
    // interpolate 4 bands → 8 bars
    const map = [0,0.5,1,1.5,2,2.5,3,3.5];
    for (let i = 0; i < 8; i++) {
      const pi = Math.floor(map[i]), frac = map[i] - pi;
      const v = pi + 1 < bands.length ? bands[pi] * (1-frac) + bands[pi+1] * frac : (bands[pi]||0);
      bars[i].style.height = `${Math.max(3, v*48)}px`;
      bars[i].style.opacity = d.music.running ? 1 : 0.25;
    }
    $("musicStatus").textContent = d.music.running
      ? `syncing · ${d.music.palette} (${d.music.beat})`
      : "idle — press spectrum or pulse";
  };
  ws.onclose = () => setTimeout(openWS, 500);
}
openWS();
