$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\xiemo\Desktop\ShardForge'
$review = Join-Path $repo 'vesselforge\tmp\review_20261004\profile_catalog'
$python = Join-Path $repo 'third_party\vesselforge-runtime\venv\Scripts\python.exe'
$script = Join-Path $review 'freeze_candidate_mesh_plan.py'
$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $repo
$startedUtc = [DateTime]::UtcNow.ToString('o')
$lines = @(& $python $script 2>&1)
$exitCode = $LASTEXITCODE
$finishedUtc = [DateTime]::UtcNow.ToString('o')
$lines | ForEach-Object { [string]$_ } | Set-Content -LiteralPath (Join-Path $review 'freeze_output.txt') -Encoding utf8
Set-Content -LiteralPath (Join-Path $review 'freeze_exit_code.txt') -Value ([string]$exitCode) -Encoding ascii
$record = [ordered]@{
    cwd = $repo
    shell_command = "& '$script'"
    executable = $python
    argv = @($script)
    environment = @{ PYTHONDONTWRITEBYTECODE = '1' }
    started_utc = $startedUtc
    finished_utc = $finishedUtc
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $review 'freeze_argv.json') -Encoding utf8
$hashes = @{}
foreach ($relative in @(
    'vesselforge/src/vesselforge/profile_catalog.py',
    'vesselforge/tests/test_profile_catalog.py',
    'vesselforge/src/vesselforge/geometry.py',
    'vesselforge/pyproject.toml',
    'third_party/vesselforge-runtime/venv/Scripts/python.exe',
    'vesselforge/tmp/review_20261004/profile_catalog/freeze_candidate_mesh_plan.py',
    'vesselforge/tmp/review_20261004/profile_catalog/run_freeze_candidate_mesh_plan.ps1',
    'vesselforge/tmp/review_20261004/profile_catalog/generate_candidate_meshes.py',
    'vesselforge/tmp/review_20261004/profile_catalog/run_candidate_meshes.ps1',
    'vesselforge/tmp/review_20261004/profile_catalog/mesh_inputs.json',
    'vesselforge/tmp/review_20261004/profile_catalog/mesh_preflight_receipt.json'
)) {
    $path = Join-Path $repo ($relative -replace '/', '\')
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $hashes[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    } else {
        $hashes[$relative] = $null
    }
}
$receipt = Get-Content -LiteralPath (Join-Path $review 'mesh_preflight_receipt.json') -Raw | ConvertFrom-Json
$expected = $receipt.locked_source_sha256
$sourceMatches = $true
foreach ($property in $expected.PSObject.Properties) {
    if ($hashes[$property.Name] -ne $property.Value) { $sourceMatches = $false }
}
$prelaunch = [ordered]@{
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    freeze_runner_exit_code = $exitCode
    frozen_inputs_sha256 = $receipt.locked_inputs_sha256
    all_locked_source_hashes_match = $sourceMatches
    files = $hashes
}
$prelaunch | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $review 'hashes_pre_mesh.json') -Encoding utf8
if ($null -ne $previousBytecodeSetting) {
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
} else {
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
}
if ($exitCode -ne 0) { exit $exitCode }
if (-not $sourceMatches) { exit 10 }
