import React, { useState } from 'react';
import { Icon, Button, IconButton, Pill, pushToast } from './Primitives';
import { useFaqs, useCreateFaq, useUpdateFaq, useDeleteFaq } from './api';
import { useQueryClient } from '@tanstack/react-query';
import { useFocusTrap } from './useFocusTrap';

// ─── Datos estáticos ───────────────────────────────────────────────────────────

const STEPS = [
  { id: 'question', label: 'Pregunta',      title: '¿Qué te preguntan tus clientes?',    subtitle: 'Escribila tal como la haría alguien por WhatsApp.' },
  { id: 'answer',   label: 'Respuesta',     title: '¿Qué querés que conteste el bot?',   subtitle: 'Clara, completa y en el tono de tu inmobiliaria.' },
  { id: 'organize', label: 'Organización',  title: 'Organizala (opcional)',               subtitle: 'Categoría y palabras clave para que el bot la encuentre mejor.' },
  { id: 'review',   label: 'Revisar',       title: 'Revisá y activá',                    subtitle: 'Vista previa antes de guardar.' },
];

const STEP_HELP = {
  question: {
    heading: 'Cómo escribir la pregunta',
    tips: [
      'Usá el lenguaje natural de tus clientes.',
      'Evitá tecnicismos; pensá en WhatsApp.',
      'Una pregunta por FAQ es lo ideal.',
    ],
    examples: [
      '¿Aceptan mascotas en los departamentos?',
      '¿Qué documentos necesito para alquilar?',
      '¿Puedo ver la propiedad este fin de semana?',
    ],
  },
  answer: {
    heading: 'Cómo escribir la respuesta',
    tips: [
      'Sé directo desde la primera línea.',
      'Si hay pasos, numeralos.',
      'Mencioná próximos pasos o contacto si aplica.',
    ],
    examples: [
      'Sí, aceptamos mascotas pequeñas con depósito adicional de 1 mes.',
      'Necesitás DNI, últimos 3 recibos de sueldo y referencia laboral.',
    ],
  },
  organize: {
    heading: 'Categorías y tags',
    tips: [
      'La categoría agrupa FAQs (ej: "requisitos", "pagos").',
      'Los tags son sinónimos que mejoran el match.',
      'Podés dejarlo vacío y completarlo después.',
    ],
    examples: [
      'Categoría: financiación → Tags: cuotas, crédito, banco',
      'Categoría: visitas → Tags: horario, reserva, agendar',
    ],
  },
  review: {
    heading: 'Antes de guardar',
    tips: [
      'Activá la FAQ para que el bot la use de inmediato.',
      'Podés desactivarla si querés guardarla para después.',
      'Siempre podés editarla o eliminarla desde la lista.',
    ],
    examples: [],
  },
};

