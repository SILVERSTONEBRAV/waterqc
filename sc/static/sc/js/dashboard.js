(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var dataNode = document.getElementById("sc-trend-data");
    var canvas = document.getElementById("scAttendanceTrend");
    if (!dataNode || !canvas || typeof Chart === "undefined") return;

    var rows = [];
    try { rows = JSON.parse(dataNode.textContent || "[]"); } catch (_) { return; }
    var ctx = canvas.getContext("2d");
    var gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, "rgba(21, 164, 190, .28)");
    gradient.addColorStop(1, "rgba(21, 164, 190, 0)");

    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map(function (row) { return row.label; }),
        datasets: [
          {
            label: "Rostered staff",
            data: rows.map(function (row) { return row.total; }),
            borderColor: "#159ebd",
            backgroundColor: gradient,
            pointBackgroundColor: "#fff",
            pointBorderColor: "#159ebd",
            pointBorderWidth: 2,
            pointRadius: 3,
            borderWidth: 2.5,
            fill: true,
            tension: .35
          },
          {
            label: "Present recorded to date",
            data: rows.map(function (row) { return row.present; }),
            borderColor: "#26ad7d",
            backgroundColor: "transparent",
            pointBackgroundColor: "#fff",
            pointBorderColor: "#26ad7d",
            pointBorderWidth: 2,
            pointRadius: 3,
            borderWidth: 2,
            fill: false,
            tension: .35
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 7, color: "#75849a", font: { size: 10 } } },
          tooltip: { backgroundColor: "#122b45", padding: 10, displayColors: true }
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#8694a6", font: { size: 10 } } },
          y: { beginAtZero: true, grid: { color: "rgba(117,132,154,.12)" }, ticks: { precision: 0, color: "#8694a6", font: { size: 10 } } }
        }
      }
    });
  });
})();
