import React from 'react';

/**
 * Tasa de conversión sobre el embudo de leads (contratos firmados / total de contactos).
 * Presentacional — recibe los conteos ya calculados en el contenedor.
 */
export default function ConversionRate({ converted, total }) {
  const rate = total > 0 ? Math.round((converted / total) * 100) : 0;
  return (
    <div className="conversion-rate">
      <div className="conversion-rate-head">
        <span className="conversion-rate-label">Tasa de conversión</span>
        <span className="conversion-rate-value tabular">{rate}%</span>
      </div>
      <div className="conversion-rate-sub">
        {converted} de {total} contacto{total !== 1 ? 's' : ''} llegaron a contrato
      </div>
    </div>
  );
}
