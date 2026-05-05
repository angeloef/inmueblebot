/**
 * data.jsx — Utilidades de formato y stubs de compatibilidad.
 *
 * Los datos reales vienen de la API a través de los hooks de React Query
 * definidos en src/api.js.
 */

// ─── Utilidades de formato (locale: es-AR) ────────────────────────────────────

export const fmtCurrency = (n, cur) => {
  if (cur === 'USD') return `USD ${n.toLocaleString('es-AR')}`;
  return `$ ${n.toLocaleString('es-AR')}`;
};

export const padDate = (y, m, d) =>
  `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

export const parseTime = (t) => {
  const [h, m] = t.split(':').map(Number);
  return h + m / 60;
};

export const fmtTime12 = (t) => {
  const [h, m] = t.split(':').map(Number);
  const ap = h >= 12 ? 'pm' : 'am';
  const hh = h % 12 || 12;
  return m === 0 ? `${hh}${ap}` : `${hh}:${String(m).padStart(2, '0')}${ap}`;
};
