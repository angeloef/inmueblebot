# ViviendApp — Web (Next.js 15)

Frontend SaaS de ViviendApp: landing, auth, y panel de control para inmobiliarias.

## Desarrollo local

```bash
cd web
cp .env.local.example .env.local
# Editá .env.local con tus valores
npm install
npm run dev
```

Abre [http://localhost:3000](http://localhost:3000).

## Deploy en Render

El archivo `render.yaml` en la raíz del monorepo configura el servicio automáticamente.
El `rootDir` es `web/`, por lo que Render ejecuta `npm install && npm run build` desde ese directorio.

## NOTA importante: backend inmueblebot-api

Después de crear el servicio en Render, **configurá la variable `PUBLIC_APP_URL`** en el backend `inmueblebot-api` con la URL del web (ej: `https://viviendapp-web.onrender.com`). Esto es necesario para:
- Links en emails transaccionales (verificación, reset de contraseña)
- Configuración de CORS en la API
