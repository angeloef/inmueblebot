import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import Login from './Login';
import { AuthProvider, useAuth } from './auth';
import '../tokens.css';
import '../styles.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30s antes de refetch automático
      retry: 1,
    },
  },
});

// Pantalla mínima mientras se resuelve GET /auth/me.
function Splash() {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: 'var(--fg-tertiary, #667085)', fontSize: 14,
    }}>
      Cargando…
    </div>
  );
}

// Gate de sesión: el dashboard solo monta con un JWT válido (cookie httpOnly).
function Root() {
  const { status } = useAuth();
  if (status === 'loading') return <Splash />;
  if (status === 'anon') return <Login />;
  return <App />;
}

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
