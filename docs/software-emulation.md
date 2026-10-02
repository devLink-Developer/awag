# Emulación sin aceleración para el MVP

Este perfil experimental ejecuta Android 35 x86_64 mediante QEMU/TCG, con `-accel off`, sin `/dev/kvm`. Se habilitó por petición del operador. El despliegue habitual con KVM sigue disponible. El rendimiento y los tiempos E2E deben medirse en el servidor real.

En Habitmundo se eligió la imagen **AOSP API 35, revisión 2**, en lugar de Google APIs: el archivo instalado ocupa aproximadamente 1,6 GiB. No incluye Play Store ni servicios de Google. La instalación y el registro de WhatsApp siguen siendo manuales; su compatibilidad debe validarse con el APK oficial.

El perfil configura el emulador con dos núcleos y 1024 MiB de RAM del invitado, pantalla de 480×800 y 15 Hz. Desactiva Vulkan, snapshots, audio y cámaras. Limita la caché de traducción TCG a 64 MiB. El contenedor dispone de hasta 1,5 CPU compartida entre los núcleos emulados y el renderizado software, y tiene un máximo de 1,75 GiB de memoria y 2,75 GiB contando swap; no se reinicia automáticamente después de fallar. El arranque tiene un plazo de 1800 segundos. Estos límites pueden requerir ajustes con WhatsApp instalado.

El perfil solicita `ro.hw_timeout_multiplier=10` para ampliar las esperas internas de Android en hardware lento. Este ajuste conserva el watchdog con un plazo mayor; no modifica el marcador de envío ni suprime la coordinación del gateway.

Si la imagen AOSP rechaza esa propiedad de arranque, el script usa temporalmente `adb root`, configura el multiplicador, reinicia Zygote y vuelve a `adb unroot`. Comprueba el resultado y falla si no puede aplicarlo. No desactiva SELinux ni borra datos. Este bootstrap requiere una imagen de desarrollo que admita ADB root, como la AOSP utilizada.

## Preparar

Desde la raíz del proyecto en Ubuntu, con `.env` generado y las imágenes principales construidas:

```bash
docker compose build gateway-api appium
python3 scripts/prepare_software_android.py --root ./android --variant default
docker compose -f docker-compose.yml -f docker-compose.software-emulator.yml --profile software-emulator build emulator gateway-api
docker compose -f docker-compose.yml -f docker-compose.software-emulator.yml --profile software-emulator run --rm --no-deps emulator bash /usr/local/bin/prepare-software-userdata.sh
```

El instalador verifica el SHA-1 publicado del ZIP oficial y el CRC/tamaño de cada miembro. Descarga por rangos y conserva bloques vacíos como archivos dispersos, sin guardar el ZIP. Detiene la extracción si quedan menos de 768 MiB libres. `--variant google_apis` prepara la imagen estándar; no cambia un AVD existente de imagen ni borra sus datos.

`prepare-software-userdata.sh` crea una partición ext4/QCOW2 dispersa de **1 GiB**, únicamente si todavía no existe `userdata-qemu.img`. Evita el mínimo automático de 6 GiB del emulador actual al crear un AVD. Si existe la partición, sale sin formatearla. Ejecutarlo antes de arrancar Android. No ejecutar `-wipe-data` ni borrar `android/avd` para actualizar.

En `.env`, configurar `ADB_SERIAL=emulator-5556`. La imagen y los datos privados quedan en `android/`, excluido de Git y de los contextos Docker. Aceptar las licencias del SDK según el procedimiento habitual antes de utilizar sus imágenes.

## Operar en Habitmundo

Las imágenes ya instaladas permiten iniciar sin compilar. Usar siempre los tres archivos para conservar los límites del servidor y los plazos ampliados del software:

```bash
cd /opt/awag
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml --profile software-emulator up -d --no-build emulator gateway-api postgres redis appium
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml --profile software-emulator ps
docker logs --tail 30 whatsapp-gateway-emulator-1
docker exec whatsapp-gateway-emulator-1 timeout 120s adb -s emulator-5556 shell getprop sys.boot_completed
```

Solo `sys.boot_completed=1` confirma el arranque completo. `adb devices` con estado `device` confirma conectividad, pero Android puede seguir iniciando servicios. Monitorizar `docker stats`, `free -m` y `df -h /`. El timeout, una salida anticipada o `OOMKilled=true` requieren inspección; no implican un arranque correcto.

Habitmundo utiliza 1 GiB de swap en `/opt/awag/android/swapfile`, activado con la unidad `docker/opt-awag-android-swapfile.swap`. Preparación inicial, únicamente si el archivo no existe:

```bash
sudo fallocate -l 1G /opt/awag/android/swapfile
sudo chmod 600 /opt/awag/android/swapfile
sudo mkswap /opt/awag/android/swapfile
sudo cp docker/opt-awag-android-swapfile.swap /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opt-awag-android-swapfile.swap
```

No repetir `mkswap` sobre un archivo activo. El swap evita algunos fallos por presión de memoria; la CPU sigue usando emulación software.

