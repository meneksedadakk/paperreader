// Teacher live results table: renders the embedded initial payload, then polls the JSON API.
(function () {
  const table = document.getElementById("live");
  if (!table) return;
  const tests = JSON.parse(table.dataset.tests); // [[key, name], ...]
  const pollMs = (parseInt(table.dataset.poll, 10) || 5) * 1000;
  const tbody = table.querySelector("tbody");
  const headRow = table.querySelector("thead tr");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = v => (v === null || v === undefined ? "—" : Number(v).toFixed(2));

  const columns = [
    { id: "rank", label: "Sıra", value: r => (r.rank === null ? 1e9 : r.rank) },
    { id: "name", label: "Öğrenci", value: r => r.name.toLowerCase() },
    { id: "status", label: "Durum", value: r => (r.status === "submitted" ? 0 : 1) },
    ...tests.map(([key, name]) => ({ id: key, label: name, value: r => (r.tests ? r.tests[key].net : -1e9) })),
    { id: "total", label: "Toplam net", value: r => (r.total ? r.total.net : -1e9) },
  ];
  let sort = { id: "rank", dir: 1 };
  let data = JSON.parse(document.getElementById("initial-data").textContent);

  headRow.innerHTML = columns.map(c => `<th data-id="${c.id}">${esc(c.label)}<span class="arrow"></span></th>`).join("") + "<th></th>";
  headRow.addEventListener("click", e => {
    const th = e.target.closest("th[data-id]");
    if (!th) return;
    sort = { id: th.dataset.id, dir: sort.id === th.dataset.id ? -sort.dir : 1 };
    render();
  });

  function cell(s) {
    return s ? `<strong>${fmt(s.net)}</strong><br><small class="muted">${s.correct}/${s.wrong}/${s.blank}</small>` : "—";
  }

  function render() {
    const col = columns.find(c => c.id === sort.id);
    const rows = [...data.rows].sort((a, b) => {
      const x = col.value(a), y = col.value(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir || a.student_id - b.student_id;
    });
    headRow.querySelectorAll("th[data-id]").forEach(th => {
      th.querySelector(".arrow").textContent = th.dataset.id === sort.id ? (sort.dir === 1 ? " ▲" : " ▼") : "";
    });
    tbody.innerHTML = rows.map(r => {
      const sub = r.status === "submitted";
      const link = table.dataset.detail.replace(/0$/, r.student_id);
      return `<tr>
        <td class="num">${r.rank ?? "—"}</td>
        <td>${esc(r.name)} <small class="muted">(${esc(r.username)})</small></td>
        <td>${sub ? '<span class="badge ok">Gönderdi</span>' : '<span class="badge">Göndermedi</span>'}
            ${r.edited ? `<br><small class="muted">${r.edited} soru düzeltildi</small>` : ""}</td>
        ${tests.map(([key]) => `<td class="num">${cell(r.tests && r.tests[key])}</td>`).join("")}
        <td class="num">${cell(r.total)}</td>
        <td>${sub ? `<a href="${link}">Detay</a>` : ""}</td></tr>`;
    }).join("");

    document.getElementById("stat-submitted").textContent = `${data.submitted} / ${data.total_students}`;
    document.getElementById("stat-avg").textContent = data.average_net === null ? "—" : data.average_net.toFixed(2);
    document.getElementById("stat-updated").textContent = new Date().toLocaleTimeString("tr-TR");

    const tt = document.querySelector("#topics tbody");
    const specified = data.class_topics.filter(t => t.topic !== "Belirtilmemiş");
    tt.innerHTML = specified.length ? specified.map(t => {
      const pct = Math.round(t.ratio * 100);
      return `<tr><td>${esc(t.subject)}</td><td class="${t.weak ? "weak" : ""}">${esc(t.topic)}</td>
        <td class="num">${t.correct} / ${t.total}</td>
        <td><div class="topic-bar ${t.weak ? "weak-bar" : ""}"><span style="width:${pct}%"></span></div><small>%${pct}</small></td></tr>`;
    }).join("") : '<tr><td colspan="4" class="muted">Henüz gönderim yok.</td></tr>';

    document.getElementById("missed").innerHTML = data.missed.length
      ? data.missed.map(m => `<li>${esc(m.label)} — ${m.wrong}/${m.students} öğrenci yanlış yaptı</li>`).join("")
      : '<li class="muted">Henüz veri yok.</li>';
  }

  async function poll() {
    try {
      const res = await fetch(table.dataset.url, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (res.ok) { data = await res.json(); render(); }
    } catch (_) { /* network hiccup: keep the last data */ }
  }

  render();
  setInterval(() => { if (!document.hidden) poll(); }, pollMs);
})();
