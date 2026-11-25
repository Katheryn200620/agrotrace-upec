/* AgroTrace-UPEC · Asistente virtual (chat) y control por voz.
   El chat consulta al servidor (/asistente/mensaje/), que responde con datos reales y respetando permisos.
   La voz usa la Web Speech API del navegador (Chrome y Edge). Si no está disponible, todo sigue funcionando con el teclado. */
(function () {
  const cuerpo = document.body;
  const URL_MENSAJE = cuerpo.dataset.urlMensaje, URL_VOZ = cuerpo.dataset.urlVoz, URL_BUSCAR = cuerpo.dataset.urlBuscar;
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  const Reconocedor = window.SpeechRecognition || window.webkitSpeechRecognition;

  const norm = t => (t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[¿?¡!.,]/g, "").trim();

  // ------------------------------------------------------------------ chat
  function crearMensaje(caja, clase, texto) {
    const div = document.createElement("div");
    div.className = "msg " + clase;
    const p = document.createElement("p");
    p.textContent = texto;
    div.appendChild(p);
    caja.appendChild(div);
    caja.scrollTop = caja.scrollHeight;
    return div;
  }

  async function preguntar(caja, texto, dictado) {
    if (!texto.trim()) return;
    crearMensaje(caja, "yo", texto);
    const espera = crearMensaje(caja, "bot cargando", "Consultando…");
    try {
      const r = await fetch(URL_MENSAJE, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ pregunta: texto, dictado: !!dictado }) });
      const d = await r.json();
      espera.remove();
      const div = crearMensaje(caja, "bot", d.texto || d.error || "Sin respuesta.");
      if (d.enlaces && d.enlaces.length) {
        const enl = document.createElement("div"); enl.className = "enlaces";
        d.enlaces.forEach(e => { if (!e.url) return; const a = document.createElement("a"); a.href = e.url; a.textContent = e.texto; enl.appendChild(a); });
        div.appendChild(enl);
      }
      if (d.sugerencias && d.sugerencias.length) {
        const chips = document.createElement("div"); chips.className = "chips";
        d.sugerencias.slice(0, 3).forEach(s => { const b = document.createElement("button"); b.type = "button"; b.textContent = s; b.dataset.sugerencia = ""; chips.appendChild(b); });
        div.appendChild(chips);
      }
      const pie = document.createElement("div"); pie.className = "pie-msg";
      pie.textContent = d.fuente === "ia" ? "Respuesta generada con IA a partir de sus datos" : "Respuesta con datos del sistema";
      if (d.id) {
        ["1", "0"].forEach(v => {
          const b = document.createElement("button"); b.type = "button"; b.className = "valorar";
          b.title = v === "1" ? "Me sirvió" : "No me sirvió"; b.setAttribute("aria-label", b.title);
          b.innerHTML = v === "1" ? '<i class="bi bi-hand-thumbs-up"></i>' : '<i class="bi bi-hand-thumbs-down"></i>';
          b.addEventListener("click", () => {
            const f = new FormData(); f.append("util", v);
            fetch(`${URL_MENSAJE}${d.id}/valorar/`, { method: "POST", headers: { "X-CSRFToken": csrf }, body: f });
            pie.querySelectorAll(".valorar").forEach(x => x.disabled = true); b.classList.add("elegido");
          });
          pie.appendChild(b);
        });
      }
      div.appendChild(pie);
      caja.scrollTop = caja.scrollHeight;
      const leer = document.querySelector("[data-leer-voz]");
      if (leer && leer.checked && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance(d.texto); u.lang = "es-ES"; speechSynthesis.cancel(); speechSynthesis.speak(u);
      }
    } catch (e) {
      espera.remove();
      crearMensaje(caja, "bot error", "No se pudo conectar con el servidor. Revise que el aplicativo siga abierto.");
    }
  }

  document.querySelectorAll("[data-chat-form]").forEach(form => {
    const caja = form.parentElement.querySelector("[data-chat-mensajes]");
    form.addEventListener("submit", e => { e.preventDefault(); const i = form.pregunta; preguntar(caja, i.value); i.value = ""; });
    caja.addEventListener("click", e => { const b = e.target.closest("[data-sugerencia]"); if (b) preguntar(caja, b.textContent); });
    const mic = form.querySelector("[data-chat-dictar]");
    if (mic) {
      if (!Reconocedor) { mic.disabled = true; mic.title = "Su navegador no permite dictar (use Chrome o Edge)"; }
      else mic.addEventListener("click", () => escuchar(texto => preguntar(caja, texto, true), mic));
    }
  });

  const panel = document.querySelector("[data-chat-panel]");
  const abrir = document.querySelector("[data-chat-abrir]");
  if (panel && abrir) {
    abrir.addEventListener("click", () => { panel.hidden = !panel.hidden; if (!panel.hidden) panel.querySelector("input").focus(); });
    panel.querySelector("[data-chat-cerrar]").addEventListener("click", () => { panel.hidden = true; abrir.focus(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) panel.hidden = true; });
  }
  window.AgroChat = { preguntar: texto => {
    if (!panel) return;
    panel.hidden = false;
    preguntar(panel.querySelector("[data-chat-mensajes]"), texto, true);
  } };

  // ------------------------------------------------------------------ voz
  const estado = document.querySelector("[data-voz-estado]");
  let ocultar;
  function aviso(texto, tipo) {
    if (!estado) return;
    estado.hidden = false; estado.className = "voz-estado " + (tipo || ""); estado.textContent = texto;
    clearTimeout(ocultar); if (tipo !== "escuchando") ocultar = setTimeout(() => { estado.hidden = true; }, 4500);
  }

  let activo = null;
  function escuchar(alTerminar, boton) {
    if (!Reconocedor) { aviso("Su navegador no tiene reconocimiento de voz. Use Google Chrome o Microsoft Edge.", "error"); return; }
    if (activo) { activo.stop(); return; }
    const r = new Reconocedor();
    r.lang = "es-EC"; r.interimResults = true; r.maxAlternatives = 1; r.continuous = false;
    let final = "";
    r.onstart = () => { activo = r; boton && boton.classList.add("escuchando"); aviso("Escuchando… hable ahora", "escuchando"); };
    r.onresult = e => {
      let t = ""; for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      final = t; aviso("«" + t + "»", "escuchando");
    };
    r.onerror = e => {
      const msg = { "not-allowed": "Permita el uso del micrófono en el navegador (icono del candado).",
        "no-speech": "No se escuchó nada. Intente de nuevo.", "network": "El reconocimiento de voz necesita internet." }[e.error] || "Error de voz: " + e.error;
      aviso(msg, "error");
    };
    r.onend = () => { activo = null; boton && boton.classList.remove("escuchando"); if (final) alTerminar(final); else if (estado && estado.classList.contains("escuchando")) estado.hidden = true; };
    r.start();
  }

  function enlacesMenu() {
    return [...document.querySelectorAll(".menu a.item")].map(a => ({ texto: norm(a.textContent), grupo: norm(a.closest(".area-menu")?.querySelector(".area-nombre")?.textContent), url: a.getAttribute("href") }));
  }
  const SINONIMOS = {
    "estadisticas": ["indicadores generales", "analitica de datos", "panel del area"], "indicadores": ["indicadores generales", "analitica de datos"],
    "analitica": ["analitica de datos", "indicadores generales"], "inventario": ["inventario actual"], "existencias": ["inventario actual"],
    "productores": ["productores y proveedores"], "proveedores": ["productores y proveedores"], "parcelas": ["parcelas y cultivos", "cultivos por parcela"],
    "cultivos": ["cultivos por parcela", "parcelas y cultivos"], "labores": ["labores e insumos"], "cosechas": ["registro de cosechas"],
    "recepcion": ["recepcion y pesaje"], "clasificacion": ["clasificacion por categoria"], "lotes": ["lotes"], "movimientos": ["entradas y salidas"],
    "despachos": ["despachos y entregas"], "transportistas": ["transportistas y vehiculos"], "clientes": ["clientes"], "ventas": ["ventas y pedidos"],
    "pedidos": ["ventas y pedidos"], "eventos": ["historial de eventos"], "historial": ["historial de eventos"], "simulacro": ["simulacro de retiro"],
    "alertas": ["alertas y notificaciones"], "notificaciones": ["alertas y notificaciones"], "usuarios": ["usuarios, roles y permisos"],
    "auditoria": ["auditoria"], "reportes": ["reportes y exportacion"], "asistente": ["asistente virtual"], "chat": ["asistente virtual"],
    "agentes": ["agentes guiados"], "etiquetas": ["etiquetado (qr)"], "productos": ["catalogo de productos"], "catalogo": ["catalogo de productos"],
    "procedencia": ["panel de procedencia"], "panel": ["panel de procedencia"], "odoo": ["integracion erp (odoo)"], "erp": ["integracion erp (odoo)"], "api": ["api rest"]
  };
  function buscarDestino(frase) {
    const links = enlacesMenu();
    const palabras = frase.split(/\s+/);
    for (const p of palabras) {
      for (const objetivo of SINONIMOS[p] || []) {
        const l = links.find(x => x.texto === objetivo || x.texto.startsWith(objetivo));
        if (l) return l;
      }
    }
    let mejor = null, puntos = 0;
    links.forEach(l => {
      const n = palabras.filter(p => p.length > 3 && (l.texto.includes(p) || (l.grupo || "").includes(p))).length;
      if (n > puntos) { puntos = n; mejor = l; }
    });
    return mejor;
  }
  function registrar(texto, comando, accion) {
    fetch(URL_VOZ, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify({ texto, comando, accion }) }).catch(() => {});
  }
  function ir(url, texto, comando, descripcion) {
    aviso("✓ " + descripcion, "ok"); registrar(texto, comando, descripcion);
    setTimeout(() => { window.location.href = url; }, 600);
  }

  function ejecutar(original) {
    const t = norm(original);
    let m;
    if (/^(ayuda|comandos|que puedo decir)/.test(t)) return ir("/asistente/voz/", original, "ayuda", "Abriendo la lista de comandos");
    if (/(ir al |abrir el )?(inicio|pantalla principal|catalogo)$/.test(t) && !/indicadores|area/.test(t)) return ir("/", original, "inicio", "Yendo al inicio");
    if ((m = t.match(/(?:consultar|buscar|ver|abrir) (?:el )?lote (.+)/))) {
      const codigo = m[1].replace(/\bhache\b|\bache\b/g, "h").replace(/[\s-]/g, "").toUpperCase().replace(/^H?/, "H");
      return ir(`${URL_BUSCAR}?q=${encodeURIComponent(codigo)}`, original, "consultar_lote", "Consultando el lote " + codigo);
    }
    if ((m = t.match(/buscar (?:el )?producto (.+)/))) {
      const l = enlacesMenu().find(x => x.texto.startsWith("catalogo de productos"));
      if (l) return ir(`${l.url}?q=${encodeURIComponent(m[1])}`, original, "buscar_producto", "Buscando el producto «" + m[1] + "»");
      if (window.AgroChat) { registrar(original, "buscar_producto", "Pregunta al asistente"); return window.AgroChat.preguntar("¿Qué productos hay en el catálogo?"); }
    }
    if ((m = t.match(/^(?:asistente|pregunta|preguntar|oye asistente)[ ,:]+(.+)/))) {
      registrar(original, "pregunta", "Pregunta al asistente"); aviso("Preguntando al asistente…", "ok");
      return window.AgroChat && window.AgroChat.preguntar(m[1]);
    }
    if (/inventario|existencias|stock/.test(t) && /consultar|ver|abrir|mostrar|cuanto/.test(t)) {
      const l = buscarDestino("inventario");
      if (l) return ir(l.url, original, "inventario", "Abriendo el inventario");
      registrar(original, "inventario", "Pregunta al asistente");
      return window.AgroChat && window.AgroChat.preguntar("¿Qué hay en el inventario?");
    }
    const destino = buscarDestino(t.replace(/^(abrir|ir a|ir al|ver|mostrar|consultar|panel de)\s+/, ""));
    if (destino && /^(abrir|ir|ver|mostrar|consultar|panel|estadisticas|indicadores)/.test(t)) return ir(destino.url, original, "abrir", "Abriendo " + destino.texto);
    registrar(original, "no_reconocido", "Sin acción");
    aviso("No entendí «" + original + "». Diga, por ejemplo: «abrir productores» o «consultar lote H26112201».", "error");
  }

  document.querySelectorAll("[data-voz]").forEach(b => {
    if (!Reconocedor) { b.title = "Control por voz no disponible en este navegador (use Chrome o Edge)"; b.classList.add("no-disponible"); }
    b.addEventListener("click", () => escuchar(ejecutar, b));
  });
  window.AgroVoz = { ejecutar, disponible: !!Reconocedor };
})();
