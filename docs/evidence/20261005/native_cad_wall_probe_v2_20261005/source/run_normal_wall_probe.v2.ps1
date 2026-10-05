$ErrorActionPreference = 'Stop'
$root = 'C:\Users\xiemo\Desktop\ShardForge'
$python = Join-Path $root 'third_party\vesselforge-runtime\venv\Scripts\python.exe'
$script = Join-Path $root 'vesselforge\tmp\review_20261005\native_cad_wall_probe_20261005\normal_wall_probe.v2.py'
$outDir = Split-Path -Parent $script
$step = Join-Path $root 'vesselforge\experiments\smooth_surface_native_adapter_20261005\tmp\runs\single_inner_native_01\candidate.step'
$sourceReceipt = Join-Path (Split-Path -Parent $step) 'run_receipt.json'
$artifacts = @('normal_wall_probe_attempt.lock','normal_wall_probe_data.json','normal_wall_probe_run_manifest.json','normal_wall_probe_render_status.json','normal_wall_probe_section_y0.png','normal_wall_probe_rays_3d.png')
$existing = @($artifacts | Where-Object { Test-Path -LiteralPath (Join-Path $outDir $_) })
if ($existing.Count -gt 0) { throw ('One-shot output already exists; refusing launch: ' + ($existing -join ', ')) }
$before = [ordered]@{
    adapter_sha256 = (Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
    step_sha256 = (Get-FileHash -LiteralPath $step -Algorithm SHA256).Hash.ToLowerInvariant()
    run_receipt_sha256 = (Get-FileHash -LiteralPath $sourceReceipt -Algorithm SHA256).Hash.ToLowerInvariant()
}
if ($before.step_sha256 -ne '9a6ac86efb2d714e5d2d737263307014487fe2e45979c4181f6071c6f0cf6c71' -or
    $before.run_receipt_sha256 -ne '4c17fe03c74a6fe4474d98b3de9305916572910247c64bd144189ca2c3f711c8') {
    throw 'Frozen STEP or run receipt hash mismatch; refusing launch.'
}
$argv = @($python,'-B',$script)
$startedUtc = [DateTime]::UtcNow.ToString('o')
$clock = [Diagnostics.Stopwatch]::StartNew()
$captured = & $python -B $script 2>&1
$processRc = $LASTEXITCODE
$clock.Stop()
$finishedUtc = [DateTime]::UtcNow.ToString('o')
$after = [ordered]@{
    adapter_sha256 = (Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
    step_sha256 = (Get-FileHash -LiteralPath $step -Algorithm SHA256).Hash.ToLowerInvariant()
    run_receipt_sha256 = (Get-FileHash -LiteralPath $sourceReceipt -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifestPath = Join-Path $outDir 'normal_wall_probe_run_manifest.json'
$dataPath = Join-Path $outDir 'normal_wall_probe_data.json'
$worker = if (Test-Path -LiteralPath $dataPath) { Get-Content -LiteralPath $dataPath -Raw | ConvertFrom-Json } else { $null }
$renderStatusPath = Join-Path $outDir 'normal_wall_probe_render_status.json'
$renderStatus = if (Test-Path -LiteralPath $renderStatusPath) { Get-Content -LiteralPath $renderStatusPath -Raw | ConvertFrom-Json } else { $null }
$inner = if (Test-Path -LiteralPath $manifestPath) { Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json } else { $null }
$parent = [ordered]@{
    actual_argv = $argv
    working_directory = $root
    started_utc = $startedUtc
    finished_utc = $finishedUtc
    elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds,3)
    actual_rc = $processRc
    hashes_before = $before
    hashes_after = $after
    source_hashes_unchanged = ($before.adapter_sha256 -eq $after.adapter_sha256 -and $before.step_sha256 -eq $after.step_sha256 -and $before.run_receipt_sha256 -eq $after.run_receipt_sha256)
    worker_status = if ($inner) { $inner.status } else { 'NO_WORKER_MANIFEST' }
    render_status = if ($renderStatus) { $renderStatus.status } else { 'NO_RENDER_STATUS_RECORD' }
    render_status_record = $renderStatus
    step_import_started = if ($worker) { $worker.step_import_started } else { $null }
    step_import_completed = if ($worker) { $worker.step_import_completed } else { $null }
    normal_ray_calls_started = if ($worker) { $worker.ray_calls_started } else { $null }
    ray_candidate_count = if ($worker) { $worker.ray_candidate_count } else { $null }
    total_raw_hits = if ($worker) { $worker.total_raw_hits } else { $null }
    finite_summary = if ($worker) { $worker.finite_summary } else { $null }
    section_png_sha256 = if (Test-Path -LiteralPath (Join-Path $outDir 'normal_wall_probe_section_y0.png')) { (Get-FileHash -LiteralPath (Join-Path $outDir 'normal_wall_probe_section_y0.png') -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    rays_png_sha256 = if (Test-Path -LiteralPath (Join-Path $outDir 'normal_wall_probe_rays_3d.png')) { (Get-FileHash -LiteralPath (Join-Path $outDir 'normal_wall_probe_rays_3d.png') -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    captured_process_output = ($captured | Out-String)
}
$parent | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $outDir 'parent_execution_receipt.json') -Encoding utf8
$parent | ConvertTo-Json -Depth 12
exit $processRc
