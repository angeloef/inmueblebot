import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Icon } from './Primitives';
import {
  useConversations,
  useConversation,
  useReplyToConversation,
  useToggleBot,
} from './api';

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'ahora';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d`;
  return new Date(dateStr).toLocaleDateString('es-AR');
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  return new Intl.DateTimeFormat('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(dateStr));
}

// ── Styles ───────────────────────────────────────────────────────────────────

const S = {
  container: {
    display: 'flex',
    flexDirection: 'row',
    height: 'calc(100vh - 64px)',
    background: 'var(--surface-base)',
  },
  // Left panel — conversation list
  panel: {
    width: 320,
    minWidth: 320,
    borderRight: '1px solid var(--border-subtle)',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--surface-raised)',
  },
  panelHeader: {
    padding: '12px 16px',
    borderBottom: '1px solid var(--border-subtle)',
    background: 'var(--surface-base)',
  },
  panelTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: 'var(--fg-primary)',
    marginBottom: 8,
  },
  searchInput: {
    width: '100%',
    padding: '8px 12px',
    borderRadius: 8,
    border: '1px solid var(--border-subtle)',
    fontSize: 13,
    background: 'var(--surface-raised)',
    color: 'var(--fg-primary)',
    outline: 'none',
    boxSizing: 'border-box',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
  },
  convItem: (selected) => ({
    display: 'flex',
    alignItems: 'center',
    padding: '12px 16px',
    borderBottom: '1px solid var(--border-subtle)',
    cursor: 'pointer',
    background: selected ? 'var(--gray-100, #f5f5f5)' : 'transparent',
    transition: 'background 0.15s',
    gap: 12,
  }),
  avatar: {
    width: 40,
    height: 40,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: 14,
    background: 'var(--accent-100, #e8eaf6)',
    color: 'var(--accent-600, #3949ab)',
    flexShrink: 0,
  },
  convInfo: {
    flex: 1,
    minWidth: 0,
  },
  convName: {
    fontSize: 13,
    fontWeight: 700,
    color: 'var(--fg-primary)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  convPreview: {
    fontSize: 12,
    color: 'var(--fg-tertiary)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginTop: 2,
  },
  convRight: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    gap: 4,
    flexShrink: 0,
  },
  convTime: {
    fontSize: 11,
    color: 'var(--fg-tertiary)',
  },
  pausedBadge: {
    fontSize: 11,
    color: '#e67e22',
    fontWeight: 600,
  },
  emptyList: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: 'var(--fg-tertiary)',
    fontSize: 14,
  },
  // Right panel — chat view
  chatPanel: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  placeholder: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: 'var(--fg-tertiary)',
    gap: 12,
  },
  chatHeader: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    height: 56,
    borderBottom: '1px solid var(--border-subtle)',
    background: 'var(--surface-raised)',
    gap: 12,
  },
  headerInfo: {
    flex: 1,
    minWidth: 0,
  },
  headerName: {
    fontSize: 14,
    fontWeight: 700,
    color: 'var(--fg-primary)',
  },
  headerSub: {
    fontSize: 11,
    color: 'var(--fg-tertiary)',
    marginTop: 1,
  },
  statePill: {
    display: 'inline-block',
    fontSize: 10,
    padding: '2px 6px',
    borderRadius: 4,
    background: 'var(--gray-100, #f5f5f5)',
    color: 'var(--fg-secondary)',
    marginLeft: 6,
    textTransform: 'capitalize',
  },
  botToggle: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 2,
    flexShrink: 0,
  },
  botToggleLabel: {
    fontSize: 10,
    color: 'var(--fg-tertiary)',
  },
  msgArea: {
    flex: 1,
    overflowY: 'auto',
    padding: 16,
    background: '#e5ddd5',
  },
  msgRow: (align) => ({
    display: 'flex',
    justifyContent: align === 'right' ? 'flex-end' : 'flex-start',
    marginBottom: 8,
  }),
  msgBubble: (role) => {
    let bg = '#fff';
    let borderRadius = '0 8px 8px 8px';
    let align = 'left';
    if (role === 'user') {
      bg = '#d9fdd3';
      borderRadius = '8px 0 8px 8px';
      align = 'right';
    } else if (role === 'admin') {
      bg = '#e3f2fd';
    }
    return {
      maxWidth: '70%',
      padding: '8px 12px',
      borderRadius,
      background: bg,
      wordBreak: 'break-word',
      whiteSpace: 'pre-wrap',
    };
  },
  msgContent: {
    fontSize: 13,
    color: '#111',
    lineHeight: 1.4,
  },
  msgMeta: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  msgTime: {
    fontSize: 10,
    color: 'var(--fg-tertiary)',
  },
  msgLabel: {
    fontSize: 10,
    color: 'var(--fg-tertiary)',
    fontWeight: 500,
  },
  inputBar: {
    display: 'flex',
    alignItems: 'center',
    padding: '8px 16px',
    height: 56,
    gap: 8,
    background: 'var(--surface-raised)',
    borderTop: '1px solid var(--border-subtle)',
  },
  input: {
    flex: 1,
    padding: '8px 16px',
    borderRadius: 20,
    border: '1px solid var(--border-subtle)',
    fontSize: 13,
    background: 'var(--surface-raised)',
    color: 'var(--fg-primary)',
    outline: 'none',
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: '50%',
    border: 'none',
    background: 'var(--accent-500)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    flexShrink: 0,
  },
  sendBtnDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: 'var(--fg-tertiary)',
    fontSize: 14,
  },
};

// ── Sub-components ───────────────────────────────────────────────────────────

function ToggleSwitch({ isOn, loading, onToggle }) {
  return (
    <button
      type="button"
      className={`toggle-switch ${isOn ? 'toggle-on' : 'toggle-off'}`}
      onClick={onToggle}
      disabled={loading}
      title={isOn ? 'Pausar bot' : 'Activar bot'}
      style={{
        width: 40,
        height: 22,
        borderRadius: 11,
        border: 'none',
        position: 'relative',
        cursor: loading ? 'not-allowed' : 'pointer',
        opacity: loading ? 0.6 : 1,
        background: isOn ? '#25D366' : '#ccc',
        transition: 'background 0.2s',
        overflow: 'hidden',
        padding: 0,
      }}
    >
      <span
        style={{
          display: 'block',
          width: 18,
          height: 18,
          borderRadius: '50%',
          background: '#fff',
          position: 'absolute',
          top: 2,
          left: isOn ? 60 : 2,
          transition: 'left 0.2s',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }}
      />
    </button>
  );
}

function ConversationRow({ conv, selected, onClick }) {
  const avatarLetter = (conv.phone ?? '?').charAt(0).toUpperCase() || '?';
  return (
    <button
      type="button"
      style={{ ...S.convItem(selected), width: '100%', textAlign: 'left', font: 'inherit', color: 'inherit' }}
      aria-current={selected ? 'true' : undefined}
      aria-label={`Conversación con ${conv.phone || 'sin teléfono'}${conv.bot_paused ? ', bot pausado' : ''}`}
      onClick={onClick}
    >
      <div style={S.avatar} aria-hidden="true">{avatarLetter}</div>
      <div style={S.convInfo}>
        <div style={S.convName}>{conv.phone || 'Sin teléfono'}</div>
        <div style={S.convPreview}>
          {conv.last_message_at
            ? timeAgo(conv.last_message_at)
            : '—'}
        </div>
      </div>
      <div style={S.convRight}>
        <div style={S.convTime}>
          {conv.last_message_at ? timeAgo(conv.last_message_at) : ''}
        </div>
        {conv.bot_paused && <div style={S.pausedBadge} aria-hidden="true">⏸</div>}
      </div>
    </button>
  );
}

function ChatHeader({ conversation, botPaused, toggling, onToggleBot, onBack }) {
  const avatarLetter = (conversation.phone ?? '?').charAt(0).toUpperCase() || '?';
  const stateLabel = conversation.state ?? 'active';
  return (
    <div style={S.chatHeader}>
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          style={{
            width: 36, height: 36, flexShrink: 0,
            border: 'none', background: 'transparent',
            borderRadius: 6, cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center',
            justifyContent: 'center', color: 'var(--fg-secondary)',
            marginRight: -4,
          }}
          aria-label="Abrir lista de contactos"
        >
          <Icon name="chevronLeft" size={20} />
        </button>
      )}
      <div style={S.avatar}>{avatarLetter}</div>
      <div style={S.headerInfo}>
        <div style={S.headerName}>
          {conversation.phone || 'Sin teléfono'}
          <span style={S.statePill}>{stateLabel}</span>
        </div>
        <div style={S.headerSub}>
          BSUID: {conversation.bsuid ?? '—'}
        </div>
      </div>
      <div style={S.botToggle}>
        <ToggleSwitch
          isOn={!botPaused}
          loading={toggling}
          onToggle={onToggleBot}
        />
        <span style={{
          ...S.botToggleLabel,
          color: botPaused ? '#e67e22' : '#25D366',
          fontWeight: 500,
        }}>
          {botPaused ? 'Bot pausado' : 'Bot activo'}
        </span>
      </div>
    </div>
  );
}

function Message({ msg }) {
  const role = msg.sender === 'user' ? 'user' : (msg.sender === 'admin' ? 'admin' : 'bot');
  const isRight = role === 'user';
  const labels = { user: '👤', bot: '🤖', admin: '👤 Agente' };

  return (
    <div style={S.msgRow(isRight ? 'right' : 'left')}>
      <div style={S.msgBubble(role)}>
        <div style={S.msgContent}>{msg.content}</div>
        <div style={S.msgMeta}>
          <span style={S.msgTime}>{formatTime(msg.timestamp)}</span>
          <span style={S.msgLabel}>{labels[role] ?? ''}</span>
        </div>
      </div>
    </div>
  );
}

function ConversationList({ conversations, selectedId, onSelect, search, onSearchChange, panelStyle }) {
  const list = (conversations ?? []).filter(c => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (c.phone ?? '').toLowerCase().includes(q)
      || (c.bsuid ?? '').toLowerCase().includes(q);
  });

  return (
    <div style={{ ...S.panel, ...panelStyle }}>
      <div style={S.panelHeader}>
        <div style={S.panelTitle}>Chats</div>
        <input
          style={S.searchInput}
          placeholder="Buscar por teléfono..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <div style={S.list}>
        {list.length === 0 && (
          <div style={S.emptyList}>
            {search ? 'Sin resultados' : 'No hay conversaciones aún'}
          </div>
        )}
        {list.map(conv => (
          <ConversationRow
            key={conv.id}
            conv={conv}
            selected={String(conv.id) === String(selectedId)}
            onClick={() => onSelect(conv.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ChatView({ conversationId, onBack }) {
  const { data: conversation, isLoading, isError, error } = useConversation(conversationId);
  const replyMut = useReplyToConversation();
  const toggleBotMut = useToggleBot();

  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [sseFallback, setSseFallback] = useState(false);
  const msgEndRef = useRef(null);
  const inputRef = useRef(null);

  // Sync conversation data into local state
  useEffect(() => {
    if (conversation) {
      setMessages(conversation.messages ?? []);
    }
  }, [conversation]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // SSE connection for real-time updates
  useEffect(() => {
    if (!conversationId) return;
    const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';
    const token = import.meta.env.VITE_API_TOKEN ?? '';
    const url = `${baseUrl}/admin/conversations/${conversationId}/stream?token=${token}`;

    let eventSource = null;
    try {
      eventSource = new EventSource(url);

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'new_message') {
            setMessages(prev => {
              // Avoid duplicates
              if (prev.some(m => m.id === data.message.id)) return prev;
              return [...prev, data.message];
            });
          }
        } catch {}
      };

      eventSource.onerror = () => {
        eventSource?.close();
        setSseFallback(true);
      };
    } catch {
      setSseFallback(true);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      setSseFallback(false);
    };
  }, [conversationId]);

  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text || replyMut.isPending) return;

    // Optimistic UI: append message immediately
    const optimistic = {
      id: `temp-${Date.now()}`,
      role: 'admin',
      sender: 'admin',
      content: text,
      timestamp: new Date().toISOString(),
      metadata: null,
    };
    setMessages(prev => [...prev, optimistic]);
    setInputText('');

    replyMut.mutate(
      { id: conversationId, text },
      {
        onError: () => {
          // Remove optimistic message on error
          setMessages(prev => prev.filter(m => m.id !== optimistic.id));
        },
        onSuccess: () => {
          // Remove optimistic temp messages on success to prevent ghost double messages
          // (onSettled will refetch and re-sync, but we clean up early to avoid flicker)
          setMessages(prev => prev.filter(m => !String(m.id).startsWith('temp-')));
        },
      }
    );
  }, [inputText, replyMut, conversationId]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleToggleBot = () => {
    toggleBotMut.mutate({ id: conversationId });
  };

  if (isLoading) {
    return (
      <div style={S.chatPanel}>
        <div style={S.loading}>Cargando mensajes...</div>
      </div>
    );
  }

  if (isError) {
    const friendlyMessage =
      error?.response?.status === 404
        ? 'Conversación no encontrada'
        : 'No se pudo cargar la conversación';
    return (
      <div style={S.chatPanel}>
        <div style={{ ...S.loading, color: 'var(--danger-500)' }}>
          {friendlyMessage}
        </div>
      </div>
    );
  }

  if (!conversation) return null;

  return (
    <div style={S.chatPanel}>
      <ChatHeader
        conversation={conversation}
        botPaused={conversation?.bot_paused ?? false}
        toggling={toggleBotMut.isPending}
        onToggleBot={handleToggleBot}
        onBack={onBack}
      />
      {sseFallback && (
        <div style={{
          padding: '4px 12px',
          fontSize: 11,
          background: '#fff3cd',
          color: '#856404',
          textAlign: 'center',
        }}>
          Conexión en tiempo real perdida — usando actualización periódica
        </div>
      )}
      <div style={S.msgArea}>
        {messages.length === 0 && (
          <div style={{
            textAlign: 'center',
            color: 'var(--fg-tertiary)',
            fontSize: 13,
            padding: 40,
          }}>
            No hay mensajes en esta conversación
          </div>
        )}
        {messages.map(msg => (
          <Message key={msg.id ?? `${msg.timestamp}-${Math.random()}`} msg={msg} />
        ))}
        <div ref={msgEndRef} />
      </div>
      <div style={S.inputBar}>
        <input
          ref={inputRef}
          style={S.input}
          placeholder="Escribí un mensaje..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={replyMut.isPending}
        />
        <button
          style={{
            ...S.sendBtn,
            ...(replyMut.isPending || !inputText.trim() ? S.sendBtnDisabled : {}),
          }}
          onClick={handleSend}
          disabled={replyMut.isPending || !inputText.trim()}
          aria-label="Enviar"
        >
          <Icon name="arrowRight" size={16} stroke={3} />
        </button>
      </div>
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export default function Chats() {
  const { data, isLoading, isError } = useConversations();
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < 769 : false
  );

  // Detect mobile via matchMedia
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = (e) => {
      setIsMobile(e.matches);
      if (!e.matches) setSidebarOpen(false);
    };
    mq.addEventListener('change', handler);
    handler(mq);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const conversations = data?.conversations ?? [];

  // Auto-select first conversation when list loads, or reset if current selection vanishes
  useEffect(() => {
    if (conversations.length === 0) {
      setSelectedId(null);
    } else if (!selectedId || !conversations.some(c => c.id === selectedId)) {
      setSelectedId(conversations[0].id);
    }
  }, [conversations]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelect = (id) => {
    setSelectedId(id);
    if (isMobile) setSidebarOpen(false);
  };

  // On mobile without a selected conversation, show the list as full-screen view
  if (isMobile && !selectedId) {
    return (
      <div style={S.container}>
        <ConversationList
          conversations={conversations}
          selectedId={selectedId}
          onSelect={handleSelect}
          search={search}
          onSearchChange={setSearch}
        />
      </div>
    );
  }

  // Mobile overlay styles for the left panel
  const mobilePanelOverlay = isMobile && sidebarOpen;

  return (
    <div style={S.container}>
      {/* Backdrop overlay on mobile when sidebar is open */}
      {mobilePanelOverlay && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 100,
            background: 'var(--bg-overlay, rgba(15,17,20,0.45))',
          }}
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Left panel — conversation list (wrapped only on mobile for slide-out) */}
      {isMobile ? (
        <div style={{
          ...S.panel,
          position: 'fixed', top: 0, left: 0, bottom: 0, zIndex: 101,
          width: 300, minWidth: 300,
          borderRight: 'none',
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 280ms cubic-bezier(0.2,0.7,0.2,1)',
          boxShadow: '0 4px 8px rgba(0,0,0,0.06), 0 12px 32px rgba(0,0,0,0.10)',
        }}>
          <ConversationList
            conversations={conversations}
            selectedId={selectedId}
            onSelect={handleSelect}
            search={search}
            onSearchChange={setSearch}
          />
        </div>
      ) : (
        <ConversationList
          conversations={conversations}
          selectedId={selectedId}
          onSelect={handleSelect}
          search={search}
          onSearchChange={setSearch}
        />
      )}

      {/* Right panel — chat view or placeholder */}
      {selectedId ? (
        <ChatView
          key={selectedId}
          conversationId={selectedId}
          onBack={isMobile && !sidebarOpen ? () => setSidebarOpen(true) : undefined}
        />
      ) : (
        <div style={S.chatPanel}>
          <div style={S.placeholder}>
            <Icon name="whatsapp" size={48} style={{ opacity: 0.3 }} />
            <span>Seleccioná una conversación para ver los mensajes</span>
          </div>
        </div>
      )}
    </div>
  );
}
