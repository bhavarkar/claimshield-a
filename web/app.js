"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function inr(n) {
  const v = Number(n || 0);
  return "₹" + v.toLocaleString("en-IN", { maximumFractionDigits: v % 1 ? 2 : 0 });
}

const TYPE_LABEL = {
  DUPLICATE_CHARGE: "Duplicate charge",
  ARITHMETIC_ERROR: "Quantity x rate error",
  TOTAL_MISMATCH: "Total doesn't add up",
  QUANTITY_MISMATCH: "Quantity exceeds stay",
  UPCODING_SIGNAL: "Possible upcoding",
  PRICE_OUTLIER: "Above benchmark",
  COVERAGE_MISMATCH: "Settled differently from policy",
  CLINICAL_REVIEW: "Clinical question",
};

const state = { billFile: null, policyFile: null, sample: null, samples: null, caseId: null, source: null };

// ---------------------------------------------------------------- setup

async function init() {
  const [health, samples] = await Promise.all([fetch("/api/health").then((r) => r.json()), fetch("/api/samples").then((r) => r.json())]);
  renderStack(health.stack);
  state.samples = samples;
  renderSamples(samples);
  wireDrop("bill");
  wireDrop("policy");
  $("#audit").addEventListener("click", startAudit);
  $("#again").addEventListener("click", reset);
  const linked = new URLSearchParams(location.search).get("case");
  if (linked && /^[a-z0-9-]{6,64}$/.test(linked)) showRun(linked);
}

function renderStack(stack) {
  const cloud = /Document AI|BigQuery|Vertex|Gemini|Cloud Storage/;
  $("#stack").innerHTML = Object.entries(stack)
    .map(([k, v]) => `<span class="${cloud.test(v) && !/local/.test(v) ? "cloud" : ""}" title="${esc(k)}">${esc(v)}</span>`)
    .join("");
}

function renderSamples(cat) {
  const box = $("#samples");
  box.innerHTML = "";
  for (const b of Object.values(cat.bills)) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "sample";
    card.dataset.id = b.id;
    card.innerHTML = `
      <b>${esc(b.hospital)}</b>
      <div class="meta">${esc(b.procedure)}</div>
      <div class="meta">${esc(b.patient)} · ${esc(b.policy_plan)} · billed ${inr(b.gross)}</div>
      <div class="links">${b.clean ? '<span class="tag">clean bill</span>' : ""}
        <a href="${esc(b.url)}" target="_blank" rel="noopener">view bill</a>
        <a href="${esc(cat.policies[b.policy].url)}" target="_blank" rel="noopener">view policy</a></div>`;
    card.addEventListener("click", (e) => {
      if (e.target.tagName === "A") return;
      selectSample(b.id);
    });
    box.appendChild(card);
  }
}

function selectSample(id) {
  state.sample = state.sample === id ? null : id;
  state.billFile = state.policyFile = null;
  for (const k of ["bill", "policy"]) {
    $(`#file-${k}`).value = "";
    $(`#drop-${k}`).classList.remove("ready");
  }
  $("#hint-bill").textContent = "Itemised final bill with the insurer settlement";
  $("#hint-policy").textContent = "Policy wording with schedule and clauses";
  document.querySelectorAll(".sample").forEach((el) => el.classList.toggle("selected", el.dataset.id === state.sample));
  updateReady();
}

