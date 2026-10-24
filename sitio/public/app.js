"use strict";

/* ---------- Configuración ---------- */

const DATOS = "datos/";
const GESTIONES = [
  { nombre: "Néstor Kirchner", corto: "Kirchner", desde: "2003-05-25", hasta: "2007-12-10" },
  { nombre: "Cristina Fernández de Kirchner I", corto: "CFK I", desde: "2007-12-10", hasta: "2011-12-10" },
  { nombre: "Cristina Fernández de Kirchner II", corto: "CFK II", desde: "2011-12-10", hasta: "2015-12-10" },
  { nombre: "Mauricio Macri", corto: "Macri", desde: "2015-12-10", hasta: "2019-12-10" },
  { nombre: "Alberto Fernández", corto: "Fernández", desde: "2019-12-10", hasta: "2023-12-10" },
  { nombre: "Javier Milei", corto: "Milei", desde: "2023-12-10", hasta: null },
];
const COLORES = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"];
const ORDEN_SECCIONES = ["Precios", "Actividad", "Consumo", "Empleo e ingresos", "Pobreza y programas sociales",
  "Sector externo e inversión", "Estado y fiscal", "Deuda pública", "Dólar y finanzas", "Crédito y alquileres", "Seguridad", "Opinión pública"];
const FUENTES = {
  datosgobar: "INDEC y organismos nacionales (datos.gob.ar)",
  bcra: "BCRA",
  argentinadatos: "ArgentinaDatos",
  fred: "FRED",
  encuestas: "Encuestadoras (carga manual con fuente)",
  yahoo: "Yahoo Finance",
  "cálculo propio": "Cálculo propio",
};
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "septiembre", "octubre", "noviembre", "diciembre"];

const nf = (dec) => new Intl.NumberFormat("es-AR", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmt = (v, dec = 1) => (v == null || !isFinite(v) ? "s/d" : nf(dec).format(v));
const signo = (v, dec = 1) => (v == null || !isFinite(v) ? "s/d" : (v > 0 ? "+" : v < 0 ? "−" : "") + nf(dec).format(Math.abs(v)));
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const el = (tag, attrs = {}, ...hijos) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const h of hijos) if (h != null) e.append(h);
  return e;
};
const slug = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
const fecha = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d || 1); };

function periodo(f, frecuencia) {
  const d = fecha(f);
  if (frecuencia === "T") return `${["I", "II", "III", "IV"][Math.floor(d.getMonth() / 3)]} trim. ${d.getFullYear()}`;
  if (frecuencia === "S") return `${d.getMonth() < 6 ? "1.er" : "2.º"} sem. ${d.getFullYear()}`;
  if (frecuencia === "A") return String(d.getFullYear());
  return `${MESES_LARGO[d.getMonth()]} ${d.getFullYear()}`;
}

/* ---------- Unidades y formato ---------- */

// Para montos "millones de ...": elige la magnitud según el valor más grande.
function magnitud(unidad, maxAbs) {
  const m = unidad.match(/^millones de (.*)$/);
  if (!m) return { div: 1, unidad };
  if (maxAbs >= 1e6) return { div: 1e6, unidad: `billones de ${m[1]}` };
  if (maxAbs >= 1e3) return { div: 1e3, unidad: `miles de millones de ${m[1]}` };
  return { div: 1, unidad };
}
function decimales(v) {
  const a = Math.abs(v);
  return a >= 100 ? 0 : a >= 10 ? 1 : 2;
}
function valorConUnidad(v, unidad) {
  if (/^pesos de hoy/.test(unidad)) return { num: "$ " + fmt(v, 0), resto: unidad.replace(/^pesos de hoy/, "de hoy") };
  const mg = magnitud(unidad, Math.abs(v));
  const x = v / mg.div;
  if (unidad === "% de la PEA" || unidad === "%" || unidad === "% TNA") return { num: fmt(x, 1) + "%", resto: unidad.replace(/^%\s*/, "") };
  return { num: fmt(x, decimales(x)), resto: mg.unidad };
}
// Sufijo para diferencias (tipos tasa y saldo)
function sufijoDiferencia(f) {
  if (/%/.test(f.unidad)) return " pp";
  if (f.unidad === "puntos básicos") return " pb";
  return "";
}
const esDiferencia = (f) => f.tipo_valor === "tasa" || f.tipo_valor === "saldo";
// Índices y valores a precios de un año base: se destaca la variación, no el nivel
const esIndice = (f) => (/índice/.test(f.unidad) || /de 2004/.test(f.unidad)) && f.tipo_valor !== "tasa";

function cifraPrincipal(f) {
  // Con serie desestacionalizada, la variación mensual se toma de ella (convención de INDEC)
  if (f.desest && f.desest.intermensual != null && !esDiferencia(f)) {
    const base = esIndice(f) ? { grande: signo(f.interanual_ultimo) + "%", etiqueta: "interanual" }
      : (() => { const vu = valorConUnidad(f.ultimo.valor, f.unidad); return { grande: vu.num, etiqueta: vu.resto }; })();
    return { ...base, chica: `${signo(f.desest.intermensual)}% vs. mes anterior (desest.)` };
  }
  const variacionMensual = esDiferencia(f)
    ? (f.tipo_valor === "saldo" ? signoMonto(f.intermensual, f.unidad) : signo(f.intermensual, decimales(f.intermensual || 0)) + sufijoDiferencia(f))
    : signo(f.intermensual) + "%";
  const contra = f.frecuencia === "T" ? "vs. trimestre anterior" : f.frecuencia === "S" ? "vs. semestre anterior" : f.frecuencia === "A" ? "vs. año anterior" : "vs. mes anterior";
  if (f.vista_historica === "mensual") {
    return { grande: fmt(f.intermensual) + "%", etiqueta: "mensual", chica: `interanual ${fmt(f.interanual_ultimo)}%` };
  }
  if (esIndice(f)) {
    return { grande: signo(f.interanual_ultimo) + "%", etiqueta: "interanual", chica: `${variacionMensual} ${contra}` };
  }
  const vu = valorConUnidad(f.ultimo.valor, f.unidad);
  // series anuales: además, el cambio desde el último año antes del gobierno actual (2023)
  const g = (f.vistas && f.vistas.gestion_actual) || [];
  const extra = f.frecuencia === "A" && !esDiferencia(f) && g.length >= 3 && g[0][1]
    ? ` · ${signo((g[g.length - 1][1] / g[0][1] - 1) * 100)}% vs. ${g[0][0].slice(0, 4)}` : "";
  return { grande: vu.num, etiqueta: vu.resto, chica: `${variacionMensual} ${contra}${extra}` };
}
function signoMonto(v, unidad) {
  const mg = magnitud(unidad, Math.abs(v));
  const corto = mg.unidad.replace(/^miles de millones.*/, "mil millones").replace(/^billones.*/, "billones").replace(/^millones.*/, "millones");
  return signo(v / mg.div, decimales(v / mg.div)) + " " + corto;
}

/* ---------- Vistas ---------- */

const VISTAS = [
  { id: "interanual", texto: "Interanual" },
  { id: "gestion_actual", texto: "Gestión actual" },
  { id: "desde_2003", texto: "Desde 2003" },
  { id: "comparativa", texto: "Por gestión" },
];

function describirVista(f, vista) {
  const dif = esDiferencia(f);
  switch (vista) {
    case "interanual":
      return dif ? "Diferencia contra el mismo período del año anterior." : "Variación % contra el mismo período del año anterior.";
    case "gestion_actual":
      if (f.vista_historica === "mensual") return "Variación % mensual desde diciembre de 2023.";
      if (f.frecuencia === "A") return "Serie en su unidad desde 2023, el último año antes de asumir el gobierno actual.";
      if (f.frecuencia === "T") return "Serie en su unidad desde el cuarto trimestre de 2023, el último antes de asumir el gobierno actual.";
      return "Serie en su unidad desde diciembre de 2023.";
    case "desde_2003":
      return f.vista_historica === "mensual" ? "Variación % mensual desde 2003." : "Serie en su unidad desde 2003 o desde el primer dato disponible.";
    case "comparativa":
      return dif ? "Diferencia interanual de cada mes, por meses de mandato." : "Variación % interanual de cada mes, por meses de mandato."
  }
}

