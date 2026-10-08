$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\xiemo\Desktop\ShardForge'
$review = Join-Path $repo 'vesselforge\tmp\review_20261004\profile_catalog'
$python = Join-Path $repo 'third_party\vesselforge-runtime\venv\Scripts\python.exe'
$pytestArgs = @('-m', 'pytest', 'vesselforge/tests/test_profile_catalog.py', '-q', '-p', 'no:cacheprovider')
$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $repo
$startedUtc = [DateTime]::UtcNow.ToString('o')
$lines = @(& $python @pytestArgs 2>&1)
$exitCode = $LASTEXITCODE
$finishedUtc = [DateTime]::UtcNow.ToString('o')
$lines | ForEach-Object { [string]$_ } | Set-Content -LiteralPath (Join-Path $review 'pytest_output.txt') -Encoding utf8
Set-Content -LiteralPath (Join-Path $review 'exit_code.txt') -Value ([string]$exitCode) -Encoding ascii
$argvRecord = [ordered]@{
    cwd = $repo
    executable = $python
    argv = $pytestArgs
    environment = @{ PYTHONDONTWRITEBYTECODE = '1' }
    started_utc = $startedUtc
    finished_utc = $finishedUtc
}
$argvRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $review 'argv.json') -Encoding utf8
$hashes = @{}
foreach ($relative in @('vesselforge/src/vesselforge/profile_catalog.py', 'vesselforge/tests/test_profile_catalog.py', 'vesselforge/tmp/review_20261004/profile_catalog/run_profile_catalog_pytest.ps1', 'vesselforge/tmp/review_20261004/profile_catalog/pytest_output.txt')) {
    $path = Join-Path $repo ($relative -replace '/', '\')
    $hashes[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $review 'hashes_after.json') -Encoding utf8
if ($null -ne $previousBytecodeSetting) {
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
} else {
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
}
if ($exitCode -ne 0) { exit $exitCode }
