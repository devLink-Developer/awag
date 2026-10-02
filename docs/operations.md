# Operación del laboratorio

## Arranque, apagado y persistencia

1. Iniciar `bash scripts/start-emulator.sh` y esperar arranque completo.
2. Registrar WhatsApp manualmente antes de iniciar worker/dispatcher.
3. Iniciar `bash scripts/start-services.sh`; esperar health de instancia fresco.
4. Para apagar: `docker compose stop worker dispatcher gateway-api`, detener Android con Ctrl+C y después `docker compose stop appium postgres redis`.
5. Reiniciar con el mismo AVD y volúmenes. Confirmar que no vuelve a aparecer registro y enviar una prueba controlada.

`docker compose stop` y `down` sin `--volumes` conservan PostgreSQL/Redis. El AVD se conserva fuera de Compose. No borrar `~/.local/share/whatsapp-gateway/avd`, `data/media`, `data/screenshots` ni volúmenes durante una prueba de persistencia.

La actualización del SDK no debe cambiar ADB unilateralmente. Host y contenedores deben usar la misma versión; un servidor ADB reiniciado durante una operación vuelve incierto un envío en curso.

## Inspección

```bash
docker compose ps
docker compose logs --tail=100 worker dispatcher gateway-api
curl --fail http://127.0.0.1:8000/health
ss -lntp
```

En `ss`, 8000, 4723, 5037, 5432 y 6379 deben estar limitados a loopback. Los puertos de emulador e instrumentación tampoco deben estar abiertos en interfaces públicas. No configurar ADB con `-a`, Appium con `0.0.0.0` ni publicar puertos extra. La red `storage` conecta los contenedores de almacenamiento; acceso de los procesos del host por puertos loopback autenticados.

Para inspeccionar UI: detener worker/dispatcher y usar la ventana del emulador. Las capturas debug están deshabilitadas por defecto. Para habilitarlas, cambiar `DEBUG_AUTOMATION=true` y recrear API/worker, manteniendo autenticación.

## Ejercicios de recuperación

- **HTTP concurrente:** enviar simultáneamente el mismo payload y clave. Debe existir un UUID y una fila outbox original; otra intención con esa clave debe devolver `409`.
- **Redis indisponible:** detener Redis antes del POST. La creación en PostgreSQL puede responder `QUEUED`; el dispatcher publicará al recuperar Redis. Ningún worker debe controlar UI sin coordinación.
- **Worker interrumpido antes del envío:** con mensaje sin marcador, detener el worker y reiniciarlo. Después del umbral de recuperación debe reintentarse con un máximo de tres intentos.
- **Worker interrumpido después del marcador:** el trabajo se recupera como `FAILED/SEND_OUTCOME_UNKNOWN`; no se repite el clic. Inspeccionar conversación y evidencia antes de crear cualquier mensaje nuevo.
- **Persistencia Android:** iniciar sesión manualmente, enviar, apagar ordenadamente Android y volver a iniciar el mismo AVD. La sesión debe mantenerse. Repetir en ambos idiomas.
- **Cambio de selectores:** una pantalla no reconocida debe fallar y producir evidencia, sin navegación por coordenadas ni selección de otro adjunto.

Los marcadores son conservadores: el proceso puede caer después de persistir el marcador y antes de que el clic ocurra. Ese caso también exige revisión; la UI no ofrece una transacción distribuida que permita garantizar entrega exactamente una vez.

## Calibración de selectores

Registrar versión del APK, versión de Android, idioma y driver. Con la automatización detenida, inspeccionar jerarquías mediante Appium Inspector conectado por túnel al Appium privado, usando `noReset=true/fullReset=false`. No dejar otra sesión abierta al reiniciar worker.

Editar únicamente `app/automation/selectors.py` para IDs y etiquetas. El parser de verificación exige status por burbuja, contenido/tipo y crecimiento respecto a la línea de base. No relajar esa condición para hacer pasar el E2E. Si el APK requiere otra estructura de agrupación, adaptar `verification.py` con muestras anonimizadas y pruebas contra esos layouts.

Probar número guardado y no guardado, rechazo de número no registrado, texto Unicode, textos idénticos consecutivos, adjuntos con/sin pie y fallos de red durante upload. La vista previa y la nueva burbuja deben corresponder al archivo seleccionado.
