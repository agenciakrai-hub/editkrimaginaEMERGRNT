# Watchful — PRD

## Problema original
Plataforma web/PWA en español para que agentes, agencias y fotógrafos inmobiliarios editen fotos de inmuebles con IA y generen videos-tour. Organización por "Propiedad/Listing". Edición esencial gratis; ediciones avanzadas y video con créditos.

## User choices (esta entrega)
- Alcance: Fase 1 + Fase 2
- Auth: Ambas (JWT email/password + Google gestionado por Emergent)
- IA de imagen: Gemini Nano Banana (`gemini-3.1-flash-image-preview`) vía Emergent Universal Key (defaults)
- Stripe/créditos de pago: fase posterior (defaults)
- Video-tour + emails: fase posterior (defaults)

## Arquitectura
- Frontend: React + Tailwind + shadcn/ui + framer-motion. Tema oscuro violeta-cyan. PWA (manifest).
- Backend: FastAPI. Módulos: server.py (rutas), auth.py (JWT + sesiones), storage.py (object storage), ai_edit.py (catálogo de acciones + Gemini).
- DB: MongoDB — colecciones users, user_sessions, properties, photos, jobs.
- Almacenamiento: Emergent Object Storage (originales en watchful/uploads, resultados en watchful/edits).
- Auth: JWT (cookie access_token + Bearer) y Google Emergent (session_token). Resolver prioriza Authorization header.

## Personas
- Agente inmobiliario individual.
- Agencia / equipo (roles — pendiente fase 5).
- Fotógrafo de inmuebles.

## Requisitos core (estáticos)
- Propiedad como proyecto que agrupa fotos/ediciones.
- Ediciones IA: cielo, luz/HDR, enderezar (gratis); twilight, declutter, césped, window pull, staging, upscale (créditos).
- Comparador antes/después con slider.
- Procesamiento por lotes con progreso.
- Contador de créditos siempre visible; coste antes de confirmar.
- Etiqueta de divulgación "Imagen editada digitalmente" (por defecto en staging).
- 30 créditos gratis al registrarse.

## Implementado (2026-06)
- [x] Auth JWT (registro/login/me/logout) + Google Emergent (session) — 2026-06
- [x] Modelo Propiedad: crear/listar/ver/eliminar (scoping por usuario) — 2026-06
- [x] Subida de fotos (multipart, jpg/png/webp, máx 25MB) a object storage + servido autenticado — 2026-06
- [x] Catálogo de 9 acciones IA con costes (GET /api/actions) — 2026-06
- [x] Edición individual con Gemini Nano Banana + deducción/reembolso de créditos — 2026-06
- [x] Comparador antes/después (original vs current_path) en editor y landing — 2026-06
- [x] Procesamiento por lotes asíncrono con job + polling de progreso + reembolso por fallo — 2026-06
- [x] Etiqueta de divulgación + toggle en staging/twilight — 2026-06
- [x] Revertir foto al original; descarga del resultado — 2026-06
- [x] Landing marketing, dashboard, property view, editor full-screen — 2026-06
- Testing: backend 16/16 pytest, frontend flujo crítico 100% (iteration_1).

## Iteración 2 (2026-06)
- [x] Video-tour 16:9 y Reel vertical 9:16 desde fotos (ffmpeg: Ken Burns, fundidos, música ambiente, portada con nombre de agencia); costes tour=12/reel=8 créditos, reembolso si falla
- [x] Compra de créditos con Stripe (paquetes 100/300/1.000 €) — checkout + status + webhook idempotente; sandbox Flow A (ES, tax full)
- [x] Mejora automática: acción "auto" gratis en un clic (una pasada de IA con todas las mejoras esenciales); también disponible en modo lote
- [x] Subida robusta: cada foto en su propia petición + optimización en navegador (máx 2560px) → soluciona error 413
- [x] Conversión HEIC/HEIF y RAW en el servidor (pillow-heif + rawpy) a JPEG optimizado; límite 60MB/archivo
- [x] CORS listo para producción (refleja cualquier origen con credenciales) — deployment check PASS
- Testing iteración 2: backend 10/10 pytest, frontend video+pagos OK (iteration_2). HEIC verificado por conversión e2e.

