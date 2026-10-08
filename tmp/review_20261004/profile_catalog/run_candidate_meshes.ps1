$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\xiemo\Desktop\ShardForge'
$review = Join-Path $repo 'vesselforge\tmp\review_20261004\profile_catalog'
$python = Join-Path $repo 'third_party\vesselforge-runtime\venv\Scripts\python.exe'
$script = Join-Path $review 'generate_candidate_meshes.py'
$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $repo
$startedUtc = [DateTime]::UtcNow.ToString('o')
$lines = @(& $python $script 2>&1)
$exitCode = $LASTEXITCODE
$finishedUtc = [DateTime]::UtcNow.ToString('o')
$lines | ForEach-Object { [string]$_ } | Set-Content -LiteralPath (Join-Path $review 'mesh_output.txt') -Encoding utf8
Set-Content -LiteralPath (Join-Path $review 'mesh_exit_code.txt') -Value ([string]$exitCode) -Encoding ascii
$record = [ordered]@{
    cwd = $repo
    shell_command = "& '$script'"
    executable = $python
    argv = @($script)
    environment = @{ PYTHONDONTWRITEBYTECODE = '1' }
    started_utc = $startedUtc
    finished_utc = $finishedUtc
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $review 'mesh_argv.json') -Encoding utf8
$hashes = @{}
$relativeFiles = @(
    'vesselforge/src/vesselforge/profile_catalog.py',
    'vesselforge/tests/test_profile_catalog.py',
    'vesselforge/tmp/review_20261004/profile_catalog/generate_candidate_meshes.py',
    'vesselforge/tmp/review_20261004/profile_catalog/run_candidate_meshes.ps1',
    'vesselforge/tmp/review_20261004/profile_catalog/mesh_inputs.json',
    'vesselforge/tmp/review_20261004/profile_catalog/mesh_preflight_receipt.json',
    'vesselforge/tmp/review_20261004/profile_catalog/mesh_output.txt',
    'vesselforge/tmp/review_20261004/profile_catalog/candidate_meshes.json',
    'vesselforge/tmp/review_20261004/profile_catalog/candidate_profiles_mesh.png',
    'vesselforge/tmp/review_20261004/profile_catalog/meshes/bowl.stl',
    'vesselforge/tmp/review_20261004/profile_catalog/meshes/beaker.stl',
    'vesselforge/tmp/review_20261004/profile_catalog/meshes/jar.stl'
)
foreach ($relative in $relativeFiles) {
    $path = Join-Path $repo ($relative -replace '/', '\')
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $hashes[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    } else {
        $hashes[$relative] = $null
    }
}
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $review 'mesh_hashes_after.json') -Encoding utf8
if ($null -ne $previousBytecodeSetting) {
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
} else {
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
}
if ($exitCode -ne 0) { exit $exitCode }
