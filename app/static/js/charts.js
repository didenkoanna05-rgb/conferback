// Обгортка над Chart.js: однаковий вигляд усіх графіків системи.
window.CB = (function () {
  var c = {
    navy: '#1f3a5f', blue: '#2b5c9a', sky: '#5b9bd5', accent: '#f26b3a', amber: '#e0a526',
    green: '#2e9d68', teal: '#14a39a', red: '#d64545', muted: '#b8c4d0', grey: '#8a96a3'
  };
  var palette = [c.blue, c.accent, c.teal, c.amber, c.navy, c.sky, c.green, c.red, c.grey];
  if (window.Chart) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = '#5c6773';
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.maintainAspectRatio = false;
  }
  function fmt(v, opt) {
    if (v === null || v === undefined) return '—';
    var s = Math.round(v).toLocaleString('uk-UA');
    return opt && opt.money ? s + ' ' + opt.money : s;
  }
  function el(id) { var e = document.getElementById(id); return e && window.Chart ? e : null; }

  function bars(id, labels, series, opt) {
    var e = el(id); if (!e) return;
    opt = opt || {};
    new Chart(e, {
      type: 'bar',
      data: { labels: labels, datasets: series.map(function (s, i) {
        return { label: s.label, data: s.data, backgroundColor: s.color || palette[i], borderRadius: 6, maxBarThickness: 38 };
      }) },
      options: {
        indexAxis: opt.horizontal ? 'y' : 'x',
        plugins: {
          legend: { display: series.length > 1, position: 'bottom' },
          tooltip: { callbacks: { label: function (ctx) { return ' ' + (ctx.dataset.label || '') + ': ' + fmt(ctx.raw, opt); } } }
        },
        scales: {
          x: { stacked: !!opt.stacked, grid: { display: !!opt.horizontal }, ticks: opt.horizontal ? { callback: function (v) { return fmt(v, opt); } } : {} },
          y: { stacked: !!opt.stacked, grid: { display: !opt.horizontal, color: '#eef1f5' }, beginAtZero: true,
               ticks: opt.horizontal ? {} : { callback: function (v) { return fmt(v, opt); } } }
        }
      }
    });
  }

  function doughnut(id, labels, data, opt) {
    var e = el(id); if (!e) return;
    opt = opt || {};
    var total = data.reduce(function (a, b) { return a + (b || 0); }, 0);
    new Chart(e, {
      type: 'doughnut',
      data: { labels: labels, datasets: [{ data: data, backgroundColor: opt.colors || palette, borderWidth: 2, borderColor: '#fff' }] },
      options: {
        cutout: '62%',
        plugins: {
          legend: { position: 'bottom' },
          tooltip: { callbacks: { label: function (ctx) {
            var pct = total ? Math.round(100 * ctx.raw / total) : 0;
            return ' ' + ctx.label + ': ' + fmt(ctx.raw, opt) + ' (' + pct + ' %)';
          } } }
        }
      }
    });
  }

  function line(id, labels, data, opt) {
    var e = el(id); if (!e) return;
    new Chart(e, {
      type: 'line',
      data: { labels: labels, datasets: [{ label: (opt && opt.label) || '', data: data, borderColor: c.accent,
        backgroundColor: 'rgba(242,107,58,.15)', fill: true, tension: .35, pointRadius: 4, pointBackgroundColor: c.accent }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#eef1f5' } }, x: { grid: { display: false } } } }
    });
  }

  return { c: c, palette: palette, bars: bars, doughnut: doughnut, line: line };
})();
