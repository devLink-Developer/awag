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
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 15037,27183 -ErrorAction SilentlyContinue)
$pidFile = Join-Path $clientRoot 'tunnel.pid'
if ($listeners.Count -gt 0) {
    if (!(Test-Path -LiteralPath $pidFile)) { throw 'Puertos del tunel ocupados por otro proceso.' }
    $savedPid = [int](Get-Content -LiteralPath $pidFile)
    $ownedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid"
    if (!$ownedProcess -or $ownedProcess.ExecutablePath -ne $sshPath -or
        $ownedProcess.CommandLine -notmatch [regex]::Escape("127.0.0.1:15037:127.0.0.1:5037") -or
        $ownedProcess.CommandLine -notmatch [regex]::Escape("127.0.0.1:27183:127.0.0.1:27183") -or
        $ownedProcess.CommandLine -notmatch ('\s' + [regex]::Escape($SshAlias) + '\s*$') -or
        @($listeners | Where-Object OwningProcess -ne $savedPid).Count -gt 0 -or
        @($listeners.LocalPort | Sort-Object -Unique).Count -ne 2) {
        throw 'Los puertos no pertenecen al tunel de AWAG; no se modificaron.'
    }
} else {
    $tunnel = Start-Process -FilePath $sshPath -WindowStyle Hidden -PassThru -ArgumentList @(
        '-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
        '-L', '127.0.0.1:15037:127.0.0.1:5037',
        '-L', '127.0.0.1:27183:127.0.0.1:27183', $SshAlias
    ) -RedirectStandardError (Join-Path $clientRoot 'tunnel.log')
    Set-Content -LiteralPath $pidFile -Value $tunnel.Id
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $tunnel.Refresh()
        if ($tunnel.HasExited) { throw "Fallo el tunel SSH. Consulta $clientRoot\tunnel.log." }
        $ready = @(Get-NetTCPConnection -State Listen -LocalPort 15037,27183 -ErrorAction SilentlyContinue |
            Where-Object OwningProcess -eq $tunnel.Id)
    } until ($ready.Count -eq 2 -or (Get-Date) -gt $deadline)
    if ($ready.Count -ne 2) { throw 'El tunel SSH no abrio ambos puertos a tiempo.' }
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
    $display = Start-Process -FilePath $scrcpyPath -WorkingDirectory $ScrcpyDirectory -PassThru -ArgumentList @(
        "--serial=$Serial", '--force-adb-forward', '--port=27183', '--no-audio',
        '--video-bit-rate=1M', '--max-fps=5', '--max-size=480',
        '--no-clipboard-autosync', '--window-title=AWAG_WhatsApp_QA'
    ) -RedirectStandardOutput (Join-Path $clientRoot 'scrcpy-output.log') -RedirectStandardError (Join-Path $clientRoot 'scrcpy-error.log')
    Set-Content -LiteralPath (Join-Path $clientRoot 'scrcpy.pid') -Value $display.Id
    Write-Output "scrcpy iniciado (PID $($display.Id)). El registro del numero y OTP se hace manualmente."
} finally {
    $env:ADB_SERVER_SOCKET = $oldAdbSocket
    $env:ADB = $oldAdbBinary
}
