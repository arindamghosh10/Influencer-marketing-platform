/* Chart helpers following the platform's data-viz rules:
 * categorical slots in fixed order, 2px lines, thin rounded bars, recessive grid,
 * crosshair + one tooltip listing every series, legend for 2+ series,
 * direct end labels for up to 4 series (in text ink, never the series colour),
 * and a server-rendered table view next to every chart. */
(function () {
  const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
  const INK = { primary: "#0f172a", secondary: "#475569", muted: "#94a3b8", grid: "#e2e8f0", surface: "#ffffff" };
  const fmt = new Intl.NumberFormat("en-IN");

  const crosshair = {
    id: "crosshair",
    afterDatasetsDraw(chart) {
      const active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      const x = active[0].element.x;
      const { top, bottom } = chart.chartArea;
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = INK.muted;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  const endLabels = {
    id: "endLabels",
    afterDatasetsDraw(chart) {
      if (chart.config.type !== "line" || chart.data.datasets.length > 4 || chart.data.datasets.length < 2) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.font = "12px Inter, system-ui, sans-serif";
      ctx.textBaseline = "middle";
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        let pt = null;
        for (let j = meta.data.length - 1; j >= 0; j--) {
          if (ds.data[j] !== null && ds.data[j] !== undefined) { pt = meta.data[j]; break; }
        }
        if (!pt) return;
        ctx.strokeStyle = ds.borderColor;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(pt.x + 6, pt.y);
        ctx.lineTo(pt.x + 14, pt.y);
        ctx.stroke();
        ctx.fillStyle = INK.secondary;
        ctx.fillText(ds.label, pt.x + 18, pt.y);
      });
      ctx.restore();
    },
  };

  function isolated(values, i) {
    const has = (j) => j >= 0 && j < values.length && values[j] !== null && values[j] !== undefined;
    return has(i) && !has(i - 1) && !has(i + 1);
  }

  function render(canvas) {
    const data = JSON.parse(document.getElementById(canvas.dataset.source).textContent);
    const kind = canvas.dataset.kind || "line";
    const unit = data.unit === "₹" ? "₹" : "";
    const labels = data.series.length ? data.series[0].points.map((p) => p.x) : [];
    const many = data.series.length;
    const datasets = data.series.map((s, i) => ({
      label: s.name,
      data: s.points.map((p) => p.y),
      borderColor: SERIES[i],
      backgroundColor: SERIES[i],
      borderWidth: kind === "line" ? 2 : 0,
      // A lone value (e.g. a post's first day) has no line to draw, so show it as a dot.
      pointRadius: (ctx) => (kind === "line" && isolated(ctx.dataset.data, ctx.dataIndex) ? 4 : 0),
      pointHoverRadius: 5,
      pointHitRadius: 12,
      pointHoverBorderColor: INK.surface,
      pointHoverBorderWidth: 2,
      spanGaps: false,
      tension: 0.25,
      borderRadius: kind === "bar" ? { topLeft: 4, topRight: 4 } : 0,
      borderSkipped: "bottom",
      maxBarThickness: 28,
    }));
    const endPad = kind === "line" && many >= 2 && many <= 4 ? 110 : 8;
    new Chart(canvas, {
      type: kind,
      data: { labels, datasets },
      plugins: [crosshair, endLabels],
      options: {
        maintainAspectRatio: false,
        animation: false,
        layout: { padding: { right: endPad, top: 8 } },
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, ticks: { color: INK.secondary, maxTicksLimit: 8, maxRotation: 0 }, border: { color: INK.grid } },
          y: {
            beginAtZero: true,
            grid: { color: INK.grid },
            border: { display: false },
            ticks: { color: INK.secondary, maxTicksLimit: 5, callback: (v) => unit + fmt.format(v) },
          },
        },
        plugins: {
          legend: {
            display: many >= 2,
            position: "top",
            align: "start",
            labels: { color: INK.secondary, usePointStyle: true, pointStyle: kind === "line" ? "line" : "rect", boxWidth: 16 },
          },
          tooltip: {
            backgroundColor: INK.surface,
            borderColor: INK.grid,
            borderWidth: 1,
            titleColor: INK.secondary,
            bodyColor: INK.primary,
            bodyFont: { weight: "600" },
            usePointStyle: true,
            callbacks: {
              labelPointStyle: () => ({ pointStyle: "line", rotation: 0 }),
              label: (item) => item.raw === null ? null : `${unit}${fmt.format(item.raw)}  ${item.dataset.label}`,
            },
          },
        },
      },
    });
  }

  function init() {
    if (!window.Chart) return;
    document.querySelectorAll("canvas[data-chart]").forEach(render);
  }
  document.addEventListener("DOMContentLoaded", init);
})();
