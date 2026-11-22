// Manager screen: upload -> validation -> weights -> ranking -> assignment/approve -> report.
const state = { round: null, surveyors: [], ranking: [], map: null, markers: null, openRow: null };
const $ = (id) => document.getElementById(id);

const ROLE_LABEL = { prob: "סיכוי לפער", amount: "סכום (₪)", ignore: "לא בשימוש" };
const KIND_LABEL = {
  missing_address: ["כתובת חסרה", "bad"], missing_neighborhood: ["שכונה חסרה", "bad"],
  duplicate: ["כפילות", "bad"], geocode_failed: ["אין מיקום", "bad"],
  bad_number: ["ערך לא מספרי", "warn"], geocoded: ["מיקום מכתובת", "muted"],
};
const STATUS = { done: ["בוצע", "ok"], not_done: ["לא בוצע", "bad"], pending: ["ממתין", "muted"] };

async function init() {
  state.surveyors = await api("/api/surveyors");
  await loadRounds();
  const last = new URLSearchParams(location.search).get("round");
  if (last) await selectRound(+last);
}

async function loadRounds(selected) {
  const rounds = await api("/api/rounds");
  const sel = $("roundSelect");
  sel.innerHTML = '<option value="">— סבב חדש —</option>' + rounds.map((r) =>
    `<option value="${r.id}">${esc(r.name)} · ${r.properties} נכסים${r.status === "approved" ? " · אושר" : ""}</option>`).join("");
  if (selected) sel.value = selected;
}

async function selectRound(id) {
  if (!id) {
    state.round = null;
    $("roundArea").classList.add("hidden");
    $("secUpload").classList.remove("hidden");
    history.replaceState(null, "", "manager.html");
    return;
  }
  state.round = await api(`/api/rounds/${id}`);
  $("roundSelect").value = id;
  history.replaceState(null, "", `manager.html?round=${id}`);
  $("secUpload").classList.add("hidden");
  $("roundArea").classList.remove("hidden");
  renderValidation();
  renderCriteria();
  renderHoodFilter();
  renderAssignments();
  await loadRanking();
  if (state.round.status === "approved") await loadReport();
  else $("secReport").classList.add("hidden");
}

// ---------- 1. upload ----------
$("uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = $("fileInput").files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("name", $("roundName").value);
  fd.append("file", f);
  $("uploadBtn").disabled = true;
  $("uploadBtn").textContent = "בודק את הקובץ…";
  try {
    const r = await api("/api/rounds", { method: "POST", body: fd });
    await loadRounds(r.id);
    await selectRound(r.id);
    toast(`הסבב נוצר: ${r.validation.summary.valid} נכסים תקינים`);
  } catch (err) {
    toast(err.message, true);
  } finally {
    $("uploadBtn").disabled = false;
    $("uploadBtn").textContent = "העלאה ובדיקת תקינות";
  }
});
$("roundSelect").addEventListener("change", (e) => selectRound(+e.target.value || null));

// ---------- 2. validation ----------
function renderValidation() {
  const v = state.round.validation;
  const s = v.summary || {};
  $("valSummary").innerHTML = `
    <div class="stat"><b>${s.rows ?? "-"}</b><span>שורות בקובץ</span></div>
    <div class="stat"><b style="color:var(--ok)">${s.valid ?? "-"}</b><span>נכסים תקינים</span></div>
    <div class="stat"><b style="color:var(--bad)">${s.errors ?? 0}</b><span>שורות שהושמטו</span></div>
    <div class="stat"><b style="color:var(--warn)">${s.warnings ?? 0}</b><span>אזהרות</span></div>
    <div class="hint" style="margin:0">קובץ: ${esc(v.filename || "")}</div>`;
  const issues = v.issues || [];
  $("valIssuesWrap").classList.toggle("hidden", !issues.length);
  $("valIssues").innerHTML = issues.map((i) => {
    const [label, cls] = KIND_LABEL[i.kind] || [i.kind, "muted"];
    return `<tr><td>${i.row}</td><td><span class="chip ${cls}">${label}</span></td><td>${esc(i.message)}</td></tr>`;
  }).join("");
}

