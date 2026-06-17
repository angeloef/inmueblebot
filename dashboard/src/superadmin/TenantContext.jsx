/**
 * TenantContext.jsx — estado global del tenant seleccionado en la superficie /superadmin.
 *
 * El selector del header (SuperadminShell) escribe acá; los planes 05 (explorador) y 06
 * (analítica) lo consumen vía `useSuperadminTenant()` para scopear sus vistas. `null` =
 * "Todas las inmobiliarias" (vista cross-tenant agregada).
 *
 * La lista de tenants viene de `useTenants()` (GET /admin/tenants, ya gateado por
 * require_superadmin). No duplicamos ese server-state acá: solo guardamos el id elegido.
 */
import React, { createContext, useContext, useMemo, useState } from 'react';
import { useTenants } from '../api';

const SuperadminTenantContext = createContext(null);

export function useSuperadminTenant() {
  const ctx = useContext(SuperadminTenantContext);
  if (!ctx) throw new Error('useSuperadminTenant debe usarse dentro de <SuperadminTenantProvider>');
  return ctx;
}

export function SuperadminTenantProvider({ children }) {
  const { data: tenants = [], isLoading, isError } = useTenants();
  const [selectedTenantId, setSelectedTenantId] = useState(null);

  const selectedTenant = useMemo(
    () => tenants.find((t) => t.id === selectedTenantId) ?? null,
    [tenants, selectedTenantId],
  );

  const value = useMemo(
    () => ({
      tenants,
      isLoading,
      isError,
      selectedTenantId,
      selectedTenant,
      setSelectedTenantId,
    }),
    [tenants, isLoading, isError, selectedTenantId, selectedTenant],
  );

  return (
    <SuperadminTenantContext.Provider value={value}>
      {children}
    </SuperadminTenantContext.Provider>
  );
}
