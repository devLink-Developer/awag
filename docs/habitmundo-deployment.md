# Despliegue en Habitmundo

Fecha: 2 de octubre de 2026. El gateway está desplegado en `/opt/awag`. Por petición del operador se preparó un MVP con emulación software: **Android 35 AOSP confirmó `sys.boot_completed=1` con `-accel off`**. La instalación, el registro y los envíos reales de WhatsApp siguen pendientes.

## Instalación y verificación

El servidor usa Ubuntu 24.04 x86_64 y Docker Compose. Se instalaron API, PostgreSQL, Redis, Appium, worker y dispatcher. Las imágenes principales se transfirieron por SSH y se verificaron con SHA-256 antes de cargarlas. El backend software reutiliza sus dependencias y añade el código actualizado de `app/` y `scripts/`; `REVISION` identifica el snapshot de código y configuración instalado.

- `.env` generado directamente en el servidor con secretos nuevos y permisos `600`; almacenamiento privado y volúmenes persistentes.
- Migración Alembic aplicada e instancia persistente con `ADB_SERIAL=emulator-5556`, idioma español y debug desactivado.
- Override `docker-compose.habitmundo.yml`: límites de memoria, logs de 10 MiB con tres archivos, `traefik.enable=false` y reinicio `unless-stopped` para los seis servicios.
- API `/health` `200` con PostgreSQL y Redis accesibles; Appium `/status` con `ready=true`.
- Autenticación obligatoria (`401` sin token), métricas protegidas, OpenAPI disponible y rutas debug ausentes (`404`).
- Listeners exclusivamente en `127.0.0.1` para API 8000, Appium 4723, PostgreSQL 5432 y Redis 6379.
- En el despliegue base, el worker confirmó `OFFLINE` por ausencia de Android. El resultado actualizado del perfil software se detalla debajo.

No se crearon mensajes de prueba en el servidor ni se realizaron envíos reales.

## Operación

