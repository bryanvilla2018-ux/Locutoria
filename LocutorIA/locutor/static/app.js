'use strict';
/* ====================== utilidades ====================== */
const $ = (s, e = document) => e.querySelector(s);
// replaceChildren tolerante: acepta listas anidadas y descarta null/false
const _rc = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...k) { _rc.apply(this, k.flat(Infinity).filter(x => x != null && x !== false)); };
function h(tag, a, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(a || {})) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value' || k === 'checked') el[k] = v;
    else if (v === true) el.setAttribute(k, '');
    else if (v != null && v !== false) el.setAttribute(k, v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(k));
  if (a && a.value != null) el.value = a.value;
  return el;
}
async function api(ruta, metodo = 'GET', cuerpo) {
  const r = await fetch('/api/' + ruta, { method: metodo, headers: { 'Content-Type': 'application/json', 'X-Locutor': '1' }, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });
  let j = null; try { j = await r.json(); } catch (e) { /* sin cuerpo */ }
  if (!r.ok) throw new Error((j && j.error) || r.statusText);
  return j;
}
function toast(msg, tipo = 'ok') { const t = h('div', { class: 'toast ' + (tipo === 'err' ? 'err' : '') }, msg); $('#toasts').append(t); setTimeout(() => t.remove(), tipo === 'err' ? 7000 : 2600); }
const hacer = (fn, ok) => async (...a) => { try { const r = await fn(...a); if (ok) toast(ok); return r; } catch (e) { toast(e.message, 'err'); } };
function reproducir(url, titulo) {
  $('#rep-titulo').textContent = titulo || 'Vista previa'; const a = $('#rep-audio'); a.src = url; $('#reproductor').classList.remove('oculto'); a.play();
}
$('#rep-cerrar').onclick = () => { $('#rep-audio').pause(); $('#reproductor').classList.add('oculto'); };
async function descargar(url, nombre) {
  const t = await (await fetch(url)).text();
  if (window.pywebview && pywebview.api && pywebview.api.guardar) { await pywebview.api.guardar(nombre, t); return; }
  const a = h('a', { href: URL.createObjectURL(new Blob([t], { type: 'text/csv' })), download: nombre }); document.body.append(a); a.click(); a.remove();
}
const nativo = () => !!(window.pywebview && pywebview.api && pywebview.api.elegir_archivo);
const fmtDur = s => s ? Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0') : '';
const hoy = () => new Date(new Date() - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 10);

/* ====================== ajustes (se guardan solos) ====================== */
let S = {}, pend = {}, tmr = null;
const get = p => p.split('.').reduce((o, k) => (o == null ? o : o[k]), S);
function set(p, v) {
  const ks = p.split('.'); let o = S; for (const k of ks.slice(0, -1)) o = (o[k] = o[k] || {}); o[ks[ks.length - 1]] = v;
  pend[p] = v; clearTimeout(tmr); tmr = setTimeout(flush, 350); $('#guardado').textContent = 'Guardando…';
}
async function flush() {
  const c = pend; pend = {};
  try { await api('ajustes', 'PATCH', { cambios: c }); $('#guardado').textContent = '✓ Cambios guardados'; }
  catch (e) { toast('No se pudo guardar: ' + e.message, 'err'); }
}

/* ====================== controles de formulario ====================== */
function campoG(etq, leer, escribir, o = {}) {
  const t = o.tipo || 'text', val = leer(); let ctl, extra = null;
  if (t === 'check') ctl = h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: !!val, onchange: e => escribir(e.target.checked) }), h('span', { class: 'slider' }));
  else if (t === 'area') ctl = h('textarea', { rows: o.filas || 3, oninput: e => escribir(e.target.value) }, val == null ? '' : val);
  else if (t === 'lineas') ctl = h('textarea', { rows: o.filas || 3, placeholder: o.ph || '', oninput: e => escribir(e.target.value.split('\n').map(x => x.trim()).filter(Boolean)) }, (val || []).join('\n'));
  else if (t === 'minutos') ctl = h('input', { type: 'text', value: (val || []).join(', '), onchange: e => escribir(e.target.value.split(/[ ,;]+/).map(Number).filter(n => n >= 0 && n < 60)) });
  else if (t === 'select') ctl = h('select', { value: String(val), onchange: e => escribir(o.num ? Number(e.target.value) : e.target.value) }, o.opciones.map(x => h('option', { value: String(x.v !== undefined ? x.v : x) }, x.t || x)));
  else if (t === 'num') ctl = h('input', { type: 'number', min: o.min, max: o.max, step: o.paso || 1, value: val == null ? 0 : val, onchange: e => escribir(e.target.value === '' ? 0 : Number(e.target.value)) });
  else if (t === 'rango') { extra = h('span', { class: 'valor' }, val); ctl = h('input', { type: 'range', min: o.min, max: o.max, step: o.paso, value: val, oninput: e => { extra.textContent = e.target.value; escribir(Number(e.target.value)); } }); }
  else if (t === 'fecha' || t === 'hora') ctl = h('input', { type: t === 'fecha' ? 'date' : 'time', value: val || '', onchange: e => escribir(e.target.value) });
  else if (t === 'dias') ctl = h('div', { class: 'dias' }, ['L', 'M', 'X', 'J', 'V', 'S', 'D'].map((d, i) => h('label', {}, h('input', { type: 'checkbox', checked: (val || [1, 1, 1, 1, 1, 1, 1])[i] === 1, onchange: e => { const a = (leer() || [1, 1, 1, 1, 1, 1, 1]).slice(); a[i] = e.target.checked ? 1 : 0; escribir(a); } }), h('span', {}, d))));
  else if (t === 'secreto') ctl = h('input', { type: 'password', autocomplete: 'off', placeholder: get('claves_guardadas.' + o.clave) ? '•••••••• guardada (escribe para cambiarla)' : 'Pega tu clave aquí', onchange: e => { escribir(e.target.value); S.claves_guardadas[o.clave] = true; toast('Clave guardada'); } });
  else if (t === 'clave') ctl = h('input', { type: 'password', autocomplete: 'off', value: val || '', onchange: e => escribir(e.target.value) });
  else if (t === 'archivo') {
    const inp = h('input', { type: 'text', value: val || '', placeholder: o.ph || '', onchange: e => escribir(e.target.value) });
    ctl = h('div', { class: 'con-btn' }, inp, nativo() ? h('button', { class: 'btn', onclick: async () => { const r = await pywebview.api[o.carpeta ? 'elegir_carpeta' : 'elegir_archivo'](); if (r) { inp.value = r; escribir(r); } } }, 'Examinar…') : null);
  } else ctl = h('input', { type: 'text', value: val == null ? '' : val, placeholder: o.ph || '', list: o.lista, onchange: e => escribir(e.target.value) });
  return h('div', { class: 'campo' }, h('label', {}, etq, extra, o.ayuda ? h('small', {}, o.ayuda) : null), ctl);
}
const campo = (etq, path, o) => campoG(etq, () => get(path), v => { set(path, v); if (o && o.alCambiar) o.alCambiar(v); }, o);
const dos = (...c) => h('div', { class: 'dos' }, c);
const tres = (...c) => h('div', { class: 'tres' }, c);
const tarjeta = (titulo, ...c) => h('div', { class: 'tarjeta' }, titulo ? h('h2', {}, titulo) : null, c);
const pagina = (titulo, sub, ...c) => h('div', {}, h('h1', {}, titulo), h('p', { class: 'sub' }, sub), c);
function pestanas(defs) {
  const cab = h('div', { class: 'pestanas' }), cuerpo = h('div');
  const ir = i => { [...cab.children].forEach((b, j) => b.classList.toggle('act', i === j)); cuerpo.replaceChildren(defs[i].f()); };
  defs.forEach((d, i) => cab.append(h('button', { class: 'pestana', onclick: () => ir(i) }, d.t)));
  ir(0); return h('div', {}, cab, cuerpo);
}

