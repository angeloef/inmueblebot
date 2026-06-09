# ViviendApp — Web (Next.js 15)

Frontend SaaS de ViviendApp: landing pública, autenticación (login/signup) y panel
placeholder. Consume la API FastAPI (`inmueblebot-api`) vía route handlers server-side.

- **Stack:** Next.js 15 (App Router) · TypeScript · Tailwind v3 · Node ≥ 20
- **Auth:** el JWT nunca llega al browser. Las credenciales pasan por `/api/auth/*`
  (server-side) que setean cookies **httpOnly + Secure (prod) + SameSite=Lax**.

---

## 1. Desarrollo local

```bash
cd web
cp .env.local.example .env.local     # editá los valores si hace falta
npm install
npm run dev                          # http://localhost:3000
```

Requiere el backend corriendo (por defecto `http://localhost:8000`). Para que el
login/signup funcionen, el backend debe tener la **migración de la Fase 1 aplicada**
(`alembic upgrade head` → tablas `tenant_accounts` y `subscriptions`).

---

## 2. Deploy en Render (paso a paso)

> ⚠️ **No uses Blueprint.** El `render.yaml` de este repo está en `web/`, no en la raíz
> (la raíz es el backend Python). Render solo auto-detecta Blueprints en la raíz del repo.
> Creá el servicio **a mano**; `web/render.yaml` queda como **referencia** de la config.

### 2.1 — Prerrequisito en el backend (`inmueblebot-api`)

Antes de levantar el web, el backend debe estar al día con la Fase 1:

1. Que el backend esté redeployado con el código de la Fase 1 (rama `main`).
2. Correr la migración: `alembic upgrade head` (crea `tenant_accounts` + `subscriptions`).
3. Tener seteadas en el backend: `SECRET_KEY` (fuerte, **no** el default), `RESEND_API_KEY`
   (opcional — sin ella los emails se omiten), `TRIAL_DAYS` (default 14).

Sin esto, el web carga pero el login/signup devuelven error.

### 2.2 — Crear el Web Service

En el dashboard de Render: **New → Web Service → conectá este repo**. Configurá:

| Campo | Valor |
|---|---|
| **Name** | `viviendapp-web` |
| **Language / Runtime** | Node |
| **Branch** | `main` |
| **Root Directory** | `web` |
| **Build Command** | `npm install && npm run build` |
| **Start Command** | `npm start` |
| **Plan** | Free (o el que prefieras) |

### 2.3 — Variables de entorno

Cargá estas en la sección **Environment** del servicio:

| Key | Value | Notas |
|---|---|---|
| `NODE_VERSION` | `20.18.0` | Next 15 necesita Node ≥ 20 |
| `NEXT_PUBLIC_API_URL` | `https://inmueblebot-api.onrender.com` | URL pública del backend |
| `API_URL` | `https://inmueblebot-api.onrender.com` | igual (uso server-side) |
| `NEXT_PUBLIC_SITE_URL` | `https://viviendapp-web.onrender.com` | la URL de **este** servicio (para SEO/OG) |
| `NEXT_PUBLIC_DASHBOARD_URL` | `http://localhost:5173` | **placeholder** — se cambia en la Fase 4 |

> Las `NEXT_PUBLIC_*` se "hornean" en el build. Si cambiás alguna después del primer
> deploy (p.ej. `NEXT_PUBLIC_SITE_URL`), hacé un **Manual Deploy → Clear build cache & deploy**
> para que tome efecto.

### 2.4 — Conectar el web con el backend (CORS + emails)

Una vez que el web tenga su URL pública, en el backend `inmueblebot-api` seteá:

```
PUBLIC_APP_URL=https://viviendapp-web.onrender.com
```

Esto hace dos cosas: (a) los links de los emails (verificación, reset de contraseña)
apuntan al web, y (b) el origen queda permitido por CORS (el backend ya incluye
`PUBLIC_APP_URL` en la lista de orígenes; no hay que tocar código Python).

---

## 3. Verificación post-deploy

1. Abrí la URL del web → la landing carga con la marca (azul `#164a71`, mockup WhatsApp).
2. `/signup` → crear una cuenta de prueba → deberías quedar logueado (cookie
   `vivienda_access` **httpOnly** en DevTools → Application → Cookies; **no** en localStorage).
3. `/login` con credenciales malas → "Email o contraseña incorrectos".
4. Network tab: ninguna llamada del browser va directo al backend — todo pasa por
   `/api/auth/*` del mismo origen.

---

## 4. Notas

- **Camino A:** el dashboard real sigue siendo la app Vite (otro servicio). El redirect
  post-login al dashboard es un **placeholder** (`NEXT_PUBLIC_DASHBOARD_URL`) hasta la Fase 4.
- **Pricing / checkout:** la sección de precios linkea a `/signup` (trial 14 días). El pago
  con MercadoPago es la **Fase 3**.
- **Onboarding de WhatsApp:** el paso "Conectá tu WhatsApp" post-signup es informativo
  (placeholder) hasta tener la aprobación de Meta Tech Provider (Fase 5).
