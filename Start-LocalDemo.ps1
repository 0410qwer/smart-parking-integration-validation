[CmdletBinding()]
param(
    [ValidateSet('Multi','Live','Reference','Memory','Replay','Simulation')][string]$Mode = 'Multi',
    [int]$BrokerPort = 18890,
    [int]$HttpPort = 8780,
    [string]$PythonPath = '',
    [string]$Database = '',
    [string]$StreamId = '',
    [string]$SessionDirectory = '',
    [double]$DurationSeconds = 0,
    [switch]$Headless,
    [switch]$SeedCapture,
    [switch]$DemoCycle
)
$ErrorActionPreference = 'Stop'
try {
    if (-not $PythonPath) {
        if ($env:PARKING_PYTHON) { $PythonPath = $env:PARKING_PYTHON }
        else {
            $candidatePython = Join-Path $env:LOCALAPPDATA 'Python/pythoncore-3.14-64/python.exe'
            if (Test-Path -LiteralPath $candidatePython) { $PythonPath = $candidatePython }
            else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
        }
    }
    if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python executable missing: $PythonPath. Pass -PythonPath with an installed Python 3 executable." }
    $supervisor = Join-Path $PSScriptRoot 'integration-validation/demo/local_stack/supervisor.py'
    $demoArgs = @($supervisor, '--mode', $Mode, '--broker-port', "$BrokerPort", '--http-port', "$HttpPort", '--duration', "$DurationSeconds")
    if ($Database) { $demoArgs += @('--database', $Database) }
    if ($StreamId) { $demoArgs += @('--stream', $StreamId) }
    if ($SessionDirectory) { $demoArgs += @('--session-directory', $SessionDirectory) }
    if ($Headless) { $demoArgs += '--headless' }
    if ($SeedCapture) { $demoArgs += '--seed-capture' }
    if ($DemoCycle) { $demoArgs += '--demo-cycle' }
    & $PythonPath @demoArgs
    exit $LASTEXITCODE
} catch {
    Write-Error "Local demo startup failed: $($_.Exception.Message)"
    exit 1
}
