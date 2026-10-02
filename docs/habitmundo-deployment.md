# Despliegue en Habitmundo

Fecha: 2 de octubre de 2026. Los seis servicios del gateway están desplegados en `/opt/awag`. El emulador y los envíos reales permanecen pendientes de habilitar KVM y registrar WhatsApp manualmente.

## Instalación y verificación

El servidor usa Ubuntu 24.04 x86_64 y Docker Compose. Se instalaron API, PostgreSQL, Redis, Appium, worker y dispatcher. Las imágenes construidas y probadas en desarrollo se transfirieron por SSH y se verificaron con SHA-256 antes de cargarlas. El runtime Python corresponde al commit `8d104f6`; `REVISION` identifica el snapshot de código y configuración instalado.

- `.env` generado directamente en el servidor con secretos nuevos y permisos `600`; almacenamiento privado y volúmenes persistentes.
- Migración Alembic aplicada e instancia persistente con `ADB_SERIAL=emulator-5556`, idioma español y debug desactivado.
- Override `docker-compose.habitmundo.yml`: límites de memoria, logs de 10 MiB con tres archivos, `traefik.enable=false` y reinicio `unless-stopped` para los seis servicios.
- API `/health` `200` con PostgreSQL y Redis accesibles; Appium `/status` con `ready=true`.
- Autenticación obligatoria (`401` sin token), métricas protegidas, OpenAPI disponible y rutas debug ausentes (`404`).
- Listeners exclusivamente en `127.0.0.1` para API 8000, Appium 4723, PostgreSQL 5432 y Redis 6379.
- Worker y dispatcher en ejecución: la comprobación publicada fue procesada y la instancia informa `OFFLINE` con fecha fresca, porque no existe Android arrancado.

No se crearon mensajes de prueba en el servidor ni se realizaron envíos reales.

## Operación

En Habitmundo usar ambos archivos Compose para conservar los límites y la exclusión de Traefik:

```bash
cd /opt/awag
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml ps
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml up -d --no-build --wait
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml exec -T gateway-api python -m alembic current
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

El VPS tiene 2 vCPU y 3.8 GiB de RAM total; después de arrancar los servicios había aproximadamente 0.7 GiB disponible, sin emulador. Hay que dimensionar memoria, CPU y almacenamiento antes de iniciar el AVD junto con las aplicaciones existentes.

## Completar Android y la aceptación

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

**La API está desplegada y verificada; ningún envío real de WhatsApp está verificado ni operativo todavía.**