/* ====================== lista editable genérica ====================== */
function Lista(op) {
  let sel = op.items.length ? 0 : -1;
  const tabla = h('table', { class: 'tabla seleccionable' }), form = h('div', { class: 'form-item' });
  function filas() {
    tabla.replaceChildren(h('thead', {}, h('tr', {}, op.columnas.map(c => h('th', {}, c.t)))),
      h('tbody', {}, op.items.length ? op.items.map((it, i) => h('tr', { class: i === sel ? 'sel' : '', onclick: () => { sel = i; filas(); formulario(); } },
        op.columnas.map(c => h('td', {}, c.f ? c.f(it) : String(it[c.k] == null ? '' : it[c.k]))))) : h('tr', {}, h('td', { colspan: op.columnas.length, class: 'vacio' }, op.vacio || 'Todavía no hay nada. Pulsa «Añadir».'))));
  }
  function formulario() {
    const it = op.items[sel];
    if (!it) { form.replaceChildren(h('div', { class: 'vacio' }, 'Añade un elemento para editarlo aquí.')); return; }
    const cambiar = (k, v) => { it[k] = v; op.alCambiar(it, { [k]: v }); filas(); };
    const out = []; let grupo = [];
    const cerrar = () => { if (grupo.length) out.push(h('div', { class: 'dos' }, grupo)); grupo = []; };
    for (const c of op.campos) {
      if (c.si && !c.si(it)) continue;
      const el = campoG(c.etq, () => it[c.k], v => { cambiar(c.k, v); if (c.recarga) formulario(); }, c);
      if (c.mitad) grupo.push(el); else { cerrar(); out.push(el); }
    }
    cerrar();
    form.replaceChildren(out, h('div', { class: 'fila', style: 'margin-top:6px' }, (op.acciones || []).map(a => h('button', { class: 'btn', onclick: hacer(() => a.f(it, formulario)) }, a.t))));
  }
  const barra = h('div', { class: 'fila', style: 'margin-top:12px' },
    h('button', { class: 'btn pri', onclick: hacer(async () => { const n = await op.nuevo(); op.items.push(n); sel = op.items.length - 1; op.tras && op.tras(); filas(); formulario(); }) }, '＋ Añadir'),
    op.duplicar === false ? null : h('button', { class: 'btn', onclick: hacer(async () => { const it = op.items[sel]; if (!it) return; const c = JSON.parse(JSON.stringify(it)); delete c.id; c.nombre = (c.nombre || '') + ' (copia)'; const n = await op.nuevo(c); op.items.push(n); sel = op.items.length - 1; op.tras && op.tras(); filas(); formulario(); }) }, 'Duplicar'),
    h('button', { class: 'btn peligro', onclick: hacer(async () => { const it = op.items[sel]; if (!it) return; if (op.puedeBorrar && !op.puedeBorrar(it)) { toast('Este elemento es del sistema: puedes desactivarlo, no borrarlo.', 'err'); return; } if (!confirm('¿Eliminar este elemento?')) return; await op.alBorrar(it); op.items.splice(sel, 1); sel = Math.min(sel, op.items.length - 1); op.tras && op.tras(); filas(); formulario(); }) }, 'Eliminar'));
  filas(); formulario();
  const el = h('div', { class: 'lista' }, h('div', {}, h('div', { class: 'lista-tabla' }, tabla), barra), form);
  return { el, reemplazar(nuevos) { const id = (op.items[sel] || {}).id; op.items.splice(0, op.items.length, ...nuevos); sel = id ? op.items.findIndex(x => x.id === id) : sel; if (sel < 0) sel = op.items.length ? 0 : -1; filas(); if (!form.contains(document.activeElement)) formulario(); } };
}
const siNo = v => v ? '✓' : '—';
const CRUD = (lista) => ({ nuevo: base => api(lista, 'POST', base || {}), alCambiar: (it, c) => api(`${lista}/${it.id}`, 'PATCH', c).catch(e => toast(e.message, 'err')), alBorrar: it => api(`${lista}/${it.id}`, 'DELETE') });
const LOCAL = (ruta, base) => ({ items: get(ruta), nuevo: async b => b || base(), alCambiar: () => set(ruta, get(ruta)), alBorrar: async () => { }, tras: () => set(ruta, get(ruta)) });

/* ====================== estado en vivo ====================== */
let EST = null, ultimoLog = 0, refsPanel = null;
const PLAN_TXT = { esperando: 'Esperando el momento justo', generando: 'Generando voz…', insertado: 'Insertado en RadioBOSS ✓', ensayo: 'Ensayo (no se insertó)', descartado: 'Descartado', omitido: 'Omitido', 'falló': 'No se pudo' };

function PaginaPanel() {
  const r = refsPanel = {};
  const btn = (txt, cls, fn) => h('button', { class: 'btn ' + cls, onclick: hacer(fn) }, txt);
  r.iniciar = btn('▶ Iniciar locutor IA', 'pri', async () => { await api('motor/iniciar', 'POST'); });
  r.detener = btn('■ Detener', 'peligro', async () => { await api('motor/detener', 'POST'); });
  r.pausa = btn('⏸ Pausar voz', '', async () => { await api('motor/' + (EST.pausado ? 'reanudar' : 'pausar'), 'POST'); });
  r.log = h('div', { class: 'log' });
  r.decir = h('input', { type: 'text', placeholder: 'Ej.: saluda a Carlos que cumple 30 años, de parte de su familia', onkeydown: e => { if (e.key === 'Enter') r.enviar.click(); } });
  r.enviar = btn('Decirlo en el próximo espacio', 'pri', async () => { if (!r.decir.value.trim()) return; await api('decir', 'POST', { mensaje: r.decir.value.trim() }); r.decir.value = ''; toast('Listo: se dirá entre canciones'); });
  const dom = h('div', {},
    h('h1', {}, 'Panel en vivo'), h('p', { class: 'sub' }, 'Lo que sucede ahora mismo entre RadioBOSS y el locutor IA.'),
    r.alerta = h('div'),
    h('div', { class: 'tarjeta hero' }, r.estado = h('div', { class: 'grande' }), r.pEnsayo = h('span'), r.pRB = h('span'),
      h('div', { class: 'fila', style: 'margin-left:auto' }, r.iniciar, r.pausa, r.detener)),
    h('div', { class: 'rejilla g2' },
      tarjeta('🎵 Sonando ahora', r.actual = h('div', { class: 'cancion' }, '—'), r.actualA = h('div', { class: 'mut' }), h('div', { class: 'etq', style: 'margin-top:14px' }, 'Sigue'), r.sigue = h('div', {}, '—')),
      tarjeta('🎙️ Plan del locutor', r.plan = h('div', { class: 'cancion' }, '—'), r.planD = h('div', { class: 'mut' }), r.cuenta = h('div', { class: 'peq', style: 'margin-top:8px' }), h('div', { class: 'barra' }, r.barra = h('i')))),
    h('div', { class: 'rejilla g4' },
      tarjeta('', h('div', { class: 'etq' }, 'Horario / perfil'), r.perfil = h('div', { class: 'num' }, '—')),
      tarjeta('', h('div', { class: 'etq' }, 'Próxima pausa del locutor'), r.cont = h('div', { class: 'num' }, '—'), h('div', { class: 'peq mut' }, 'canciones')),
      tarjeta('', h('div', { class: 'etq' }, 'Próxima tanda'), r.tanda = h('div', { class: 'num' }, '—')),
      tarjeta('', h('div', { class: 'etq' }, 'Hoy'), r.hoy = h('div', { class: 'peq', style: 'line-height:1.9' }))),
    h('div', { class: 'rejilla g2' },
      tarjeta('💬 Decir algo en el aire', h('div', { class: 'con-btn' }, r.decir, r.enviar), h('p', { class: 'peq mut' }, 'La IA lo redacta con la personalidad del locutor y lo dice entre canciones. Para saludos con hora o varios a la vez usa la sección Saludos.')),
      tarjeta('📺 Acciones rápidas', h('div', { class: 'fila' }, btn('Tanda comercial ahora', '', async () => { await api('motor/tanda', 'POST'); toast('Habrá tanda al terminar la próxima canción'); }),
        btn('Modo ensayo: cambiar', '', async () => { set('sistema.ensayo', !get('sistema.ensayo')); await flush(); }),
      ), h('p', { class: 'peq mut' }, 'En modo ensayo el locutor genera todo pero NO inserta nada en RadioBOSS: ideal para probar sin riesgo.'))),
    tarjeta('Registro', r.log));
  return dom;
}
function actualizarPanel(e) {
  const r = refsPanel; if (!r || !r.estado.isConnected) return;
  r.estado.textContent = !e.corriendo ? '⏹ Locutor IA detenido' : e.pausado ? '⏸ Locutor IA en pausa' : '🔴 Locutor IA activo';
  r.pEnsayo.replaceChildren(h('span', { class: 'pill ' + (e.ensayo ? 'aviso' : 'vivo') }, e.ensayo ? 'MODO ENSAYO' : 'EN VIVO'));
  r.pRB.replaceChildren(h('span', { class: 'pill ' + (e.conectado ? 'ok' : 'err') }, e.conectado ? 'RadioBOSS conectado' : 'RadioBOSS sin conexión'));
  r.iniciar.disabled = e.corriendo; r.detener.disabled = !e.corriendo; r.pausa.disabled = !e.corriendo; r.pausa.textContent = e.pausado ? '▶ Reanudar voz' : '⏸ Pausar voz';
  r.alerta.replaceChildren(!e.corriendo ? h('div', { class: 'info-caja' }, 'El locutor está detenido. Pulsa «Iniciar». Mientras esté en MODO ENSAYO no se tocará nada de RadioBOSS.')
    : (!e.conectado ? h('div', { class: 'aviso-caja' }, 'No hay conexión con RadioBOSS. Revisa Ajustes → RadioBOSS (puerto, contraseña) y que la API esté activada. ' + (e.error || '')) : null));
  const tr = t => t ? `${t.titulo}${t.artista ? ' — ' + t.artista : ''}` : '—';
  r.actual.textContent = tr(e.actual); r.actualA.textContent = e.actual ? 'Duración ' + fmtDur(e.actual.dur) + ' · ' + (e.reproduciendo || '') : '';
  r.sigue.textContent = tr(e.siguiente);
  const p = e.plan;
  r.plan.textContent = p ? p.nombre : 'Sin intervención planeada'; r.planD.textContent = p ? `${PLAN_TXT[p.estado] || p.estado} · después de: ${p.despues || ''}${p.detalle ? ' (' + p.detalle + ')' : ''}` : 'Esperando a que empiece la próxima canción.';
  if (p && (p.estado === 'esperando' || p.estado === 'generando')) { const falta = Math.max(0, p.fin - e.ahora); r.cuenta.textContent = `Sale al aire en ~${fmtDur(falta) || '0:00'}`; r.barra.style.width = Math.min(100, Math.max(5, 100 - falta / 2.4)) + '%'; }
  else { r.cuenta.textContent = ''; r.barra.style.width = p && p.estado === 'insertado' ? '100%' : '0'; }
  r.perfil.textContent = e.perfil; r.cont.textContent = Math.max(e.objetivo - e.desde, 0); r.tanda.textContent = e.tanda_forzada ? 'ahora' : (e.proxima_tanda || '—');
  r.hoy.replaceChildren(`🎙️ Intervenciones: ${e.hoy.voces}`, h('br'), `📢 Comerciales insertados: ${e.hoy.spots_insertados}`, h('br'), `✅ Emisión confirmada: ${e.hoy.spots_emitidos}`);
}
function pintarLogs(lineas) {
  const l = refsPanel && refsPanel.log; if (!l || !l.isConnected) return;
  const abajo = l.scrollHeight - l.scrollTop - l.clientHeight < 40;
  for (const x of lineas) l.append(h('div', { class: x.nivel }, h('span', { class: 't' }, x.ts), x.msg));
  while (l.children.length > 400) l.firstChild.remove();
  if (abajo) l.scrollTop = l.scrollHeight;
}

