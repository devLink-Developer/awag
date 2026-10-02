$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements-dev.txt first.' }
$env:TEST_DB_PASSWORD = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:TEST_DATABASE_URL = 'postgresql+psycopg://gateway_test:' + $env:TEST_DB_PASSWORD + '@127.0.0.1:55432/gateway_test'
$env:TEST_REDIS_URL = 'redis://127.0.0.1:56379/0'
try {
    docker compose -p whatsapp-gateway-tests -f tests/compose.yml up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Test containers could not start.' }
    & $python -m pytest -q
    $testExit = $LASTEXITCODE
} finally {
    docker compose -p whatsapp-gateway-tests -f tests/compose.yml down --volumes
    Remove-Item Env:TEST_DB_PASSWORD,Env:TEST_DATABASE_URL,Env:TEST_REDIS_URL -ErrorAction SilentlyContinue
}
exit $testExit
