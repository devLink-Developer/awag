# Android WhatsApp Automation Gateway

MVP de laboratorio/QA para controlar la aplicación oficial de WhatsApp mediante ADB, Appium y UiAutomator2. Envía texto, imágenes, documentos, archivos de audio y video, con un adjunto por trabajo. Registro, OTP e instalación de WhatsApp son manuales.

## Arquitectura

```text
Cliente REST → FastAPI → PostgreSQL: Message + Outbox
                                  ↓
                             Dispatcher → Redis/Celery → Worker
                                                           ↓
                                                     Appium + ADB
                                                           ↓
                                            AVD persistente / WhatsApp oficial
```

Docker ejecuta API, worker, dispatcher, PostgreSQL, Redis y Appium. Ubuntu ejecuta KVM, Android SDK, el servidor ADB y el emulador. API/worker/Appium comparten la red del host Linux; Appium, ADB y los puertos publicados de almacenamiento son accesibles solo por loopback. Por eso `.env` usa `http://127.0.0.1:4723`, en lugar del DNS `appium` de una red bridge.

El AVD se ejecuta fuera de Docker en el despliegue con KVM. Para el MVP sin aceleración existe un [perfil experimental en Docker](docs/software-emulation.md), con almacenamiento persistente y plazos ampliados. La imagen Appium contiene el binario SDK del emulador para sus diagnósticos, pero no inicia otro AVD. Appium habilita únicamente `*:session_discovery`, necesario para recuperar sesiones abandonadas mediante `/appium/sessions`; no habilita shell remoto. API escucha en `127.0.0.1:8000`; para acceder desde otro equipo:

```bash
ssh -L 8000:127.0.0.1:8000 usuario@servidor-ubuntu
```

## Estructura

```text
.
├── app/
│   ├── api/           # autenticación, contratos REST y debug delegado
│   ├── automation/    # adb.py, appium.py, whatsapp.py, selectors.py, verification.py
│   ├── config/        # configuración validada
│   ├── events/        # dispatcher y recuperación outbox
│   ├── instances/     # alta inicial persistente
│   ├── messages/      # creación e idempotencia transaccional
│   ├── models/        # Instance, Message, Media, Outbox
│   ├── schemas/       # validación y respuestas públicas
│   ├── services/      # base de datos, archivos, errores y logs JSON
│   ├── workers/       # tareas, locks y procesamiento
│   └── main.py
├── docker/            # imágenes backend, Appium, emulador y unidad swap
├── migrations/        # esquema inicial Alembic
├── scripts/           # instalación, arranque, fixtures, tests y E2E
├── tests/             # unitarias, PostgreSQL/Redis y E2E opt-in
├── docs/              # endpoints, operación y resultados de verificación
├── docker-compose.yml
├── docker-compose.habitmundo.yml
├── docker-compose.software-emulator.yml
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── constraints.txt
└── README.md
```

## Instalación en Ubuntu

Destino: Ubuntu 24.04, CPU x86_64 con virtualización habilitada y acceso a `/dev/kvm`. Ejecutar desde la raíz del proyecto. Los instaladores usan `sudo` para paquetes y grupos.

```bash
bash scripts/setup-ubuntu.sh
bash scripts/setup-docker.sh
```

Cerrar sesión y volver a entrar para activar los grupos `kvm` y `docker`. Comprobar:

```bash
kvm-ok
docker compose version
python3 -m venv .venv
source .venv/bin/activate
pip install -c constraints.txt -r requirements-dev.txt
python scripts/generate-env.py
bash scripts/setup-android.sh
```

`generate-env.py` crea secretos aleatorios sin imprimirlos y no reemplaza `.env`. El SDK se instala en `~/.local/share/whatsapp-gateway/sdk`; el AVD en `~/.local/share/whatsapp-gateway/avd`. `setup-android.sh` solicita aceptación manual de licencias SDK y no reemplaza un AVD existente.

ADB está fijado a **37.0.1** tanto en host como contenedores para evitar reinicios del servidor por incompatibilidad de versiones. Las imágenes usan Python 3.12, Node 22, Appium 3.8.0 y UiAutomator2 8.7.0. Las versiones Python están fijadas en requirements y constraints.

### Iniciar Android e instalar WhatsApp manualmente

En una terminal Ubuntu con escritorio:

```bash
bash scripts/start-emulator.sh
```

El script mantiene el proceso en primer plano, comprueba KVM y espera `sys.boot_completed=1`. Para ejecuciones posteriores sin ventana: `bash scripts/start-emulator.sh --headless`. No emplea `-wipe-data`, no borra `/data` y desactiva snapshots conservando `userdata-qemu.img`.

Para arrancar explícitamente sin KVM usar `EMULATOR_ACCEL_MODE=off` y seguir [el procedimiento del MVP software](docs/software-emulation.md). La comprobación de KVM sigue activa por defecto; el perfil software usa un plazo de arranque de 1800 segundos y limita recursos.

