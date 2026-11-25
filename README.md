# Here are your Instructions

## Tour virtual

El montaje automático usa un modelo de visión compatible con `/chat/completions` de OpenAI y salida JSON. Configura estas variables en el backend de Emergent.

- `TOUR_AI_BASE_URL` contiene la URL base del proveedor, incluido `/v1` cuando corresponda.
- `TOUR_AI_MODEL` contiene el identificador del modelo de visión.
- `TOUR_AI_API_KEY` contiene la clave del proveedor y debe guardarse como secreto.

El modelo analiza vistas reducidas. El HTML descargado incluye todas las panorámicas y funciona sin servidor en un navegador con WebGL. La edición se mantiene mientras la herramienta está abierta.