/* ====================== LOCUTOR ====================== */
function PaginaLocutor() {
  return pagina('Locutor', 'Quién es, cómo habla, qué opina, qué dice y cuándo. Todo se guarda al instante.', pestanas([
    { t: 'Personalidad', f: () => h('div', {},
      tarjeta('Identidad del locutor', dos(campo('Nombre del locutor', 'locutor.nombre'), campo('Dialecto / forma de hablar', 'locutor.dialecto', { tipo: 'area', filas: 2 })),
        campo('Personalidad', 'locutor.personalidad', { tipo: 'area', filas: 2 }),
        campo('Opiniones y forma de ser', 'locutor.opiniones', { tipo: 'area', filas: 5, ayuda: 'Qué le gusta, cómo opina, su humor. Aquí defines su «carácter».' }),
        campo('Temas prohibidos', 'locutor.prohibido', { tipo: 'area', filas: 3, ayuda: 'Cosas que JAMÁS debe tocar (política, religión, otras emisoras…).' })),
      tarjeta('Largo y memoria', tres(campo('Palabras mínimas', 'locutor.palabras_min', { tipo: 'num', min: 3, max: 100 }), campo('Palabras máximas', 'locutor.palabras_max', { tipo: 'num', min: 5, max: 150 }), campo('Recordar últimas intervenciones', 'locutor.memoria', { tipo: 'num', min: 0, max: 40, ayuda: 'Para no repetirse.' })),
        dos(campo('Máximo de saludos por pausa', 'locutor.max_saludos', { tipo: 'num', min: 1, max: 10 }), campo('Permitir datos curiosos', 'locutor.curiosidades', { tipo: 'check', ayuda: 'Desactivado: la IA no inventa datos de artistas (recomendado).' }))),
      tarjeta('La estación', dos(campo('Nombre de la estación', 'estacion.nombre'), campo('Eslogan', 'estacion.eslogan')), dos(campo('Ciudad', 'estacion.ciudad'), campo('Contacto (WhatsApp, teléfono)', 'estacion.contacto')),
        tres(campo('Sitio web / redes', 'estacion.web'), campo('Latitud (clima)', 'estacion.latitud', { tipo: 'num', paso: 0.0001 }), campo('Longitud (clima)', 'estacion.longitud', { tipo: 'num', paso: 0.0001 })))) },
    { t: 'Tipos de intervención', f: () => h('div', {},
      h('div', { class: 'info-caja' }, 'Cada tipo es un «molde» de lo que puede decir. El peso decide qué tan seguido sale. Puedes crear tipos nuevos (concursos, frases del día, promos de tu programa…).'),
      tarjeta('Tipos de pausa del locutor', Lista({
        ...LOCAL('tipos', () => ({ id: 'custom_' + Math.random().toString(36).slice(2, 7), nombre: 'Nuevo tipo', peso: 1, activo: true, necesita_siguiente: true, instruccion: 'Describe qué debe decir el locutor…' })),
        columnas: [{ t: 'Nombre', k: 'nombre' }, { t: 'Peso', k: 'peso' }, { t: 'Activo', f: it => siNo(it.activo) }], puedeBorrar: it => it.id.startsWith('custom_'),
        campos: [{ k: 'nombre', etq: 'Nombre' }, { k: 'instruccion', etq: 'Instrucción para la IA', tipo: 'area', filas: 5, ayuda: 'Qué debe hacer en este tipo de pausa.' },
          { k: 'peso', etq: 'Peso (frecuencia relativa)', tipo: 'num', min: 0, max: 100, mitad: true }, { k: 'activo', etq: 'Activo', tipo: 'check', mitad: true },
          { k: 'necesita_siguiente', etq: 'Solo si hay canción siguiente', tipo: 'check', ayuda: 'Si presenta la próxima canción, actívalo.' }]
      }).el),
      tarjeta('Instrucciones especiales', campo('Antes de la tanda («nos vamos a pausa»)', 'instrucciones.pre_tanda', { tipo: 'area', filas: 2 }), campo('Al regresar de la tanda', 'instrucciones.post_tanda', { tipo: 'area', filas: 2 }),
        campo('Al leer saludos de oyentes', 'instrucciones.saludo', { tipo: 'area', filas: 2 }), campo('Al cumplir una orden del operador', 'instrucciones.orden', { tipo: 'area', filas: 2 }))) },
    { t: 'Horarios y perfiles', f: () => h('div', {},
      h('div', { class: 'info-caja' }, 'Cambia el ánimo y la frecuencia según la hora: mañanero con energía, noche tranquila, madrugada casi sin hablar. Los horarios pueden cruzar la medianoche.'),
      tarjeta('', Lista({
        ...LOCAL('perfiles', () => ({ nombre: 'Nuevo horario', desde: '00:00', hasta: '06:00', estilo: 'Natural.', cada_min: 2, cada_max: 4, habla: true })),
        columnas: [{ t: 'Perfil', k: 'nombre' }, { t: 'Horario', f: it => `${it.desde} – ${it.hasta}` }, { t: 'Cada', f: it => `${it.cada_min}-${it.cada_max} canc.` }, { t: 'Habla', f: it => siNo(it.habla) }],
        campos: [{ k: 'nombre', etq: 'Nombre del perfil' }, { k: 'desde', etq: 'Desde', tipo: 'hora', mitad: true }, { k: 'hasta', etq: 'Hasta', tipo: 'hora', mitad: true },
          { k: 'estilo', etq: 'Estilo / energía', tipo: 'area', filas: 3, ayuda: 'Se le indica a la IA para ese horario.' }, { k: 'cada_min', etq: 'Habla cada (mín. canciones)', tipo: 'num', min: 1, max: 30, mitad: true },
          { k: 'cada_max', etq: 'Habla cada (máx. canciones)', tipo: 'num', min: 1, max: 30, mitad: true }, { k: 'habla', etq: 'El locutor habla en este horario (las tandas siguen)', tipo: 'check' }]
      }).el)) },
    { t: 'Fechas especiales', f: () => h('div', {},
      h('div', { class: 'info-caja' }, 'El día indicado (formato MES-DÍA, ej. 09-15) la IA sabrá que es una fecha especial y podrá mencionarla de vez en cuando.'),
      tarjeta('', Lista({
        ...LOCAL('fechas', () => ({ fecha: '01-01', nota: 'Hoy es…' })), columnas: [{ t: 'Fecha', k: 'fecha' }, { t: 'Nota', k: 'nota' }], duplicar: false,
        campos: [{ k: 'fecha', etq: 'Fecha (MM-DD)', ph: '09-15' }, { k: 'nota', etq: 'Qué es hoy', ph: 'Hoy es el Día de la Independencia' }]
      }).el)) },
    { t: 'Probar', f: PruebaGuion }]));
}
function PruebaGuion() {
  const sal = h('div', { class: 'cancion', style: 'font-size:16px;font-weight:400;min-height:48px' }, 'Aquí aparecerá lo que diría el locutor.'); let ultimo = '';
  const tipos = [...get('tipos').map(t => ({ v: t.id, t: t.nombre })), { v: 'pre_tanda', t: 'Antes de tanda' }, { v: 'post_tanda', t: 'Regreso de tanda' }];
  const sel = h('select', {}, tipos.map(t => h('option', { value: t.v }, t.t)));
  return tarjeta('Probar al locutor', h('p', { class: 'mut' }, 'Genera una intervención con la configuración actual (usa la canción que suena, o una de ejemplo). Genera varias veces para ver la variedad.'),
    h('div', { class: 'fila' }, sel, h('button', { class: 'btn pri', onclick: hacer(async () => { sal.textContent = 'Generando…'; const r = await api('probar/guion', 'POST', { tipo: sel.value }); ultimo = r.texto; sal.textContent = r.texto + (r.origen === 'plantilla' ? '   (plantilla: configura la clave de Claude para texto con IA)' : ''); }) }, 'Generar guion'),
      h('button', { class: 'btn', onclick: hacer(async () => { if (!ultimo) { toast('Primero genera un guion', 'err'); return; } toast('Sintetizando voz…'); const r = await api('probar/voz', 'POST', { texto: ultimo, rol: 'locutor' }); reproducir(r.url, 'Locutor — prueba'); }) }, '▶ Escuchar con la voz')), h('div', { style: 'margin-top:14px' }, sal));
}