Si el puerto 5554 está ocupado, usar un puerto par disponible y su puerto siguiente para ADB. Por ejemplo: `EMULATOR_PORT=5556 bash scripts/start-emulator.sh`. En ese caso, configurar `ADB_SERIAL=emulator-5556` en `.env` y reemplazar `emulator-5554` por `emulator-5556` en los comandos siguientes. El script acepta puertos pares entre 5554 y 5682.

En otra terminal:

```bash
export ANDROID_HOME="$HOME/.local/share/whatsapp-gateway/sdk"
export ANDROID_AVD_HOME="$HOME/.local/share/whatsapp-gateway/avd"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
adb -s emulator-5554 get-state
adb -s emulator-5554 shell getprop sys.boot_completed
```

Obtener el APK desde [WhatsApp para Android](https://www.whatsapp.com/android), guardarlo como `~/Downloads/WhatsApp.apk` y ejecutar:

```bash
adb -s emulator-5554 install "$HOME/Downloads/WhatsApp.apk"
```

Abrir WhatsApp en la ventana del emulador. Completar personalmente registro, verificación y permisos. Configurar el idioma de Android y WhatsApp en español; dejar `UI_LANGUAGE=es`. Para inglés, configurar ambos manualmente y cambiar `.env` a `UI_LANGUAGE=en`. No hay scripts de OTP, registro ni bypass.

El gateway reconoce instalación ausente, registro pendiente y UI preparada. No controla que WhatsApp acepte el registro manual en el AVD; ese paso debe completarse antes de la aceptación E2E. Mantener worker/dispatcher detenidos durante el registro o cambios manuales de idioma.

### Iniciar servicios

Después de configurar WhatsApp:

```bash
bash scripts/start-services.sh
```

El script valida Compose, construye imágenes, inicia almacenamiento/Appium, aplica migraciones, registra la instancia y levanta API/worker/dispatcher. Los comandos individuales son:

```bash
docker compose build
docker compose up -d --wait postgres redis appium
docker compose run --rm --no-deps gateway-api python -m alembic upgrade head
docker compose run --rm --no-deps gateway-api python -m scripts.bootstrap_instance
docker compose up -d gateway-api worker dispatcher
curl --fail http://127.0.0.1:8000/health
```

OpenAPI: `http://127.0.0.1:8000/openapi.json`. Documentación interactiva: `http://127.0.0.1:8000/docs`; usar **Authorize** con el token local.

## Enviar texto y adjuntos

Cargar las variables de la configuración local en una terminal Bash y obtener el UUID:

```bash
set -a
source .env
set +a
INSTANCE_ID=$(curl --fail --silent -H "Authorization: Bearer $API_TOKEN" \
  http://127.0.0.1:8000/api/v1/instances | python -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
```

Texto:

```bash
curl --fail -X POST "http://127.0.0.1:8000/api/v1/instances/$INSTANCE_ID/messages" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: laboratorio-texto-001' \
  -d '{"to":"+5491112345678","text":"Mensaje de prueba"}'
```

Reemplazar el destinatario por el número del laboratorio. La respuesta es `202 {"id":"uuid","status":"QUEUED"}`. Consultar `/api/v1/messages/{uuid}` para el resultado.

La carpeta compartida del host es `data/incoming` por defecto. Publicar archivos completos mediante un rename atómico; no modificarlos mientras se registran. La API recibe solamente nombres de archivo. Registra una copia independiente en `/data/media` y no descarga URLs ni acepta rutas.

```bash
# Depositar previamente foto.png en data/incoming.
MEDIA_ID=$(curl --fail --silent -X POST http://127.0.0.1:8000/api/v1/media \
  -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"filename":"foto.png","type":"image"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

python -c 'import json,sys; print(json.dumps({"to":sys.argv[1],"type":"image","media_id":sys.argv[2],"text":"Foto de prueba"}))' \
  '+5491112345678' "$MEDIA_ID" \
  | curl --fail -X POST "http://127.0.0.1:8000/api/v1/instances/$INSTANCE_ID/messages" \
      -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
      -H 'Idempotency-Key: laboratorio-imagen-001' --data-binary @-
```

Cambiar `type` a `document`, `audio` o `video` al registrar y enviar otros archivos. Texto puro: hasta 4096 caracteres. Pies de imagen/documento/video: hasta 1024. Audio no acepta `text` y se envía como archivo de audio, no como nota de voz.

| Tipo | Formatos admitidos | Límite predeterminado |
|---|---|---|
| Imagen | JPEG, PNG verificados | 10 MiB |
| Documento | Archivo regular de contenido genérico | 100 MiB |
| Audio | MP3, M4A, OGG verificados con ffprobe | 16 MiB |
| Video | MP4, H.264, audio AAC si existe | 16 MiB |

Son límites configurables del gateway. No se convierten formatos. El nombre original del documento se conserva; imágenes/audio/video se transfieren con nombres internos únicos para identificar el archivo en Android.

## Pruebas

La lógica de negocio se prueba sin Android. SQLite se usa únicamente para pruebas unitarias; las pruebas de concurrencia, migraciones y locks usan PostgreSQL y Redis reales.

```bash
source .venv/bin/activate
pytest -q -m 'not integration and not e2e'
ruff check .
bash scripts/test-integration.sh
```

En Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration and not e2e'
powershell -ExecutionPolicy Bypass -File scripts/test-integration.ps1
```

Los scripts de integración crean servicios dedicados en `55432/56379`, credenciales temporales y esquemas aislados; al terminar eliminan solamente los recursos Compose de `whatsapp-gateway-tests`. No usar ese nombre de proyecto para otros servicios. El E2E no se ejecuta por defecto.

### E2E real, español e inglés

Verificar primero `/api/v1/instances/{id}/health`: debe indicar `WHATSAPP_READY`, `stale=false` y el idioma configurado. Generar archivos propios de prueba:

```bash
python -m scripts.make_fixtures data/incoming
python -m scripts.e2e --to '+5491112345678' --language es
```

Esta prueba envía **seis mensajes reales**: dos textos idénticos, imagen, documento, audio y video. Repite cada POST con su misma clave para comprobar idempotencia y espera los estados reales del worker. Se detiene al primer fallo; conserva un informe exitoso en `artifacts/e2e-*.json`.

Repetir en inglés: detener worker/dispatcher, cambiar manualmente idioma de Android/WhatsApp y `UI_LANGUAGE=en`, recrear los servicios y esperar un health fresco antes de ejecutar `--language en`:

```bash
docker compose stop worker dispatcher
# Cambiar idiomas y .env manualmente.
docker compose up -d --force-recreate worker dispatcher gateway-api
python -m scripts.e2e --to '+5491112345678' --language en
```

La verificación requiere una nueva burbuja saliente del contenido esperado con indicador Sent/Delivered/Read o su equivalente español, sin reloj ni progreso pendiente. `SENT` confirma envío observado, no entrega al destinatario. Un layout desconocido o una confirmación ambigua producen fallo; un clic no es suficiente.

## Recuperación, evidencia y límites

- Mensaje y outbox se crean juntos; la publicación puede repetirse sin repetir un mensaje terminal. El dispatcher recupera trabajos publicados sin resultado después del umbral de 360 segundos.
- Claves HTTP tienen unicidad por instancia y payload. Una repetición compatible devuelve `200` con el mismo UUID y estado actual; un payload distinto devuelve `409`. Sin clave, cada POST crea un mensaje nuevo.
- Redis usa token, TTL y renovación; un advisory lock PostgreSQL permanece en una conexión dedicada para impedir solapamientos después de una expiración. Pérdida de coordinación detiene las acciones. No hay fallback sin lock.
- Hasta tres intentos automáticos para errores recuperables anteriores al intento de envío. El marcador se confirma en PostgreSQL antes del clic. Un fallo posterior, incluso antes del clic efectivo, se trata conservadoramente como `FAILED/SEND_OUTCOME_UNKNOWN`.
- El siguiente propietario cancela sesiones Appium abandonadas e instrumentación UiAutomator antes de reutilizar el dispositivo. Si no puede hacerlo, no continúa el envío.
- Fallos dejan screenshot y activity cuando están disponibles. Archivo: `data/screenshots/{instance}/{message}/error.png`. Las capturas pueden contener lo visible en la UI y permanecen en el volumen privado; la API devuelve su referencia, no una URL pública.
- No hay reenvío automático ni endpoint de reintento para `SEND_OUTCOME_UNKNOWN`. Revisar la conversación y evidencia personalmente. Una nueva clave representa una nueva intención de envío.
- Medios, outbox e historial se conservan; no hay borrado automático en el MVP. El operador administra retención con servicios detenidos y respaldo previo.
- El perfil de `app/automation/selectors.py` debe calibrarse con la versión de WhatsApp instalada. Los fixtures XML de tests son sintéticos, no prueba de compatibilidad con un APK real. Los nombres de selectores, álbumes y pickers pueden cambiar.
- Un audio con metadatos que oculten su nombre interno en el selector puede no seleccionarse; el sistema falla en lugar de elegir otro archivo. Los formatos y perfiles requieren E2E real antes de considerarse aceptados.
- No está implementado soporte completo de ejecución Android en Windows, múltiples números simultáneos, recepción, envíos masivos ni notas de voz.

Consultar [endpoints](docs/endpoints.md), [operación del laboratorio](docs/operations.md) y [verificación ejecutada](docs/verification.md).

El [despliegue en Habitmundo](docs/habitmundo-deployment.md) utiliza `docker-compose.habitmundo.yml` junto con el Compose principal para límites de memoria, rotación de logs y exclusión del proxy compartido. El informe distingue servicios desplegados de la aceptación Android pendiente.

Referencias: [Android Emulator y persistencia](https://developer.android.com/studio/run/emulator-commandline), [Appium UiAutomator2](https://github.com/appium/appium-uiautomator2-driver), [Docker en Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [red del host](https://docs.docker.com/engine/network/drivers/host/), [locks Redis](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/), [click to chat de WhatsApp](https://faq.whatsapp.com/5913398998672934).