const SUGGESTED_FAQS = [
  {
    question: '¿Aceptan mascotas en las propiedades?',
    answer: 'Depende de la propiedad. Consultanos por la dirección específica y te confirmamos si el propietario autoriza mascotas.',
    category: 'requisitos',
    tags: ['mascotas', 'animales', 'perro', 'gato'],
  },
  {
    question: '¿Cuáles son los requisitos para alquilar?',
    answer: 'Necesitás DNI, últimos 3 recibos de sueldo o comprobante de ingresos, y un garante propietario (o seguro de caución como alternativa).',
    category: 'requisitos',
    tags: ['documentos', 'garante', 'recibos', 'DNI'],
  },
  {
    question: '¿Cuál es la comisión inmobiliaria?',
    answer: 'La comisión para el inquilino es de un mes de alquiler + IVA. Para el propietario, acordamos condiciones al momento de la tasación.',
    category: 'financiación',
    tags: ['comisión', 'honorarios', 'costo'],
  },
  {
    question: '¿Puedo ver la propiedad antes de alquilar?',
    answer: '¡Claro! Podés agendar una visita directamente por este chat. Tenemos turnos de lunes a sábados.',
    category: 'visitas',
    tags: ['visita', 'turno', 'ver', 'agendar'],
  },
  {
    question: '¿Las expensas están incluidas en el alquiler?',
    answer: 'No. Las expensas ordinarias corren por cuenta del inquilino y las extraordinarias por cuenta del propietario, salvo acuerdo diferente en el contrato.',
    category: 'pagos',
    tags: ['expensas', 'gastos', 'incluidas'],
  },
  {
    question: '¿Cómo se actualiza el alquiler?',
    answer: 'El alquiler se actualiza según el índice ICL (Índice para Contratos de Locación) publicado por el BCRA, con una frecuencia pactada en el contrato.',
    category: 'financiación',
    tags: ['actualización', 'ICL', 'índice', 'ajuste'],
  },
  {
    question: '¿Cuáles son los horarios de atención?',
    answer: 'Atendemos de lunes a viernes de 9 a 18 hs y los sábados de 9 a 13 hs. Por este canal podés consultarnos en cualquier momento.',
    category: 'horarios',
    tags: ['horario', 'atención', 'lunes', 'viernes'],
  },
  {
    question: '¿Aceptan seguro de caución como garantía?',
    answer: 'Sí, aceptamos seguro de caución de las principales aseguradoras. Te asesoramos durante el trámite sin costo adicional.',
    category: 'requisitos',
    tags: ['caución', 'seguro', 'garantía', 'garante'],
  },
];

const STEP_MICROCOPY = ['Empezá por la pregunta', 'Casi a la mitad', '¡Un paso más!', '¡Casi listo!'];

// ─── Wizard ────────────────────────────────────────────────────────────────────