function wireDrop(kind) {
  const drop = $(`#drop-${kind}`);
  const input = $(`#file-${kind}`);
  const set = (file) => {
    if (!file) return;
    state[`${kind}File`] = file;
    state.sample = null;
    document.querySelectorAll(".sample").forEach((el) => el.classList.remove("selected"));
    drop.classList.add("ready");
    $(`#hint-${kind}`).textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`;
    updateReady();
  };
  input.addEventListener("change", () => set(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); set(e.dataTransfer.files[0]); });
}

function updateReady() {
  const ready = Boolean(state.sample || (state.billFile && state.policyFile));
  $("#audit").disabled = !ready;
  const s = state.sample && state.samples.bills[state.sample];
  $("#selection").textContent = s
    ? `Sample: ${s.hospital} - ${s.procedure} with ${s.policy_plan}`
    : state.billFile && state.policyFile ? "Ready to audit your documents." : "Choose a bill and a policy, or pick a sample case.";
}

// ---------------------------------------------------------------- run

async function startAudit() {
  const form = new FormData();
  if (state.sample) form.append("sample_bill", state.sample);
  else { form.append("bill", state.billFile); form.append("policy", state.policyFile); }
  $("#audit").disabled = true;
  $("#audit").textContent = "Starting…";
  let res;
  try {
    res = await fetch("/api/audit", { method: "POST", body: form });
  } finally {
    $("#audit").textContent = "Audit";
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.detail || "Could not start the audit.");
    updateReady();
    return;
  }
  const { case_id } = await res.json();
  history.replaceState(null, "", `?case=${case_id}`);
  showRun(case_id);
}

function showRun(case_id) {
  state.caseId = case_id;
  $("#start").classList.add("hidden");
  $("#results").classList.add("hidden");
  $("#run").classList.remove("hidden");
  $("#case-id").textContent = case_id;
  $("#log").innerHTML = "";
  document.querySelectorAll(".agent").forEach((el) => (el.className = "agent"));
  streamTrace(case_id);
}

function streamTrace(caseId) {
  const src = new EventSource(`/api/cases/${caseId}/events`);
  state.source = src;
  src.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  src.addEventListener("end", async () => {
    src.close();
    await loadResults(caseId);
  });
  src.onerror = () => {
    // EventSource retries on its own. If the case has finished meanwhile, just load it.
    fetch(`/api/cases/${caseId}`).then((r) => r.json()).then((c) => {
      if (c.status && c.status !== "running") { src.close(); loadResults(caseId); }
    });
  };
}

function onEvent(e) {
  const node = document.querySelector(`.agent[data-agent="${e.agent}"]`);
  if (node) {
    if (e.kind === "start") node.classList.add("running");
    if (e.kind === "result") { node.classList.remove("running"); node.classList.add("done"); }
    if (e.kind === "error") node.classList.add("error");
  }
  if (e.agent === "orchestrator" && e.kind === "error") document.querySelectorAll(".agent.running").forEach((n) => n.classList.replace("running", "error"));
  const li = document.createElement("li");
  li.className = `k-${e.kind}`;
  li.innerHTML = `<span class="t">${e.t.toFixed(2)}s</span><span class="a">${esc(e.agent)}</span><span class="m">${esc(e.message)}</span>`;
  const log = $("#log");
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;
}

// ---------------------------------------------------------------- results

async function loadResults(caseId) {
  const c = await fetch(`/api/cases/${caseId}`).then((r) => r.json());
  $("#results").classList.remove("hidden");
  if (c.status !== "complete") {
    $("#verdict").className = "verdict fail";
    $("#verdict").textContent = `The audit could not finish: ${c.error || "unknown error"}. Check that both files are an itemised hospital bill and a policy wording.`;
    for (const id of ["#summary", "#notes"]) $(id).innerHTML = "";
    for (const id of ["#findings-panel", "#letters-panel"]) $(id).classList.add("hidden");
    document.querySelectorAll("#results .grid2").forEach((g) => g.classList.add("hidden"));
    return;
  }
  for (const id of ["#findings-panel", "#letters-panel"]) $(id).classList.remove("hidden");
  document.querySelectorAll("#results .grid2").forEach((g) => g.classList.remove("hidden"));
  renderSummary(c);
  renderFindings(c);
  renderBill(c);
  renderCalc(c);
  renderLetters(c);
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary(c) {
  const r = c.reconciliation;
  const v = $("#verdict");
  if (!c.findings.length) {
    v.className = "verdict good";
    v.innerHTML = `<b>Nothing worth disputing.</b> The itemised bill adds up, no charge stood out against reference pricing, and the insurer's settlement matches your policy. You were correctly asked to pay ${inr(r.patient_paid)}.`;
  } else {
    const high = c.findings.filter((f) => f.confidence === "High").length;
    v.className = "verdict money";
    v.innerHTML = `<b>${c.findings.length} item${c.findings.length > 1 ? "s" : ""} worth disputing</b> (${high} high-confidence). ` +
      `You paid ${inr(r.patient_paid)}; under your policy you should owe <b>${inr(r.fair_patient_payable_high)}</b>.`;
  }
  const cards = [
    ["Billed by hospital", inr(r.billed_gross), ""],
    ["Insurer paid", inr(r.insurer_paid), ""],
    ["You paid", inr(r.patient_paid), ""],
    ["You should owe", inr(r.fair_patient_payable_high), "under your policy"],
    ["Likely recovery", inr(r.recovery_likely), r.recovery_upper > r.recovery_likely + 0.5 ? `up to ${inr(r.recovery_upper)} incl. items worth reviewing` : "high-confidence items", "hero"],
    ["Hospital overcharges", inr(r.hospital_overcharge_high), r.hospital_overcharge_all > r.hospital_overcharge_high + 0.5 ? `up to ${inr(r.hospital_overcharge_all)}` : "high confidence"],
    ["Insurer shortfall", inr(r.insurer_shortfall), "vs your policy"],
  ];
  $("#summary").innerHTML = cards
    .map(([l, val, sub, cls]) => `<div class="card ${cls || ""}"><div class="label">${esc(l)}</div><div class="value">${esc(val)}</div><div class="sub">${esc(sub)}</div></div>`)
    .join("");
  $("#notes").innerHTML = (r.notes || []).map((n) => `<div class="note">${esc(n)}</div>`).join("");
}

