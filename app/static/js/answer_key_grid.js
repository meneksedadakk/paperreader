// 120-question answer key grid: tabs, counters, keyboard entry, bulk topic assignment.
(function () {
  const form = document.getElementById("exam-form");
  if (!form) return;
  const sections = [...form.querySelectorAll(".test-section")];
  const tabs = [...form.querySelectorAll("[data-tab]")];
  const saveBtn = document.getElementById("save-btn");
  const dist = document.getElementById("dist");
  const TOTAL = 120;

  const rowsOf = s => [...s.querySelectorAll(".key-row[data-q]")];
  const answered = row => !!row.querySelector("input[type=radio]:checked");

  function update() {
    let total = 0;
    const totals = {};
    sections.forEach((s, i) => {
      const rows = rowsOf(s);
      const done = rows.filter(answered);
      total += done.length;
      rows.forEach(r => r.classList.toggle("missing", r.classList.contains("missing") && !answered(r)));
      const tab = tabs[i];
      tab.textContent = `${tab.dataset.name} ${done.length}/${tab.dataset.count}`;
      const counts = { A: 0, B: 0, C: 0, D: 0, E: 0, X: 0 };
      done.forEach(r => counts[r.querySelector("input:checked").value]++);
      totals[tab.dataset.name] = counts;
    });
    saveBtn.disabled = total < TOTAL;
    saveBtn.title = total < TOTAL ? `${TOTAL - total} sorunun cevabı eksik` : "";
    dist.textContent = `Girilen: ${total}/${TOTAL} · ` + Object.entries(totals).map(([name, c]) =>
      `${name}: A${c.A} B${c.B} C${c.C} D${c.D} E${c.E}${c.X ? " İptal" + c.X : ""}`).join(" | ");
  }

  function showTab(key) {
    sections.forEach(s => (s.hidden = s.dataset.test !== key));
    tabs.forEach(t => t.setAttribute("aria-current", String(t.dataset.tab === key)));
  }

  function firstMissing() {
    for (const s of sections) {
      const r = rowsOf(s).find(row => !answered(row));
      if (r) return { section: s, row: r };
    }
    return null;
  }

  tabs.forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  document.getElementById("goto-missing").addEventListener("click", () => {
    const m = firstMissing();
    if (!m) return;
    showTab(m.section.dataset.test);
    m.row.scrollIntoView({ block: "center" });
    const input = m.row.querySelector("input[type=radio]");
    if (input) input.focus();
  });

  // keyboard entry: A-E select, X = cancelled question; then jump to the next row
  form.addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.tagName === "INPUT" && e.target.type === "text") return;
    const row = e.target.closest(".key-row[data-q]");
    if (!row) return;
    const key = e.key.toUpperCase();
    if (!"ABCDEX".includes(key) || key.length !== 1) return;
    const radio = row.querySelector(`input[type=radio][value="${key}"]`);
    if (!radio) return;
    e.preventDefault();
    radio.checked = true;
    radio.dispatchEvent(new Event("change", { bubbles: true }));
    const next = row.nextElementSibling;
    if (next && next.matches(".key-row[data-q]")) next.querySelector("input[type=radio]").focus();
  });

  form.addEventListener("change", update);

  document.getElementById("bulk-apply").addEventListener("click", () => {
    const key = document.getElementById("bulk-test").value;
    const from = parseInt(document.getElementById("bulk-from").value, 10);
    const to = parseInt(document.getElementById("bulk-to").value, 10);
    const topic = document.getElementById("bulk-topic").value.trim();
    const section = sections.find(s => s.dataset.test === key);
    if (!section || !(from >= 1) || !(to >= from)) return;
    rowsOf(section).forEach(r => {
      const n = parseInt(r.dataset.local, 10);
      if (n >= from && n <= to) r.querySelector("input[type=text]").value = topic;
    });
  });

  // open the tab of the first missing answer (e.g. after a server-side validation error), else the first tab
  const missing = firstMissing();
  showTab(missing && form.querySelector(".key-row.missing") ? missing.section.dataset.test : sections[0].dataset.test);
  update();
})();
