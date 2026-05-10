import React, { useState } from 'react';
import { Icon, Button, IconButton, Pill, pushToast } from './Primitives';
import { useFaqs, useCreateFaq, useUpdateFaq, useDeleteFaq } from './api';

function FaqModal({ faq, onClose }) {
  const [question, setQuestion] = useState(faq?.question ?? '');
  const [answer, setAnswer] = useState(faq?.answer ?? '');
  const [category, setCategory] = useState(faq?.category ?? '');
  const [tagsText, setTagsText] = useState((faq?.tags ?? []).join(', '));
  const [order, setOrder] = useState(faq?.order ?? 0);
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
        order: Number(order),
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
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Categoría</label>
              <input
                value={category}
                onChange={e => setCategory(e.target.value)}
                placeholder="Ej: horarios, financiación, proceso"
              />
            </div>
            <div className="field" style={{ width: 80 }}>
              <label>Orden</label>
              <input
                type="number"
                value={order}
                onChange={e => setOrder(Number(e.target.value))}
              />
            </div>
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
            <Button kind="secondary" onClick={onClose}>Cancelar</Button>
            <Button kind="primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar'}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}

function FaqRow({ faq, onEdit, onDelete }) {
  const handleDelete = () => {
    if (confirm(`¿Eliminar FAQ: "${faq.question.slice(0, 50)}..."?`)) {
      onDelete(faq.id);
    }
  };

  return (
    <div className="row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6, padding: '12px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{faq.question}</div>
          <div className="muted" style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{faq.answer}</div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
            {faq.category && <Pill kind="active">{faq.category}</Pill>}
            {(faq.tags ?? []).map(t => (
              <span key={t} className="pill pill-neutral">{t}</span>
            ))}
            {/* @ts-ignore */}
            {!faq.active && <Pill kind="cancelled">Inactiva</Pill>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
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
  const [editing, setEditing] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [search, setSearch] = useState('');

  const handleDelete = (id) => {
    deleteMut.mutate(id, {
      onSuccess: () => pushToast({ text: 'FAQ eliminada.', kind: 'danger' }),
    });
  };

  const filtered = faqs.filter(f => {
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
        <Button kind="primary" icon="plus" onClick={() => setShowNew(true)}>Nueva FAQ</Button>
      </div>

      <div style={{ marginBottom: 16 }}>
        <input
          className="search-input"
          placeholder="Buscar por pregunta, respuesta, categoría o tag..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            width: '100%',
            padding: '10px 14px',
            border: '1px solid var(--border)',
            borderRadius: 8,
            fontSize: 14,
            background: 'var(--bg)',
            color: 'var(--fg)',
          }}
        />
      </div>

      {isLoading ? (
        <div className="muted" style={{ textAlign: 'center', padding: 40 }}>Cargando...</div>
      ) : filtered.length === 0 ? (
        <div className="muted" style={{ textAlign: 'center', padding: 40 }}>
          {search ? 'Sin resultados para esa búsqueda.' : 'Aún no hay preguntas frecuentes. Hacé clic en "Nueva FAQ" para agregar.'}
        </div>
      ) : (
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {filtered.map(faq => (
            <FaqRow
              key={faq.id}
              faq={faq}
              onEdit={setEditing}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {showNew && <FaqModal onClose={() => setShowNew(false)} />}
      {editing && <FaqModal faq={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
