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

## Credenciales de prueba
Ver /app/memory/test_credentials.md (admin@watchful.app / Watchful2026!).
