param(
    [string]$SshAlias = 'distromaxi',
    [string]$Serial = 'emulator-5556',
    [string]$ScrcpyDirectory = "$env:LOCALAPPDATA\AWAG\scrcpy-win64-v4.1"
)
$ErrorActionPreference = 'Stop'
if ($SshAlias -notmatch '^[A-Za-z0-9_.-]+$' -or $Serial -notmatch '^[A-Za-z0-9_.:-]+$') {
    throw 'Alias SSH o serial no valido.'
}
$clientRoot = Join-Path $env:LOCALAPPDATA 'AWAG'
$adbPath = Join-Path $ScrcpyDirectory 'adb.exe'
$scrcpyPath = Join-Path $ScrcpyDirectory 'scrcpy.exe'
if (!(Test-Path -LiteralPath $adbPath) -or !(Test-Path -LiteralPath $scrcpyPath)) {
    throw "Instala el ZIP oficial de scrcpy en $ScrcpyDirectory."
}
New-Item -ItemType Directory -Path $clientRoot -Force | Out-Null
$sshPath = (Get-Command ssh.exe -ErrorAction Stop).Source
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 15037 -ErrorAction SilentlyContinue)
$pidFile = Join-Path $clientRoot 'tunnel.pid'
if ($listeners.Count -gt 0) {
    if (!(Test-Path -LiteralPath $pidFile)) { throw 'Puertos del tunel ocupados por otro proceso.' }
    $savedPid = [int](Get-Content -LiteralPath $pidFile)
    $ownedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid"
    if (!$ownedProcess -or $ownedProcess.ExecutablePath -ne $sshPath -or
        $ownedProcess.CommandLine -notmatch [regex]::Escape("127.0.0.1:15037:127.0.0.1:5037") -or
        $ownedProcess.CommandLine -notmatch ('-R\s+' + [regex]::Escape("127.0.0.1:27183:127.0.0.1:27183")) -or
        $ownedProcess.CommandLine -notmatch ('\s' + [regex]::Escape($SshAlias) + '\s*$') -or
        @($listeners | Where-Object OwningProcess -ne $savedPid).Count -gt 0) {
        throw 'Los puertos no pertenecen al tunel de AWAG; no se modificaron.'
    }
} else {
    $tunnel = Start-Process -FilePath $sshPath -WindowStyle Hidden -PassThru -ArgumentList @(
        '-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
        '-L', '127.0.0.1:15037:127.0.0.1:5037',
        '-R', '127.0.0.1:27183:127.0.0.1:27183', $SshAlias
    ) -RedirectStandardError (Join-Path $clientRoot 'tunnel.log')
    Set-Content -LiteralPath $pidFile -Value $tunnel.Id
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $tunnel.Refresh()
        if ($tunnel.HasExited) { throw "Fallo el tunel SSH. Consulta $clientRoot\tunnel.log." }
        $ready = @(Get-NetTCPConnection -State Listen -LocalPort 15037 -ErrorAction SilentlyContinue |
            Where-Object OwningProcess -eq $tunnel.Id)
    } until ($ready.Count -eq 1 -or (Get-Date) -gt $deadline)
    if ($ready.Count -ne 1) { throw 'El tunel SSH no abrio el puerto ADB a tiempo.' }
}
$oldAdbSocket = $env:ADB_SERVER_SOCKET
$oldAdbBinary = $env:ADB
try {
    $env:ADB_SERVER_SOCKET = 'tcp:127.0.0.1:15037'
    $env:ADB = $adbPath
    $state = & $adbPath -s $Serial get-state
    if ($LASTEXITCODE -ne 0 -or $state -ne 'device') { throw 'Android no esta disponible por el tunel.' }
    $existingWindow = @(Get-Process scrcpy -ErrorAction SilentlyContinue |
        Where-Object MainWindowTitle -eq 'AWAG_WhatsApp_QA')
    if ($existingWindow.Count -gt 0) {
        Write-Output 'La ventana AWAG_WhatsApp_QA ya esta abierta.'
        return
    }
    if (@(Get-NetTCPConnection -State Listen -LocalPort 27183 -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'El puerto local de scrcpy esta ocupado; no se modifico ese proceso.'
    }
    $display = Start-Process -FilePath $scrcpyPath -WorkingDirectory $ScrcpyDirectory -PassThru -ArgumentList @(
        "--serial=$Serial", '--port=27183', '--no-audio',
        '--video-bit-rate=1M', '--max-fps=5', '--max-size=480',
        '--no-clipboard-autosync', '--no-mouse-hover', '--window-title=AWAG_WhatsApp_QA'
    ) -RedirectStandardOutput (Join-Path $clientRoot 'scrcpy-output.log') -RedirectStandardError (Join-Path $clientRoot 'scrcpy-error.log')
    Set-Content -LiteralPath (Join-Path $clientRoot 'scrcpy.pid') -Value $display.Id
    $displayDeadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 500
        $display.Refresh()
        if ($display.HasExited) {
            throw "scrcpy termino antes de abrir la ventana. Consulta $clientRoot\scrcpy-error.log."
        }
    } until ($display.MainWindowTitle -eq 'AWAG_WhatsApp_QA' -or (Get-Date) -gt $displayDeadline)
    if ($display.MainWindowTitle -eq 'AWAG_WhatsApp_QA') {
        Write-Output "Ventana scrcpy abierta (PID $($display.Id)). El registro del numero y OTP se hace manualmente."
    } else {
        Write-Warning "Android sigue preparando el video (PID $($display.Id)). Consulta $clientRoot\scrcpy-output.log; no abras otro cliente."
    }
} finally {
    $env:ADB_SERVER_SOCKET = $oldAdbSocket
    $env:ADB = $oldAdbBinary
}
