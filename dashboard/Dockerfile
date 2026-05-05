# =============================================================================
# Dashboard — Multi-stage Dockerfile
#
# Stage 1 (builder): Node.js compila el código React → archivos estáticos
# Stage 2 (runtime): Nginx sirve esos archivos y hace proxy de /api → FastAPI
#
# Por qué multi-stage:
#   El builder necesita Node + todas las dev-dependencies (~500 MB).
#   El runtime solo necesita los archivos compilados + Nginx (~25 MB).
#   La imagen final no contiene Node en absoluto.
# =============================================================================

# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copiamos package*.json ANTES que el código fuente.
# Docker cachea cada instrucción como una capa. Si solo cambia src/App.jsx
# pero no el package.json, Docker reutiliza la capa del npm ci (evita
# reinstalar ~200 paquetes en cada rebuild → mucho más rápido).
COPY package*.json ./
RUN npm ci --silent

# Ahora copiamos el resto del código
COPY . .

# Variables de entorno de Vite (VITE_*) se leen en tiempo de BUILD, no runtime.
# Vite las "hornea" dentro del JS compilado. Por eso las pasamos como ARG.
# ARG = variable disponible solo durante el build.
# ENV = la expone también a los comandos RUN.
ARG VITE_API_BASE_URL=/api
ARG VITE_API_TOKEN
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_TOKEN=$VITE_API_TOKEN

RUN npm run build
# Resultado: /app/dist/ con index.html + assets/ (JS/CSS minificados)


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copiamos SOLO los archivos compilados del stage anterior.
# Node.js, npm, y todo el código fuente quedan fuera de la imagen final.
COPY --from=builder /app/dist /usr/share/nginx/html

# Nuestra configuración de Nginx (SPA routing + proxy a la API)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# nginx -g 'daemon off;' → corre Nginx en primer plano (necesario en Docker:
# el container vive mientras el proceso PID 1 esté corriendo)
CMD ["nginx", "-g", "daemon off;"]
