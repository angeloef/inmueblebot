// Auto-actualización de la pestaña tras un deploy nuevo, sin F5 manual.
//
// El SPA que ya está corriendo nunca toma un build nuevo por sí solo: su JS sigue en
// memoria hasta recargar. Este watcher consulta GET /version (un hash del index.html
// del servidor, que cambia en cada deploy) y, si difiere del que había al cargar la
// pestaña, recarga para tomar el bundle nuevo.

const POLL_MS = 60_000; // chequeo de fondo cada 60s

let bootBuild = null;
let reloading = false;

async function fetchBuild() {
  try {
    const res = await fetch('/version', { cache: 'no-store' });
    if (!res.ok) return null;
    const data = await res.json();
    // El backend expone { commit: RENDER_GIT_COMMIT }. 'build' es fallback por si
    // cambia el shape. 'dev' (sin RENDER_GIT_COMMIT en local) se trata como "sin versión".
    const v = data?.commit ?? data?.build ?? null;
    return v && v !== 'dev' ? v : null;
  } catch {
    return null; // offline / cold start: reintentamos en el próximo ciclo
  }
}

function reloadOnce() {
  if (reloading) return;
  reloading = true;
  window.location.reload();
}

async function check() {
  if (reloading) return;
  const current = await fetchBuild();
  if (current && bootBuild && current !== bootBuild) {
    reloadOnce();
  }
}

export async function startVersionWatcher() {
  // Guard de bfcache: si el browser restaura la pestaña desde el back/forward cache
  // (navegación atrás/adelante, o volver tras el login), recarga para tomar el bundle
  // vigente en vez de mostrar un snapshot viejo en memoria.
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) window.location.reload();
  });

  bootBuild = await fetchBuild();
  if (!bootBuild || bootBuild === 'unknown') return; // sin endpoint: no hacemos nada

  setInterval(check, POLL_MS);
  // Chequeos oportunos cuando el usuario vuelve a la pestaña: detecta el deploy al
  // instante sin esperar el intervalo, y minimiza recargar en medio de una acción.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check();
  });
  window.addEventListener('focus', check);
}