/* ====================== VOZ ====================== */
function PaginaVoz() {
  const caja = h('div');
  const cargar = (prov, id) => hacer(async () => { const v = await api('voces/' + prov); $('#' + id).replaceChildren(...v.map(x => h('option', { value: x.id }, x.nombre))); toast(v.length + ' voces cargadas: haz clic en el campo y elige'); });
  function dibujar() {
    const p = get('tts.proveedor');
    if (p === 'edge') caja.replaceChildren(tarjeta('Microsoft Edge (gratis, sin clave)', h('p', { class: 'mut' }, 'Buena para probar y para comerciales sencillos. Se nota algo más sintética que ElevenLabs.'),
      dos(campo('Voz del locutor', 'tts.edge.voz_locutor', { lista: 'voces-edge', ayuda: 'Ej.: es-SV-RodrigoNeural (El Salvador), es-MX-JorgeNeural' }), campo('Voz de comerciales', 'tts.edge.voz_comercial', { lista: 'voces-edge' })), h('datalist', { id: 'voces-edge' }),
      h('button', { class: 'btn', onclick: cargar('edge', 'voces-edge') }, 'Cargar voces en español'),
      dos(campo('Velocidad (%)', 'tts.edge.rate', { tipo: 'rango', min: -40, max: 40, paso: 1 }), campo('Tono (Hz)', 'tts.edge.pitch', { tipo: 'rango', min: -30, max: 30, paso: 1 }))));
    else if (p === 'elevenlabs') caja.replaceChildren(tarjeta('ElevenLabs (la más natural)', campo('Clave de API de ElevenLabs', 'claves.elevenlabs', { tipo: 'secreto', clave: 'elevenlabs' }),
      dos(campo('ID de voz del locutor', 'tts.elevenlabs.voz_locutor', { lista: 'voces-el' }), campo('ID de voz de comerciales', 'tts.elevenlabs.voz_comercial', { lista: 'voces-el' })), h('datalist', { id: 'voces-el' }),
      h('button', { class: 'btn', onclick: cargar('elevenlabs', 'voces-el') }, 'Cargar mis voces'), h('div', { style: 'height:14px' }),
      campo('Modelo', 'tts.elevenlabs.modelo', { lista: 'modelos-el', ayuda: 'eleven_multilingual_v2 (recomendado), eleven_turbo_v2_5, eleven_flash_v2_5' }), h('datalist', { id: 'modelos-el' }, ['eleven_multilingual_v2', 'eleven_turbo_v2_5', 'eleven_flash_v2_5'].map(m => h('option', { value: m }))),
      tres(campo('Estabilidad', 'tts.elevenlabs.stability', { tipo: 'rango', min: 0, max: 1, paso: 0.05, ayuda: 'Más baja = más expresiva' }), campo('Similitud', 'tts.elevenlabs.similarity', { tipo: 'rango', min: 0, max: 1, paso: 0.05 }), campo('Estilo', 'tts.elevenlabs.style', { tipo: 'rango', min: 0, max: 1, paso: 0.05 }))));
    else caja.replaceChildren(tarjeta('OpenAI (voz con instrucciones)', campo('Clave de API de OpenAI', 'claves.openai', { tipo: 'secreto', clave: 'openai' }),
      dos(campo('Voz del locutor', 'tts.openai.voz_locutor', { tipo: 'select', opciones: ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer', 'verse'] }), campo('Voz de comerciales', 'tts.openai.voz_comercial', { tipo: 'select', opciones: ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer', 'verse'] })),
      campo('Modelo', 'tts.openai.modelo'), campo('Cómo debe sonar', 'tts.openai.instrucciones', { tipo: 'area', filas: 3, ayuda: 'Ej.: «cálido, cercano, ritmo natural, sonrisa en la voz».' })));
  }
  const demo = h('textarea', { rows: 3 }, 'Buenas tardes, estás en ' + (get('estacion.nombre') || 'tu radio') + '... y esto que viene está buenísimo.');
  const rol = h('select', {}, h('option', { value: 'locutor' }, 'Voz del locutor'), h('option', { value: 'comercial' }, 'Voz de comerciales'));
  const pa = campo('Proveedor de voz', 'tts.proveedor', { tipo: 'select', opciones: [{ v: 'edge', t: 'Microsoft Edge (gratis)' }, { v: 'elevenlabs', t: 'ElevenLabs' }, { v: 'openai', t: 'OpenAI' }], alCambiar: dibujar });
  dibujar();
  return pagina('Voz', 'Con qué voz habla el locutor y cómo se «masteriza» para radio.',
    tarjeta('', pa), caja,
    tarjeta('Probar la voz', demo, h('div', { class: 'fila', style: 'margin-top:10px' }, rol, h('button', { class: 'btn pri', onclick: hacer(async () => { toast('Sintetizando…'); const r = await api('probar/voz', 'POST', { texto: demo.value, rol: rol.value }); reproducir(r.url, 'Prueba de voz'); }) }, '▶ Generar y escuchar'))),
    tarjeta('Procesado de audio (sonido de radio)', tres(campo('Masterizar la voz', 'audio.procesar', { tipo: 'check', ayuda: 'Filtro de graves, compresión y volumen parejo' }), campo('Compresor', 'audio.compresor', { tipo: 'check' }), campo('Volumen objetivo (LUFS)', 'audio.loudness', { tipo: 'num', min: -30, max: -8, ayuda: '-16 es un buen punto de partida' })),
      dos(campo('Silencio al inicio (ms)', 'audio.pad_ini_ms', { tipo: 'num', min: 0, max: 2000, paso: 50 }), campo('Silencio al final (ms)', 'audio.pad_fin_ms', { tipo: 'num', min: 0, max: 2000, paso: 50 }))),
    tarjeta('Diccionario de pronunciación', h('p', { class: 'mut' }, 'Si la voz pronuncia mal un nombre, marca o artista, escribe aquí cómo debe sonar (se reemplaza solo al sintetizar).'),
      Lista({ ...LOCAL('pronunciacion', () => ({ palabra: '', como: '' })), columnas: [{ t: 'Palabra', k: 'palabra' }, { t: 'Se dice', k: 'como' }], duplicar: false,
        campos: [{ k: 'palabra', etq: 'Palabra escrita', ph: 'Bad Bunny' }, { k: 'como', etq: 'Cómo se pronuncia', ph: 'bad buni' }] }).el));
}

