[CmdletBinding()]
param([string]$PythonPath = $env:PARKING_PYTHON, [switch]$IncludeTestCompiler)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Check-Native([string]$Description) {
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" }
}
if (-not $PythonPath) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $PythonPath = (& py -3 -c 'import sys; print(sys.executable)').Trim() }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Pass -PythonPath with a real Python executable, not a Windows Store alias.' }
foreach ($tool in @('git','node','npm.cmd')) { Get-Command $tool -ErrorAction Stop | Out-Null }
& $PythonPath -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required; tested with 3.14"'; Check-Native 'Python version check'
$env:PARKING_PYTHON = $PythonPath
$frontend = Join-Path $PSScriptRoot 'smart-parking-web'
$pinned = '9546209475df899161187155fc3d6deab822eece'
if (-not (Test-Path -LiteralPath $frontend)) {
    & git clone --no-checkout -- https://github.com/hxnwls/smart-parking-web.git $frontend; Check-Native 'Frontend clone'
    & git -C $frontend checkout --detach $pinned; Check-Native 'Pinned frontend checkout'
} else {
    $actual = (& git -C $frontend rev-parse HEAD).Trim(); Check-Native 'Existing frontend inspection'
    if ($actual -ne $pinned) { throw 'Existing frontend differs from the documented pin. No files were changed; inspect it separately.' }
}
& $PythonPath -m pip install --target (Join-Path $PSScriptRoot 'integration-validation/demo/mqtt/vendor') -r (Join-Path $PSScriptRoot 'integration-validation/demo/mqtt/requirements.txt'); Check-Native 'Paho installation'
& npm.cmd ci --prefix (Join-Path $PSScriptRoot 'integration-validation/demo/mqtt'); Check-Native 'Broker dependency installation'
& npm.cmd ci --prefix (Join-Path $PSScriptRoot 'integration-validation/demo/browser'); Check-Native 'Playwright dependency installation'
if ($IncludeTestCompiler) {
    & $PythonPath -m pip install --target (Join-Path $PSScriptRoot 'integration-validation/demo/sensor-wokwi/tools') ziglang==0.15.1; Check-Native 'Host-test compiler installation'
}
$edgePaths = @('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe')
if (-not ($edgePaths | Where-Object { Test-Path -LiteralPath $_ })) { throw 'Install Microsoft Edge before using Multi/Live modes or browser tests.' }
Write-Output 'Setup complete. In the terminal that starts the demo, set PARKING_PYTHON to your real Python executable. See README.md.'