function FaqWizard({ faq, onClose, defaultOrder }) {
  const [step, setStep] = useState(0);
  const [question, setQuestion] = useState(faq?.question ?? '');
  const [answer, setAnswer] = useState(faq?.answer ?? '');
  const [category, setCategory] = useState(faq?.category ?? '');
  const [tagsText, setTagsText] = useState((faq?.tags ?? []).join(', '));
  const [active, setActive] = useState(faq?.active ?? true);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});

  const createMut = useCreateFaq();
  const updateMut = useUpdateFaq();
  const isEditing = !!faq?.id;
  const trapRef = useFocusTrap(onClose);

  const totalSteps = STEPS.length;
  const pct = Math.round(((step + 1) / totalSteps) * 100);

  const validate = (upToStep) => {
    const errs = {};
    if (upToStep > 0 && !question.trim()) errs.question = 'Escribí la pregunta.';
    if (upToStep > 1 && !answer.trim()) errs.answer = 'Escribí la respuesta.';
    return errs;
  };

  const goNext = () => {
    const errs = validate(step + 1);
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setStep(s => Math.min(s + 1, totalSteps - 1));
  };

  const goBack = () => setStep(s => Math.max(s - 1, 0));

  const jumpTo = (i) => {
    const errs = validate(i);
    if (!Object.keys(errs).length || i < step) { setErrors({}); setStep(i); }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && step < totalSteps - 1) {
      e.preventDefault();
      goNext();
    }
  };

  const handleSave = async () => {
    const errs = validate(totalSteps);
    if (Object.keys(errs).length) { setErrors(errs); setStep(0); return; }
    setSaving(true);
    try {
      const data = {
        question: question.trim(),
        answer:   answer.trim(),
        category: category.trim() || null,
        tags:     tagsText.split(',').map(t => t.trim()).filter(Boolean),
        order:    faq?.order ?? defaultOrder,
        active,
      };
      if (isEditing) {
        await updateMut.mutateAsync({ id: faq.id, ...data });
        pushToast({ text: 'FAQ actualizada.', kind: 'success' });
      } else {
        await createMut.mutateAsync(data);
        pushToast({ text: 'FAQ creada.', kind: 'success' });
      }
      onClose();
    } catch {
      pushToast({ text: 'Error al guardar.', kind: 'danger' });
    } finally {
      setSaving(false);
    }
  };

  const helpData = STEP_HELP[STEPS[step].id];

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div
        className="drawer faq-wizard"
        role="dialog"
        aria-modal="true"
        aria-labelledby="faq-wizard-title"
        ref={trapRef}
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="faq-wizard-title" style={{ margin: 0, fontSize: 15 }}>
              {isEditing ? 'Editar FAQ' : 'Nueva FAQ'}
            </h2>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
              {STEPS[step].title}
            </div>
          </div>
          <IconButton name="x" title="Cerrar" onClick={onClose} />
        </div>

        {/* Progreso */}
        <div className="faq-progress-wrap">
          <div className="faq-step-dots" aria-label="Pasos del wizard">
            {STEPS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                aria-current={i === step ? 'step' : undefined}
                aria-label={`Ir al paso ${i + 1}: ${s.label}`}
                className={`faq-step-dot${i < step ? ' done' : ''}${i === step ? ' current' : ''}`}
                onClick={() => jumpTo(i)}
              >
                {i < step ? <Icon name="check" size={11} /> : i + 1}
              </button>
            ))}
          </div>
          <div
            className="faq-progress-bar"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Progreso"
          >
            <div className="faq-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="faq-progress-label">
            <span>{STEP_MICROCOPY[step]}</span>
            <span className="muted">{step + 1} / {totalSteps}</span>
          </div>
        </div>

        {/* Cuerpo: form + panel de ayuda */}
        <div className="faq-wizard-body">
          <div className="faq-wizard-form">
            {step === 0 && (
              <div className="field">
                <label htmlFor="faq-question">Pregunta</label>
                <textarea
                  id="faq-question"
                  className={errors.question ? 'invalid' : ''}
                  value={question}
                  onChange={e => { setQuestion(e.target.value); setErrors(prev => ({ ...prev, question: undefined })); }}
                  rows={5}
                  placeholder="Ej: ¿Qué documentos necesito para alquilar?"
                  autoFocus
                />
                {errors.question && <span className="field-error">{errors.question}</span>}
              </div>
            )}

            {step === 1 && (
              <div className="field">
                <label htmlFor="faq-answer">Respuesta del bot</label>
                <textarea
                  id="faq-answer"
                  className={errors.answer ? 'invalid' : ''}
                  value={answer}
                  onChange={e => { setAnswer(e.target.value); setErrors(prev => ({ ...prev, answer: undefined })); }}
                  rows={7}
                  placeholder="Ej: Necesitás DNI, últimos 3 recibos de sueldo y un garante propietario."
                  autoFocus
                />
                {errors.answer && <span className="field-error">{errors.answer}</span>}
              </div>
            )}

            {step === 2 && (
              <>
                <div className="field">
                  <label htmlFor="faq-category">Categoría</label>
                  <input
                    id="faq-category"
                    value={category}
                    onChange={e => setCategory(e.target.value)}
                    placeholder="Ej: horarios, financiación, requisitos"
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label htmlFor="faq-tags">Tags (separados por coma)</label>
                  <input
                    id="faq-tags"
                    value={tagsText}
                    onChange={e => setTagsText(e.target.value)}
                    placeholder="horario, atención, sucursal"
                  />
                </div>
              </>
            )}

            {step === 3 && (
              <div>
                <div className="faq-preview-bubble">
                  <div className="faq-preview-q">{question}</div>
                  <div className="faq-preview-a">{answer}</div>
                  {(category || tagsText) && (
                    <div className="faq-preview-meta">
                      {category && <Pill kind="active">{category}</Pill>}
                      {tagsText.split(',').map(t => t.trim()).filter(Boolean).map(t => (
                        <span key={t} className="pill pill-neutral">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="field" style={{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <input
                    type="checkbox"
                    id="faq-active"
                    checked={active}
                    onChange={e => setActive(e.target.checked)}
                    style={{ width: 'auto', flexShrink: 0 }}
                  />
                  <label htmlFor="faq-active" style={{ margin: 0, textTransform: 'none', fontSize: 13, color: 'var(--fg-primary)', fontWeight: 500 }}>
                    Activar esta FAQ
                  </label>
                </div>
                <p className="muted" style={{ fontSize: 12, margin: '4px 0 0' }}>
                  {active ? 'El bot empezará a usarla de inmediato.' : 'Guardada pero no activa; podés activarla después.'}
                </p>
              </div>
            )}
          </div>

          {/* Panel lateral de ayuda */}
          <aside className="faq-help-panel" aria-label="Consejos">
            <div className="faq-help-heading">
              <Icon name="info" size={13} style={{ color: 'var(--accent-500)', flexShrink: 0 }} />
              {helpData.heading}
            </div>
            <ul className="faq-help-tips">
              {helpData.tips.map((tip, i) => <li key={i}>{tip}</li>)}
            </ul>
            {helpData.examples.length > 0 && (
              <>
                <div className="faq-help-examples-label">Ejemplos reales</div>
                {helpData.examples.map((ex, i) => (
                  <div key={i} className="faq-help-example">&ldquo;{ex}&rdquo;</div>
                ))}
              </>
            )}
          </aside>
        </div>

        {/* Footer */}
        <div className="faq-wizard-footer">
          <Button kind="secondary" size="sm" onClick={step === 0 ? onClose : goBack}>
            {step === 0 ? 'Cancelar' : 'Atrás'}
          </Button>
          {step < totalSteps - 1 ? (
            <Button kind="primary" size="sm" onClick={goNext} icon="arrowRight">
              Siguiente
            </Button>
          ) : (
            <Button kind="primary" size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando...' : isEditing ? 'Actualizar' : 'Crear FAQ'}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

// ─── FaqCard ──────────────────────────────────────────────────────────────────

function FaqCard({ faq, onEdit, onDelete }) {
  const handleDelete = (e) => {
    e.stopPropagation();
    if (confirm('¿Eliminar esta FAQ?')) onDelete(faq.id);
  };

  return (
    <article
      className="faq-card"
      tabIndex={0}
      aria-label={`FAQ: ${faq.question}`}
      onClick={() => onEdit(faq)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEdit(faq); } }}
    >
      <div className="faq-card-body">
        <div className="faq-card-q">{faq.question}</div>
        <div className="faq-card-a">{faq.answer}</div>
        <div className="faq-card-meta">
          {faq.category && <Pill kind="active">{faq.category}</Pill>}
          {(faq.tags ?? []).map(t => <span key={t} className="pill pill-neutral">{t}</span>)}
          {!faq.active && <Pill kind="cancelled">Inactiva</Pill>}
        </div>
      </div>
      <div className="faq-card-actions" onClick={e => e.stopPropagation()}>
        <IconButton name="edit" onClick={() => onEdit(faq)} title="Editar esta FAQ" />
        <IconButton name="trash" onClick={handleDelete} title="Eliminar esta FAQ" />
      </div>
    </article>
  );
}

// ─── SuggestedFaqsModal ───────────────────────────────────────────────────────

function SuggestedFaqsModal({ onClose, defaultOrder, createMut, existingQuestions = [] }) {
  const [selected, setSelected] = useState(() => new Set(SUGGESTED_FAQS.map((_, i) => i)));
  const [progress, setProgress] = useState(null);
  const trapRef = useFocusTrap(onClose);

  const toggle = (i) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(i)) next.delete(i); else next.add(i);
    return next;
  });

  const handleAdd = async () => {
    // Filtrar los que ya existen (por pregunta normalizada) para no duplicar.
    const existing = new Set(existingQuestions.map(q => q.trim().toLowerCase()));
    const toCreate = [...selected]
      .map(i => SUGGESTED_FAQS[i])
      .filter(item => !existing.has(item.question.trim().toLowerCase()));
    if (toCreate.length === 0) {
      pushToast({ text: 'Esos ejemplos ya están cargados.', kind: 'info' });
      onClose();
      return;
    }
    setProgress({ done: 0, total: toCreate.length });
    let done = 0;
    for (const item of toCreate) {
      try {
        await createMut.mutateAsync({ ...item, active: true, order: defaultOrder + done });
      } catch { /* continúa con el siguiente */ }
      done++;
      setProgress({ done, total: toCreate.length });
    }
    pushToast({ text: `${done} FAQ${done !== 1 ? 's' : ''} agregada${done !== 1 ? 's' : ''}.`, kind: 'success' });
    onClose();
  };

  const progressPct = progress ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <div className="modal-backdrop" onClick={onClose} aria-hidden="true">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="suggested-title"
           ref={trapRef} onClick={e => e.stopPropagation()}>
          <div className="drawer-head" style={{ padding: '14px 20px' }}>
            <h2 id="suggested-title" style={{ margin: 0, fontSize: 15 }}>Ejemplos comunes del rubro</h2>
            <IconButton name="x" title="Cerrar" onClick={onClose} />
          </div>
          <div style={{ padding: '8px 20px 12px', borderBottom: '1px solid var(--border-default)' }}>
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>
              Seleccioná las FAQs que querés agregar. Quedan como FAQs normales, editables.
            </p>
          </div>
          <div style={{ overflow: 'auto', maxHeight: '55vh', padding: '8px 20px' }}>
            {SUGGESTED_FAQS.map((s, i) => (
              <label key={i} className={`faq-suggest-item${selected.has(i) ? ' selected' : ''}`}>
                <input
                  type="checkbox"
                  checked={selected.has(i)}
                  onChange={() => toggle(i)}
                  style={{ width: 'auto', flexShrink: 0 }}
                />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{s.question}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    {s.answer.length > 90 ? s.answer.slice(0, 90) + '…' : s.answer}
                  </div>
                </div>
              </label>
            ))}
          </div>

          {progress && (
            <div style={{ padding: '8px 20px 0' }}>
              <div
                className="faq-progress-bar"
                role="progressbar"
                aria-valuenow={progressPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Progreso de creación de FAQs"
              >
                <div className="faq-progress-fill" style={{ width: `${progressPct}%` }} />
              </div>
              <div className="faq-progress-label" style={{ marginTop: 4 }}>
                <span>Creando FAQs…</span>
                <span className="muted">{progress.done} / {progress.total}</span>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', padding: '12px 20px', borderTop: '1px solid var(--border-default)' }}>
            <Button kind="secondary" size="sm" onClick={onClose}>Cancelar</Button>
            <Button kind="primary" size="sm" onClick={handleAdd} disabled={selected.size === 0 || !!progress || createMut.isPending}>
              Agregar{selected.size > 0 ? ` ${selected.size} FAQ${selected.size !== 1 ? 's' : ''}` : ''}
            </Button>
          </div>
      </div>
    </div>
  );
}

// ─── Estado vacío ─────────────────────────────────────────────────────────────

function EmptyState({ onNew, onSuggest }) {
  return (
    <div className="faq-empty">
      <div className="faq-empty-icon">
        <Icon name="msg" size={36} style={{ color: 'var(--accent-400)' }} />
      </div>
      <h3 className="faq-empty-title">Tu bot todavía no sabe responder</h3>
      <p className="faq-empty-sub">
        Enseñale agregando preguntas frecuentes. Cuantas más tenga, mejor atiende a tus clientes solo.
      </p>
      <div className="faq-empty-actions">
        <Button kind="primary" icon="plus" onClick={onNew}>Crear mi primera FAQ</Button>
        <Button kind="secondary" icon="star" onClick={onSuggest}>Agregar ejemplos comunes</Button>
      </div>
    </div>
  );
}

// ─── Página FAQs ──────────────────────────────────────────────────────────────

export default function FAQs() {
  const { data: faqs = [], isLoading } = useFaqs();
  const deleteMut  = useDeleteFaq();
  const updateMut  = useUpdateFaq();
  const createMut  = useCreateFaq();
  const qc         = useQueryClient();
  const [editing, setEditing]           = useState(null);
  const [showNew, setShowNew]           = useState(false);
  const [showSuggested, setShowSuggested] = useState(false);
  const [search, setSearch]             = useState('');
  const [filterActive, setFilterActive] = useState('all');

  const handleDelete = (id) => {
    deleteMut.mutate(id, {
      onSuccess: () => pushToast({ text: 'FAQ eliminada.', kind: 'danger' }),
    });
  };

  const sorted = [...faqs].sort((a, b) => a.order - b.order);
  const defaultOrder = sorted.length > 0 ? sorted[sorted.length - 1].order + 1 : 1;

  const reorder = async (fromIdx, toIdx) => {
    const next = [...sorted];
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    try {
      for (let i = 0; i < next.length; i++) {
        const f = next[i];
        if (f.order !== i + 1) {
          await updateMut.mutateAsync({ id: f.id, question: f.question, answer: f.answer, category: f.category, tags: f.tags, order: i + 1, active: f.active });
        }
      }
    } catch {
      pushToast({ text: 'Error al reordenar.', kind: 'danger' });
      qc.invalidateQueries({ queryKey: ['faqs'] });
    }
  };

  const counts = {
    all:      faqs.length,
    active:   faqs.filter(f => f.active).length,
    inactive: faqs.filter(f => !f.active).length,
  };

  const filtered = sorted.filter(f => {
    if (filterActive === 'active'   && !f.active) return false;
    if (filterActive === 'inactive' &&  f.active) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      f.question.toLowerCase().includes(q) ||
      f.answer.toLowerCase().includes(q) ||
      (f.category || '').toLowerCase().includes(q) ||
      (f.tags ?? []).some(t => t.toLowerCase().includes(q))
    );
  });

  const isEmpty = !isLoading && faqs.length === 0;

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Preguntas Frecuentes</h1>
          <div className="sub">Gestioná las FAQ que el chatbot responde a los clientes</div>
        </div>
        {!isEmpty && (
          <div className="page-h-actions">
            <Button kind="secondary" icon="star" onClick={() => setShowSuggested(true)}>Ejemplos</Button>
            <Button kind="primary" icon="plus" onClick={() => setShowNew(true)}>Nueva FAQ</Button>
          </div>
        )}
      </div>

      <div className="scroll-surface surface">
        {isEmpty ? (
          <EmptyState onNew={() => setShowNew(true)} onSuggest={() => setShowSuggested(true)} />
        ) : (
          <>
            <div className="filter-bar">
              <input
                aria-label="Buscar FAQs"
                placeholder="Buscar por pregunta, respuesta, categoría o tag..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {[['all', 'Todas', counts.all], ['active', 'Activas', counts.active], ['inactive', 'Inactivas', counts.inactive]].map(([k, l, n]) => (
                <button key={k} type="button" className={`chip ${filterActive === k ? 'active' : ''}`} aria-pressed={filterActive === k} onClick={() => setFilterActive(k)}>
                  {l}<span className="num">{n}</span>
                </button>
              ))}
            </div>
            <div className="tbl-scroll">
              {isLoading ? (
                <div className="tbl-empty">Cargando...</div>
              ) : filtered.length === 0 ? (
                <div className="tbl-empty">Sin resultados para esa búsqueda.</div>
              ) : (
                <div className="faq-card-list">
                  {filtered.map((faq) => (
                    <FaqCard
                      key={faq.id}
                      faq={faq}
                      onEdit={setEditing}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {showNew && <FaqWizard defaultOrder={defaultOrder} onClose={() => setShowNew(false)} />}
      {editing  && <FaqWizard faq={editing} onClose={() => setEditing(null)} />}
      {showSuggested && (
        <SuggestedFaqsModal
          onClose={() => setShowSuggested(false)}
          defaultOrder={defaultOrder}
          createMut={createMut}
          existingQuestions={faqs.map(f => f.question)}
        />
      )}
    </div>
  );
}