/* ====================== COMERCIALES ====================== */
async function PaginaComerciales() {
  const items = await api('comerciales');
  const lista = Lista({
    items, ...CRUD('comerciales'), vacio: 'Aún no tienes comerciales. Pulsa «Añadir».',
    columnas: [{ t: 'Comercial', k: 'nombre' }, { t: 'Modo', f: it => ({ texto: 'Texto', brief: 'Brief IA', archivo: 'Archivo' })[it.modo] }, { t: 'Uso', f: it => ({ tanda: 'Tanda', mencion: 'Mención', ambos: 'Ambos' })[it.uso] }, { t: 'Peso', k: 'peso' }, { t: 'Activo', f: it => siNo(it.activo) }],
    campos: [
      { k: 'nombre', etq: 'Cliente / nombre del comercial' }, { k: 'categoria', etq: 'Categoría', ph: 'comida, autos, salud…', mitad: true, ayuda: 'Evita dos de la misma en una tanda' },
      { k: 'uso', etq: 'Dónde suena', tipo: 'select', mitad: true, opciones: [{ v: 'tanda', t: 'En la tanda' }, { v: 'mencion', t: 'Como mención del locutor' }, { v: 'ambos', t: 'Ambos' }] },
      { k: 'modo', etq: 'Cómo se crea el audio', tipo: 'select', recarga: true, opciones: [{ v: 'texto', t: 'Texto exacto (la IA solo lo lee)' }, { v: 'brief', t: 'Brief (la IA redacta el guion)' }, { v: 'archivo', t: 'Archivo de audio ya grabado' }] },
      { k: 'brief', etq: 'Brief del cliente', tipo: 'area', filas: 3, si: it => it.modo === 'brief', ayuda: 'Datos del negocio, teléfono, horario… La IA redacta; REVISA el guion antes de salir al aire.' },
      { k: 'texto', etq: 'Guion (texto que se leerá)', tipo: 'area', filas: 5, si: it => it.modo !== 'archivo', ayuda: 'Con modo Texto es el copy aprobado por el cliente.' },
      { k: 'archivo', etq: 'Archivo de audio', tipo: 'archivo', si: it => it.modo === 'archivo', ph: 'C:\\Comerciales\\spot.mp3' },
      { k: 'voz', etq: 'Voz', tipo: 'select', mitad: true, opciones: [{ v: 'comercial', t: 'Voz de comerciales' }, { v: 'locutor', t: 'Voz del locutor' }], si: it => it.modo !== 'archivo' },
      { k: 'peso', etq: 'Peso (más alto = más seguido)', tipo: 'num', min: 0, max: 20, mitad: true }, { k: 'activo', etq: 'Activo', tipo: 'check', mitad: true },
      { k: 'max_por_dia', etq: 'Máx. veces al día (0 = sin límite)', tipo: 'num', min: 0, max: 500, mitad: true },
      { k: 'desde', etq: 'Vigente desde', tipo: 'fecha', mitad: true }, { k: 'hasta', etq: 'Vigente hasta', tipo: 'fecha', mitad: true },
      { k: 'dias', etq: 'Días de la semana', tipo: 'dias' },
      { k: 'hora_desde', etq: 'Desde la hora', tipo: 'hora', mitad: true }, { k: 'hora_hasta', etq: 'Hasta la hora', tipo: 'hora', mitad: true },
      { k: 'cama', etq: 'Cama musical (opcional)', tipo: 'archivo', si: it => it.modo !== 'archivo', ph: 'Música de fondo que suena bajita debajo de la voz' },
      { k: 'cama_volumen', etq: 'Volumen de la cama', tipo: 'rango', min: 0.05, max: 0.6, paso: 0.05, si: it => it.modo !== 'archivo' }],
    acciones: [{ t: '▶ Escuchar', f: async it => { toast('Preparando audio…'); const r = await api(`comerciales/${it.id}/escuchar`, 'POST'); reproducir(r.url, it.nombre); } },
      { t: '✨ Redactar con IA', f: async (it, recargar) => { if (!it.brief) throw new Error('Escribe primero el brief del cliente.'); toast('Redactando…'); const r = await api(`comerciales/${it.id}/redactar`, 'POST'); it.texto = r.texto; recargar(); toast('Guion redactado: revísalo'); } }]
  });
  return pagina('Comerciales y tandas', 'Tus anunciantes, cuándo suenan y cómo se arman las pausas comerciales.',
    tarjeta('Tandas', dos(campo('Tandas activas', 'tandas.activas', { tipo: 'check' }), campo('Minutos de cada hora', 'tandas.minutos', { tipo: 'minutos', ayuda: 'Separados por coma. Ej.: 15, 45  (a los :15 y :45)' })),
      tres(campo('Solo entre las', 'tandas.hora_desde', { tipo: 'hora' }), campo('y las', 'tandas.hora_hasta', { tipo: 'hora' }), campo('Comerciales por tanda', 'tandas.cantidad', { tipo: 'num', min: 1, max: 12 })),
      campo('No repetir categoría dentro de una tanda', 'tandas.separar_categorias', { tipo: 'check' }),
      dos(campo('Cortinilla de entrada (opcional)', 'tandas.cortinilla_entrada', { tipo: 'archivo' }), campo('Cortinilla de salida (opcional)', 'tandas.cortinilla_salida', { tipo: 'archivo' }))),
    tarjeta('Comerciales', lista.el));
}