En Habitmundo, la imagen AOSP está montada desde un SquashFS de aproximadamente 707 MiB. La compresión conserva los bytes de cada archivo, comprobados con SHA-256, y permite reservar espacio para el swap. Los datos del AVD permanecen separados y escribibles. Para repetir esta optimización con el emulador detenido y `mksquashfs` instalado:

```bash
sudo bash scripts/pack-software-image.sh /opt/awag/android
task_mount_unit=$(systemd-escape --path --suffix=mount /opt/awag/android/system-images/android-35/default)
sudo cp docker/awag-software-image.mount.example "/etc/systemd/system/$task_mount_unit"
sudo systemctl daemon-reload
sudo systemctl enable "$task_mount_unit"
sudo systemctl is-active "$task_mount_unit"
```

El script conserva el original en `default.unpacked` hasta que el operador confirma el montaje persistente. Solo después de verificar la unidad activa y los checksums puede eliminarse esa copia de la imagen SDK. No eliminar `android/avd` ni el archivo SquashFS. En Habitmundo el montaje persistente ya está instalado y la copia original verificada fue retirada.

## Preparar el auxiliar Appium

El perfil software utiliza `APPIUM_SKIP_SETTINGS_APP_REINSTALL=true`. El driver comprueba que `io.appium.settings` existe y reutiliza el APK instalado, evitando reinstalarlo y esperar su servicio en cada conexión. El perfil normal conserva la inicialización automática. En un AVD nuevo, después de completar el arranque y con Appium iniciado, instalar el auxiliar de la misma imagen fijada del driver:

```bash
docker exec whatsapp-gateway-appium-1 timeout 900s adb -H 127.0.0.1 -P 5037 -s emulator-5556 install -r -g /opt/appium/node_modules/appium-uiautomator2-driver/node_modules/io.appium.settings/apks/settings_apk-debug.apk
```

Comprobar `Success`. Repetir esta provisión al actualizar el driver y su APK auxiliar; no sustituirlo por otra fuente. Habitmundo ya tiene la versión 8.0.9, código 191, coincidente con el APK de su imagen. Si falta el auxiliar, la sesión Appium falla y debe completarse esta provisión. Este paso instala un componente de Appium; el registro de WhatsApp continúa siendo manual.

## Instalación y registro manual

Mantener worker/dispatcher detenidos mientras se opera manualmente la UI:

```bash
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml stop worker dispatcher
```

Obtener el APK de [WhatsApp para Android](https://www.whatsapp.com/android). Desde Windows, suponiendo que está en Descargas:

```powershell
scp "$HOME/Downloads/WhatsApp.apk" distromaxi:/opt/awag/WhatsApp.apk
```

En el servidor, con Android ya arrancado:

```bash
docker compose -f docker-compose.yml -f docker-compose.habitmundo.yml -f docker-compose.software-emulator.yml run --rm --no-deps -v /opt/awag/WhatsApp.apk:/tmp/WhatsApp.apk:ro gateway-api adb -H 127.0.0.1 -P 5037 -s emulator-5556 install -r /tmp/WhatsApp.apk
```

Comprobar que la instalación responde `Success`; el APK debe soportar la ABI del emulador. No instalar APK de terceros ni automatizar OTP. Este procedimiento de instalación no implica que el registro ni los envíos hayan sido verificados.

Para controlar la pantalla desde Windows, usar un túnel SSH al servidor ADB y un cliente `scrcpy` con Platform Tools **37.0.1**:

```powershell
ssh -N -L 127.0.0.1:15037:127.0.0.1:5037 -L 127.0.0.1:27183:127.0.0.1:27183 distromaxi
# Otra terminal con adb y scrcpy en PATH:
$env:ADB_SERVER_SOCKET = 'tcp:127.0.0.1:15037'
adb -s emulator-5556 devices
scrcpy --serial=emulator-5556 --force-adb-forward --port=27183 --video-bit-rate=1M --max-fps=15
```

Completar personalmente número, verificación y permisos en WhatsApp. Los puertos ADB/emulador permanecen en loopback; no publicarlos en Internet. Una vez terminado, iniciar worker/dispatcher con los tres archivos, esperar salud fresca `WHATSAPP_READY` y ejecutar el procedimiento E2E del README. Las capturas, actividad y envíos reales tienen que verificarse contra el APK instalado.

Los plazos de comandos e instalación Appium pasan a 900 segundos, esperas UI a 180 segundos y confirmación de envío a 600 segundos. El lock tiene TTL de 2100 segundos y renovación cada 60 segundos. La tarea tiene un límite de 3600 segundos y se considera interrumpida después de 3900 segundos. Se mantienen propiedad del lock, límite de tarea y tratamiento `SEND_OUTCOME_UNKNOWN`; ampliar tiempos no autoriza reenvíos inciertos.

Referencias: [opciones y persistencia del emulador](https://developer.android.com/studio/run/emulator-commandline), [implementación del mínimo de datos](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android-qemu2-glue/main.cpp), [caché de traducción TCG](https://www.qemu.org/docs/master/system/qemu-manpage.html), [túneles para scrcpy](https://github.com/Genymobile/scrcpy/blob/master/doc/tunnels.md).