// Devuelve { series, tipoX, formatoY, referencia, unidadEje, bandas }
function prepararVista(f, vista) {
  const v = f.vistas[vista];
  const dif = esDiferencia(f);
  const puntos = (lista) => lista.map(([x, y]) => [typeof x === "string" ? fecha(x) : x, y]);
  if (vista === "comparativa") {
    const series = GESTIONES.map((g, i) => ({ nombre: g.corto, color: css(COLORES[i]), puntos: v[g.nombre] ? puntos(v[g.nombre]) : null, grueso: i === GESTIONES.length - 1 }))
      .filter((s) => s.puntos && s.puntos.length);
    return { series, tipoX: "meses", ...formatoY(f, vista, series), referencia: 0, bandas: false };
  }
  const conDesest = f.desest && (vista === "gestion_actual" || vista === "desde_2003") && f.vista_historica !== "mensual";
  const series = conDesest
    ? [{ nombre: "Original", color: css("--tinta-3"), puntos: puntos(v), grueso: false },
       { nombre: "Desestacionalizada", color: css("--s1"), puntos: puntos(f.desest[vista]), grueso: true }]
    : [{ nombre: f.nombre, color: css("--s1"), puntos: puntos(v), grueso: true }];
  const ref = vista === "interanual" ? 0 : (f.vista_historica === "mensual" || f.tipo_valor === "saldo" ? 0 : null);
  return { series, tipoX: "fecha", ...formatoY(f, vista, series), referencia: ref, bandas: vista !== "gestion_actual" };
}

function formatoY(f, vista, series) {
  const maxAbs = Math.max(...series.flatMap((s) => s.puntos.map((p) => Math.abs(p[1]))), 0);
  const dif = esDiferencia(f);
  const enNivel = vista === "desde_2003" || vista === "gestion_actual";
  const porcentaje = ((vista === "interanual" || vista === "comparativa") && !dif) || (enNivel && f.vista_historica === "mensual");
  if (porcentaje) return { eje: (y) => fmt(y, decimales(maxAbs) > 1 ? 1 : 0) + "%", tip: (y) => fmt(y, 1) + "%", unidadEje: "" };
  const mg = magnitud(f.unidad, maxAbs);
  const suf = dif && !enNivel ? sufijoDiferencia(f) : "";
  const dec = decimales(maxAbs / mg.div);
  return {
    eje: (y) => fmt(y / mg.div, Math.max(0, dec - 1)) + suf,
    tip: (y) => (dif && !enNivel ? signo(y / mg.div, dec) : fmt(y / mg.div, dec)) + suf,
    unidadEje: enNivel || f.tipo_valor === "saldo" ? mg.unidad : "",
  };
}

/* ---------- Gráfico de líneas (SVG) ---------- */

function ticksLindos(min, max, n = 5) {
  if (min === max) { min -= 1; max += 1; }
  const paso0 = (max - min) / n;
  const pot = Math.pow(10, Math.floor(Math.log10(paso0)));
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * pot).find((p) => p >= paso0);
  const ini = Math.floor(min / paso) * paso, fin = Math.ceil(max / paso) * paso;
  const t = [];
  for (let v = ini; v <= fin + paso / 2; v += paso) t.push(+v.toFixed(10));
  return t;
}

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };

function dibujar(contenedor, cfg) {
  contenedor.innerHTML = "";
  const W = contenedor.clientWidth || 400, H = contenedor.clientHeight || 240;
  const m = { t: cfg.unidadEje ? 26 : 14, r: 10, b: 24, l: 46 };
  const xs = cfg.series.flatMap((s) => s.puntos.map((p) => +p[0]));
  const ys = cfg.series.flatMap((s) => s.puntos.map((p) => p[1]));
  if (cfg.referencia != null) ys.push(cfg.referencia);
  const ty = ticksLindos(Math.min(...ys), Math.max(...ys));
  const y0 = ty[0], y1 = ty[ty.length - 1];
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const X = (x) => m.l + ((+x - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (y) => m.t + (1 - (y - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.titulo });

  // Bandas de gestión (vistas en el tiempo)
  if (cfg.bandas && cfg.tipoX === "fecha") {
    GESTIONES.forEach((g, i) => {
      const a = Math.max(+fecha(g.desde), x0), b = Math.min(g.hasta ? +fecha(g.hasta) : x1, x1);
      if (b <= a) return;
      if (i % 2 === 0) svg.append(svgEl("rect", { class: "banda", x: X(a), y: m.t, width: X(b) - X(a), height: H - m.t - m.b }));
      if (X(b) - X(a) > 34) {
        const t = svgEl("text", { class: "banda-txt", x: X(a) + 4, y: m.t + 11 });
        t.textContent = g.corto;
        svg.append(t);
      }
    });
  }
  // Grilla y eje Y
  for (const t of ty) {
    svg.append(svgEl("line", { class: "grilla-h", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
    const tx = svgEl("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" });
    tx.textContent = cfg.eje(t);
    svg.append(tx);
  }
  if (cfg.unidadEje) {
    const u = svgEl("text", { x: m.l - 40, y: 12 });
    u.textContent = cfg.unidadEje;
    svg.append(u);
  }
  if (cfg.referencia != null && cfg.referencia >= y0 && cfg.referencia <= y1) {
    svg.append(svgEl("line", { class: "ref", x1: m.l, x2: W - m.r, y1: Y(cfg.referencia), y2: Y(cfg.referencia) }));
  }
  // Eje X
  const ticksX = [];
  if (cfg.tipoX === "fecha") {
    const a0 = new Date(x0).getFullYear(), a1 = new Date(x1).getFullYear();
    const span = a1 - a0;
    const paso = span > 16 ? 4 : span > 8 ? 2 : 1;
    if (span < 3) {
      for (let d = new Date(new Date(x0).getFullYear(), new Date(x0).getMonth(), 1); +d <= x1; d.setMonth(d.getMonth() + 1)) {
        if (d.getMonth() % 6 === 0) ticksX.push([+d, `${MESES[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`]);
      }
    } else {
      for (let a = Math.ceil(a0 / paso) * paso; a <= a1; a += paso) { const d = +new Date(a, 0, 1); if (d >= x0) ticksX.push([d, String(a)]); }
    }
  } else {
    for (let mth = 12; mth <= x1; mth += 12) ticksX.push([mth, `año ${mth / 12}`]);
    if (x0 <= 1) ticksX.unshift([x0, "mes 1"]);
  }
  for (const [x, lab] of ticksX) {
    const t = svgEl("text", { x: X(x), y: H - 6, "text-anchor": "middle" });
    t.textContent = lab;
    svg.append(t);
  }
  // Líneas
  for (const s of cfg.series) {
    const d = s.puntos.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
    svg.append(svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": s.grueso ? 2 : 1.5, "stroke-linejoin": "round", "stroke-linecap": "round", opacity: s.grueso || cfg.series.length === 1 ? 1 : 0.85 }));
  }
  // Interacción: cruz y tooltip
  const cruz = svgEl("line", { class: "cruz", y1: m.t, y2: H - m.b, visibility: "hidden" });
  const puntosHover = cfg.series.map((s) => { const c = svgEl("circle", { r: 4, fill: s.color, stroke: css("--superficie"), "stroke-width": 2, visibility: "hidden" }); svg.append(c); return c; });
  svg.append(cruz);
  const capa = svgEl("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" });
  svg.append(capa);
  const tip = document.getElementById("tooltip");
  const mover = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) * (W / r.width);
    const xv = x0 + ((px - m.l) / (W - m.l - m.r)) * (x1 - x0);
    let filas = [], xRef = null;
    cfg.series.forEach((s, i) => {
      let mejor = null;
      for (const p of s.puntos) if (!mejor || Math.abs(+p[0] - xv) < Math.abs(+mejor[0] - xv)) mejor = p;
      const lejos = cfg.tipoX === "meses" ? Math.abs(+mejor[0] - xv) > 1.5 : Math.abs(+mejor[0] - xv) > 1000 * 3600 * 24 * 100;
      if (!mejor || lejos) { puntosHover[i].setAttribute("visibility", "hidden"); return; }
      if (xRef == null) xRef = mejor[0];
      puntosHover[i].setAttribute("cx", X(mejor[0])); puntosHover[i].setAttribute("cy", Y(mejor[1]));
      puntosHover[i].setAttribute("visibility", "visible");
      filas.push([s, mejor[1], mejor[0]]);
    });
    if (!filas.length) return salir();
    cruz.setAttribute("x1", X(xRef)); cruz.setAttribute("x2", X(xRef)); cruz.setAttribute("visibility", "visible");
    const cab = cfg.tipoX === "fecha"
      ? periodo(`${new Date(xRef).getFullYear()}-${String(new Date(xRef).getMonth() + 1).padStart(2, "0")}-01`, cfg.frecuencia)
      : `Mes ${xRef} de mandato`;
    tip.innerHTML = "";
    tip.append(el("div", { class: "t-fecha", text: cab }));
    filas.sort((a, b) => b[1] - a[1]).forEach(([s, y]) => {
      const nom = el("span", {}, cfg.series.length > 1 ? el("i", { style: `background:${s.color}` }) : null, cfg.series.length > 1 ? s.nombre : "Valor");
      tip.append(el("div", { class: "t-fila" }, nom, el("span", { text: cfg.tip(y) })));
    });
    tip.hidden = false;
    const cx = ev.touches ? ev.touches[0].clientX : ev.clientX, cy = ev.touches ? ev.touches[0].clientY : ev.clientY;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - tw - 8, cx + 14) + "px";
    tip.style.top = Math.max(8, cy - th - 12) + "px";
  };
  const salir = () => { tip.hidden = true; cruz.setAttribute("visibility", "hidden"); puntosHover.forEach((c) => c.setAttribute("visibility", "hidden")); };
  capa.addEventListener("mousemove", mover);
  capa.addEventListener("touchmove", mover, { passive: true });
  capa.addEventListener("mouseleave", salir);
  capa.addEventListener("touchend", salir);
  contenedor.append(svg);
}

/* ---------- Fichas de indicadores ---------- */

function ficha(f, { anidada = false } = {}) {
  const c = cifraPrincipal(f);
  const grafico = el("div", { class: "grafico" });
  const leyendaVista = el("p", { class: "leyenda-vista" });
  const leyenda = el("ul", { class: "leyenda", hidden: true });
  const vistasDisponibles = VISTAS.filter((v) => (v.id === "comparativa" ? Object.keys(f.vistas.comparativa || {}).length : (f.vistas[v.id] || []).length));
  // Para saldos (pueden ser negativos) la vista inicial es la serie en su unidad
  // Con desestacionalizada se abre en "Desde 2003", donde se ven las dos líneas
  const inicial = f.vista_inicial || (f.tipo_valor === "saldo" || f.desest ? "desde_2003" : "interanual");
  let actual = vistasDisponibles.find((v) => v.id === inicial) ? inicial : vistasDisponibles[0]?.id;
  const botones = vistasDisponibles.map((v) => el("button", { type: "button", "aria-pressed": String(v.id === actual), text: v.texto, onclick: () => { actual = v.id; render(); } }));
  function render() {
    botones.forEach((b, i) => b.setAttribute("aria-pressed", String(vistasDisponibles[i].id === actual)));
    leyendaVista.textContent = describirVista(f, actual);
    const cfg = { ...prepararVista(f, actual), titulo: `${f.nombre}: ${describirVista(f, actual)}`, frecuencia: f.frecuencia };
    leyenda.innerHTML = "";
    leyenda.hidden = cfg.series.length < 2;
    if (cfg.series.length > 1) cfg.series.forEach((s) => leyenda.append(el("li", {}, el("i", { style: `background:${s.color}` }), s.nombre)));
    dibujar(grafico, cfg);
  }
  const art = el("article", { class: anidada ? "ficha anidada" : "ficha", id: anidada ? null : f.id },
    el("div", { class: "ficha-cab" },
      el("div", {}, el("h3", { text: f.nombre }), el("p", { class: "unidad", text: `Último dato: ${periodo(f.ultimo.fecha, f.frecuencia)}` })),
      el("div", { class: "cifra" },
        el("span", { class: "grande" }, c.grande, ["mensual", "interanual"].includes(c.etiqueta) ? el("small", { text: " " + c.etiqueta }) : null),
        ["mensual", "interanual"].includes(c.etiqueta) ? null : el("span", { class: "chica", text: c.etiqueta }),
        el("span", { class: "chica", text: c.chica }))),
    el("div", { class: "vistas", role: "group", "aria-label": "Vista del gráfico" }, ...botones),
    leyendaVista, grafico, leyenda,
    f.nota ? el("p", { class: "nota", text: f.nota }) : null,
    el("div", { class: "ficha-pie" },
      el("span", { text: `Fuente: ${FUENTES[f.fuente] || f.fuente}` }),
      el("a", { href: `${DATOS}${f.id}.csv`, download: `${f.id}.csv`, text: "Descargar CSV" })));
  new ResizeObserver(() => render()).observe(grafico);
  return art;
}

function tarjeta(f) {
  const c = cifraPrincipal(f);
  const corta = c.etiqueta.length <= 12;
  const valor = el("p", { class: "valor" }, c.grande, corta ? " " : null, corta ? el("small", { text: c.etiqueta }) : null);
  return el("a", { class: "tarjeta", href: `#${f.id}` },
    el("p", { class: "nombre", text: f.nombre }), valor, corta ? null : el("p", { class: "unidad-t", text: c.etiqueta }),
    el("p", { class: "detalle", text: `${c.chica} · ${periodo(f.ultimo.fecha, f.frecuencia)}` }));
}

/* ---------- Grupos (p. ej. EMAE por sector) ---------- */

function diferenciaNivel(m, desde) {
  // Diferencia en la unidad de la serie entre el último dato y una fecha (o 12 meses antes)
  const lista = m.vistas.desde_2003;
  if (!lista || !lista.length) return null;
  const [fu, vu] = lista[lista.length - 1];
  let objetivo = desde;
  if (!objetivo) { const d = fecha(fu); objetivo = `${d.getFullYear() - 1}-${String(d.getMonth() + 1).padStart(2, "0")}-01`; }
  const previo = lista.find(([f]) => f === objetivo);
  return previo ? vu - previo[1] : null;
}

// Períodos para comparar en los rankings: hace un año o el mes previo a cada asunción
const PERIODOS_RANKING = [
  { id: "anio", texto: "Hace un año" },
  ...[...GESTIONES].reverse().map((g) => ({ id: g.nombre, texto: `Inicio de ${g.corto}`, base: basePrevia(g.desde) })),
];
function basePrevia(desde) {
  const d = fecha(desde); d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}
function promedio12(lista, hastaIdx) {
  if (hastaIdx < 11) return null;
  let s = 0; for (let k = hastaIdx - 11; k <= hastaIdx; k++) s += lista[k][1];
  return s / 12;
}
// Variación de un miembro contra el período elegido.
//  - porcentaje (EMAE por sector, series originales): último año = interanual del último mes;
//    contra una asunción = promedio de los últimos 12 meses vs. los 12 meses previos a asumir.
//  - diferencia (empleo, mayormente desestacionalizado): último dato menos el del mes base.
function compararMiembro(m, periodo, porDiferencia) {
  const lista = m.vistas.desde_2003;
  if (!lista || lista.length < 2) return null;
  const n = lista.length - 1, [fu, vu] = lista[n];
  const idx = (f) => lista.findIndex(([x]) => x === f);
  if (periodo.id === "anio") {
    if (!porDiferencia) return m.interanual_ultimo;
    const d = fecha(fu); const k = idx(`${d.getFullYear() - 1}-${String(d.getMonth() + 1).padStart(2, "0")}-01`);
    return k >= 0 ? vu - lista[k][1] : null;
  }
  const k = idx(periodo.base);
  if (k < 0) return null;
  if (porDiferencia) return vu - lista[k][1];
  const a = promedio12(lista, n), b = promedio12(lista, k);
  return a != null && b ? (a / b - 1) * 100 : null;
}

function filaNivel(nombre, v, max, texto, attrs = {}) {
  const ancho = max ? (Math.max(v, 0) / max) * 88 : 0;
  return el(attrs.onclick ? "button" : "div", { class: "rank-fila nivel", role: "listitem", ...(attrs.onclick ? { type: "button" } : {}), ...attrs },
    el("span", { class: "rank-nombre", text: nombre }),
    el("span", { class: "rank-pista" },
      el("span", { class: "rank-barra pos", style: `left:0;width:${ancho}%` }),
      el("span", { class: "rank-num" + (ancho > 60 ? " dentro" : ""), style: ancho > 60 ? `left:${ancho - 1}%;transform:translateX(-100%)` : `left:${ancho}%`, text: texto })));
}

function fichaGrupoNivel(g) {
  // ranking del último valor publicado (p. ej. gasto por función en % del PIB)
  const ordenados = g.miembros.filter((m) => m.ultimo && m.ultimo.valor != null).sort((a, b) => b.ultimo.valor - a.ultimo.valor);
  const max = Math.max(...ordenados.map((m) => m.ultimo.valor), 1e-9);
  let elegido = ordenados[0] && ordenados[0].id;
  const barras = el("div", { class: "ranking", role: "list" });
  const detalle = el("div", { class: "grupo-detalle" });
  const ref = ordenados[0] ? periodo(ordenados[0].ultimo.fecha, ordenados[0].frecuencia) : "";
  const pintar = () => {
    barras.innerHTML = "";
    ordenados.forEach((m) => barras.append(filaNivel(m.nombre, m.ultimo.valor, max, fmt(m.ultimo.valor, 1) + (g.sufijo_ranking ?? ""),
      { "aria-pressed": String(m.id === elegido), onclick: () => { elegido = m.id; pintar(); } })));
    detalle.innerHTML = "";
    const m = g.miembros.find((x) => x.id === elegido);
    if (m) detalle.append(ficha(m, { anidada: true }));
  };
  pintar();
  return el("article", { class: "ficha ancha", id: g.id },
    el("div", { class: "ficha-cab" }, el("div", {}, el("h3", { text: g.nombre }),
      el("p", { class: "unidad", text: `${g.unidad_ranking || ""} · último dato: ${ref}. Tocá una fila para ver su serie.` }))),
    barras, detalle, g.nota ? el("p", { class: "nota", text: g.nota }) : null);
}

/* ---------- RIGI: proyectos aprobados ---------- */

function ejecucionRigi(d, mm) {
  const e = d.ejecucion_estimada, dv = d.divisas_bcra, plan = d.plan_anual || [];
  if (!e && !dv) return null;
  const caja = el("div", { class: "rigi-ejecucion" }, el("h4", { class: "subtitulo-ficha", text: "¿Cuánto se invirtió hasta ahora? (estimación)" }));
  const cifras = el("div", { class: "estratos" });
  if (e) cifras.append(el("div", { class: "estrato" }, el("p", { class: "estrato-nombre", text: "Según el cronograma comprometido" }),
    el("p", { class: "estrato-valor", text: mm(e.monto) }),
    el("p", { class: "estrato-detalle", text: `Inversión que los proyectos aprobados planearon hacer hasta ${fechaCorta(e.hasta)}: años 2024 y 2025 completos y la parte proporcional de ${e.hasta.slice(0, 4)}.` })));
  if (dv) cifras.append(el("div", { class: "estrato" }, el("p", { class: "estrato-nombre", text: "Dólares ingresados por el mercado de cambios" }),
    el("p", { class: "estrato-valor", text: mm(dv.neto) }),
    el("p", { class: "estrato-detalle", text: `Ingreso neto acumulado de los proyectos aprobados hasta ${fechaCorta(dv.fecha)} según el BCRA (${mm(dv.bruto)} de ingresos y ${mm(dv.egresos)} de egresos). Mide divisas que entraron, no toda la inversión: parte se financia con fondos locales o equipos importados.` })));
  caja.append(cifras);
  if (plan.length) {
    const visibles = plan.filter((f) => f.anio <= new Date().getFullYear() + 6);
    const max = Math.max(...visibles.map((f) => f.total), 1);
    const lista = el("div", { class: "ranking", role: "list" });
    visibles.forEach((f) => lista.append(filaNivel(String(f.anio) + (f.anio < new Date().getFullYear() ? "" : f.anio === new Date().getFullYear() ? " (en curso)" : " (previsto)"), f.total, max, mm(f.total))));
    caja.append(el("p", { class: "unidad", text: `Cronograma anual de inversión de los proyectos aprobados (total previsto ${mm(e ? e.total_plan : 0)} hasta 2056)` }), lista);
  }
  caja.append(el("p", { class: "nota", text: "No hay un dato oficial de inversión ya ejecutada. La primera cifra es lo que los proyectos se comprometieron a invertir hasta hoy según el cronograma publicado por el Ministerio de Economía; la ejecución real puede ser menor o mayor. La segunda es el único dato observado disponible." }));
  return caja;
}

const TONO_ANTECEDENTE = { previo: "gris", activo_previo: "violeta", nuevo: "azul" };

function antecedentesRigi(d, mm) {
  const a = d.antecedentes;
  if (!a) return null;
  const max = Math.max(...a.grupos.map((g) => g.inversion), 1);
  const lista = el("div", { class: "ranking", role: "list" });
  a.grupos.forEach((g) => lista.append(filaNivel(`${g.etiqueta} (${g.proyectos})`, g.inversion, max,
    `${mm(g.inversion)} · ${fmt(100 * g.inversion / d.total_inversion, 0)}%`)));
  return el("div", { class: "rigi-antecedentes" },
    el("h4", { class: "subtitulo-ficha", text: "¿Proyectos nuevos o ya anunciados antes del RIGI?" }), lista,
    el("p", { class: "nota", text: "Clasificación propia a partir del primer anuncio público que encontramos de cada proyecto, comparado con abril de 2024, cuando el RIGI se presentó en el proyecto de Ley Bases. “Ya anunciado”: el mismo proyecto (con su inversión o capacidad) se había anunciado antes. “Activo previo”: el área, mina o planta existía antes, pero la inversión aprobada se anunció después. “Anunciado después”: no encontramos anuncios anteriores. Que un proyecto se anunciara antes no significa que se hubiera concretado sin el RIGI, ni lo contrario. Cada fila de la tabla enlaza a la fuente usada." }));
}

function celdaAntecedente(p) {
  const a = p.antecedente;
  if (!a) return el("td", { text: "s/d" });
  const [y, m] = (a.primer_anuncio || "").split("-");
  const cuando = (a.clave === "activo_previo" ? "Inversión anunciada: " : "Primer anuncio: ") + (m ? `${m}/${y}` : y);
  return el("td", {},
    el("span", { class: `estado-chip tono-${TONO_ANTECEDENTE[a.clave] || "gris"}`, text: a.etiqueta, title: a.detalle }),
    el("small", { class: "rigi-empresa" }, a.fuente ? el("a", { href: a.fuente, target: "_blank", rel: "noopener", title: a.detalle, text: cuando }) : cuando));
}

function fichaRigi(d) {
  const mm = (v) => "US$ " + fmt(v, 0) + " M";
  const maxS = Math.max(...d.sectores.map((s) => s.inversion), 1e-9);
  const sectores = el("div", { class: "ranking", role: "list" });
  d.sectores.forEach((s) => sectores.append(filaNivel(`${s.sector} (${s.proyectos})`, s.inversion, maxS, mm(s.inversion))));
  const t = el("table", { class: "tabla rigi" });
  t.append(el("thead", {}, el("tr", {}, ...["Proyecto", "Sector", "Provincia", "Inversión", "Empleos", "Antecedente"].map((h) => el("th", { scope: "col", text: h })))));
  const tb = el("tbody");
  d.proyectos.forEach((p) => tb.append(el("tr", {},
    el("td", {}, p.norma ? el("a", { href: p.norma, target: "_blank", rel: "noopener", text: p.nombre, title: p.descripcion }) : p.nombre, el("small", { class: "rigi-empresa", text: p.empresa })),
    el("td", { text: p.sector }), el("td", { text: p.provincias.join(", ") }),
    el("td", { class: "num", text: mm(p.inversion) }), el("td", { class: "num", text: p.empleos == null ? "s/d" : fmt(p.empleos, 0) }), celdaAntecedente(p))));
  t.append(tb);
  return el("article", { class: "ficha ancha", id: d.id },
    el("div", { class: "ficha-cab" }, el("div", {}, el("h3", { text: d.nombre }),
      el("p", { class: "unidad", text: `Inversión comprometida en millones de dólares · consultado el ${fechaCorta(d.fecha)}` }))),
    el("div", { class: "estratos" },
      el("div", { class: "estrato" }, el("p", { class: "estrato-nombre", text: "Proyectos aprobados" }), el("p", { class: "estrato-valor", text: String(d.proyectos.length) })),
      el("div", { class: "estrato" }, el("p", { class: "estrato-nombre", text: "Inversión comprometida" }), el("p", { class: "estrato-valor", text: mm(d.total_inversion) })),
      el("div", { class: "estrato" }, el("p", { class: "estrato-nombre", text: "Empleos estimados" }), el("p", { class: "estrato-valor", text: fmt(d.total_empleos, 0) }))),
    ejecucionRigi(d, mm),
    el("h4", { class: "subtitulo-ficha", text: "Por sector" }), sectores,
    antecedentesRigi(d, mm),
    el("h4", { class: "subtitulo-ficha", text: "Proyectos (el nombre lleva a la resolución de aprobación)" }),
    el("div", { class: "tabla-envoltura" }, t),
    el("p", { class: "nota", text: d.nota }),
    el("div", { class: "ficha-pie" }, el("span", { text: `Fuente: ${d.fuente}` })));
}

/* ---------- Imagen de dirigentes (encuestas) ---------- */

function fichaImagen(d) {
  const pct = (v) => fmt(v, 0) + "%";
  const lista = el("div", { class: "imagen-lista", role: "list" });
  const fila = (f) => {
    const detalle = f.mediciones.map((m) => `${m.encuestadora} (${fechaCorta(m.fecha)}): ${pct(m.positiva)} positiva, ${pct(m.negativa)} negativa`).join("\n");
    return el("div", { class: "imagen-fila", role: "listitem", title: detalle },
      el("span", { class: "imagen-nombre" }, f.figura, el("small", { text: f.n === 1 ? ` · 1 encuestadora (${f.mediciones[0].encuestadora})` : ` · ${f.n} encuestadoras` })),
      el("span", { class: "imagen-pista", "aria-label": `${pct(f.positiva)} positiva, ${pct(f.negativa)} negativa` },
        el("span", { class: "imagen-barra pos", style: `width:${f.positiva}%`, text: pct(f.positiva) }),
        el("span", { class: "imagen-barra neg", style: `width:${f.negativa}%`, text: pct(f.negativa) })),
      el("span", { class: "imagen-dif " + (Math.round(f.diferencial) >= 0 ? "pos" : "neg"), text: (Math.round(f.diferencial) > 0 ? "+" : "") + fmt(Math.round(f.diferencial), 0) }));
  };
  const varias = d.figuras.filter((f) => f.n >= 2), una = d.figuras.filter((f) => f.n < 2);
  varias.forEach((f) => lista.append(fila(f)));
  const resto = el("details", { class: "imagen-resto" }, el("summary", { text: `Ver ${una.length} dirigentes medidos por una sola encuestadora` }));
  const lista2 = el("div", { class: "imagen-lista", role: "list" });
  una.forEach((f) => lista2.append(fila(f)));
  resto.append(lista2);
  const fuentes = [...new Map(d.figuras.flatMap((f) => f.mediciones).map((m) => [m.encuestadora, m.fuente])).entries()];
  return el("article", { class: "ficha ancha", id: d.id },
    el("div", { class: "ficha-cab" }, el("div", {}, el("h3", { text: d.nombre }),
      el("p", { class: "unidad", text: `Imagen positiva y negativa, % de los encuestados · promedio de ${d.encuestadoras.join(", ")} · encuestas hasta ${fechaCorta(d.hasta)}` }))),
    el("div", { class: "imagen-leyenda" }, el("span", { class: "imagen-chip pos", text: "Positiva" }), el("span", { class: "imagen-chip neg", text: "Negativa" }), el("span", { class: "imagen-chip dif", text: "Diferencial (puntos)" })),
    lista, una.length ? resto : null,
    el("p", { class: "nota", text: d.nota + " Pasá el cursor sobre un dirigente para ver cada medición." }),
    el("div", { class: "ficha-pie" }, el("span", {}, "Fuentes: ", ...fuentes.flatMap(([n, u], i) => [i ? ", " : "", el("a", { href: u, target: "_blank", rel: "noopener", text: n })]))));
}

function recortarMiembro(m, hasta) {
  // copia del miembro con la serie cortada en una fecha, para comparar todos al mismo mes
  const lista = (m.vistas.desde_2003 || []).filter(([f]) => f <= hasta);
  if (!lista.length) return null;
  const [fu, vu] = lista[lista.length - 1];
  const d = fecha(fu), previo = lista.find(([f]) => f === `${d.getFullYear() - 1}-${String(d.getMonth() + 1).padStart(2, "0")}-01`);
  return { ...m, ultimo: { fecha: fu, valor: vu }, interanual_ultimo: previo && previo[1] ? (vu / previo[1] - 1) * 100 : null,
           vistas: { ...m.vistas, desde_2003: lista } };
}

function fichaGrupo(g) {
  if (g.ranking === "nivel") return fichaGrupoNivel(g);
  if (g.fecha_comun) {  // todos los miembros comparados al último mes que tienen en común
    const comun = g.miembros.map((m) => m.ultimo.fecha).sort()[0];
    const completos = g.miembros;
    g = { ...g, miembros: g.miembros.map((m) => recortarMiembro(m, comun)).filter(Boolean), completos };
  }
  const porDiferencia = g.ranking === "diferencia";
  let per = PERIODOS_RANKING[0];
  const esc = g.escala_ranking || 1, suf = g.sufijo_ranking ?? " mil";
  const decRank = (x) => (Math.abs(x) < 1 ? 2 : Math.abs(x) < 10 ? 1 : 0);
  const fmtRank = (v) => (porDiferencia ? signo(v * esc, decRank(v * esc)) + suf : signo(v) + "%");
  const detalle = el("div", { class: "grupo-detalle" });
  let elegido = null;
  const barras = el("div", { class: "ranking", role: "list" });
  const selector = el("select", { class: "selector", "aria-label": "Comparar contra", onchange: (e) => { per = PERIODOS_RANKING[e.target.selectedIndex]; pintar(); } },
    ...PERIODOS_RANKING.map((pr) => el("option", { text: pr.texto })));
  const subtitulo = el("p", { class: "unidad" });
  const pintar = () => {
    const ordenados = g.miembros.map((m) => [m, compararMiembro(m, per, porDiferencia)]).filter(([, v]) => v != null && isFinite(v)).sort((a, b) => b[1] - a[1]);
    const maxAbs = Math.max(...ordenados.map(([, v]) => Math.abs(v)), 1e-9);
    if (!elegido && ordenados[0]) elegido = ordenados[0][0].id;
    const ref = ordenados[0] ? periodo(ordenados[0][0].ultimo.fecha, ordenados[0][0].frecuencia) : "";
    const que = per.id === "anio" ? "contra un año antes"
      : porDiferencia ? `contra ${periodo(per.base, "M")}, el mes previo a la asunción`
      : `promedio de los últimos 12 meses contra los 12 meses previos a la asunción (hasta ${periodo(per.base, "M")})`;
    subtitulo.textContent = `${porDiferencia ? `Variación en ${g.unidad_ranking || "unidades"}` : "Variación %"} ${que} · último dato: ${ref}. Tocá una fila para ver su serie.`;
    barras.innerHTML = "";
    if (!ordenados.length) barras.append(el("p", { class: "vacio", text: "No hay datos para ese período." }));
    ordenados.forEach(([m, v]) => {
      const ancho = (Math.abs(v) / maxAbs) * 45;
      const fila = el("button", { type: "button", class: "rank-fila", "aria-pressed": String(m.id === elegido), role: "listitem",
        onclick: () => { elegido = m.id; pintar(); } },
        el("span", { class: "rank-nombre", text: m.nombre }),
        el("span", { class: "rank-pista" },
          el("span", { class: "rank-barra " + (v < 0 ? "neg" : "pos"), style: v < 0 ? `right:50%;width:${ancho}%` : `left:50%;width:${ancho}%` }),
          // barras largas: el número va adentro para no salirse de la ficha
          el("span", { class: "rank-num" + (ancho > 30 ? " dentro" : ""), style: ancho > 30 ? (v < 0 ? `right:${50 + ancho - 1}%;transform:translateX(100%)` : `left:${50 + ancho - 1}%;transform:translateX(-100%)`) : (v < 0 ? `right:${50 + ancho}%` : `left:${50 + ancho}%`), text: fmtRank(v) })));
      barras.append(fila);
    });
    if (detalle.dataset.id !== elegido) {
      detalle.innerHTML = "";
      detalle.dataset.id = elegido || "";
      const m = (g.completos || g.miembros).find((x) => x.id === elegido);
      if (m) detalle.append(ficha(m, { anidada: true }));
    }
  };
  pintar();
  return el("article", { class: "ficha ancha", id: g.id },
    el("div", { class: "ficha-cab" }, el("div", {}, el("h3", { text: g.nombre }), subtitulo)),
    el("label", { class: "etiqueta-selector" }, "Comparar contra ", selector),
    barras, detalle, g.nota ? el("p", { class: "nota", text: g.nota }) : null);
}

/* ---------- Pirámide de ingresos ---------- */

function fichaPiramide(d) {
  let lectura = "hogares";
  const colores = { Bajo: css("--s1"), Medio: css("--s2"), Alto: css("--s3") };
  const estratoDe = (dec) => (dec <= 4 ? "Bajo" : dec <= 8 ? "Medio" : "Alto");
  const cuerpo = el("div", { class: "piramide" });
  const resumen = el("div", { class: "estratos" });
  const botones = ["hogares", "personas"].map((k) => el("button", { type: "button", "aria-pressed": String(k === lectura), text: k === "hogares" ? "Hogares" : "Personas",
    onclick: () => { lectura = k; render(); } }));
  const pesos = (v) => "$ " + fmt(v, 0);
  function render() {
    botones.forEach((b) => b.setAttribute("aria-pressed", String(b.textContent.toLowerCase() === lectura)));
    const datos = d[lectura];
    const max = Math.max(...datos.deciles.map((x) => x.ingreso_medio));
    cuerpo.innerHTML = "";
    cuerpo.append(el("div", { class: "pir-fila pir-cab" }, el("span", { text: "Decil" }), el("span", { text: "Ingreso per cápita medio" }),
      el("span", { text: lectura === "hogares" ? "Hogares" : "Personas" })));
    [...datos.deciles].sort((a, b) => b.decil - a.decil).forEach((x) => {
      const e = estratoDe(x.decil);
      const cant = lectura === "hogares" ? x.hogares_miles : x.poblacion_miles;
      const rango = x.decil === 10 ? `más de ${pesos(x.desde)}` : `${pesos(x.desde)} a ${pesos(x.hasta)}`;
      cuerpo.append(el("div", { class: "pir-fila" },
        el("span", { class: "pir-decil" }, el("strong", { text: String(x.decil) }), el("small", { text: rango })),
        el("span", { class: "pir-pista" }, el("span", { class: "pir-barra", style: `width:${(x.ingreso_medio / max) * 100}%;background:${colores[e]}` }),
          // barras cortas: el monto va afuera, en tinta normal
          el("span", { class: "pir-num" + ((x.ingreso_medio / max) < 0.14 ? " afuera" : ""), style: (x.ingreso_medio / max) < 0.14 ? `left:calc(${(x.ingreso_medio / max) * 100}% + 6px)` : "", text: pesos(x.ingreso_medio) })),
        el("span", { class: "pir-cant", text: fmt(cant / 1000, 2) + " M" })));
    });
    resumen.innerHTML = "";
    datos.estratos.forEach((s) => resumen.append(el("div", { class: "estrato" },
      el("p", { class: "estrato-nombre" }, el("i", { style: `background:${colores[s.estrato]}` }), `Estrato ${s.estrato.toLowerCase()} (deciles ${s.deciles})`),
      el("p", { class: "estrato-valor", text: pesos(s.ingreso_medio) }),
      el("p", { class: "estrato-detalle", text: `ingreso per cápita medio · ${fmt(s.cantidad_miles / 1000, 2)} millones de ${lectura} · ${fmt(s.porcentaje_ingreso, 1)}% del ingreso total` }),
      el("p", { class: "estrato-detalle", text: `de ${pesos(s.desde)} a ${s.estrato === "Alto" ? "más" : pesos(s.hasta)} por persona` }))));
  }
  render();
  return el("article", { class: "ficha ancha", id: d.id },
    el("div", { class: "ficha-cab" }, el("div", {}, el("h3", { text: d.nombre }),
      el("p", { class: "unidad", text: `Ingreso per cápita familiar por decil, en pesos corrientes por mes · ${d.periodo}` }))),
    el("div", { class: "vistas", role: "group", "aria-label": "Lectura" }, ...botones),
    el("p", { class: "leyenda-vista", text: "Cada decil reúne al 10% de los " + "hogares o de las personas, ordenados por ingreso per cápita." }),
    resumen, cuerpo,
    el("p", { class: "nota", text: d.nota }),
    el("div", { class: "ficha-pie" }, el("span", { text: `Fuente: ${d.fuente}` })));
}

/* ---------- Mapas por provincia ---------- */

const VISTAS_MAPA = [
  { id: "intermensual", texto: "Mensual", desc: "Variación % contra el mes anterior." },
  { id: "interanual", texto: "Interanual", desc: "Variación % contra el mismo mes del año anterior." },
  { id: "desde_gestion", texto: "Gestión actual", desc: "Variación % acumulada desde noviembre de 2023." },
];

function proyectar(geo, W, H, pad = 8) {
  // Equirrectangular con corrección por latitud media: suficiente para un país
  let x0 = 180, x1 = -180, y0 = 90, y1 = -90;
  const recorrer = (c, fn) => (typeof c[0] === "number" ? fn(c) : c.forEach((d) => recorrer(d, fn)));
  geo.features.forEach((f) => recorrer(f.geometry.coordinates, ([x, y]) => { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }));
  const k = Math.cos(((y0 + y1) / 2) * Math.PI / 180);
  const esc = Math.min((W - 2 * pad) / ((x1 - x0) * k), (H - 2 * pad) / (y1 - y0));
  const ox = (W - (x1 - x0) * k * esc) / 2, oy = (H - (y1 - y0) * esc) / 2;
  const P = ([x, y]) => [ox + (x - x0) * k * esc, oy + (y1 - y) * esc];
  const anillo = (r) => r.map((c, i) => (i ? "L" : "M") + P(c).map((v) => v.toFixed(1)).join(",")).join("") + "Z";
  return (g) => (g.type === "Polygon" ? g.coordinates.map(anillo).join("") : g.coordinates.map((pol) => pol.map(anillo).join("")).join(""));
}

function colorDivergente(v, max) {
  // azul (positivo) – gris (cero) – rojo (negativo), en 5 pasos por lado
  if (v == null) return css("--grilla");
  const azules = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf"];
  const rojos = ["#fbd5d2", "#f5aaa4", "#ec7d76", "#e34948", "#b8302f"];
  const paso = Math.min(4, Math.floor((Math.abs(v) / (max || 1)) * 5));
  if (Math.abs(v) < max * 0.02) return css("--insignia");
  return v > 0 ? azules[paso] : rojos[paso];
}

function colorSecuencial(v, max) {
  const azules = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"];
  if (v == null) return css("--grilla");
  return azules[Math.min(5, Math.floor((v / (max || 1)) * 6))];
}

function fichaMapa(m, geo) {
  const VISTAS = m.vistas || VISTAS_MAPA.map((v) => ({ ...v, sufijo: "%" }));
  let vista = VISTAS.find((v) => v.id === "interanual") ? "interanual" : VISTAS[0].id;
  const H = 420;
  const cont = el("div", { class: "mapa" });
  const leyenda = el("div", { class: "mapa-leyenda" });
  const tabla = el("ol", { class: "mapa-lista" });
  const desc = el("p", { class: "leyenda-vista" });
  const botones = VISTAS.map((v) => el("button", { type: "button", "aria-pressed": String(v.id === vista), text: v.texto, onclick: () => { vista = v.id; render(); } }));
  const tip = document.getElementById("tooltip");
  function render() {
    botones.forEach((b, i) => b.setAttribute("aria-pressed", String(VISTAS[i].id === vista)));
    const vv = VISTAS.find((v) => v.id === vista);
    const suf = vv.sufijo || "%";
    const fmtV = (v) => (v == null ? "s/d" : (vv.secuencial ? fmt(v, 1) : signo(v)) + suf);
    const colorDe = (v, max) => (vv.secuencial ? colorSecuencial(v, max) : colorDivergente(v, max));
    desc.textContent = vv.desc;
    const vals = Object.entries(m.provincias).filter(([n]) => n !== "Total del país").map(([n, x]) => [n, x[vista]]);
    const max = Math.max(...vals.map(([, v]) => Math.abs(v ?? 0)), 0.1);
    const W = Math.min(cont.clientWidth || 300, 340);
    const path = proyectar(geo, W, H);
    cont.innerHTML = "";
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": `${m.nombre}: ${desc.textContent}` });
    geo.features.forEach((f) => {
      const n = f.properties.nombre, v = m.provincias[n]?.[vista];
      const p = svgEl("path", { d: path(f.geometry), fill: colorDe(v, max), stroke: css("--superficie"), "stroke-width": 0.8 });
      const mostrar = (ev) => {
        tip.innerHTML = "";
        tip.append(el("div", { class: "t-fecha", text: n.replace(", Antártida e Islas del Atlántico Sur", "") }), el("div", { class: "t-fila" }, el("span", { text: vv.texto }), el("span", { text: fmtV(v) })));
        tip.hidden = false;
        tip.style.left = Math.min(window.innerWidth - tip.offsetWidth - 8, ev.clientX + 14) + "px";
        tip.style.top = Math.max(8, ev.clientY - tip.offsetHeight - 12) + "px";
        p.setAttribute("stroke", css("--tinta")); p.setAttribute("stroke-width", 1.5);
      };
      p.addEventListener("mousemove", mostrar);
      p.addEventListener("mouseleave", () => { tip.hidden = true; p.setAttribute("stroke", css("--superficie")); p.setAttribute("stroke-width", 0.8); });
      svg.append(p);
    });
    cont.append(svg);
    leyenda.innerHTML = "";
    const escala = vv.secuencial ? [0, max / 3, (2 * max) / 3, max] : [-max, -max / 2, 0, max / 2, max];
    leyenda.append(...escala.map((v) => el("span", {}, el("i", { style: `background:${colorDe(v === 0 ? 0 : v * 0.999, max)}` }), (vv.secuencial ? fmt(v, 0) : signo(v, max < 10 ? 1 : 0)) + suf)));
    tabla.innerHTML = "";
    [...vals].sort((a, b) => (b[1] ?? -1e9) - (a[1] ?? -1e9)).forEach(([n, v]) =>
      tabla.append(el("li", {}, el("span", { text: n.replace(", Antártida e Islas del Atlántico Sur", "") }), el("span", { text: fmtV(v) }))));
  }
  const total = m.provincias["Total del país"];
  const art = el("article", { class: "ficha ancha", id: m.id },
    el("div", { class: "ficha-cab" },
      el("div", {}, el("h3", { text: m.nombre }), el("p", { class: "unidad", text: `${m.unidad} · ${m.periodo || periodo(m.fecha, "M")}` })),
      total ? el("div", { class: "cifra" }, el("span", { class: "grande" }, signo(total[VISTAS[m.vistas ? 0 : 1].id]) + (VISTAS[m.vistas ? 0 : 1].sufijo || "%"), el("small", { text: " " + VISTAS[m.vistas ? 0 : 1].texto.toLowerCase() })), el("span", { class: "chica", text: "total del país" })) : null),
    el("div", { class: "vistas", role: "group", "aria-label": "Vista del mapa" }, ...botones), desc,
    el("div", { class: "mapa-cuerpo" }, el("div", {}, cont, leyenda), tabla),
    m.nota ? el("p", { class: "nota", text: m.nota }) : null,
    el("div", { class: "ficha-pie" }, el("span", { text: `Fuente: ${m.fuente}` })));
  new ResizeObserver(() => render()).observe(cont);
  return art;
}

/* ---------- Gobierno (registros con nombre) ---------- */

function parseCSV(texto) {
  const filas = []; let fila = [], campo = "", q = false;
  for (let i = 0; i < texto.length; i++) {
    const ch = texto[i];
    if (q) {
      if (ch === '"' && texto[i + 1] === '"') { campo += '"'; i++; }
      else if (ch === '"') q = false;
      else campo += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { fila.push(campo); campo = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && texto[i + 1] === "\n") i++;
      fila.push(campo); campo = "";
      if (fila.some((c) => c !== "")) filas.push(fila);
      fila = [];
    } else campo += ch;
  }
  if (campo !== "" || fila.length) { fila.push(campo); filas.push(fila); }
  const [cab, ...resto] = filas;
  return resto.map((r) => Object.fromEntries(cab.map((c, i) => [c, (r[i] || "").trim()])));
}
async function csv(nombre) {
  try {
    const r = await fetch(`${DATOS}politica/${nombre}.csv`);
    if (!r.ok) return null;
    return parseCSV(await r.text());
  } catch { return null; }
}

function correspondeGestion(valor, gestion) {
  if (!valor) return false;
  if (valor === gestion.nombre) return true;
  if (valor.includes("/")) {
    const base = gestion.nombre.replace(/ I+$/, "");
    return valor.split("/").map((s) => s.trim()).includes(base);
  }
  return false;
}

function fuentes(texto) {
  const urls = (texto || "").split(/[;|\s]+/).filter((u) => /^https?:\/\//.test(u));
  if (!urls.length) return null;
  return el("p", { class: "fuentes" }, ...urls.map((u) => {
    let host = u; try { host = new URL(u).hostname.replace(/^www\d?\./, ""); } catch {}
    return el("a", { href: u, target: "_blank", rel: "noopener", text: host });
  }));
}

function fechaCorta(s) {
  if (!s) return "";
  const m = s.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
  if (!m) return s;
  return `${m[3] ? Number(m[3]) + " " : ""}${MESES[Number(m[2]) - 1]} ${m[1]}`;
}

/* Estados con color: rojo = condena / incumplida / vetada; naranja = intermedio desfavorable;
   ámbar = en curso; violeta = procesado; azul = investigación o avance; verde = cumplida / vigente / sobreseído */
const TONOS = {
  "Condena firme": "rojo", "Condena en primera instancia": "naranja", "En juicio": "ambar", "Elevada a juicio": "ambar",
  "Procesado": "violeta", "En investigación": "azul", "Sobreseído": "verde", "Sin causa judicial": "gris",
  "Sancionada": "verde", "Vigente": "verde", "Veto superado": "azul", "Vetada": "rojo", "Rechazada": "gris", "Pendiente": "ambar",
  "Cumplida": "verde", "Incumplida": "rojo", "Incumplida con avances": "naranja", "En proceso, adelantada": "azul", "En proceso, demorada": "ambar",
};
const tono = (estado) => TONOS[estado] || "gris";

function resumenEstados(filas, campo, orden) {
  const cuentas = {};
  filas.forEach((r) => { const e = r[campo]; if (e) cuentas[e] = (cuentas[e] || 0) + 1; });
  const claves = Object.keys(cuentas).sort((a, b) => (orden.indexOf(a) + 99) % 99 - (orden.indexOf(b) + 99) % 99);
  return el("div", { class: "estados-resumen" }, ...claves.map((k) =>
    el("span", { class: "estado-chip tono-" + tono(k) }, el("strong", { text: String(cuentas[k]) }), " " + k)));
}

function bloqueLista(titulo, intro, filas, item, { porGestion = true, estado = null, orden = [] } = {}) {
  const lista = el("div", { class: "lista" });
  const caja = el("div", { class: "bloque", id: slug(titulo) }, el("h3", { text: titulo }), el("p", { class: "intro", text: intro }));
  const resumen = el("div");
  let filtro = null, todos = false;
  const MAX = 8;
  const pintar = () => {
    lista.innerHTML = "";
    const sel = filtro ? filas.filter((r) => correspondeGestion(r.gestion, filtro)) : filas;
    if (estado) { resumen.innerHTML = ""; resumen.append(resumenEstados(sel, estado, orden)); }
    if (!sel.length) lista.append(el("p", { class: "vacio", text: "Sin registros para esta gestión." }));
    (todos ? sel : sel.slice(0, MAX)).forEach((r) => lista.append(item(r)));
    if (sel.length > MAX) lista.append(el("button", { type: "button", class: "ver-mas", text: todos ? "Ver menos" : `Ver los ${sel.length}`,
      onclick: () => { todos = !todos; pintar(); } }));
  };
  if (porGestion) {
    const opciones = [null, ...GESTIONES.filter((g) => filas.some((r) => correspondeGestion(r.gestion, g)))];
    const botones = opciones.map((g) => el("button", { type: "button", "aria-pressed": String(g === null), text: g ? g.corto : "Todas",
      onclick: () => { filtro = g; todos = false; botones.forEach((b, i) => b.setAttribute("aria-pressed", String(opciones[i] === g))); pintar(); } }));
    caja.append(el("div", { class: "filtro", role: "group", "aria-label": "Filtrar por gestión" }, ...botones));
  }
  caja.append(resumen, lista);
  pintar();
  return caja;
}

function itemDetalle({ insignia, fuerte, estado, titulo, meta, resumen, cita, campos, fuentesTexto }) {
  const dl = el("dl");
  for (const [k, v] of campos) if (v) dl.append(el("dt", { text: k }), el("dd", { text: v }));
  return el("details", { class: "item" + (estado ? " con-estado tono-" + tono(estado) : "") },
    el("summary", {},
      estado ? el("span", { class: "estado tono-" + tono(estado), text: estado }) : null,
      el("div", { class: "item-cab" },
        insignia ? el("span", { class: "insignia" + (fuerte ? " fuerte" : ""), text: insignia }) : null,
        el("span", { class: "item-titulo", text: titulo }),
        meta ? el("span", { class: "item-meta", text: meta }) : null),
      resumen ? el("p", { class: "item-resumen", text: resumen }) : null,
      cita ? el("p", { class: "cita", text: cita }) : null),
    dl, fuentes(fuentesTexto));
}

const cortoGestion = (g) => (g || "").split("/").map((s) => (GESTIONES.find((x) => x.nombre === s.trim()) || { corto: s.trim().replace("Cristina Fernández de Kirchner", "CFK") }).corto).join(" / ");

async function gobierno() {
  const [promesas, causas, leyes, dichos, altos, ministros] = await Promise.all(
    ["promesas", "causas", "leyes", "dichos", "gabinete_altos_funcionarios", "gabinete_ministros"].map(csv));
  const cont = document.getElementById("gobierno-bloques");
  let alguno = false;

  if (promesas) {
    alguno = true;
    cont.append(bloqueLista("Promesas y hechos",
      "Promesas de campaña y de asunción con su veredicto al cierre del mandato (o al último balance). Macri, Fernández y Milei: relevamiento de Chequeado, salvo dos promesas de Milei (dolarizar y cerrar el Banco Central) que el sitio califica como incumplidas a la fecha porque el resultado prometido no existe; cada una lo indica en su metodología. Kirchner y CFK: relevamiento propio con el mismo criterio, a partir del discurso de asunción y anuncios formales.",
      promesas.filter((r) => r.veredicto), (r) => itemDetalle({
        estado: r.veredicto, titulo: r.promesa, meta: cortoGestion(r.gestion),
        resumen: r.dato_clave, campos: [["Veredicto al", fechaCorta(r.fecha_veredicto)], ["Metodología", r.metodologia]], fuentesTexto: r.fuente }),
      { estado: "veredicto", orden: ["Cumplida", "En proceso, adelantada", "En proceso, demorada", "Incumplida con avances", "Incumplida"] }));
  }
  if (causas) {
    alguno = true;
    cont.append(bloqueLista("Causas judiciales e investigaciones",
      "Casos con causa judicial y cobertura de medios de distintas líneas editoriales, con su estado procesal a la fecha indicada. Aparte, investigaciones administrativas o periodísticas sin causa judicial. Ser investigado no implica culpabilidad.",
      causas, (r) => itemDetalle({
        estado: r.estado_resumen, insignia: r.tipo && r.tipo.startsWith("Causa") ? (r.materia || "Causa judicial") : "Investigación administrativa", titulo: r.caso, meta: cortoGestion(r.gestion),
        resumen: r.estado_judicial,
        campos: [["Qué se investiga", r.que_se_investiga], ["Principales acusados", r.principales_acusados], ["Tribunal u organismo", r.tribunal], ["Estado al", fechaCorta(r.fecha_estado)]],
        fuentesTexto: r.fuentes }),
      { estado: "estado_resumen", orden: ["Condena firme", "Condena en primera instancia", "En juicio", "Elevada a juicio", "Procesado", "En investigación", "Sobreseído", "Sin causa judicial"] }));
  }
  if (leyes) {
    alguno = true;
    cont.append(bloqueLista("Leyes y decretos discutidos",
      "Normas propuestas desde diciembre de 2023 por el Gobierno, sus aliados o la oposición: recorrido, resultado, cambios en el trámite y judicialización.",
      leyes, (r) => itemDetalle({
        estado: r.estado_resumen, titulo: r.norma, meta: r.impulsor, resumen: r.que_proponia,
        campos: [["Resultado", r.resultado], ["Recorrido", r.recorrido], ["Cómo votó el oficialismo", r.voto_oficialismo], ["Cambios en el trámite", r.cambios_en_el_tramite], ["Judicialización o aplicación", r.judicializacion_o_aplicacion], ["Estado al", fechaCorta(r.fecha_estado)]],
        fuentesTexto: r.fuentes }),
      { porGestion: false, estado: "estado_resumen", orden: ["Sancionada", "Vigente", "Veto superado", "Pendiente", "Vetada", "Rechazada"] }));
  }
  if (dichos) {
    alguno = true;
    cont.append(bloqueLista("Dichos, prensa y redes",
      "Dichos de funcionarios en ejercicio, agresiones o presiones a periodistas y medios, y conducta en redes, con cita textual y fuente. No incluye a particulares.",
      dichos, (r) => itemDetalle({
        insignia: r.tipo, titulo: `${r.protagonista} — ${fechaCorta(r.fecha)}`, meta: r.cargo, resumen: r.hecho,
        cita: r.cita_textual ? `“${r.cita_textual.replace(/^"|"$/g, "")}”` : null,
        campos: [["Desenlace", r.desenlace]], fuentesTexto: r.fuentes })));
  }
  if (altos || ministros) {
    alguno = true;
    const caja = el("div", { class: "bloque", id: "gabinete" }, el("h3", { text: "Rotación de funcionarios" }));
    if (altos) {
      caja.append(el("p", { class: "intro", text: "Renuncias de altos funcionarios políticos por gestión, según el recuento del politólogo Pablo Salinas (no publica su metodología)." }));
      const max = Math.max(...altos.map((r) => Number(r.renuncias_altos_funcionarios) || 0));
      const barras = el("div", { class: "barras" });
      altos.forEach((r) => {
        const n = Number(r.renuncias_altos_funcionarios);
        const g = GESTIONES.find((x) => x.nombre === r.gestion);
        const pista = el("div", { class: "pista" });
        if (n) {
          const pct = (n / max) * 100;
          pista.append(el("div", { class: "relleno", style: `width:${pct}%` }), el("span", { class: "num" + (pct > 70 ? " dentro" : ""), style: `left:${pct}%`, text: fmt(n, 0) + (r.nota && r.nota.startsWith("En curso") ? " (en curso)" : "") }));
        } else pista.append(el("span", { class: "sin-dato", text: r.nota || "Sin dato publicado" }));
        barras.append(el("div", { class: "barra" }, el("span", { text: g ? g.corto : r.gestion }), pista));
      });
      caja.append(barras, fuentes(altos.map((r) => r.fuente).filter((v, i, a) => a.indexOf(v) === i).join(";")));
    }
    if (ministros) {
      caja.append(el("p", { class: "intro", style: "margin-top:20px", text: "Ministros y jefes de Gabinete. Reemplazo: otra persona asume la misma cartera. Reestructuración: la cartera se elimina, fusiona o cambia de nombre. Traslado: la misma persona pasa a otra cartera." }));
      const t = el("table", { class: "tabla" });
      t.append(el("thead", {}, el("tr", {}, ...["Gestión", "Ministros", "Reemplazos", "Por año", "Traslados", "Reestructuraciones", "Permanencia media (meses)"].map((h) => el("th", { scope: "col", text: h })))));
      const tb = el("tbody");
      ministros.forEach((r) => tb.append(el("tr", {}, el("td", { text: cortoGestion(r.gestion) + (r.gestion === "Javier Milei" ? " (en curso)" : "") }),
        ...[r.ministros, r.reemplazos, fmt(Number(r.reemplazos_por_anio), 1), r.traslados, r.reestructuraciones, fmt(Number(r.permanencia_promedio_meses), 1)].map((v) => el("td", { text: v })))));
      t.append(tb);
      caja.append(el("div", { class: "tabla-envoltura" }, t));
    }
    cont.append(caja);
  }
  if (alguno) {
    document.getElementById("gobierno").hidden = false;
    document.getElementById("nav-secciones").append(el("a", { href: "#gobierno", text: "Gobierno" }));
  }
}

/* ---------- Inicio ---------- */

async function iniciar() {
  const indice = await (await fetch(`${DATOS}indice.json`)).json();
  // un archivo con problemas no tumba la página: ese indicador simplemente no se muestra
  const leer = async (id) => { try { return await (await fetch(`${DATOS}${id}.json`)).json(); } catch { return null; } };
  const fichas = (await Promise.all(indice.map(async (i) => {
    if (i.tipo !== "grupo") return leer(i.id);
    const miembros = (await Promise.all(i.miembros.map(leer))).filter(Boolean);
    return miembros.length ? { ...i, miembros, actualizado: miembros[0].actualizado } : null;
  }))).filter(Boolean);
  const listaMapas = (await leer("mapas/indice")) || [];
  const mapasCargados = (await Promise.all(listaMapas.map((m) => leer(`mapas/${m}`)))).filter(Boolean);
  const geo = mapasCargados.length ? await leer("mapas/provincias") : null;
  const piramide = await leer("distribucion_ingreso");
  const rigi = await leer("rigi");
  const imagen = await leer("encuestas_imagen");
  const actualizado = fichas.map((f) => f.actualizado).sort().pop();
  document.getElementById("actualizado").textContent = actualizado ? `Actualizado el ${fechaCorta(actualizado)}.` : "";

  const tarjetas = document.getElementById("tarjetas");
  fichas.filter((f) => f.portada).forEach((f) => tarjetas.append(tarjeta(f)));

  const nav = document.getElementById("nav-secciones");
  const secciones = document.getElementById("secciones");
  const nombres = [...new Set([...fichas.map((f) => f.seccion), ...mapasCargados.map((m) => m.seccion)])].sort((a, b) => (ORDEN_SECCIONES.indexOf(a) + 99) % 99 - (ORDEN_SECCIONES.indexOf(b) + 99) % 99);
  for (const s of nombres) {
    const id = slug(s);
    nav.append(el("a", { href: `#${id}`, text: s }));
    const grilla = el("div", { class: "grilla" });
    fichas.filter((f) => f.seccion === s).forEach((f) => grilla.append(f.tipo === "grupo" ? fichaGrupo(f) : ficha(f)));
    if (geo) mapasCargados.filter((m) => m.seccion === s).forEach((m) => grilla.append(fichaMapa(m, geo)));
    if (piramide && piramide.seccion === s) grilla.append(fichaPiramide(piramide));
    if (rigi && rigi.seccion === s) grilla.append(fichaRigi(rigi));
    if (imagen && imagen.seccion === s) grilla.append(fichaImagen(imagen));
    secciones.append(el("section", { class: "seccion", id, "aria-labelledby": `t-${id}` }, el("h2", { id: `t-${id}`, text: s }), grilla));
  }
  await gobierno();
}

iniciar().catch((e) => {
  document.getElementById("secciones").append(el("p", { class: "vacio", text: "No se pudieron cargar los datos. " + e.message }));
});