/* ====================== SALUDOS ====================== */
async function PaginaSaludos() {
  const items = await api('saludos');
  const lista = Lista({ items, ...CRUD('saludos'), vacio: 'No hay saludos en la cola.',
    columnas: [{ t: 'Para', k: 'para' }, { t: 'De', k: 'de' }, { t: 'Mensaje', f: it => (it.mensaje || '').slice(0, 40) }, { t: 'Estado', f: it => it.estado === 'leido' ? 'Leído ' + (it.leido || '') : it.estado === 'fallido' ? 'Fallido' : 'Pendiente' }],
    campos: [{ k: 'tipo', etq: 'Tipo', tipo: 'select', mitad: true, opciones: [{ v: 'saludo', t: 'Saludo de oyente' }, { v: 'orden', t: 'Orden al locutor' }] }, { k: 'prioridad', etq: 'Prioridad', tipo: 'select', mitad: true, opciones: [{ v: 'normal', t: 'En la próxima pausa normal' }, { v: 'ya', t: 'Lo antes posible' }] },
      { k: 'de', etq: 'De parte de', mitad: true }, { k: 'para', etq: 'Para', mitad: true }, { k: 'mensaje', etq: 'Mensaje o instrucción', tipo: 'area', filas: 4 },
      { k: 'no_antes', etq: 'No antes de la hora (opcional)', tipo: 'hora', mitad: true, ayuda: 'Ej.: un cumpleaños a las 12:00' }, { k: 'estado', etq: 'Estado', tipo: 'select', mitad: true, opciones: [{ v: 'pendiente', t: 'Pendiente' }, { v: 'leido', t: 'Leído' }, { v: 'fallido', t: 'Fallido (sin IA)' }] }] });
  const f = { tipo: 'saludo', de: '', para: '', mensaje: '', no_antes: '', prioridad: 'normal' };
  const inp = (k, ph, tipo = 'text') => h('input', { type: tipo, placeholder: ph, oninput: e => f[k] = e.target.value });
  const msg = h('textarea', { rows: 2, placeholder: 'Ej.: feliz cumpleaños, que la pase lindo con toda la familia', oninput: e => f.mensaje = e.target.value });
  timers.push(setInterval(async () => { try { lista.reemplazar(await api('saludos')); } catch (e) { /* sin conexión */ } }, 4000));
  return pagina('Saludos y dedicatorias', 'Mensajes de oyentes que el locutor leerá con sus propias palabras, entre canciones.',
    tarjeta('Nuevo saludo', h('div', { class: 'tres' }, h('div', { class: 'campo' }, h('label', {}, 'De parte de'), inp('de', 'Familia Pérez')), h('div', { class: 'campo' }, h('label', {}, 'Para'), inp('para', 'Doña Rosa')),
      h('div', { class: 'campo' }, h('label', {}, 'No antes de (opcional)'), inp('no_antes', '', 'time'))), h('div', { class: 'campo' }, h('label', {}, 'Mensaje'), msg),
      h('button', { class: 'btn pri', onclick: hacer(async () => { if (!f.mensaje.trim()) throw new Error('Escribe el mensaje.'); await api('saludos', 'POST', f); lista.reemplazar(await api('saludos')); toast('Añadido a la cola'); msg.value = ''; f.mensaje = ''; }) }, '＋ Añadir a la cola')),
    tarjeta('Cola', lista.el));
}