## Backlog priorizado
### P0 (próximo)
- Video-tour automático (Ken Burns + transiciones + música) y reel vertical desde fotos aprobadas.
- Créditos de pago con Stripe (paquetes) + bloqueo/compra al quedarse sin créditos.

### P1
- Presets de exportación por portal (Idealista, Fotocasa, Zillow, MLS) con tamaños.
- Marca de agua / logo de agencia; presets de estilo guardados.
- Cuentas de agencia / equipo con roles.
- Emails (Resend/SendGrid): aviso de trabajo listo + enlaces compartibles.

### P2
- Conversión HEIC/RAW en subida.
- Filtro de moderación de contenido.
- Descripción del anuncio con IA; detección de estancias; tour 360°.
- App nativa React + TypeScript.

## Iteración 3 — Panel de administrador (2026-06)
- [x] Panel admin en `/app/admin`, visible SOLO para super-admin (SUPER_ADMIN_EMAIL=krimagina2025@gmail.com). Gate en frontend (redirige) y backend (403).
- [x] Sección 1 — Usuarios y planes: CRUD de planes de suscripción (nombre, precio, créditos, periodo, características, destacado, activo). Los planes activos se sincronizan en la landing pública (GET /api/plans → pricing-section). Lista de usuarios con plan/vencimiento/créditos y asignación manual de plan (con concesión de créditos, sin apilar al reasignar el mismo plan).
- [x] Sección 2 — Consumo por usuario: registro `usage_events` desde ahora (créditos foto vs vídeo + llamadas reales a Gemini; lote de N = N llamadas). Consumo propio del admin separado + totales del resto + tabla por usuario.
- [x] Sección 3 — Proveedores IA: alta de proveedores (OpenAI-compatible / fal.ai / custom) con URL+key; detección de modelos vía /models (curado para fal), estado válido/sin créditos/clave inválida. Toggles Foto/Vídeo por modelo (Vídeo = "próximamente"). Override de motor por herramienta: cada herramienta de foto puede usar un proveedor+modelo asignado en lugar de Gemini Nano Banana, con vuelta al modelo por defecto. Borrar proveedor limpia sus overrides.
- Backend nuevos módulos: `admin.py` (rutas), `providers.py` (adaptadores IA). server.py: is_super_admin, log_usage, get_tool_override, enrutado en `_apply_edit`.
- Testing iteración 3: backend 10/10 pytest + frontend 100% (iteration_7).

## Calidad de edición IA (2026-06)
- [x] Anti-alucinación: prompts estrictos (la "Mejora automática" ya no inventa ventanas/cielos; herramientas de ajuste no añaden/quitan objetos; las de contenido preservan la arquitectura). `ai_edit.py` GEO_GUARD/STRICT_GUARD.
- [x] Resolución client-ready: `imaging.finalize_edit()` sube la salida de Nano Banana (~1024px) a la resolución del original (hasta 2560px) con Lanczos + unsharp y entrega JPEG calidad 95 (≈4-6× más píxeles). Aplicado en `server._apply_edit` (motor por defecto y proveedores).
- [x] Fiabilidad: motor principal `gemini-3.1-flash-image-preview` (rápido, ~8s, probado en prod) con **respaldo automático a `gemini-3-pro-image-preview`** si falla, + timeout controlado (`AI_EDIT_TIMEOUT`). Configurable con env `AI_IMAGE_MODEL` / `AI_IMAGE_FALLBACK_MODEL`.
- Nota: todas las ediciones IA se pagan del saldo de la Universal Key (EMERGENT_LLM_KEY). Si en prod fallan tras republicar, recargar saldo.

## Rebrand (2026-06)
- [x] App renombrada a "edit KRimagina" en título del navegador, meta, manifest PWA, login, header, footer y nombre de descarga. Logo (KR) añadido como badge en el componente Logo (`/app/frontend/public/logo-krimagina.jpg`) + favicon/apple-touch-icon.

### Pendiente de esta línea (backlog)
- Checkout de suscripción recurrente con Stripe (los planes hoy se asignan manualmente).
- IA imagen-a-vídeo real para el toggle "Vídeo" de proveedores (hoy vídeo = ffmpeg local).

## Credenciales de prueba
Ver /app/memory/test_credentials.md (admin@watchful.app / Watchful2026!).
