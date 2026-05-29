# Notification Icons — Design Handoff

Brief for redesigning the dashboard's notification icons to match the existing design system.
Your job: **read the current icons below (how they look + what each one means), then decide the
new icon + treatment from the design system.** This doc only describes the current state — it does
not prescribe the new design.

## Where they live

- **Icon map:** `dashboard/src/Shell.jsx` → `TYPE_ICON` (lines ~69–79)
- **Render site:** `dashboard/src/Shell.jsx` → `NotificationPanel`, `<span className="notif-icon">{TYPE_ICON[n.type] ?? '🔔'}</span>` (line ~135)
- **Styling:** `dashboard/styles.css` → `.notif-icon { font-size: 18px; flex-shrink: 0; line-height: 1.4; }` (line ~451)
- **Type source of truth + trigger text (backend):** `app/services/notification_service.py` → `class NotifType` and the per-type `create(...)` calls (lines ~11–147)

## Current state (the problem)

Notification icons are **raw emoji** rendered as text in a 18px `.notif-icon` span. They don't match
the rest of the dashboard, which uses a consistent custom SVG icon set, and as text they can't inherit
color, stroke weight, or sizing from the design tokens.

## The 8 current icons — how they look and what they do

Each row is one notification type. "Looks like" = the literal emoji glyph rendered today. "Means /
fires when" = the dashboard title and the event that creates it (from `notification_service.py`).

| Type (`n.type`)      | Looks like (current emoji)        | Dashboard title                      | Means / fires when |
|----------------------|-----------------------------------|--------------------------------------|--------------------|
| `visit_scheduled`    | 📅 calendar page                  | "Nueva visita agendada"              | A property visit was booked (property + date/time + client). |
| `visit_rescheduled`  | 🔄 two arrows in a circle         | "Visita reprogramada"                | An existing visit was moved to a new date/time. |
| `visit_cancelled`    | ❌ red cross mark                 | "Visita cancelada"                   | A visit was cancelled (optionally with a reason). |
| `call_scheduled`     | 📞 telephone receiver             | "Nueva llamada agendada"             | A phone call with the client was booked for a date/time. |
| `handoff_requested`  | 🚨 red rotating siren light       | "Cliente solicita atención humana"   | The client asked to talk to a human agent (bot hands off). High priority. |
| `new_lead`           | 👤 bust / single person           | "Nuevo cliente registrado"           | A brand-new contact wrote for the first time. |
| `lead_qualified`     | ⭐ star                           | "Lead calificado"                    | A lead reached a qualifying score (shows name + score). |
| `bot_error`          | ⚠️ warning triangle               | "Error del bot"                      | The bot hit an error while handling a client (shows error summary). |
| *(fallback)*         | 🔔 bell                           | —                                    | Any unknown/unmapped type defaults to this. |

Notes on appearance/behavior:
- All 8 sit in the same slot, all at 18px, no background — so today they read as a mixed bag of
  multicolor emoji (some are inherently red like ❌/🚨/⚠️, others flat like 📅/📞).
- A notification row also has read/unread states: unread rows get an accent-tinted background
  (`.notif-item.unread`), and there's an unread count badge in the panel header and on the topbar bell.

## The design system to match (target, your call on specifics)

Icons elsewhere use the `Icon` component in `dashboard/src/Primitives.jsx`:

```jsx
<Icon name="calendar" size={16} />
```

- Inline SVG, **Feather/Lucide style**: `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, round caps/joins.
- Color is inherited via `currentColor` — drive it with CSS `color` or a token.
- Names already available include: `calendar`, `refresh`, `x`, `phone`, `user`, `users`, `star`, `bell`, `info`, `clock`, `mail`, `activity`, `check`, `mapPin`. Full set is in `Primitives.jsx`.
- Semantic color tokens used across the app: `--accent-500/-50`, `--danger-500`, `--success-500`, `--info-500` (see `tokens.css` / `styles.css`).
- If a type needs a glyph the set doesn't have yet, add a new path to the `Icon` component rather than
  falling back to an emoji.

You decide the final icon-per-type, color treatment, sizing, and whether to wrap them in a colored
badge/circle — guided by the design system above.
