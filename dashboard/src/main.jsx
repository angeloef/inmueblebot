import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import Login from './Login';
import SuperadminApp from './superadmin/SuperadminApp';
import { AuthProvider, useAuth } from './auth';
import { startVersionWatcher } from './version';
import '../tokens.css';
import '../styles.css';
import '../saas.css';

// Login canónico (la landing). Si está seteado, un usuario anónimo se redirige
// allá en vez de ver el form local; sin la env (dev) el form local sigue activo.
const LOGIN_URL = import.meta.env.VITE_LOGIN_URL || '';
// Guard anti-loop: si el handoff falla y volvemos anónimos, no rebotamos infinito
// landing↔dashboard — la segunda vez se muestra el form local como fallback.
const REDIRECT_FLAG = 'vivienda_login_redirected';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30s antes de refetch automático
      retry: 1,
    },
  },
});

// Pantalla mínima mientras se resuelve GET /auth/me (o se reconecta tras un cold start).
function Splash({ text = 'Cargando…' }) {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: 'var(--fg-tertiary, #667085)', fontSize: 14,
    }}>
      {text}
    </div>
  );
}

// Gate de sesión: el dashboard solo monta con un JWT válido (cookie httpOnly).
// 'reconnecting' = error de red / cold start de Render: mostramos un mensaje en vez
// de expulsar al login a un usuario que probablemente tiene cookies válidas.
// 'anon' + LOGIN_URL → redirect al login canónico de la landing, preservando el
// deep-link (?next=/dashboard/clientes) para volver a la vista bookmarkeada.
function Root() {
  const { status } = useAuth();
  // La superficie /superadmin es un árbol aparte con su propio login y gate por rol; no pasa
  // por el redirect al login canónico de la landing (que es para inmobiliarias). Lo leemos del
  // router (reactivo) en vez de un const a nivel módulo, para no servir el árbol equivocado si
  // alguna navegación client-side cambia el path sin recargar.
  const isSuperadminPath = useLocation().pathname.startsWith('/superadmin');

  const shouldRedirect =
    status === 'anon' && !!LOGIN_URL && !sessionStorage.getItem(REDIRECT_FLAG);

  useEffect(() => {
    if (status === 'authed') {
      sessionStorage.removeItem(REDIRECT_FLAG);  // login OK → rearmar el guard
      return;
    }
    if (shouldRedirect) {
      sessionStorage.setItem(REDIRECT_FLAG, '1');
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace(`${LOGIN_URL}?next=${next}`);
    }
  }, [status, shouldRedirect]);

  if (isSuperadminPath) return <SuperadminApp />;

  if (status === 'loading') return <Splash />;
  if (status === 'reconnecting') return <Splash text="Conectando con el servidor…" />;
  if (status === 'anon') {
    if (shouldRedirect) return <Splash text="Redirigiendo al login…" />;
    return <Login />;
  }
  return <App />;
}

// Detecta deploys nuevos y recarga la pestaña sola (sin F5 manual).
startVersionWatcher();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Root />
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>
);
