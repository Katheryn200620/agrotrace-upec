/* AgroTrace-UPEC · comportamiento común */
(function () {
  // Menú lateral en celulares
  const menu = document.querySelector(".menu");
  document.querySelectorAll("[data-abrir-menu]").forEach(b => b.addEventListener("click", () => menu.classList.toggle("abierto")));
  document.addEventListener("click", e => {
    if (menu && menu.classList.contains("abierto") && !menu.contains(e.target) && !e.target.closest("[data-abrir-menu]")) {
      menu.classList.remove("abierto");
    }
  });

  // Áreas desplegables del menú lateral
  document.querySelectorAll("[data-area-menu]").forEach(b => b.addEventListener("click", () => {
    const caja = b.closest(".area-menu");
    const abierta = caja.classList.toggle("abierta");
    b.setAttribute("aria-expanded", String(abierta));
  }));
  const activo = document.querySelector(".menu a.item.activo");
  if (activo) activo.scrollIntoView({ block: "center" });

  // Filas de tabla que abren el detalle
  document.querySelectorAll("tr[data-href]").forEach(tr => tr.addEventListener("click", e => {
    if (!e.target.closest("a, button, form, input")) window.location = tr.dataset.href;
  }));

  // Confirmación antes de acciones delicadas
  document.querySelectorAll("form[data-confirmar]").forEach(f => f.addEventListener("submit", e => {
    if (!window.confirm(f.dataset.confirmar)) e.preventDefault();
  }));

  // Filtros que se aplican al cambiar
  document.querySelectorAll("form[data-autoenvio] select").forEach(s => s.addEventListener("change", () => s.form.submit()));

  // Selector de tema de colores (se guarda en este navegador)
  const raiz = document.documentElement;
  const marcar = () => document.querySelectorAll(".tema-opcion").forEach(b =>
    b.setAttribute("aria-pressed", String((raiz.dataset.tema || "cosecha") === b.dataset.tema)));
  document.querySelectorAll(".tema-opcion").forEach(b => b.addEventListener("click", () => {
    const t = b.dataset.tema;
    if (t === "cosecha") delete raiz.dataset.tema; else raiz.dataset.tema = t;
    if (t === "noche") raiz.dataset.bsTheme = "dark"; else delete raiz.dataset.bsTheme;
    try { localStorage.setItem("agro-tema", t); } catch (e) {}
    marcar();
    if (window.AgroGraficos && window._agroDatos) window.AgroGraficos(window._agroDatos);
    if (window.AgroPanel && window._agroPanel) window.AgroPanel(window._agroPanel);
  }));
  marcar();

  // Marcar campos obligatorios
  document.querySelectorAll("input[required], select[required], textarea[required]").forEach(c => {
    const l = document.querySelector(`label[for="${c.id}"]`);
    if (l) l.classList.add("obligatorio");
  });
})();