function renderFindings(c) {
  const tbody = $("#findings");
  tbody.innerHTML = "";
  if (!c.findings.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">No discrepancies found on this bill.</td></tr>`;
    return;
  }
  for (const f of c.findings) {
    const row = document.createElement("tr");
    row.className = "row";
    const pill = f.confidence === "High" ? "high" : "review";
    row.innerHTML = `
      <td class="mono">${esc(f.finding_id)}</td>
      <td><span class="type">${esc(TYPE_LABEL[f.type] || f.type)}</span>${esc(f.title)}</td>
      <td>${f.bill_lines.length ? f.bill_lines.map((n) => `<button class="link" data-line="${n}">line ${n}</button>`).join(" ") : '<span class="muted">settlement</span>'}</td>
      <td class="clause">${f.policy ? `§${esc(f.policy.clause_id)} ${esc(f.policy.title)}` : "-"}</td>
      <td><span class="pill ${pill}">${esc(f.confidence)}</span></td>
      <td class="num"><b>${inr(f.impact)}</b></td>`;
    const detail = document.createElement("tr");
    detail.className = "detail hidden";
    detail.innerHTML = `<td colspan="6">
      <div class="k">Evidence on the bill</div><div>${esc(f.bill_evidence)}</div>
      <div class="k">In plain language</div><div>${esc(f.explanation)}</div>
      ${f.policy ? `<div class="k">Policy clause ${esc(f.policy.clause_id)} - ${esc(f.policy.title)} (${esc(f.policy.source)}, p.${f.policy.page})</div><blockquote>${esc(f.policy.quote)}</blockquote>` : ""}
      <div class="by">Detected by ${esc(f.detected_by)} via ${esc(f.method)} · raise with the ${esc(f.counterparty)}</div></td>`;
    row.addEventListener("click", (e) => {
      if (e.target.dataset.line) { flashLine(e.target.dataset.line); return; }
      detail.classList.toggle("hidden");
      row.classList.toggle("open");
    });
    tbody.append(row, detail);
  }
}

function renderBill(c) {
  const b = c.bill;
  $("#bill-meta").textContent = `${b.hospital} · bill ${b.bill_number} · ${b.patient_name} (${b.patient_age ?? "?"}) · ${b.admission_date} to ${b.discharge_date} · ${b.procedure}`;
  const flags = {};
  for (const f of c.findings) for (const n of f.bill_lines) {
    if (!flags[n] || f.confidence === "High") flags[n] = { ids: [...(flags[n]?.ids || []), f.finding_id], high: f.confidence === "High" || flags[n]?.high };
    else flags[n].ids.push(f.finding_id);
  }
  $("#bill-lines").innerHTML = b.line_items.map((li) => {
    const fl = flags[li.line_no];
    const cls = fl ? (fl.high ? "flag-high" : "flag-review") : "";
    return `<tr id="line-${li.line_no}" class="${cls}"><td>${li.line_no}</td><td class="mono">${esc(li.service_date)}</td>
      <td>${esc(li.description)}${fl ? `<span class="fl">${esc(fl.ids.join(" "))}</span>` : ""}</td>
      <td class="num">${li.qty}</td><td class="num">${inr(li.unit_price)}</td><td class="num">${inr(li.amount)}</td></tr>`;
  }).join("") + `<tr><td></td><td></td><td><b>Gross total (as printed)</b></td><td></td><td></td><td class="num"><b>${inr(b.stated_gross_total)}</b></td></tr>` +
    b.deductions.map((d) => `<tr><td></td><td></td><td class="muted">Insurer deduction: ${esc(d.label)} - ${esc(d.basis)}</td><td></td><td></td><td class="num muted">${inr(d.amount)}</td></tr>`).join("");
}

