import React, { useState } from 'react';
import { Icon, Button, IconButton, Pill, pushToast } from './Primitives';
import { useFaqs, useCreateFaq, useUpdateFaq, useDeleteFaq } from './api';

function FaqModal({ faq, onClose, defaultOrder }) {
  const [question, setQuestion] = useState(faq?.question ?? '');
  const [answer, setAnswer] = useState(faq?.answer ?? '');
  const [category, setCategory] = useState(faq?.category ?? '');
  const [tagsText, setTagsText] = useState((faq?.tags ?? []).join(', '));
  const [active, setActive] = useState(faq?.active ?? true);
  const [saving, setSaving] = useState(false);

  const createMut = useCreateFaq();
  const updateMut = useUpdateFaq();
  const isEditing = !!faq?.id;

  const handleSave = async () => {
    if (!question.trim() || !answer.trim()) {
      pushToast({ text: 'Completá pregunta y respuesta.', kind: 'danger' });
      return;
    }
    setSaving(true);
    try {
      const data = {
        question: question.trim(),
        answer: answer.trim(),
        category: category.trim() || null,
        tags: tagsText.split(',').map(t => t.trim()).filter(Boolean),
        order: faq?.order ?? defaultOrder,
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

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <h2>{isEditing ? 'Editar FAQ' : 'Nueva FAQ'}</h2>
          <span className="close"><IconButton name="x" onClick={onClose} /></span>
        </div>
        <div className="drawer-body">
          <div className="field">
            <label>Pregunta</label>
            <textarea
              value={question}
              onChange={e => setQuestion(e.target.value)}
              rows={2}
              placeholder="Ej: ¿A qué hora abren?"
            />
          </div>
          <div className="field">
            <label>Respuesta</label>
            <textarea
              value={answer}
              onChange={e => setAnswer(e.target.value)}
              rows={4}
              placeholder="Ej: Nuestro horario es de lunes a viernes de 9 a 18hs..."
            />
          </div>
          <div className="field">
            <label>Categoría</label>
            <input
              value={category}
              onChange={e => setCategory(e.target.value)}
              placeholder="Ej: horarios, financiación, proceso"
            />
          </div>
          <div className="field">
            <label>Tags (separados por coma)</label>
            <input
              value={tagsText}
              onChange={e => setTagsText(e.target.value)}
              placeholder="horario, atención, sucursal"
            />
          </div>
          <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              id="faq-active"
              checked={active}
              onChange={e => setActive(e.target.checked)}
              style={{ width: 'auto' }}
            />
            <label htmlFor="faq-active" style={{ margin: 0 }}>Activa</label>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
            <Button kind="secondary" size="sm" onClick={onClose}>Cancelar</Button>
            <Button kind="primary" size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}

function FaqRow({ faq, onEdit, onDelete, onMoveUp, onMoveDown, isFirst, isLast, reorderEnabled }) {
  const handleDelete = () => {
    if (confirm(`¿Eliminar FAQ: "${faq.question.slice(0, 50)}..."?`)) {
      onDelete(faq.id);
    }
  };

  return (
    <div
      onClick={() => onEdit(faq)}
      style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{faq.question}</div>
          <div className="muted" style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{faq.answer}</div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
            {faq.category && <Pill kind="active">{faq.category}</Pill>}
            {(faq.tags ?? []).map(t => (
              <span key={t} className="pill pill-neutral">{t}</span>
            ))}
            {!faq.active && <Pill kind="cancelled">Inactiva</Pill>}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
          <IconButton name="edit" onClick={() => onEdit(faq)} title="Editar" />
          <IconButton name="trash" onClick={handleDelete} title="Eliminar" />
        </div>
      </div>
    </div>
  );
}

export default function FAQs() {
  const { data: faqs = [], isLoading } = useFaqs();
  const deleteMut = useDeleteFaq();
  const updateMut = useUpdateFaq();
  const [editing, setEditing] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [search, setSearch] = useState('');
  const [filterActive, setFilterActive] = useState('all');

  const handleDelete = (id) => {
    deleteMut.mutate(id, {
      onSuccess: () => pushToast({ text: 'FAQ eliminada.', kind: 'danger' }),
    });
  };

  // Canonical sorted list (used as source of truth for reordering)
  const sorted = [...faqs].sort((a, b) => a.order - b.order);
  const defaultOrder = sorted.length > 0 ? sorted[sorted.length - 1].order + 1 : 1;

  // Move item at fromIdx to toIdx and renormalize all orders to 1,2,3...
  const reorder = async (fromIdx, toIdx) => {
    const next = [...sorted];
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    try {
      for (let i = 0; i < next.length; i++) {
        const f = next[i];
        const newOrder = i + 1;
        if (f.order !== newOrder) {
          await updateMut.mutateAsync({
            id: f.id,
            question: f.question,
            answer: f.answer,
            category: f.category,
            tags: f.tags,
            order: newOrder,
            active: f.active,
          });
        }
      }
    } catch {
      pushToast({ text: 'Error al reordenar.', kind: 'danger' });
    }
  };

  const counts = {
    all:      faqs.length,
    active:   faqs.filter(f => f.active).length,
    inactive: faqs.filter(f => !f.active).length,
  };

  // Arrows only make sense when not searching/filtering (order would be ambiguous)
  const reorderEnabled = !search && filterActive === 'all';

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

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Preguntas Frecuentes</h1>
          <div className="sub">Gestioná las FAQ que el chatbot responde a los clientes</div>
        </div>
        <div className="page-h-actions">
          <Button kind="primary" icon="plus" onClick={() => setShowNew(true)}>Nueva FAQ</Button>
        </div>
      </div>

      <div className="scroll-surface surface">
        <div className="filter-bar">
          <input
            placeholder="Buscar por pregunta, respuesta, categoría o tag..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {[['all', 'Todas', counts.all], ['active', 'Activas', counts.active], ['inactive', 'Inactivas', counts.inactive]].map(([k, l, n]) => (
            <span key={k} className={`chip ${filterActive === k ? 'active' : ''}`} onClick={() => setFilterActive(k)}>
              {l}<span className="num">{n}</span>
            </span>
          ))}
        </div>
        <div className="tbl-scroll">
          {isLoading ? (
            <div className="muted" style={{ textAlign: 'center', padding: 40 }}>Cargando...</div>
          ) : filtered.length === 0 ? (
            <div className="muted" style={{ textAlign: 'center', padding: 40 }}>
              {search || filterActive !== 'all'
                ? 'Sin resultados para esa búsqueda.'
                : 'Aún no hay preguntas frecuentes. Hacé clic en "Nueva FAQ" para agregar.'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {filtered.map((faq, idx) => {
                const globalIdx = sorted.findIndex(f => f.id === faq.id);
                return (
                  <FaqRow
                    key={faq.id}
                    faq={faq}
                    onEdit={setEditing}
                    onDelete={handleDelete}
                    onMoveUp={() => reorder(globalIdx, globalIdx - 1)}
                    onMoveDown={() => reorder(globalIdx, globalIdx + 1)}
                    isFirst={idx === 0}
                    isLast={idx === filtered.length - 1}
                    reorderEnabled={reorderEnabled}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>

      {showNew && <FaqModal defaultOrder={defaultOrder} onClose={() => setShowNew(false)} />}
      {editing && <FaqModal faq={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
