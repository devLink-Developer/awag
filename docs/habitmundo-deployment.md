# Despliegue en Habitmundo

Inspección remota: 2 de octubre de 2026, antes de instalar componentes del gateway.

## Estado actual

El servidor usa Ubuntu 24.04 x86_64 y tiene Docker Compose. El despliegue del gateway **no se ha ejecutado** por dos bloqueos comprobados:

- El filesystem raíz tiene 24 GiB, está al 100% y no informa espacio disponible. No permite instalar imágenes, SDK, AVD ni almacenamiento persistente de forma fiable.
- `/dev/kvm` no existe y la CPU virtual no expone `vmx` ni `svm`. Que el VPS esté alojado sobre un hipervisor KVM no implica que permita aceleración KVM dentro del VPS.

El servidor tiene 2 vCPU, 3.8 GiB de RAM total y aproximadamente 1.1 GiB disponible al inspeccionarlo. Varios servicios previos ya estaban degradados. Antes de añadir el emulador, también se debe dimensionar memoria y CPU para el conjunto de aplicaciones.

No se borraron datos, no se modificaron servicios existentes y no se copiaron credenciales de acceso al repositorio.

## Requisitos para completar el despliegue

1. Proporcionar almacenamiento suficiente para Docker, Android SDK, imagen API 35, AVD persistente y medios; resolver la falta de espacio sin borrar datos de aplicaciones existentes.
2. Habilitar virtualización anidada en el proveedor del VPS y verificar `vmx`/`svm`, `/dev/kvm` y `kvm-ok`, o desplegar el gateway en un host Ubuntu que tenga KVM.
3. Reservar CPU y RAM para el emulador y los seis servicios del gateway, además de las aplicaciones actuales.
4. Ejecutar la instalación y el registro manual de WhatsApp del README. No iniciar el worker hasta completar el registro.

Una vez satisfechos los requisitos, usar `/opt/awag` como carpeta del proyecto y seguir los comandos de [instalación](../README.md#instalación-en-ubuntu). Generar `.env` en el servidor con `python3 scripts/generate-env.py`; no reutilizar secretos de desarrollo.

Los puertos requeridos deben estar disponibles: API 8000, Appium 4723, PostgreSQL 5432, Redis 6379 y ADB 5037, todos en loopback. La inspección inicial no encontró listeners en esos puertos. Repetir esa comprobación al desplegar.

Acceso al API después del arranque: túnel SSH al puerto 8000 del servidor. No publicar API, Appium, ADB ni almacenamiento en Internet. La aceptación final debe repetir las comprobaciones HTTP y los E2E reales del README; la publicación del código en GitHub no acredita un despliegue ni un envío de WhatsApp.