Para el MVP software usar los tres archivos Compose indicados en [su procedimiento](software-emulation.md#operar-en-habitmundo), incluyendo `docker-compose.software-emulator.yml`. Los comandos siguientes conservan el perfil software activo:

```bash
cd /opt/awag
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml --profile software-emulator ps
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml up -d --no-build gateway-api worker dispatcher postgres redis appium
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml exec -T gateway-api python -m alembic current
curl --fail http://127.0.0.1:8000/health
```

Las imágenes ya están instaladas. No compilar nuevas versiones en el VPS sin comprobar capacidad. Para actualizar, generar y probar las imágenes correspondientes al código nuevo y conservar credenciales y volúmenes existentes.

Desde desarrollo, el alias SSH `distromaxi` corresponde a Habitmundo:

```bash
ssh -N -L 127.0.0.1:18000:127.0.0.1:8000 distromaxi
```

Abrir `http://127.0.0.1:18000/docs` y usar el token privado del `.env` del servidor con **Authorize**. El túnel requiere las credenciales SSH existentes; no están incluidas en el repositorio.

## Bloqueo de KVM

La inspección inicial encontró la raíz al 100%. Después de la limpieza del operador había 6.8 GiB libres. Después de instalar el gateway y eliminar su archivo temporal de transporte quedaron aproximadamente 3.7 GiB. No se borraron datos ni se modificaron servicios de otras aplicaciones.

`/dev/kvm` no existe y la CPU virtual no expone `vmx` ni `svm`. Cargar `kvm_intel`, también con `nested=1`, falló con `Operation not supported`; el kernel confirmó **`VMX not supported by CPU`**. El script de arranque rechazó la operación por falta de KVM, sin iniciar una emulación sin aceleración.

Que el VPS corra sobre KVM no permite automáticamente usar KVM dentro de Ubuntu. Se requiere virtualización anidada habilitada en el hipervisor y exposición de las capacidades de CPU a la VM, como describe la [documentación oficial de KVM](https://docs.kernel.org/virt/kvm/x86/running-nested-guests.html). No se puede suplir VMX desde el Ubuntu invitado.

El VPS tiene 2 vCPU y 3.8 GiB de RAM total; después de arrancar los servicios había aproximadamente 0.7 GiB disponible, sin emulador. El perfil software limita recursos y utiliza swap. La disponibilidad y el rendimiento deben volver a medirse con WhatsApp instalado.

## MVP software autorizado

Se instaló la imagen AOSP API 35 x86_64, revisión 2, verificada contra el checksum oficial. Ocupa aproximadamente 1,6 GiB y no incluye servicios de Google. La preparación de Google APIs se detuvo al alcanzar la reserva de disco; por eso el MVP utiliza esta variante más pequeña.

Se añadieron una partición de datos persistente de 1 GiB y 1 GiB de swap privado del proyecto, con unidad systemd. La imagen de sistema se comprimió en un SquashFS de 707 MiB, verificando SHA-256 de cada archivo antes de retirar la copia sin comprimir; el montaje persistente tiene su propia unidad systemd. Se limpiaron cachés de compilación de Docker; no se eliminaron datos ni contenedores de otras aplicaciones. Con la imagen comprimida y el swap ampliado quedaban aproximadamente 2,4 GiB libres.

El primer arranque alcanzó el límite de memoria del contenedor y terminó con `OOMKilled=true`. Se desactivó Vulkan, se redujo la frecuencia gráfica, se configuró Android para baja memoria y se limitó la caché TCG. Android también reinició SystemServer por watchdog durante el inicio lento; aplicar el multiplicador de tiempos de hardware permitió completar el arranque. ADB volvió a modo sin root y SELinux permaneció activo.

El primer perfil confirmó API 35, modo de baja memoria, 768 MiB de RAM configurada, un núcleo y `sys.boot_completed=1`. El contenedor estabilizó su consumo aproximadamente en 1,1 GiB durante las comprobaciones. El primer arranque observado necesitó unos 16 minutos e incluyó los ajustes manuales de diagnóstico. Después de detener y volver a iniciar el emulador, el arranque limpio tardó unos 9 minutos: inicio a las 19:47:48 UTC y `sys.boot_completed=1` a las 19:56:44 UTC. El bootstrap automático configuró el multiplicador y restauró ADB sin root; la aplicación auxiliar de Appium instalada previamente seguía presente. La pantalla de Ajustes cargó y se capturó, pero el servicio auxiliar de Appium sufrió ANR con 768 MiB. Se ajustó el perfil a 1024 MiB y dos núcleos del invitado, con cuota de 1,5 CPU y límite de 1,75 GiB para el contenedor.

El perfil final de 1024 MiB y dos núcleos completó otro arranque en 7 minutos y 10 segundos: inicio a las 20:19:33 UTC y confirmación a las 20:26:43 UTC. `OOMKilled=false`, usuario `RUNNING_UNLOCKED`, sistema listo y partición persistente conservada.

Se creó una sesión real de UiAutomator2, se leyó el árbol de la interfaz, se capturó la pantalla y se cerró la sesión. La creación inicial tardó varios minutos. El auxiliar Appium instalado es 8.0.9, código 191, igual al APK de la imagen fijada; el perfil lo reutiliza para evitar reinstalaciones y la espera de servicio de 30 segundos que fallaba en esta VM.

Durante la preparación apareció un diálogo ANR de System UI. Se seleccionó **Esperar** bajo los locks de la instancia y se confirmó que el foco volvió al launcher. Este fallo observado y la presión de memoria impiden considerar validada la estabilidad de la UI o los envíos: hace falta aceptación real con WhatsApp instalado y autenticado.

Worker y dispatcher volvieron a iniciarse. Los siete contenedores están activos; la comprobación del worker confirmó estado `ONLINE`, ADB visible, boot completo, Appium accesible y `WHATSAPP_NOT_INSTALLED`, con fecha fresca. Se verificaron nuevamente autenticación, métricas, OpenAPI, debug desactivado y puertos loopback. PostgreSQL conserva cero mensajes y la referencia de sesión Appium quedó vacía; `/appium/sessions` confirmó que no quedó ninguna sesión activa.

Puertos ADB 5037 y emulador 5556/5557 limitados a loopback. La API conservó `/health` disponible. El [procedimiento software](software-emulation.md) describe arranque, límites, bootstrap de timeouts, acceso manual por SSH/scrcpy e instalación de WhatsApp.

## Cambiar posteriormente a KVM y completar la aceptación

1. Habilitar virtualización anidada desde el hipervisor/proveedor, o usar otro host Ubuntu con KVM. Verificar `vmx`/`svm`, `/dev/kvm` y `kvm-ok`.
2. Reservar recursos suficientes y mantener libres los puertos 5556/5557 y 8200. **5554 está ocupado por SSH en Habitmundo**.
3. Detener worker/dispatcher y seguir la instalación Ubuntu/SDK/AVD del README. Arrancar con el puerto configurado:

   ```bash
   cd /opt/awag
   docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml stop worker dispatcher
   EMULATOR_PORT=5556 bash scripts/start-emulator.sh
   ```

4. Instalar y registrar WhatsApp manualmente, usando `adb -s emulator-5556` en los comandos del README. No se automatizan OTP ni registro.
5. Volver a iniciar worker/dispatcher con ambos archivos Compose. Esperar salud fresca `WHATSAPP_READY`.
6. Ejecutar E2E real de los cinco tipos, español e inglés, persistencia y recuperación de fallos.

**La API está desplegada y Android arrancó sin aceleración; ningún envío real de WhatsApp está verificado todavía.**
