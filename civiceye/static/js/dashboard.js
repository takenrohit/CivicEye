(function () {
  "use strict";
  const el = document.getElementById("chart-data");
  if (!el || typeof Chart === "undefined") return;
  const d = JSON.parse(el.textContent);
  function bar(id, labels, values, color) {
    const c = document.getElementById(id);
    if (!c) return;
    new Chart(c, {
      type: "bar",
      data: { labels: labels, datasets: [{ label: "Reports", data: values, backgroundColor: color }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });
  }
  bar("catChart", d.cat_labels, d.cat_values, "#0d6efd");
  bar("statusChart", d.status_labels, d.status_values, "#6c757d");
})();
