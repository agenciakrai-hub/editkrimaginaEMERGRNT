# Manual editor and HDR studio

Imported and adapted from agenciakrai-hub/edit-krimagina, reference ffef538. Routes: /app/manual and /app/hdr. Dashboard access is independent from the existing property editor. No Base44 backend or SDK is used. Saves create new property photos; existing source paths and histories remain unchanged.

HDR groups 3 or 5 consecutive files in natural filename order; incomplete groups are rejected. All exposures must show the same scene and aspect ratio. RAW files use their embedded JPEG preview when present; unsupported files report a decode error. Processing runs in a browser worker, with a maximum output edge of 2400 px.

Optional manual segmentation and HDR finishing use only the assigned KRAI image model (inherit Mejora Pro when unassigned). Assistance costs 1 credit for non-owner accounts; failed operations refund it. Selected-provider failures do not fall back to another service.

Video keeps the existing montage when unassigned. An assigned video-capable KRAI model is called via the gateway video_generation task, then its inline MP4 artifacts are assembled by the existing montage. An unavailable/invalid result fails and refunds the job; URL-only artifacts are not accepted. Actual video generation requires a KRAI model advertising video capability.

Checks: PYTHONPATH=backend /root/.venv/bin/python -m pytest backend/tests/test_studio_tools.py -q; node frontend/tests/studio_algorithms.cjs; CI=false yarn build (frontend).
