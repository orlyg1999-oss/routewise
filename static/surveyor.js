// Surveyor screen: one-hand, glanceable. Next property on top, then list / map.
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const S = { route: null, map: null, layer: null, showReasons: false };
const REASONS = [["locked", "נעול"], ["no_answer", "אין מענה"], ["refused", "סירוב"], ["other", "אחר"]];
const REASON_LABEL = Object.fromEntries(REASONS);

async function init() {
  if (params.get("route")) return openRoute(+params.get("route"));
  const sid = params.get("surveyor");
  if (sid) return pickRoute(+sid);
  const people = await api("/api/surveyors");
  show("pickView");
  $("pickView").innerHTML = `<h2 style="font-size:18px">מי את/ה?</h2><div class="pick-list">` +
    people.map((p) => `<button data-sid="${p.id}">${esc(p.name)}</button>`).join("") + "</div>";
  $("pickView").onclick = (e) => {
    const b = e.target.closest("button[data-sid]");
    if (b) location.search = `?surveyor=${b.dataset.sid}`;
  };
}

function show(id) {
  ["pickView", "routeView"].forEach((v) => $(v).classList.toggle("hidden", v !== id));
}

async function pickRoute(sid) {
  const { surveyor, routes } = await api(`/api/surveyor/${sid}/routes`);
  $("whoami").textContent = surveyor.name;
  show("pickView");
  if (!routes.length) {
    $("pickView").innerHTML = `<p class="hint" style="font-size:16px">עדיין לא נשלח אליך מסלול. המסלול יופיע כאן אחרי שמנהל השומה יאשר את הסבב.</p>
      <button onclick="location.reload()">רענון</button>`;
    return;
  }
  $("pickView").innerHTML = `<h2 style="font-size:18px">המסלולים שלך</h2><div class="pick-list">` +
    routes.map((r) => `<button data-rid="${r.id}"><b>${esc(r.neighborhood)}</b> · ${esc(r.round_name)}
      <span class="hint">${r.built_at ? `· נותרו ${r.pending}` : "· חדש"}</span></button>`).join("") + "</div>";
  $("pickView").onclick = (e) => {
    const b = e.target.closest("button[data-rid]");
    if (b) location.search = `?surveyor=${sid}&route=${b.dataset.rid}`;
  };
}

function getPosition() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve({});
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
      () => resolve({}), { timeout: 6000, maximumAge: 60000 });
  });
}

async function openRoute(rid) {
  let r = await api(`/api/routes/${rid}`);
  if (!r.built) {
    toast("בונה מסלול מהמיקום שלך…");
    r = await api(`/api/routes/${rid}/open`, { json: await getPosition() });
  }
  S.route = r;
  show("routeView");
  $("whoami").textContent = `שכונת ${r.neighborhood}`;
  $("startNote").textContent = r.start.source === "gps"
    ? "המסלול נבנה מהמיקום שלך כשפתחת אותו."
    : "המיקום שלך לא זמין או רחוק מהשכונה, ולכן המסלול נבנה ממרכז השכונה.";
  render();
}

const pending = () => S.route.stops.filter((s) => s.status === "pending");

function render() {
  const r = S.route, total = r.stops.length, closed = total - r.counts.pending;
  $("progText").textContent = `${r.counts.done} בוצעו · ${r.counts.not_done} לא בוצעו · ${r.counts.pending} נותרו`;
  $("progBar").style.width = `${(100 * closed) / Math.max(1, total)}%`;
  renderNext();
  renderList();
  if (S.map) renderMap();
}

function navLinks(s) {
  return {
    waze: `https://waze.com/ul?ll=${s.lat},${s.lon}&navigate=yes`,
    gmaps: `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}`,
  };
}

function renderNext() {
  const next = pending()[0];
  if (!next) {
    $("nextCard").innerHTML = `<div class="finished">סיימת את כל הנכסים במסלול ✓</div>`;
    return;
  }
  const n = navLinks(next);
  const use = next.info && next.info["שימוש רשום"] ? ` · רשום כ${esc(next.info["שימוש רשום"])}` : "";
  $("nextCard").innerHTML = `
    <div class="next">
      <div class="label">הנכס הבא${next.skips ? " · חזרה לנכס שדילגת עליו" : ""}</div>
      <div class="addr">${esc(next.address)}</div>
      <div class="meta">${esc(next.ext_id || "")}${use} · ערך צפוי ${money(next.score)}</div>
      <div class="btns">
        <a class="btn btn-nav" href="${n.waze}" target="_blank" rel="noopener">ניווט Waze</a>
        <a class="btn" href="${n.gmaps}" target="_blank" rel="noopener">Google Maps</a>
        <button class="btn-done" data-act="done" data-pid="${next.property_id}">✓ בוצע</button>
        <button class="btn-not" data-act="not" data-pid="${next.property_id}">✕ לא בוצע</button>
        <button data-act="skip" data-pid="${next.property_id}" ${pending().length < 2 ? "disabled" : ""}>דילוג לסוף ↓</button>
      </div>
      ${S.showReasons ? `<div class="reasons">${REASONS.map(([k, l]) =>
        `<button data-act="reason" data-reason="${k}" data-pid="${next.property_id}">${l}</button>`).join("")}</div>` : ""}
    </div>`;
}

