(function () {
  "use strict";

  function readData(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    try { return JSON.parse(node.textContent || "{}"); } catch (_) { return null; }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (typeof Chart === "undefined") return;
    var trend = readData("weekly-trend-data");
    var trendCanvas = document.getElementById("weeklyAssignmentTrend");
    if (trend && trendCanvas) {
      var ctx = trendCanvas.getContext("2d");
      var gradient = ctx.createLinearGradient(0, 0, 0, 240);
      gradient.addColorStop(0, "rgba(83, 115, 220, .25)");
      gradient.addColorStop(1, "rgba(83, 115, 220, 0)");
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: trend.map(function (row) { return row.label; }),
          datasets: [{
            label: "People assignments",
            data: trend.map(function (row) { return row.count; }),
            backgroundColor: gradient,
            borderColor: "#5279d9",
            borderWidth: 1.5,
            borderRadius: 7,
            maxBarThickness: 34
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: "#122b45", padding: 10 }
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: "#8694a6", font: { size: 10 } } },
            y: { beginAtZero: true, grid: { color: "rgba(117,132,154,.12)" }, ticks: { precision: 0, color: "#8694a6", font: { size: 10 } } }
          }
        }
      });
    }

    var shifts = readData("weekly-shift-data");
    var shiftCanvas = document.getElementById("weeklyShiftDistribution");
    if (shifts && shiftCanvas) {
      new Chart(shiftCanvas.getContext("2d"), {
        type: "doughnut",
        data: {
          labels: shifts.labels.length ? shifts.labels : ["No assignments"],
          datasets: [{
            data: shifts.values.length ? shifts.values : [1],
            backgroundColor: shifts.values.length ? ["#17a6bd", "#5683e1", "#28ae80", "#dba53a", "#806bc5", "#d76578"] : ["#e6edf3"],
            borderWidth: 0,
            hoverOffset: 5
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "68%",
          plugins: {
            legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 13, color: "#75849a", font: { size: 10 } } },
            tooltip: { enabled: shifts.values.length > 0, backgroundColor: "#122b45", padding: 10 }
          }
        }
      });
    }
  });
})();