/* Gráficos del panel (Chart.js). Toman los colores del tema activo. */
window.AgroGraficos = function (datos) {
  if (!window.Chart || !datos) return;
  window._agroDatos = datos;
  (window._agroCharts || []).forEach(g => g.destroy());
  const lista = window._agroCharts = [];
  const css = getComputedStyle(document.documentElement);
  const c = n => css.getPropertyValue(n).trim();
  const alfa = (hex, a) => { const h = hex.replace("#", ""); const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16);
    return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };
  const degradado = (ctx, area, color, a1, a2) => { const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, alfa(color, a1)); g.addColorStop(1, alfa(color, a2)); return g; };
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.color = c("--texto-2");
  Chart.defaults.plugins.legend.display = false;
  const rejilla = c("--linea"), tooltip = { backgroundColor: c("--texto"), titleColor: c("--superficie"), bodyColor: c("--superficie"),
    padding: 10, cornerRadius: 10, displayColors: false };

  const linea = document.getElementById("g-semanas");
  if (linea) lista.push(new Chart(linea, {
    type: "line",
    data: { labels: datos.semanas.etiquetas, datasets: [{ data: datos.semanas.valores, borderColor: c("--verde-medio"), borderWidth: 2.5,
      backgroundColor: x => x.chart.chartArea ? degradado(x.chart.ctx, x.chart.chartArea, c("--verde-medio"), .35, 0) : "transparent",
      fill: true, tension: .4, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: c("--superficie"), pointBorderColor: c("--verde-medio"), pointBorderWidth: 2 }] },
    options: { maintainAspectRatio: false, scales: { y: { beginAtZero: true, border: { display: false }, grid: { color: rejilla }, ticks: { callback: v => v + " kg" } },
      x: { grid: { display: false }, border: { display: false } } },
      plugins: { tooltip: { ...tooltip, callbacks: { label: x => `${x.parsed.y.toLocaleString("es-EC")} kg cosechados` } } } }
  }));

  // Minigráficos de las tarjetas: cada uno con su serie y su color
  document.querySelectorAll("canvas.mini").forEach(cv => {
    const serie = (datos.series || {})[cv.dataset.serie] || datos.semanas.valores;
    const color = getComputedStyle(cv.closest(".kpi")).getPropertyValue("--c").trim() || c("--verde-medio");
    const tipo = cv.dataset.tipo || "line";
    lista.push(new Chart(cv, {
      type: tipo,
      data: { labels: datos.semanas.etiquetas, datasets: [{ data: serie, borderColor: color, borderWidth: 2, pointRadius: 0, tension: .4, fill: true,
        backgroundColor: x => tipo === "bar" ? alfa(color, .75) : (x.chart.chartArea ? degradado(x.chart.ctx, x.chart.chartArea, color, .3, 0) : "transparent"),
        borderRadius: 4, barPercentage: .6 }] },
      options: { maintainAspectRatio: false, animation: false, plugins: { tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false, beginAtZero: true } } }
    }));
  });

  const barras = document.getElementById("g-rechazo");
  if (barras && datos.rechazo.length) lista.push(new Chart(barras, {
    type: "bar",
    data: { labels: datos.rechazo.map(r => [r.codigo, r.cultivo]), datasets: [{ data: datos.rechazo.map(r => r.pct),
      backgroundColor: x => { const r = datos.rechazo[x.dataIndex]; const col = r && r.pct >= 10 ? c("--ambar") : c("--verde-medio");
        return x.chart.chartArea ? degradado(x.chart.ctx, x.chart.chartArea, col, 1, .55) : col; },
      borderRadius: { topLeft: 10, topRight: 10 }, borderSkipped: false, maxBarThickness: 44 }] },
    options: { maintainAspectRatio: false, scales: { y: { beginAtZero: true, suggestedMax: 20, border: { display: false }, grid: { color: rejilla },
      ticks: { callback: v => v + " %" } }, x: { grid: { display: false }, border: { display: false } } },
      plugins: { tooltip: { ...tooltip, callbacks: { title: x => x[0].label.replace(",", " · "),
        label: x => { const r = datos.rechazo[x.dataIndex]; return `${r.pct} % rechazado (${r.rechazo} de ${r.recibido} kg)`; } } } } }
  }));

  const acep = document.getElementById("g-aceptacion");
  if (acep && datos.aceptacion && (datos.aceptacion[0] || datos.aceptacion[1])) lista.push(new Chart(acep, {
    type: "doughnut",
    data: { labels: ["Aceptado", "Rechazado"], datasets: [{ data: datos.aceptacion, borderWidth: 3, borderColor: c("--superficie"),
      backgroundColor: [c("--verde-medio"), c("--rojo")] }] },
    options: { maintainAspectRatio: false, cutout: "65%", plugins: { tooltip, legend: { display: true, position: "bottom",
      labels: { boxWidth: 9, boxHeight: 9, usePointStyle: true } } } }
  }));
  const desp = document.getElementById("g-despachos");
  if (desp && datos.despachos) lista.push(new Chart(desp, {
    type: "bar",
    data: { labels: datos.despachos.etiquetas, datasets: [{ data: datos.despachos.valores, borderRadius: 8, maxBarThickness: 34,
      backgroundColor: [c("--azul"), c("--ambar"), c("--verde-medio"), c("--texto-2")] }] },
    options: { maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: rejilla }, border: { display: false } },
      x: { grid: { display: false }, border: { display: false } } }, plugins: { tooltip } }
  }));

  const dona = document.getElementById("g-estados");
  if (dona && datos.estados.valores.length) lista.push(new Chart(dona, {
    type: "doughnut",
    data: { labels: datos.estados.etiquetas, datasets: [{ data: datos.estados.valores, borderWidth: 3, borderColor: c("--superficie"), borderRadius: 6,
      backgroundColor: [c("--verde-medio"), c("--azul"), c("--ambar"), c("--tierra"), c("--texto-2"), c("--rojo")] }] },
    options: { maintainAspectRatio: false, cutout: "70%", plugins: { tooltip, legend: { display: true, position: "bottom",
      labels: { boxWidth: 9, boxHeight: 9, usePointStyle: true, padding: 10 } } } }
  }));

  const medidor = document.getElementById("g-trazabilidad");
  if (medidor) lista.push(new Chart(medidor, {
    type: "doughnut",
    data: { datasets: [{ data: [datos.trazabilidad, 100 - datos.trazabilidad], borderWidth: 0, borderRadius: [12, 0],
      backgroundColor: x => { const a = x.chart.chartArea; if (!a || x.dataIndex) return c("--linea");
        const g = x.chart.ctx.createLinearGradient(a.left, 0, a.right, 0); g.addColorStop(0, c("--ambar")); g.addColorStop(.6, c("--verde-medio")); return g; } }] },
    options: { maintainAspectRatio: false, rotation: -90, circumference: 180, cutout: "78%", plugins: { tooltip: { enabled: false } } }
  }));
};