function renderList() {
  const nextId = pending()[0]?.property_id;
  const ordered = [...pending(), ...S.route.stops.filter((s) => s.status !== "pending")];
  let i = 0;
  $("listPane").innerHTML = ordered.map((s) => {
    const isPending = s.status === "pending";
    const label = isPending ? ++i : s.status === "done" ? "✓" : "✕";
    const sub = s.status === "done" ? `בוצע ${fmtTime(s.updated_at)}`
      : s.status === "not_done" ? `לא בוצע · ${REASON_LABEL[s.reason] || ""}`
      : `ערך צפוי ${money(s.score)}${s.skips ? " · דילגת" : ""}`;
    return `<div class="stop ${s.status} ${s.property_id === nextId ? "is-next" : ""}">
      <div class="n">${label}</div>
      <div class="a"><b>${esc(s.address)}</b><small>${sub}</small></div>
      ${!isPending ? `<button data-act="undo" data-pid="${s.property_id}">ביטול</button>` : ""}
    </div>`;
  }).join("");
}

function renderMap() {
  if (!S.map) {
    S.map = L.map("map");
    osmLayer().addTo(S.map);
    S.layer = L.layerGroup().addTo(S.map);
  }
  S.layer.clearLayers();
  const pts = [];
  const start = [S.route.start.lat, S.route.start.lon];
  L.marker(start, { icon: L.divIcon({ className: "", html: '<div class="start-marker">התחלה</div>', iconAnchor: [24, 10] }) }).addTo(S.layer);
  const line = [start];
  pending().forEach((s, i) => {
    const m = L.marker([s.lat, s.lon], { icon: numIcon(i + 1, i === 0 ? "next" : ""), zIndexOffset: i === 0 ? 1000 : -i });
    m.bindPopup(`<b>${i + 1}. ${esc(s.address)}</b><br>ערך צפוי ${money(s.score)}<br>
      <a href="${navLinks(s).waze}" target="_blank">Waze</a> · <a href="${navLinks(s).gmaps}" target="_blank">Google Maps</a>`);
    m.addTo(S.layer);
    line.push([s.lat, s.lon]);
    pts.push([s.lat, s.lon]);
  });
  S.route.stops.filter((s) => s.status !== "pending").forEach((s) => {
    L.marker([s.lat, s.lon], { icon: numIcon(s.status === "done" ? "✓" : "✕", s.status), zIndexOffset: -2000 }).addTo(S.layer);
    pts.push([s.lat, s.lon]);
  });
  L.polyline(line, { color: "#1f5fbf", weight: 3, opacity: 0.6, dashArray: "6 6" }).addTo(S.layer);
  if (!S.fitted && pts.length) { S.map.fitBounds([start, ...pts], { padding: [24, 24] }); S.fitted = true; }
  setTimeout(() => S.map.invalidateSize(), 30);
}

async function act(action, pid, reason) {
  try {
    S.route = await api(`/api/routes/${S.route.id}/stops/${pid}`, { json: { action, reason } });
    S.showReasons = false;
    render();
    const msg = { done: "סומן כבוצע", not_done: "סומן כלא בוצע", skip: "הנכס הועבר לסוף הרשימה", undo: "הסימון בוטל" }[action];
    toast(msg);
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-act]");
  if (!b) return;
  const pid = +b.dataset.pid;
  switch (b.dataset.act) {
    case "done": return act("done", pid);
    case "not": S.showReasons = !S.showReasons; return renderNext();
    case "reason": return act("not_done", pid, b.dataset.reason);
    case "skip": return act("skip", pid);
    case "undo": return act("undo", pid);
  }
});

$("tabList").onclick = () => { $("tabList").classList.add("on"); $("tabMap").classList.remove("on");
  $("listPane").classList.remove("hidden"); $("mapPane").classList.add("hidden"); };
$("tabMap").onclick = () => { $("tabMap").classList.add("on"); $("tabList").classList.remove("on");
  $("mapPane").classList.remove("hidden"); $("listPane").classList.add("hidden"); renderMap(); };

init().catch((e) => toast(e.message, true));
