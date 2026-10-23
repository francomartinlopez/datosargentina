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
const ORDEN_SECCIONES = ["Precios", "Actividad", "Empleo e ingresos", "Pobreza y programas sociales",
  "Sector externo e inversión", "Estado y fiscal", "Dólar y finanzas", "Crédito y alquileres", "Opinión pública"];
const FUENTES = {
  datosgobar: "INDEC y organismos nacionales (datos.gob.ar)",
  bcra: "BCRA",
  argentinadatos: "ArgentinaDatos",
  fred: "FRED",
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
const esIndice = (f) => /índice/.test(f.unidad) && f.tipo_valor !== "tasa";

function cifraPrincipal(f) {
  const variacionMensual = esDiferencia(f)
    ? (f.tipo_valor === "saldo" ? signoMonto(f.intermensual, f.unidad) : signo(f.intermensual, decimales(f.intermensual || 0)) + sufijoDiferencia(f))
    : signo(f.intermensual) + "%";
  const contra = f.frecuencia === "T" ? "vs. trimestre anterior" : "vs. mes anterior";
  if (f.vista_historica === "mensual") {
    return { grande: fmt(f.intermensual) + "%", etiqueta: "mensual", chica: `interanual ${fmt(f.interanual_ultimo)}%` };
  }
  if (esIndice(f)) {
    return { grande: signo(f.interanual_ultimo) + "%", etiqueta: "interanual", chica: `${variacionMensual} ${contra}` };
  }
  const vu = valorConUnidad(f.ultimo.valor, f.unidad);
  return { grande: vu.num, etiqueta: vu.resto, chica: `${variacionMensual} ${contra}` };
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
      return f.vista_historica === "mensual" ? "Variación % mensual desde diciembre de 2023." : "Serie en su unidad desde diciembre de 2023.";
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
  const series = [{ nombre: f.nombre, color: css("--s1"), puntos: puntos(v), grueso: true }];
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
      ? (cfg.frecuencia === "T" ? periodo(new Date(xRef).toISOString().slice(0, 10), "T") : `${MESES_LARGO[new Date(xRef).getMonth()]} ${new Date(xRef).getFullYear()}`)
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

function ficha(f) {
  const c = cifraPrincipal(f);
  const grafico = el("div", { class: "grafico" });
  const leyendaVista = el("p", { class: "leyenda-vista" });
  const leyenda = el("ul", { class: "leyenda", hidden: true });
  const vistasDisponibles = VISTAS.filter((v) => (v.id === "comparativa" ? Object.keys(f.vistas.comparativa || {}).length : (f.vistas[v.id] || []).length));
  let actual = vistasDisponibles.find((v) => v.id === "interanual") ? "interanual" : vistasDisponibles[0]?.id;
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
  const art = el("article", { class: "ficha", id: f.id },
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

function bloqueLista(titulo, intro, filas, item, { porGestion = true } = {}) {
  const lista = el("div", { class: "lista" });
  const caja = el("div", { class: "bloque", id: slug(titulo) }, el("h3", { text: titulo }), el("p", { class: "intro", text: intro }));
  let filtro = null, todos = false;
  const MAX = 8;
  const pintar = () => {
    lista.innerHTML = "";
    const sel = filtro ? filas.filter((r) => correspondeGestion(r.gestion, filtro)) : filas;
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
  caja.append(lista);
  pintar();
  return caja;
}

function itemDetalle({ insignia, fuerte, titulo, meta, resumen, cita, campos, fuentesTexto }) {
  const dl = el("dl");
  for (const [k, v] of campos) if (v) dl.append(el("dt", { text: k }), el("dd", { text: v }));
  return el("details", { class: "item" },
    el("summary", {},
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
      "Promesas de campaña y de asunción con su veredicto al cierre del mandato (o al último balance). Macri, Fernández y Milei: relevamiento de Chequeado. Kirchner y CFK: relevamiento propio con el mismo criterio, a partir del discurso de asunción y anuncios formales.",
      promesas.filter((r) => r.veredicto), (r) => itemDetalle({
        insignia: r.veredicto, fuerte: r.veredicto === "Cumplida", titulo: r.promesa, meta: cortoGestion(r.gestion),
        resumen: r.dato_clave, campos: [["Veredicto al", fechaCorta(r.fecha_veredicto)], ["Metodología", r.metodologia]], fuentesTexto: r.fuente })));
  }
  if (causas) {
    alguno = true;
    cont.append(bloqueLista("Causas judiciales e investigaciones",
      "Casos con causa judicial y cobertura de medios de distintas líneas editoriales, con su estado procesal a la fecha indicada. Aparte, investigaciones administrativas o periodísticas sin causa judicial. Ser investigado no implica culpabilidad.",
      causas, (r) => itemDetalle({
        insignia: r.tipo && r.tipo.startsWith("Causa") ? (r.materia || "Causa judicial") : "Sin causa judicial", titulo: r.caso, meta: cortoGestion(r.gestion),
        resumen: r.estado_judicial,
        campos: [["Qué se investiga", r.que_se_investiga], ["Principales acusados", r.principales_acusados], ["Tribunal u organismo", r.tribunal], ["Estado al", fechaCorta(r.fecha_estado)]],
        fuentesTexto: r.fuentes })));
  }
  if (leyes) {
    alguno = true;
    cont.append(bloqueLista("Leyes y decretos discutidos",
      "Normas propuestas desde diciembre de 2023 por el Gobierno, sus aliados o la oposición: recorrido, resultado, cambios en el trámite y judicialización.",
      leyes, (r) => itemDetalle({
        insignia: (r.resultado || "").split(/[(:]/)[0].trim(), titulo: r.norma, meta: r.impulsor, resumen: r.que_proponia,
        campos: [["Recorrido", r.recorrido], ["Cambios en el trámite", r.cambios_en_el_tramite], ["Judicialización o aplicación", r.judicializacion_o_aplicacion], ["Estado al", fechaCorta(r.fecha_estado)]],
        fuentesTexto: r.fuentes }), { porGestion: false }));
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
  const fichas = await Promise.all(indice.map(async (i) => (await fetch(`${DATOS}${i.id}.json`)).json()));
  const actualizado = fichas.map((f) => f.actualizado).sort().pop();
  document.getElementById("actualizado").textContent = actualizado ? `Actualizado el ${fechaCorta(actualizado)}.` : "";

  const tarjetas = document.getElementById("tarjetas");
  fichas.filter((f) => f.portada).forEach((f) => tarjetas.append(tarjeta(f)));

  const nav = document.getElementById("nav-secciones");
  const secciones = document.getElementById("secciones");
  const nombres = [...new Set(fichas.map((f) => f.seccion))].sort((a, b) => (ORDEN_SECCIONES.indexOf(a) + 99) % 99 - (ORDEN_SECCIONES.indexOf(b) + 99) % 99);
  for (const s of nombres) {
    const id = slug(s);
    nav.append(el("a", { href: `#${id}`, text: s }));
    const grilla = el("div", { class: "grilla" });
    fichas.filter((f) => f.seccion === s).forEach((f) => grilla.append(ficha(f)));
    secciones.append(el("section", { class: "seccion", id, "aria-labelledby": `t-${id}` }, el("h2", { id: `t-${id}`, text: s }), grilla));
  }
  await gobierno();
}

iniciar().catch((e) => {
  document.getElementById("secciones").append(el("p", { class: "vacio", text: "No se pudieron cargar los datos. " + e.message }));
});