/* Gráficas de los paneles por área: cada especificación viene de Django (json_script) */
window.AgroPanel = function (specs) {
  if (!window.Chart || !specs) return;
  window._agroPanel = specs;
  (window._agroPanelCharts || []).forEach(g => g.destroy());
  const lista = window._agroPanelCharts = [];
  const css = getComputedStyle(document.documentElement);
  const c = n => css.getPropertyValue(n).trim();
  const paleta = [c("--verde-medio"), c("--ambar"), c("--azul"), c("--tierra"), c("--rojo"), c("--verde-oscuro"), c("--texto-2"), "#9C8F80"];
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.color = c("--texto-2");
  const rejilla = c("--linea");
  const tooltip = { backgroundColor: c("--texto"), titleColor: c("--superficie"), bodyColor: c("--superficie"), padding: 10, cornerRadius: 10 };
  const fmt = (v, u) => `${Number(v).toLocaleString("es-EC", { maximumFractionDigits: 2 })}${u ? " " + u : ""}`;
  specs.forEach(s => {
    const cv = document.getElementById(s.id);
    if (!cv || s.vacio) return;
    const dona = s.tipo === "dona", horiz = s.tipo === "barra_h", linea = s.tipo === "linea";
    const datasets = s.series.map((serie, i) => {
      const color = paleta[i % paleta.length];
      return {
        label: serie.nombre, data: serie.valores,
        backgroundColor: dona ? s.etiquetas.map((_, j) => paleta[j % paleta.length]) : (linea ? color + "33" : color),
        borderColor: dona ? c("--superficie") : color, borderWidth: dona ? 3 : (linea ? 2.5 : 0),
        borderRadius: dona ? 4 : 8, maxBarThickness: 38, fill: linea && s.series.length === 1, tension: .35,
        pointRadius: linea ? 3 : 0, yAxisID: linea && i === 1 && s.series.length === 2 && serie.nombre.includes("$") ? "y2" : "y"
      };
    });
    const enteros = s.series.every(x => x.valores.every(v => Number.isInteger(v)));
    const eje = { callback: v => fmt(v), precision: enteros ? 0 : undefined };
    const escalas = dona ? {} : {
      x: { grid: { display: horiz }, border: { display: false }, beginAtZero: true, ticks: horiz ? eje : { autoSkip: s.etiquetas.length > 12, maxRotation: 35, minRotation: 0 } },
      y: { grid: { color: rejilla, display: !horiz }, border: { display: false }, beginAtZero: true, ticks: horiz ? {} : eje }
    };
    if (datasets.some(d => d.yAxisID === "y2")) escalas.y2 = { position: "right", beginAtZero: true, grid: { display: false }, ticks: { callback: v => "$" + v } };
    lista.push(new Chart(cv, {
      type: dona ? "doughnut" : (linea ? "line" : "bar"),
      data: { labels: s.etiquetas, datasets },
      options: {
        maintainAspectRatio: false, indexAxis: horiz ? "y" : "x", cutout: dona ? "62%" : undefined, scales: escalas,
        plugins: { legend: { display: dona || s.series.length > 1, position: "bottom", labels: { boxWidth: 9, boxHeight: 9, usePointStyle: true } },
          tooltip: { ...tooltip, callbacks: { label: x => ` ${x.dataset.label}: ${fmt(x.raw, s.unidad === "%" ? "%" : s.unidad)}` } } }
      }
    }));
  });
};
