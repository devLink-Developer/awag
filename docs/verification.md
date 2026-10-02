# Verificación de implementación

Fecha: 2 de octubre de 2026. Esta entrega implementa el MVP; la aceptación de los envíos requiere completar las pruebas Android indicadas abajo.

## Pruebas ejecutadas

| Entorno o comprobación | Resultado |
|---|---|
| Windows, Python 3.13.5, suite completa con PostgreSQL/Redis reales | **76 passed, 2 skipped**, 1 warning; salida 0. |
| Contenedor Linux, Python 3.12.11, suite completa con PostgreSQL/Redis reales | **77 passed, 1 skipped**, 1 warning; salida 0. |
| Ruff en Windows y Linux | Correcto. |
| `pip check` en Windows | Sin dependencias incompatibles. |
| `docker compose config --quiet` | Correcto. |
| `bash -n` para todos los scripts `.sh`, en Linux | Correcto. |
| Build `docker/Dockerfile` | Imagen `whatsapp-gateway:0.1.0` construida con el código final. |
| Build `docker/Dockerfile.appium` | Imagen `whatsapp-gateway-appium:0.1.0` construida. |
| Appium 3.8.0 y UiAutomator2 8.7.0 | `/status` listo; `/appium/sessions` responde `200` con lista vacía. |
| `appium driver doctor uiautomator2` dentro de la imagen | Salida 0; cero correcciones obligatorias. |
| API real desde la imagen final, PostgreSQL/Redis y migración inicial | Smoke HTTP correcto, sin worker Android. |
| Despliegue real en Habitmundo, Ubuntu 24.04 | Seis servicios en ejecución, migración aplicada y comprobaciones HTTP correctas; instancia Android `OFFLINE`. |
| Configuración Habitmundo | Puertos API/Appium/PostgreSQL/Redis en loopback, autenticación, debug ausente, exclusión de Traefik, límites de memoria y rotación de logs verificados. |
| Script de puerto configurable del emulador | `bash -n` correcto en Ubuntu; puertos fuera de rango e impares rechazados. El arranque real se detuvo por KVM ausente. |

Las pruebas de integración utilizaron PostgreSQL **17.6** y Redis **7.4.5** en servicios dedicados de Docker. Se comprobaron migraciones upgrade/downgrade/upgrade, ocho solicitudes concurrentes con una misma clave, publicación duplicada tras fallos, serialización de workers, expiración/pérdida de propiedad Redis con advisory lock PostgreSQL, recuperación de trabajos y transporte real de Celery mediante Redis.

Las pruebas locales cubren validación de contratos, registro de medios, traversal, enlaces simbólicos, modificación del archivo durante copia, límites, formatos y tipo incompatible. Audio y video se validaron usando `ffmpeg`/`ffprobe` reales. También se ejercitaron fallos anteriores y posteriores al marcador, caída simulada del worker, fallo al persistir la confirmación y conservación de errores cuando falla la captura de evidencia.

El smoke HTTP aplicó la migración, creó la instancia persistente y verificó: `/health` `200`; autenticación ausente `401`; creación de texto `202`; replay `200` con el mismo UUID; conflicto de payload `409`; registro de documento `201`; mensaje con documento `202`; métricas protegidas `200`; debug desactivado `404`; OpenAPI disponible. Los mensajes quedaron `QUEUED`: no se inició ninguna operación Android ni se envió contenido a un destinatario.

El E2E se omitió en ambos entornos porque no se proporcionó un destinatario ni un dispositivo autenticado. Windows omitió además la prueba de symlink porque la cuenta no permite crearlo; ese caso pasó en Linux. El warning de la suite corresponde a la deprecación de `httpx` en el TestClient de Starlette; no hubo errores de pruebas. Doctor informó tres componentes opcionales ausentes para bundles/grabación/streaming; el MVP no utiliza esas funciones.

Para reproducir las comprobaciones unitarias y de integración, utilizar los comandos de [README](../README.md#pruebas). El build y las pruebas Linux se realizaron en Docker Desktop; esto no prueba el arranque de un AVD mediante KVM ni la topología de red del host en Ubuntu.

Posteriormente se desplegaron los servicios del gateway en Ubuntu/Habitmundo y se verificó allí la topología de red del host para API/Appium y los puertos loopback de almacenamiento. El worker produjo un health fresco `OFFLINE` porque no hay Android arrancado. Tanto la carga normal de KVM como `kvm_intel nested=1` fallaron: el kernel informa `VMX not supported by CPU`. Consultar [el informe de despliegue](habitmundo-deployment.md). No se enviaron mensajes reales desde el servidor.

## Aceptación pendiente en Ubuntu/KVM

- Instalar SDK y crear/arrancar `WhatsApp_QA` con los scripts entregados; comprobar KVM y almacenamiento persistente.
- Instalar y registrar WhatsApp manualmente; confirmar que la instancia alcanza `WHATSAPP_READY` con un health fresco.
- Calibrar los resource IDs y selectores de conversación, teléfono, álbumes, SAF y burbujas contra el APK instalado. Los XML de tests son **sintéticos**; no demuestran compatibilidad con WhatsApp real.
- Ejecutar el procedimiento E2E del README para texto, imagen, documento, archivo de audio y video, en español e inglés. Incluye dos textos idénticos para comprobar la detección de una burbuja nueva.
- Verificar con Android real la recuperación después de interrupciones, la evidencia y el tratamiento `SEND_OUTCOME_UNKNOWN` sin reenvío automático.
- Reiniciar el emulador y los servicios y verificar conservación de sesión, archivos y trabajos. Después de habilitar Android, comprobar también los puertos del emulador, ADB e instrumentación; repetir los controles loopback y debug ya ejecutados para los servicios del gateway.

**No se declara verificado ningún envío real de WhatsApp.** Los adaptadores implementan las operaciones y fallan ante una UI desconocida o una confirmación ambigua; hasta completar esta aceptación, los cinco tipos de envío tienen verificación automatizada de lógica, pero no validación E2E sobre un dispositivo real.
