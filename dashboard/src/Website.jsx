import React, { useState, useEffect } from 'react';
import { Icon, Button, pushToast } from './Primitives';
import { http } from './api';

/**
 * Website.jsx — "Mi sitio web": el brief que la inmobiliaria completa para que armemos
 * su web pública. Fase A: captura guiada (sin preview/auto-gen). Guarda en /site-brief y,
 * al enviar, queda marcado como 'submitted' para que el equipo lo arme manualmente.
 *
 * Presets de diseño + texto libre donde tiene sentido (no plantillas de ejemplo todavía).
 */

const STYLE_OPTIONS = [
  { value: 'moderno', label: 'Moderno', hint: 'Limpio, actual, foco en fotos grandes.' },
  { value: 'clasico', label: 'Clásico', hint: 'Serio y confiable, tono tradicional.' },
  { value: 'minimalista', label: 'Minimalista', hint: 'Mucho espacio en blanco, simple.' },
  { value: 'lujo', label: 'Lujo', hint: 'Elegante, oscuro/dorado, segmento premium.' },
];
const MOOD_OPTIONS = [
  { value: 'claro', label: 'Claro' },
  { value: 'oscuro', label: 'Oscuro' },
  { value: 'colorido', label: 'Colorido' },
  { value: 'sobrio', label: 'Sobrio' },
];

const STEPS = [
  { id: 'brand', label: 'Marca', icon: 'star' },
  { id: 'pitch', label: 'Sobre la inmobiliaria', icon: 'msg' },
  { id: 'contact', label: 'Contacto', icon: 'phone' },
  { id: 'domain', label: 'Dominio', icon: 'grid' },
  { id: 'design', label: 'Diseño', icon: 'eye' },
  { id: 'catalog', label: 'Catálogo', icon: 'building' },
];

const EMPTY = {
  brand: { brand_name: '', colors: '', typography: '', logo_url: '', photos_note: '' },
  pitch: { about: '', history: '', differentiator: '', audience: '' },
  contact: { whatsapp: '', phone: '', email: '', address: '', hours: '', instagram: '', facebook: '', license: '' },
  domain: { has_domain: false, domain_name: '', wants_us_to_buy: false, notes: '' },
  design: { style_direction: '', color_mood: '', references: '', avoid: '', notes: '' },
  catalog: { op_alquiler: true, op_venta: true, hide_fields: '', cta_whatsapp: true, notes: '' },
};

function Field({ label, hint, children }) {
  return (
    <div className="field config-field">
      <label>{label}</label>
      {hint && <div className="config-hint">{hint}</div>}
      {children}
    </div>
  );
}