function flashLine(n) {
  const row = document.getElementById(`line-${n}`);
  if (!row) return;
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.classList.remove("flash");
  void row.offsetWidth;
  row.classList.add("flash");
}

function renderCalc(c) {
  const e = c.reconciliation.entitlement_fair;
  const rows = [
    ["Corrected bill", e.gross],
    ["Less: items the policy doesn't pay for", -e.non_payable],
    ["Less: room rent above the limit", -e.room_excess],
    ["Admissible amount", e.admissible],
    [e.sub_limit_applied != null ? `After sub-limit (cap ${inr(e.sub_limit_applied)})` : "After sub-limit (none applies)", e.after_sub_limit],
    [`Less: co-payment at ${e.copay_pct}%`, -e.copay],
    ["Insurer should pay", e.insurer_payable, "total"],
    ["You should pay", e.patient_payable, "total"],
  ];
  $("#calc").innerHTML = rows.map(([l, v, cls]) => `<tr class="${cls || ""}"><td>${esc(l)}</td><td class="num">${v < 0 ? "−" + inr(-v) : inr(v)}</td></tr>`).join("");
  const t = c.policy_terms;
  const refs = t.clause_refs || {};
  const ref = (k) => (refs[k] ? ` <span class="muted">(§${esc(refs[k])})</span>` : "");
  const items = [];
  if (t.sum_insured) items.push(`Sum insured ${inr(t.sum_insured)}${ref("sum_insured")}`);
  if (t.room_rent_limit) items.push(`Room rent up to ${inr(t.room_rent_limit)}/day${t.icu_rent_limit ? `, ICU ${inr(t.icu_rent_limit)}/day` : ""}${ref("room_rent")}`);
  items.push(`Co-payment ${t.copay_network_pct}% at network, ${t.copay_non_network_pct}% at non-network hospitals${t.copay_senior_pct ? `, +${t.copay_senior_pct}% if aged ${t.senior_age}+` : ""}${ref("copay")}`);
  if (t.sub_limits.length) items.push(`Sub-limits: ${t.sub_limits.map((s) => `${esc(s.procedure)} ${inr(s.amount)}/${esc(s.basis)}`).join("; ")}${ref("sub_limit")}`);
  items.push(`Non-medical items ${t.non_medical_covered ? "covered" : "not covered"}${ref("non_medical")}`);
  items.push(`Extracted by ${esc(t.extraction)}`);
  $("#terms").innerHTML = items.map((i) => `<li>${i}</li>`).join("");
}

function renderLetters(c) {
  const dl = Object.entries(c.files || {}).map(([name, url]) => {
    const label = name.startsWith("reconciliation") ? "Reconciliation report (PDF)" : name.includes("insurer") ? "Letter to insurer (PDF)" : "Letter to hospital (PDF)";
    return `<a href="${esc(url)}" target="_blank" rel="noopener">${label}</a>`;
  });
  for (const l of c.letters) dl.push(`<a href="/api/cases/${esc(c.case_id)}/letters/${esc(l.recipient)}.txt">Letter to ${esc(l.recipient)} (text)</a>`);
  $("#downloads").innerHTML = dl.join("");
  const tabs = $("#letter-tabs");
  tabs.innerHTML = "";
  if (!c.letters.length) {
    $("#letter").textContent = "No dispute letter needed: nothing on this bill is worth disputing. The reconciliation report is still available above.";
    return;
  }
  const show = (l, btn) => {
    tabs.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $("#letter").textContent = `To,\n${l.to}\n\nSubject: ${l.subject}\n\n${l.body}`;
  };
  c.letters.forEach((l, i) => {
    const b = document.createElement("button");
    b.textContent = l.recipient === "insurer" ? "To the insurer" : "To the hospital";
    b.addEventListener("click", () => show(l, b));
    tabs.appendChild(b);
    if (i === 0) show(l, b);
  });
  const copy = document.createElement("button");
  copy.textContent = "Copy";
  copy.addEventListener("click", () => navigator.clipboard.writeText($("#letter").textContent).then(() => { copy.textContent = "Copied"; setTimeout(() => (copy.textContent = "Copy"), 1200); }));
  tabs.appendChild(copy);
}

function reset() {
  state.source?.close();
  history.replaceState(null, "", location.pathname);
  $("#results").classList.add("hidden");
  $("#run").classList.add("hidden");
  $("#start").classList.remove("hidden");
  selectSample(null);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

init();
