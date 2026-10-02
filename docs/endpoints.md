# Contratos HTTP

Base: `/api/v1`. Todos los endpoints de esta base requieren `Authorization: Bearer <API_TOKEN>`. IDs son UUID. FastAPI genera los esquemas exactos en `/openapi.json` y `/docs`.

| Método y ruta | Resultado |
|---|---|
| `GET /health` | Sin token; API/PostgreSQL/Redis, `200` o `503`. |
| `GET /api/v1/instances` | Lista de instancias persistidas. |
| `GET /api/v1/instances/{id}` | Información de una instancia. |
| `GET /api/v1/instances/{id}/status` | Estado persistido y fecha. |
| `GET /api/v1/instances/{id}/health` | Última comprobación del worker, fecha, `stale` y `busy`. |
| `POST /api/v1/media` | `201`, copia validada de archivo compartido. |
| `GET /api/v1/media/{id}` | MIME, SHA-256, nombre, tamaño, tipo y fecha. |
| `POST /api/v1/instances/{id}/messages` | `202`, mensaje y outbox; no toca Android. Replay: `200`. |
| `GET /api/v1/messages/{id}` | Contenido, estado, intentos, error, timestamps y evidencia. |
| `GET /api/v1/instances/{id}/screenshot` | PNG delegado al worker; solo con debug habilitado. |
| `GET /api/v1/instances/{id}/activity` | Activity delegada al worker; solo con debug habilitado. |
| `GET /metrics` | Métricas Prometheus; requiere token. |

## Registrar archivos

```json
{"filename":"informe.pdf","type":"document"}
```

Solo basename, archivo regular y contenido completo. No hay subida HTTP, descarga URL, listado de carpetas ni rutas arbitrarias. Respuesta `MediaView` contiene `id`, usado como `media_id` en mensajes. No devuelve rutas internas.

## Crear mensajes

```json
{"to":"+5491112345678","text":"Mensaje de prueba"}
```

```json
{"to":"+5491112345678","type":"document","media_id":"uuid","text":"Documento de prueba"}
```

Tipos: `text` (predeterminado), `image`, `document`, `audio`, `video`. Un adjunto por mensaje. `media_id` es obligatorio para adjuntos e inválido para texto. Audio no acepta `text`. Destinatario E.164, sin normalización implícita. Propiedades adicionales se rechazan.

Header opcional `Idempotency-Key`: 1–200 caracteres, al menos uno no blanco. Unicidad `(instance_id, key)`; se compara el payload normalizado completo, incluido `media_id`. Dos registros distintos del mismo archivo son dos referencias distintas. La clave se conserva con el mensaje y no expira automáticamente.

Estados: `QUEUED → PROCESSING → SENT/FAILED`; errores recuperables anteriores al marcador pueden volver a `QUEUED`. `SENT/FAILED` son terminales. `SEND_OUTCOME_UNKNOWN` siempre implica revisión manual.

## Salud y debug

La API nunca crea sesiones Appium ni ejecuta ADB. El dispatcher agenda health cada 60 s. La respuesta incluye `checked_at`; `stale=true` si no hay resultado o tiene más de dos intervalos. Durante `BUSY`, se conserva la comprobación anterior. No interpretar una respuesta HTTP `200` del endpoint de instancia como readiness.

Checks: disponibilidad ADB, dispositivo visible, arranque completo, Appium accesible, paquete instalado, UI ejecutable y estado WhatsApp. `WHATSAPP_READY` solo procede de una UI reconocida y configurada. Instancias: `OFFLINE`, `BOOTING`, `ONLINE`, `WHATSAPP_READY`, `BUSY`, `ERROR`.

Debug deshabilitado: rutas ausentes (`404`). Habilitado: token obligatorio, lock común, `409` si ocupado y `503` por timeout/error. La solicitud vence en 10 s y el worker no ejecuta capturas tardías de solicitudes expiradas. No hay shell HTTP.

## Errores y métricas

Errores de dominio: `{"detail":{"code":"..."}}`. Validaciones: `422`. Ausentes: `404`. Conflicto de clave/instancia ocupada: `409`. Límite de archivo: `413`. Dependencia indisponible: `503`.

Errores de mensajes incluyen `WHATSAPP_NOT_INSTALLED`, `WHATSAPP_NOT_CONFIGURED`, `RECIPIENT_NOT_ON_WHATSAPP`, `INPUT_VERIFICATION_FAILED`, `UI_STATE_TIMEOUT`, `SELECTOR_AMBIGUOUS`, `MEDIA_INTEGRITY_ERROR`, `RETRY_EXHAUSTED`, `SEND_OUTCOME_UNKNOWN`. Nunca se devuelve el stack crudo del driver.

Métricas derivadas de PostgreSQL: `messages_queued` (gauge), `messages_sent` y `messages_failed` (counter mientras se conserva el historial), `automation_duration_seconds` (summary count/sum) e `instance_status{instance_id,status}`. No incluyen números de teléfono ni contenido.