export default function Website() {
  const [data, setData] = useState(EMPTY);
  const [status, setStatus] = useState('draft');
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data: b } = await http.get('/site-brief');
        if (!alive) return;
        setStatus(b.status || 'draft');
        setData({
          brand: { ...EMPTY.brand, ...(b.brand || {}) },
          pitch: { ...EMPTY.pitch, ...(b.pitch || {}) },
          contact: { ...EMPTY.contact, ...(b.contact || {}) },
          domain: { ...EMPTY.domain, ...(b.domain || {}) },
          design: { ...EMPTY.design, ...(b.design || {}) },
          catalog: { ...EMPTY.catalog, ...(b.catalog || {}) },
        });
      } catch (e) {
        pushToast({ kind: 'error', text: 'No se pudo cargar tu brief.' });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const set = (section, key) => (e) => {
    const val = e?.target?.type === 'checkbox' ? e.target.checked : e.target.value;
    setData((d) => ({ ...d, [section]: { ...d[section], [key]: val } }));
  };
  const setPreset = (section, key, value) =>
    setData((d) => ({ ...d, [section]: { ...d[section], [key]: value } }));

  async function save(silent) {
    setSaving(true);
    try {
      const { data: b } = await http.put('/site-brief', data);
      setStatus(b.status || 'draft');
      if (!silent) pushToast({ kind: 'success', text: 'Borrador guardado.' });
      return true;
    } catch (e) {
      pushToast({ kind: 'error', text: 'No se pudo guardar.' });
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function submit() {
    const ok = await save(true);
    if (!ok) return;
    try {
      const { data: b } = await http.post('/site-brief/submit');
      setStatus(b.status || 'submitted');
      pushToast({ kind: 'success', text: '¡Brief enviado! Nuestro equipo arma tu web.' });
    } catch (e) {
      pushToast({ kind: 'error', text: 'No se pudo enviar.' });
    }
  }

  if (loading) {
    return (
      <div className="page-view">
        <div className="page-h"><h1>Mi sitio web</h1></div>
        <div className="page-body"><p className="sub">Cargando…</p></div>
      </div>
    );
  }

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div className="page-view">
      <div className="page-h">
        <h1>Mi sitio web</h1>
        <div className="sub">
          Contanos cómo querés tu web y nosotros la armamos. Tus propiedades se sincronizan solas.
          {status === 'submitted' && ' · ✅ Brief enviado — en preparación.'}
        </div>
      </div>

      <div className="page-body" style={{ display: 'grid', gridTemplateColumns: 'minmax(150px, 200px) 1fr', gap: 20, alignItems: 'start' }}>
        {/* Step nav */}
        <nav aria-label="Pasos" style={{ display: 'grid', gap: 4 }}>
          {STEPS.map((s, i) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setStep(i)}
              className={`sb-item ${i === step ? 'active' : ''}`}
              style={{ justifyContent: 'flex-start', gap: 8, width: '100%' }}
            >
              <Icon name={s.icon} size={16} />
              <span>{s.label}</span>
            </button>
          ))}
        </nav>

        {/* Step body */}
        <div className="config-section" style={{ margin: 0 }}>
          <div className="config-section-head">
            <h2>{current.label}</h2>
          </div>
          <div className="config-section-body">
            {current.id === 'brand' && (
              <>
                <Field label="Nombre comercial"><input type="text" value={data.brand.brand_name} onChange={set('brand', 'brand_name')} placeholder="Inmobiliaria Oberá" maxLength={200} /></Field>
                <Field label="Colores de marca" hint="Códigos o descripción (ej: verde #0a7d4b y blanco)."><input type="text" value={data.brand.colors} onChange={set('brand', 'colors')} placeholder="#0a7d4b, blanco" /></Field>
                <Field label="Tipografía" hint="Si tienen manual de marca o fuente preferida."><input type="text" value={data.brand.typography} onChange={set('brand', 'typography')} placeholder="Montserrat / la que sugieran" /></Field>
                <Field label="Logo (link)" hint="Link a tu logo (Drive/Imgur). Si no tenés, lo vemos juntos."><input type="text" value={data.brand.logo_url} onChange={set('brand', 'logo_url')} placeholder="https://…" /></Field>
                <Field label="Fotos del local / equipo" hint="Contanos qué fotos tenés o links."><textarea rows={2} value={data.brand.photos_note} onChange={set('brand', 'photos_note')} placeholder="Tengo fotos de la oficina y del equipo…" /></Field>
              </>
            )}
            {current.id === 'pitch' && (
              <>
                <Field label="¿Cómo se describen?" hint="Va en el inicio / 'sobre nosotros'."><textarea rows={3} value={data.pitch.about} onChange={set('pitch', 'about')} placeholder="Somos una inmobiliaria familiar de Oberá con 20 años…" /></Field>
                <Field label="Historia"><textarea rows={2} value={data.pitch.history} onChange={set('pitch', 'history')} placeholder="Fundada en 2005…" /></Field>
                <Field label="Diferencial" hint="¿Qué los hace distintos?"><textarea rows={2} value={data.pitch.differentiator} onChange={set('pitch', 'differentiator')} placeholder="Atención 24/7 por WhatsApp, gestión de alquileres…" /></Field>
                <Field label="Público objetivo" hint="¿A quién apuntan? (alquiler/venta, zona, segmento)"><input type="text" value={data.pitch.audience} onChange={set('pitch', 'audience')} placeholder="Familias buscando alquiler en Oberá" /></Field>
              </>
            )}
            {current.id === 'contact' && (
              <>
                <Field label="WhatsApp"><input type="text" value={data.contact.whatsapp} onChange={set('contact', 'whatsapp')} placeholder="+54 9 3755 …" /></Field>
                <Field label="Teléfono"><input type="text" value={data.contact.phone} onChange={set('contact', 'phone')} /></Field>
                <Field label="Email"><input type="email" value={data.contact.email} onChange={set('contact', 'email')} placeholder="contacto@…" /></Field>
                <Field label="Dirección"><input type="text" value={data.contact.address} onChange={set('contact', 'address')} placeholder="Av. Libertad 123, Oberá" /></Field>
                <Field label="Horarios"><input type="text" value={data.contact.hours} onChange={set('contact', 'hours')} placeholder="Lun a Sáb de 9 a 18hs" /></Field>
                <Field label="Instagram"><input type="text" value={data.contact.instagram} onChange={set('contact', 'instagram')} placeholder="@inmobiliaria" /></Field>
                <Field label="Facebook"><input type="text" value={data.contact.facebook} onChange={set('contact', 'facebook')} /></Field>
                <Field label="Matrícula / colegiado"><input type="text" value={data.contact.license} onChange={set('contact', 'license')} placeholder="CUCICBA / colegio local" /></Field>
              </>
            )}
            {current.id === 'domain' && (
              <>
                <Field label="¿Ya tenés un dominio?">
                  <label className="opt-check">
                    <input type="checkbox" checked={data.domain.has_domain} onChange={set('domain', 'has_domain')} />
                    <span>Sí, ya tengo un dominio</span>
                  </label>
                </Field>
                {data.domain.has_domain && (
                  <Field label="¿Cuál?"><input type="text" value={data.domain.domain_name} onChange={set('domain', 'domain_name')} placeholder="miinmobiliaria.com.ar" /></Field>
                )}
                <Field label="¿Querés que lo compremos nosotros?" hint="Si no tenés dominio, podemos conseguirlo.">
                  <label className="opt-check">
                    <input type="checkbox" checked={data.domain.wants_us_to_buy} onChange={set('domain', 'wants_us_to_buy')} />
                    <span>Sí, compren un dominio por mí</span>
                  </label>
                </Field>
                <Field label="Notas sobre el dominio"><textarea rows={2} value={data.domain.notes} onChange={set('domain', 'notes')} placeholder="Me gustaría algo como…" /></Field>
              </>
            )}
            {current.id === 'design' && (
              <>
                <Field label="Estilo" hint="Elegí la dirección general (después la afinamos).">
                  <div className="segmented" role="radiogroup" aria-label="Estilo">
                    {STYLE_OPTIONS.map((o) => (
                      <button key={o.value} type="button" role="radio" aria-checked={data.design.style_direction === o.value}
                        title={o.hint}
                        className={`segmented-item ${data.design.style_direction === o.value ? 'segmented-on' : ''}`}
                        onClick={() => setPreset('design', 'style_direction', o.value)}>{o.label}</button>
                    ))}
                  </div>
                </Field>
                <Field label="Tono de color">
                  <div className="segmented" role="radiogroup" aria-label="Tono de color">
                    {MOOD_OPTIONS.map((o) => (
                      <button key={o.value} type="button" role="radio" aria-checked={data.design.color_mood === o.value}
                        className={`segmented-item ${data.design.color_mood === o.value ? 'segmented-on' : ''}`}
                        onClick={() => setPreset('design', 'color_mood', o.value)}>{o.label}</button>
                    ))}
                  </div>
                </Field>
                <Field label="Sitios de referencia" hint="¿Alguna web que te guste? Pegá links."><textarea rows={2} value={data.design.references} onChange={set('design', 'references')} placeholder="https://… me gusta cómo se ven las fichas" /></Field>
                <Field label="Qué evitar"><input type="text" value={data.design.avoid} onChange={set('design', 'avoid')} placeholder="Nada muy recargado" /></Field>
                <Field label="Otras preferencias"><textarea rows={2} value={data.design.notes} onChange={set('design', 'notes')} placeholder="Que se vea confiable y fácil de usar en el celular" /></Field>
              </>
            )}
            {current.id === 'catalog' && (
              <>
                <Field label="¿Qué operaciones publicar?">
                  <label className="opt-check"><input type="checkbox" checked={data.catalog.op_alquiler} onChange={set('catalog', 'op_alquiler')} /><span>Alquiler</span></label>
                  <label className="opt-check"><input type="checkbox" checked={data.catalog.op_venta} onChange={set('catalog', 'op_venta')} /><span>Venta</span></label>
                </Field>
                <Field label="Campos a ocultar en la ficha" hint="Si hay algo que NO querés mostrar (ej: precio en algunas)."><input type="text" value={data.catalog.hide_fields} onChange={set('catalog', 'hide_fields')} placeholder="precio en propiedades premium" /></Field>
                <Field label="Botón de WhatsApp en cada propiedad">
                  <label className="opt-check"><input type="checkbox" checked={data.catalog.cta_whatsapp} onChange={set('catalog', 'cta_whatsapp')} /><span>Sí, que el visitante escriba al bot por WhatsApp</span></label>
                </Field>
                <Field label="Notas sobre el catálogo"><textarea rows={2} value={data.catalog.notes} onChange={set('catalog', 'notes')} placeholder="Las propiedades salen del sistema, se sincronizan solas." /></Field>
                <p className="sub" style={{ marginTop: 8 }}>Tus propiedades se sincronizan automáticamente desde el sistema — no hay que cargarlas de nuevo.</p>
              </>
            )}
          </div>

          {/* Footer actions */}
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '12px 16px', borderTop: '1px solid var(--border, #e5e7eb)', flexWrap: 'wrap' }}>
            <Button kind="ghost" icon="chevronLeft" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>Anterior</Button>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button kind="secondary" onClick={() => save(false)} disabled={saving}>{saving ? 'Guardando…' : 'Guardar borrador'}</Button>
              {!isLast && <Button kind="primary" icon="chevronRight" onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}>Siguiente</Button>}
              {isLast && <Button kind="primary" icon="check" onClick={submit} disabled={saving}>Enviar al equipo</Button>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