// ---------- 3. criteria ----------
function renderCriteria() {
  const locked = state.round.status === "approved";
  $("lockedNote").classList.toggle("hidden", !locked);
  $("rescoreBtn").disabled = locked;
  $("critBody").innerHTML = state.round.criteria.map((c, i) => `
    <tr>
      <td><b>${esc(c.name)}</b></td>
      <td><select data-i="${i}" data-k="role" ${locked ? "disabled" : ""}>
        ${Object.entries(ROLE_LABEL).map(([k, l]) => `<option value="${k}" ${c.role === k ? "selected" : ""}>${l}</option>`).join("")}
      </select></td>
      <td><input type="number" min="0" step="0.5" value="${c.weight}" data-i="${i}" data-k="weight" ${locked || c.role === "ignore" ? "disabled" : ""}></td>
      <td><input type="checkbox" data-i="${i}" data-k="invert" ${c.invert ? "checked" : ""} ${locked || c.role !== "prob" ? "disabled" : ""}></td>
    </tr>`).join("");
  $("rescoreHint").textContent = "";
}

$("critBody").addEventListener("change", (e) => {
  const el = e.target, i = +el.dataset.i, k = el.dataset.k;
  if (k === undefined) return;
  const c = state.round.criteria[i];
  c[k] = k === "weight" ? +el.value : k === "invert" ? el.checked : el.value;
  if (k === "role") renderCriteria();
  $("rescoreHint").textContent = "יש שינויים שלא חושבו עדיין";
});