/* ====================== YOUTUBE ====================== */
async function PaginaYouTube() {
  const resultados = h('div'), trabajos = h('div'); const aviso = h('div');
  const q = h('input', { type: 'text', placeholder: 'Busca una canción o pega un enlace de YouTube…', onkeydown: e => { if (e.key === 'Enter') buscar.click(); } });
  const bajar = (url, titulo, destino) => hacer(async () => { await api('yt/descargar', 'POST', { url, titulo, destino }); toast('Descarga iniciada'); pintarJobs(); });
  const buscar = h('button', { class: 'btn pri', onclick: hacer(async () => {
    const t = q.value.trim(); if (!t) return;
    if (/^https?:\/\//.test(t)) { resultados.replaceChildren(h('div', { class: 'res' }, h('div'), h('div', {}, h('div', { class: 'cancion' }, t)), h('div', { class: 'fila' }, h('button', { class: 'btn pri mini', onclick: bajar(t, t, 'siguiente') }, 'Siguiente en RadioBOSS'), h('button', { class: 'btn mini', onclick: bajar(t, t, 'final') }, 'Al final'), h('button', { class: 'btn mini', onclick: bajar(t, t, 'biblioteca') }, 'Solo descargar')))); return; }
    resultados.replaceChildren(h('div', { class: 'vacio' }, 'Buscando…'));
    const r = await api('yt/buscar?q=' + encodeURIComponent(t));
    resultados.replaceChildren(...r.map(v => h('div', { class: 'res' }, h('img', { src: v.mini, alt: '' }), h('div', {}, h('div', { class: 'cancion', style: 'font-size:15px' }, v.titulo), h('div', { class: 'mut peq' }, `${v.canal} · ${fmtDur(v.dur)}`)),
      h('div', { class: 'fila' }, h('button', { class: 'btn pri mini', onclick: bajar(v.url, v.titulo, 'siguiente') }, 'Siguiente en RadioBOSS'), h('button', { class: 'btn mini', onclick: bajar(v.url, v.titulo, 'final') }, 'Al final'), h('button', { class: 'btn mini', onclick: bajar(v.url, v.titulo, 'biblioteca') }, 'Solo descargar')))));
    if (!r.length) resultados.replaceChildren(h('div', { class: 'vacio' }, 'Sin resultados.'));
  }) }, 'Buscar');
  async function pintarJobs() {
    try {
      const r = await api('yt/estado');
      aviso.replaceChildren(r.disponible ? null : h('div', { class: 'aviso-caja' }, 'No encuentro yt-dlp. Copia yt-dlp.exe a la carpeta «herramientas» junto al programa (el instalador lo trae).'));
      trabajos.replaceChildren(...r.trabajos.map(j => h('div', { class: 'res', style: 'grid-template-columns:1fr 150px' }, h('div', {}, h('div', {}, j.titulo), h('div', { class: 'barra' }, h('i', { style: `width:${j.pct}%;transition:none` })), j.error ? h('div', { class: 'peq', style: 'color:var(--err)' }, j.error) : null),
        h('div', { class: 'pill ' + (j.estado === 'error' ? 'err' : j.estado === 'descargando' || j.estado === 'convirtiendo' || j.estado === 'en cola' ? 'aviso' : 'ok') }, j.estado))));
      if (!r.trabajos.length) trabajos.replaceChildren(h('div', { class: 'vacio' }, 'Aún no has descargado nada en esta sesión.'));
    } catch (e) { /* ignorar */ }
  }
  timers.push(setInterval(pintarJobs, 1500)); pintarJobs();
  return pagina('YouTube y música local', 'Trae canciones de YouTube como mp3 y mándalas a RadioBOSS. Tu música local ya está en RadioBOSS.',
    h('div', { class: 'aviso-caja' }, 'Descargar de YouTube va contra sus términos de servicio, y emitir música requiere las licencias de comunicación pública de tu país (o música libre de derechos / con permiso). Úsalo solo con lo que tengas derecho a transmitir.'),
    aviso, tarjeta('Buscar', h('div', { class: 'con-btn' }, q, buscar), h('div', { style: 'margin-top:14px' }, resultados)),
    tarjeta('Descargas', trabajos, h('div', { style: 'margin-top:10px' }, h('button', { class: 'btn mini', onclick: hacer(async () => { toast('Actualizando yt-dlp…'); const r = await api('yt/actualizar', 'POST'); toast(r.mensaje.slice(0, 160)); }) }, 'Actualizar yt-dlp (si YouTube cambió y falla)'))),
    tarjeta('', campo('Carpeta donde se guardan las descargas', 'carpetas.youtube', { tipo: 'archivo', carpeta: true, ph: 'Por defecto: Música\\LocutorIA-YouTube' })));
}

/* ====================== HISTORIAL Y REPORTES ====================== */
async function PaginaHistorial() {
  const f = { tipo: '', estado: '', desde: '', hasta: '', q: '' }; const cuerpo = h('div'); const rep = h('div');
  const rango = { desde: hoy(), hasta: hoy() };
  const filtro = (k, el) => { el.addEventListener('change', e => { f[k] = e.target.value; cargar(); }); return el; };
  async function cargar() {
    const r = await api('historial?' + new URLSearchParams(f));
    cuerpo.replaceChildren(h('table', { class: 'tabla' }, h('thead', {}, h('tr', {}, ['Hora', 'Tipo', 'Nombre', 'Texto', 'Estado', ''].map(x => h('th', {}, x)))),
      h('tbody', {}, r.length ? r.map(e => h('tr', {}, h('td', {}, e.ts.slice(5, 16)), h('td', {}, e.tipo), h('td', {}, e.nombre), h('td', { style: 'max-width:420px' }, (e.texto || '').slice(0, 140)), h('td', {}, h('span', { class: 'pill ' + (e.estado === 'emitido' ? 'ok' : e.estado === 'descartado' ? 'err' : 'aviso') }, e.estado)),
        h('td', {}, e.archivo ? h('button', { class: 'btn mini', onclick: () => reproducir('/api/audio?f=' + encodeURIComponent(e.archivo), e.nombre) }, '▶') : ''))) : h('tr', {}, h('td', { colspan: 6, class: 'vacio' }, 'Nada que mostrar con estos filtros.')))));
  }
  async function reporte() {
    const r = await api('reporte?' + new URLSearchParams(rango));
    rep.replaceChildren(h('table', { class: 'tabla' }, h('thead', {}, h('tr', {}, ['Comercial', 'Insertados', 'Emisión confirmada', 'Última emisión'].map(x => h('th', {}, x)))),
      h('tbody', {}, r.length ? r.map(x => h('tr', {}, h('td', {}, x.nombre), h('td', {}, x.insertados), h('td', {}, x.emitidos), h('td', {}, x.ultimo || '—'))) : h('tr', {}, h('td', { colspan: 4, class: 'vacio' }, 'Sin comerciales en ese rango.')))));
  }
  const sel = (k, ops) => filtro(k, h('select', {}, ops.map(o => h('option', { value: o[0] }, o[1]))));
  const fd = h('input', { type: 'date', value: rango.desde, onchange: e => { rango.desde = e.target.value; reporte(); } }), fh = h('input', { type: 'date', value: rango.hasta, onchange: e => { rango.hasta = e.target.value; reporte(); } });
  cargar(); reporte(); timers.push(setInterval(cargar, 8000));
  return pagina('Historial y reportes', 'Todo lo que dijo y emitió el locutor, y la prueba de emisión de cada comercial para tus clientes.',
    tarjeta('Reporte de comerciales', h('div', { class: 'fila' }, h('span', { class: 'mut' }, 'Del'), fd, h('span', { class: 'mut' }, 'al'), fh, h('button', { class: 'btn', onclick: hacer(() => descargar(`/api/reporte.csv?${new URLSearchParams(rango)}`, `reporte_comerciales_${rango.desde}_${rango.hasta}.csv`)) }, '⬇ Exportar CSV (Excel)')),
      h('p', { class: 'peq mut' }, '«Emisión confirmada» = el programa vio realmente sonar el comercial en RadioBOSS.'), rep),
    tarjeta('Historial', h('div', { class: 'fila', style: 'margin-bottom:12px' }, sel('tipo', [['', 'Todos los tipos'], ['comercial', 'Comerciales'], ['transicion', 'Transiciones'], ['hora_clima', 'Hora y clima'], ['saludo', 'Saludos'], ['pre_tanda', 'Antes de tanda'], ['post_tanda', 'Regreso de tanda']]),
      sel('estado', [['', 'Todos los estados'], ['emitido', 'Emitido'], ['insertado', 'Insertado'], ['ensayo', 'Ensayo'], ['descartado', 'Descartado']]),
      filtro('q', h('input', { type: 'text', placeholder: 'Buscar texto…', style: 'max-width:240px' }))), cuerpo));
}

/* ====================== AJUSTES ====================== */
function PaginaAjustes() {
  const msgRB = h('div', { class: 'peq', style: 'margin-top:10px' }), msgIA = h('div', { class: 'peq', style: 'margin-top:10px' });
  const resultado = (el, r) => { el.textContent = (r.ok ? '✅ ' : '❌ ') + r.mensaje; el.style.color = r.ok ? 'var(--ok)' : 'var(--err)'; };
  return pagina('Ajustes', 'Conexión con RadioBOSS, claves, carpetas y opciones del sistema.', pestanas([
    { t: 'RadioBOSS', f: () => h('div', {}, tarjeta('Conexión con RadioBOSS', h('div', { class: 'info-caja' }, 'En RadioBOSS: Settings → API (control remoto). Activa la API, anota el puerto y, si pusiste contraseña, ponla aquí. Este programa debe correr en el mismo PC.'),
      tres(campo('Dirección (host)', 'radioboss.host'), campo('Puerto', 'radioboss.puerto', { tipo: 'num', min: 1, max: 65535 }), campo('Usuario (si tiene)', 'radioboss.usuario')),
      dos(campo('Contraseña de la API', 'radioboss.password', { tipo: 'clave' }), campo('Dónde insertar la voz', 'radioboss.posicion', { tipo: 'select', num: true, opciones: [{ v: -2, t: 'Justo después de la canción actual (recomendado)' }, { v: -3, t: 'Después de los eventos ya programados' }] })),
      h('button', { class: 'btn pri', onclick: hacer(async () => { await flush(); resultado(msgRB, await api('probar/radioboss', 'POST')); }) }, 'Probar conexión'), msgRB),
      tarjeta('Tiempos', tres(campo('Consultar cada (seg)', 'radioboss.intervalo_seg', { tipo: 'num', min: 1, max: 10 }), campo('Generar la voz N seg antes de que termine la canción', 'radioboss.anticipacion_seg', { tipo: 'num', min: 15, max: 180, ayuda: 'Si una canción tiene fade/outro recortado, sube este valor.' }),
        campo('Una pista es música si dura al menos (seg)', 'radioboss.min_cancion_seg', { tipo: 'num', min: 10, max: 300, ayuda: 'Lo más corto se trata como jingle.' })))) },
    { t: 'Claves y modelo de IA', f: () => tarjeta('Claude (escribe los guiones)', campo('Clave de API de Anthropic', 'claves.anthropic', { tipo: 'secreto', clave: 'anthropic', ayuda: 'Se guarda solo en este PC. Sin clave el locutor usa frases de plantilla (suena repetitivo).' }),
      campo('Modelo', 'llm.modelo', { lista: 'modelos-claude', ayuda: 'Haiku = rápido y barato (recomendado). Sonnet = más chispa.' }), h('datalist', { id: 'modelos-claude' }, ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'].map(m => h('option', { value: m }))),
      h('button', { class: 'btn pri', onclick: hacer(async () => { await flush(); resultado(msgIA, await api('probar/claude', 'POST')); }) }, 'Probar Claude'), msgIA,
      h('p', { class: 'peq mut', style: 'margin-top:14px' }, 'Las claves de ElevenLabs y OpenAI se ponen en la sección Voz.')) },
    { t: 'Carpetas', f: () => tarjeta('Carpetas', campo('Audios del locutor', 'carpetas.voces', { tipo: 'archivo', carpeta: true, ph: 'Vacío = carpeta automática del programa', ayuda: 'RadioBOSS debe poder leer esta carpeta (mismo PC).' }), campo('Comerciales generados', 'carpetas.spots', { tipo: 'archivo', carpeta: true, ph: 'Vacío = automática' }),
      campo('Carpetas que NO son música', 'carpetas.ignorar', { tipo: 'lineas', filas: 4, ph: 'C:\\Radio\\Jingles\nC:\\Radio\\Comerciales', ayuda: 'Una por línea. El locutor no narra sobre jingles, cortinillas ni comerciales de estas carpetas.' })) },
    { t: 'Clima y noticias', f: () => h('div', {}, tarjeta('Clima', campo('Mencionar el clima actual', 'clima.activo', { tipo: 'check', ayuda: 'Usa la latitud/longitud de la estación (Locutor → Personalidad). Gratis, sin clave.' })),
      tarjeta('Titulares (RSS)', campo('Activar titulares', 'noticias.activo', { tipo: 'check', ayuda: 'Además activa el tipo «Titular breve» en Locutor → Tipos de intervención.' }), campo('Enlaces RSS de noticias', 'noticias.feeds', { tipo: 'lineas', filas: 3, ph: 'https://…/rss.xml' }), campo('Titulares a considerar', 'noticias.max_titulares', { tipo: 'num', min: 1, max: 10 }))) },
    { t: 'Sistema y respaldo', f: () => h('div', {}, tarjeta('Operación', campo('MODO ENSAYO', 'sistema.ensayo', { tipo: 'check', ayuda: 'Genera todo pero NO inserta nada en RadioBOSS. Apágalo cuando estés listo para salir al aire.' }), campo('Iniciar el locutor al abrir el programa', 'sistema.autoiniciar', { tipo: 'check' }),
      tres(campo('Borrar audios de voz tras (horas)', 'sistema.horas_audio', { tipo: 'num', min: 1, max: 720 }), campo('Conservar historial (días)', 'sistema.historial_dias', { tipo: 'num', min: 7, max: 3650 }), campo('Puerto interno', 'sistema.puerto_ui', { tipo: 'num', min: 1024, max: 65000, ayuda: 'Requiere reiniciar' }))),
      tarjeta('Respaldo de configuración', h('p', { class: 'mut' }, 'Incluye ajustes, comerciales y saludos (no las claves).'), h('div', { class: 'fila' }, h('button', { class: 'btn', onclick: hacer(() => descargar('/api/exportar', 'locutor_ia_respaldo.json')) }, '⬇ Exportar respaldo'),
        h('label', { class: 'btn' }, '⬆ Importar respaldo', h('input', { type: 'file', accept: '.json', class: 'oculto', onchange: hacer(async e => { const d = JSON.parse(await e.target.files[0].text()); if (!confirm('Esto reemplaza tu configuración actual. ¿Continuar?')) return; await api('importar', 'POST', d); S = await api('ajustes'); toast('Respaldo importado'); ir('ajustes'); }) })))),
      tarjeta('Información', h('div', { class: 'peq mut', style: 'line-height:1.9' }, `Versión ${get('herramientas.version')}`, h('br'), `Datos: ${get('herramientas.datos')}`, h('br'), `ffmpeg: ${get('herramientas.ffmpeg') || 'no encontrado'}`, h('br'), `yt-dlp: ${get('herramientas.ytdlp') || 'no encontrado'}`),
        nativo() ? null : h('button', { class: 'btn peligro', style: 'margin-top:12px', onclick: hacer(() => api('salir', 'POST')) }, 'Cerrar el programa'))) }]));
}

/* ====================== AYUDA ====================== */
function PaginaAyuda() {
  const out = h('div');
  return pagina('Ayuda y diagnóstico', 'Guía de inicio y comprobación de que todo está listo.',
    tarjeta('Puesta en marcha en 6 pasos', h('ol', { class: 'pasos' },
      h('li', {}, h('div', {}, h('b', {}, 'Activa la API en RadioBOSS. '), 'Settings → API. Anota el puerto y la contraseña.')),
      h('li', {}, h('div', {}, h('b', {}, 'Conecta. '), 'Ajustes → RadioBOSS → «Probar conexión».')),
      h('li', {}, h('div', {}, h('b', {}, 'Pon tu clave de Claude '), 'en Ajustes → Claves y modelo de IA (sin ella el locutor repite plantillas).')),
      h('li', {}, h('div', {}, h('b', {}, 'Elige la voz '), 'en la sección Voz y pruébala. ElevenLabs es la más natural; Edge es gratis para probar.')),
      h('li', {}, h('div', {}, h('b', {}, 'Define al locutor '), 'en Locutor: personalidad, opiniones, horarios, tipos de pausa. Usa la pestaña «Probar».')),
      h('li', {}, h('div', {}, h('b', {}, 'Ensaya y sal al aire. '), 'Inicia en MODO ENSAYO, revisa el Historial; cuando todo suene bien, desactiva el ensayo en Ajustes → Sistema.'))),
      h('p', { class: 'mut' }, 'Importante: cerrar este programa NO corta la música. RadioBOSS sigue con su programación; solo dejarías de tener locutor IA.')),
    tarjeta('Diagnóstico', h('button', { class: 'btn pri', onclick: hacer(async () => { out.textContent = 'Comprobando…'; const r = await api('diagnostico'); out.replaceChildren(h('div', { class: 'diag' }, r.map(x => [h('b', { class: x.ok ? 'ok' : 'err' }, x.ok ? '✓' : '✗'), h('span', {}, x.nombre), h('span', { class: 'mut' }, x.detalle)]))); }) }, 'Comprobar todo'), h('div', { style: 'margin-top:14px' }, out)),
    tarjeta('Consejos para que suene natural', h('ul', { class: 'mut', style: 'line-height:1.8;margin:0;padding-left:18px' },
      h('li', {}, 'Mantén las intervenciones cortas (8–28 palabras). Un locutor real no da discursos entre canciones.'),
      h('li', {}, 'Escribe una buena sección «Opiniones y forma de ser» y «Temas prohibidos»: es lo que más cambia el resultado.'),
      h('li', {}, 'Usa perfiles por horario: más energía en la mañana, menos en la noche.'),
      h('li', {}, 'Agrega a la pronunciación los nombres que la voz diga mal.'),
      h('li', {}, 'Revisa el Historial las primeras semanas y ajusta las instrucciones según lo que oigas.'))));
}

/* ====================== navegación y arranque ====================== */
const PAGINAS = [['panel', '📡', 'Panel', PaginaPanel], ['locutor', '🎙️', 'Locutor', PaginaLocutor], ['voz', '🔊', 'Voz', PaginaVoz], ['comerciales', '📢', 'Comerciales', PaginaComerciales], ['saludos', '💌', 'Saludos', PaginaSaludos],
  ['youtube', '▶️', 'YouTube', PaginaYouTube], ['historial', '📜', 'Historial y reportes', PaginaHistorial], ['ajustes', '⚙️', 'Ajustes', PaginaAjustes], ['ayuda', '❓', 'Ayuda', PaginaAyuda]];
let actual = 'panel', timers = [];
async function ir(id) {
  timers.forEach(clearInterval); timers = []; actual = id; refsPanel = null;
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('act', b.dataset.id === id));
  try {
    const el = await PAGINAS.find(p => p[0] === id)[3]();
    $('#contenido').replaceChildren(el); $('#contenido').scrollTop = 0;
    if (id === 'panel') { ultimoLog = 0; if (EST) actualizarPanel(EST); }
  } catch (e) { $('#contenido').replaceChildren(h('div', { class: 'aviso-caja' }, 'Error: ' + e.message)); }
}
function menu() {
  $('#menu').replaceChildren(h('div', { class: 'logo' }, h('i', {}, '🎙'), h('div', {}, 'Locutor IA', h('small', {}, 'para RadioBOSS'))),
    PAGINAS.map(p => h('button', { class: 'nav', 'data-id': p[0], onclick: () => ir(p[0]) }, h('span', {}, p[1]), p[2])),
    h('div', { class: 'estado-lateral' }, h('div', {}, h('span', { id: 'l-pto', class: 'pto' }), h('span', { id: 'l-loc' }, 'Locutor IA')), h('div', {}, h('span', { id: 'l-rb-pto', class: 'pto' }), h('span', { id: 'l-rb' }, 'RadioBOSS')), h('div', { id: 'guardado', class: 'mut' }, '')));
}
function lateral(e) {
  $('#l-pto').className = 'pto ' + (e.corriendo ? (e.pausado ? 'av' : 'ok') : '');
  $('#l-loc').textContent = e.corriendo ? (e.pausado ? 'Locutor en pausa' : (e.ensayo ? 'Activo (ensayo)' : 'Activo en vivo')) : 'Locutor detenido';
  $('#l-rb-pto').className = 'pto ' + (e.conectado ? 'ok' : (e.corriendo ? 'err' : ''));
  $('#l-rb').textContent = e.conectado ? 'RadioBOSS conectado' : 'RadioBOSS sin conexión';
}
async function sondeo() {
  try {
    EST = await api('estado'); lateral(EST);
    if (actual === 'panel') { const ls = await api('logs?desde=' + ultimoLog); if (ls.length) ultimoLog = ls[ls.length - 1].id; actualizarPanel(EST); pintarLogs(ls); }
    S.sistema.ensayo = EST.ensayo;
  } catch (e) { $('#l-loc').textContent = 'Sin conexión con la app'; }
}
(async function arranque() {
  S = await api('ajustes'); menu(); await ir('panel'); sondeo(); setInterval(sondeo, 1000);
})();
