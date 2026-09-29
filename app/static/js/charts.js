// Horizontal bar chart of topic success (data comes from data-* attributes on #topicChart).
(function () {
  const el = document.getElementById("topicChart");
  if (!el || typeof Chart === "undefined") return;
  const labels = JSON.parse(el.dataset.labels);
  const values = JSON.parse(el.dataset.values);
  const threshold = parseInt(el.dataset.threshold, 10);
  new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Konu başarısı (%)",
        data: values,
        backgroundColor: values.map(v => (v < threshold ? "#d64545" : "#2e9e5b")),
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      scales: { x: { min: 0, max: 100, title: { display: true, text: "Başarı (%)" } } },
      plugins: { legend: { display: false } },
    },
  });
})();