$("rescoreBtn").addEventListener("click", async () => {
  try {
    const before = new Map(state.ranking.map((p) => [p.id, p.rank]));
    state.round = await api(`/api/rounds/${state.round.id}/criteria`, { method: "PUT", json: state.round.criteria });
    renderCriteria();
    renderAssignments();
    await loadRanking();
    const moved = state.ranking.filter((p) => before.get(p.id) !== p.rank).length;
    toast(`הציון חושב מחדש · ${moved} נכסים שינו מיקום בדירוג`);
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------- 4. ranking ----------
function renderHoodFilter() {
  $("hoodFilter").innerHTML = '<option value="">כל השכונות</option>' +
    state.round.neighborhoods.map((h) => `<option>${esc(h.neighborhood)}</option>`).join("");
}
$("hoodFilter").addEventListener("change", loadRanking);
$("rankSearch").addEventListener("input", () => {
  renderRanking();
  renderRankMap();
});

// Properties whose address or ext_id contains the search text.
function visibleRanking() {
  const q = $("rankSearch").value.trim().toLowerCase();
  if (!q) return state.ranking;
  return state.ranking.filter((p) => `${p.address || ""} ${p.ext_id || ""}`.toLowerCase().includes(q));
}

async function loadRanking() {
  const hood = $("hoodFilter").value;
  state.ranking = await api(`/api/rounds/${state.round.id}/ranking` + (hood ? `?neighborhood=${encodeURIComponent(hood)}` : ""));
  state.openRow = null;
  renderRanking();
  renderRankMap();
}

function renderRanking() {
  const maxScore = Math.max(1, ...state.ranking.map((p) => p.score || 0));
  const rows = visibleRanking();
  if (!rows.length) {
    $("rankBody").innerHTML = `<tr><td colspan="6" class="hint">אין נכסים שמתאימים לחיפוש</td></tr>`;
    return;
  }
  $("rankBody").innerHTML = rows.map((p) => `
    <tr class="clickable" data-id="${p.id}">
      <td>${p.rank}</td>
      <td>${esc(p.address)}<div class="bar" style="margin-top:4px"><i style="width:${(100 * (p.score || 0)) / maxScore}%"></i></div></td>
      <td>${esc(p.neighborhood)}</td>
      <td>${pct(p.prob)}</td>
      <td class="num">${nf.format(p.amount || 0)}</td>
      <td class="num"><b>${nf.format(p.score || 0)}</b></td>
    </tr>
    ${state.openRow === p.id ? `<tr><td colspan="6" class="breakdown">${breakdownHtml(p)}</td></tr>` : ""}`).join("");
}

function breakdownHtml(p) {
  const probRows = p.breakdown.filter((b) => b.role === "prob");
  const amtRows = p.breakdown.filter((b) => b.role === "amount");
  const info = Object.entries(p.info || {}).map(([k, v]) => `${esc(k)}: <b>${esc(v)}</b>`).join(" · ");
  return `
    <div><b>${esc(p.ext_id || "")}</b> ${esc(p.address)} ${info ? " · " + info : ""}</div>
    <table style="margin-top:6px">
      <thead><tr><th>קריטריון</th><th>ערך בקובץ</th><th>מנורמל</th><th>משקל</th><th>תרומה</th></tr></thead>
      <tbody>
        ${probRows.map((b) => `<tr><td>${esc(b.name)} <span class="chip">סיכוי</span></td><td>${b.value ?? "חסר"}</td>
          <td>${pct(b.normalized)}</td><td>${b.weight}</td><td><span dir="ltr">+${pct(b.contribution)}</span></td></tr>`).join("")}
        ${amtRows.map((b) => `<tr><td>${esc(b.name)} <span class="chip ok">סכום</span></td><td>${b.value ?? "חסר"}</td>
          <td>—</td><td>${b.weight}</td><td><span dir="ltr" style="white-space:nowrap">+${money(b.contribution)}</span></td></tr>`).join("")}
      </tbody>
    </table>
    <div class="formula">סיכוי <b>${pct(p.prob)}</b> × סכום <b>${money(p.amount)}</b> = הכנסה צפויה <b>${money(p.score)}</b> · מקום <b>${p.rank}</b> בסבב</div>`;
}

$("rankBody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  const id = +tr.dataset.id;
  state.openRow = state.openRow === id ? null : id;
  renderRanking();
  const p = state.ranking.find((x) => x.id === id);
  if (p && state.openRow) state.map.setView([p.lat, p.lon], 16);
});

function renderRankMap() {
  if (!state.map) {
    state.map = L.map("rankMap").setView([31.77, 35.21], 12);
    osmLayer().addTo(state.map);
    state.markers = L.layerGroup().addTo(state.map);
  }
  state.markers.clearLayers();
  const maxScore = Math.max(1, ...state.ranking.map((p) => p.score || 0));
  const pts = [];
  visibleRanking().forEach((p) => {
    const r = 4 + 10 * Math.sqrt((p.score || 0) / maxScore);
    L.circleMarker([p.lat, p.lon], { radius: r, color: "#1f5fbf", weight: 1, fillOpacity: 0.45 })
      .bindTooltip(`#${p.rank} ${esc(p.address)}<br>${money(p.score)}`, { direction: "top" })
      .on("click", () => { state.openRow = p.id; renderRanking(); })
      .addTo(state.markers);
    pts.push([p.lat, p.lon]);
  });
  if (pts.length) state.map.fitBounds(pts, { padding: [20, 20] });
  setTimeout(() => state.map.invalidateSize(), 50);
}

// ---------- 5. assignment / approve ----------
function renderAssignments() {
  const locked = state.round.status === "approved";
  $("assignBody").innerHTML = state.round.neighborhoods.map((h) => `
    <tr>
      <td><b>${esc(h.neighborhood)}</b></td>
      <td class="num">${h.n}</td>
      <td class="num">${nf.format(h.total || 0)}</td>
      <td><select data-hood="${esc(h.neighborhood)}" ${locked ? "disabled" : ""}>
        <option value="">— לא שובץ —</option>
        ${state.surveyors.map((s) => `<option value="${s.id}" ${h.surveyor_id === s.id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}
      </select></td>
    </tr>`).join("");
  $("saveAssignBtn").disabled = locked;
  $("approveBtn").disabled = locked;
  $("approveBtn").textContent = locked ? "המסלולים נשלחו לסוקרים" : "אישור הדירוג ושליחת המסלולים";
}

function collectAssignments() {
  const out = {};
  document.querySelectorAll("#assignBody select").forEach((s) => (out[s.dataset.hood] = s.value ? +s.value : null));
  return out;
}

$("saveAssignBtn").addEventListener("click", async () => {
  try {
    state.round = await api(`/api/rounds/${state.round.id}/assignments`, { method: "PUT", json: collectAssignments() });
    renderAssignments();
    toast("השיבוץ נשמר");
  } catch (err) { toast(err.message, true); }
});

$("approveBtn").addEventListener("click", async () => {
  const a = collectAssignments();
  const n = Object.values(a).filter(Boolean).length;
  if (!n) return toast("צריך לשבץ סוקר לפחות לשכונה אחת", true);
  if (!confirm(`לאשר את הדירוג ולשלוח ${n} מסלולים לסוקרים? אחרי האישור אי אפשר לשנות משקלים או שיבוץ בסבב הזה.`)) return;
  try {
    await api(`/api/rounds/${state.round.id}/assignments`, { method: "PUT", json: a });
    await api(`/api/rounds/${state.round.id}/approve`, { method: "POST" });
    await loadRounds(state.round.id);
    await selectRound(state.round.id);
    toast("המסלולים נשלחו לסוקרים");
  } catch (err) { toast(err.message, true); }
});

// ---------- 6. report ----------
async function loadReport() {
  $("secReport").classList.remove("hidden");
  $("csvLink").href = `/api/rounds/${state.round.id}/report.csv`;
  const rep = await api(`/api/rounds/${state.round.id}/report`);
  $("reportBody").innerHTML = rep.routes.map((r) => `
    <div style="border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:12px">
      <div class="row" style="justify-content:space-between">
        <div><b>${esc(r.neighborhood)}</b> · ${esc(r.surveyor)}
          ${r.opened ? `<span class="hint">· המסלול נפתח ${fmtTime(r.built_at)}</span>` : '<span class="chip muted">הסוקר עדיין לא פתח את המסלול</span>'}</div>
        <a href="surveyor.html?route=${r.route_id}" target="_blank" class="hint">תצוגת הסוקר ↗</a>
      </div>
      ${r.opened ? `
      <div class="row" style="margin:10px 0">
        <div class="stat"><b style="color:var(--ok)">${r.done}</b><span>בוצעו</span></div>
        <div class="stat"><b style="color:var(--bad)">${r.not_done}</b><span>לא בוצעו</span></div>
        <div class="stat"><b>${r.pending}</b><span>ממתינים</span></div>
        <div class="stat"><b>${money(r.visited_value)}</b><span>הכנסה צפויה מהביקורים</span></div>
        <div class="stat"><b>${r.visits_per_day}</b><span>ביקורים ליום</span></div>
      </div>
      <div class="scroll" style="max-height:260px">
        <table><thead><tr><th>סדר</th><th>כתובת</th><th class="num">ציון ₪</th><th>סטטוס</th><th>סיבה</th><th>דילוגים</th><th>זמן סימון</th></tr></thead>
        <tbody>${r.stops.map((s) => {
          const [l, c] = STATUS[s.status];
          return `<tr><td>${s.planned_seq}</td><td>${esc(s.address)}</td><td class="num">${nf.format(s.score || 0)}</td>
            <td><span class="chip ${c}">${l}</span></td><td>${esc(s.reason_label || "")}</td><td>${s.skips || ""}</td>
            <td>${s.status !== "pending" ? fmtTime(s.updated_at) : ""}</td></tr>`;
        }).join("")}</tbody></table>
      </div>` : ""}
    </div>`).join("") || '<p class="hint">אין מסלולים בסבב.</p>';
}
$("refreshReportBtn").addEventListener("click", () => loadReport().then(() => toast("הדוח עודכן")));

init().catch((e) => toast(e.message, true));
