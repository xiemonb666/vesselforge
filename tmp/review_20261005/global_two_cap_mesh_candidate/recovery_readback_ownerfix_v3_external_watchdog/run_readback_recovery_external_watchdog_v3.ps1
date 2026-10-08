$ErrorActionPreference = 'Stop'
$wall = [System.Diagnostics.Stopwatch]::StartNew()
$startedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
$freezePath = Join-Path $repoRoot 'vesselforge/experiments/global_two_cap_mesh_candidate_20261005/READBACK_RECOVERY_FREEZE_v3.json'
$freezeExpected = 'ef645114cae881eb3257439e5bcc6e529e8b861676a25607ce8adef47d000d59'
$watchRoot = $PSScriptRoot
$stdoutPath = Join-Path $watchRoot 'supervisor.stdout.log'
$stderrPath = Join-Path $watchRoot 'supervisor.stderr.log'
$receiptPath = Join-Path $watchRoot 'external_watchdog_receipt.json'
$freeze = $null
$freezeShaBefore = $null
$freezeShaAfter = $null
$sourceBefore = @{}
$sourceAfter = @{}
$inputBefore = @{}
$inputAfter = @{}
$historyBefore = @{}
$historyAfter = @{}
$candidatePath = $null
$candidateShaBefore = $null
$candidateShaAfter = $null
$supervisor = $null
$supervisorRc = $null
$workerRc = $null
$supervisorTimedOut = $false
$artifactCapTriggered = $false
$treeKillIssued = $false
$launchError = $null
$innerReceipt = $null
$workerReceipt = $null
$checksReport = $null
$mainRoot = $null
$supervisorPath = $null
$argv = @()
$waitDeadlineMs = 52000
$cleanupWaitMs = 3000
$hardWallMs = 60000
$artifactCapBytes = 20MB
$finalStatus = 'PREPARATION_FAILED'
$finalRc = 2
$childPid = $null
$bytesWhileRunning = 0L
$bytesBeforeReceipt = 0L
$bytesAfterReceipt = 0L
$manifestBeforeReceipt = @()
$pinsUnchanged = $false

function Get-Sha256([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing pinned file: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-RelativeHashMap($PathObject) {
    $result = @{}
    foreach ($entry in @($PathObject.PSObject.Properties)) {
        $full = Join-Path $repoRoot ([string]$entry.Value)
        $result[[string]$entry.Name] = Get-Sha256 $full
    }
    return $result
}
function Test-ExpectedMap($Actual, $Expected, [string]$Label) {
    $expectedProperties = @($Expected.PSObject.Properties)
    if ($Actual.Count -ne $expectedProperties.Count) { throw "$Label pin count mismatch: actual=$($Actual.Count), expected=$($expectedProperties.Count)" }
    foreach ($entry in $expectedProperties) {
        if ($Actual[[string]$entry.Name] -ne [string]$entry.Value) { throw "$Label pin mismatch: $($entry.Name)" }
    }
}
function ConvertTo-StringMap($Value) {
    $result = @{}
    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in $Value.Keys) { $result[[string]$key] = [string]$Value[$key] }
    } else {
        foreach ($entry in @($Value.PSObject.Properties)) { $result[[string]$entry.Name] = [string]$entry.Value }
    }
    return $result
}
function Test-MapsSame($Left, $Right) {
    $leftMap = ConvertTo-StringMap $Left
    $rightMap = ConvertTo-StringMap $Right
    if ($leftMap.Count -ne $rightMap.Count) { return $false }
    foreach ($key in $leftMap.Keys) { if ($leftMap[$key] -ne $rightMap[$key]) { return $false } }
    return $true
}
function Get-TreeBytes([string]$Path) {
    if (!$Path -or !(Test-Path -LiteralPath $Path -PathType Container)) { return 0L }
    $files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force)
    if ($files.Count -eq 0) { return 0L }
    return [long](($files | Measure-Object -Property Length -Sum).Sum)
}
function Get-AggregateBytes {
    return [long]((Get-TreeBytes $mainRoot) + (Get-TreeBytes $watchRoot))
}
function Get-Manifest([string]$Path, [string]$Label) {
    $items = @()
    if ($Path -and (Test-Path -LiteralPath $Path -PathType Container)) {
        foreach ($file in (Get-ChildItem -LiteralPath $Path -File -Recurse -Force | Sort-Object FullName)) {
            $items += [pscustomobject]@{
                root = $Label
                path = $file.FullName.Substring($Path.Length).TrimStart('\','/')
                bytes = [long]$file.Length
                sha256 = Get-Sha256 $file.FullName
            }
        }
    }
    return ,$items
}
function Encode-Receipt($Value) {
    $json = $Value | ConvertTo-Json -Depth 32 -Compress
    return ,([System.Text.Encoding]::UTF8.GetBytes($json + [Environment]::NewLine))
}
function Set-ReceiptStatus($Value, [string]$Label, [int]$Code, [int]$ReturnCode, [long]$ArtifactBytes) {
    if ($Label.Length -gt 40) { throw 'Receipt status label exceeds its fixed-width field.' }
    $Value.status = $Label.PadRight(40)
    $Value.status_code = $Code.ToString('D2')
    $Value.external_return_code = $ReturnCode.ToString('D3')
    $Value.artifact_bytes_after_final_receipt = $ArtifactBytes.ToString('D12')
}
function Get-StatusCode([string]$Label) {
    if ($Label -eq 'SUPERVISOR_EXITED_OK') { return 0 }
    if ($Label -eq 'SUPERVISOR_NONZERO_EXIT') { return 1 }
    if ($Label -eq 'SUPERVISOR_TIMEOUT') { return 3 }
    if ($Label -eq 'ARTIFACT_CAP_TRIGGERED' -or $Label -eq 'ARTIFACT_CAP_EXCEEDED') { return 4 }
    if ($Label -eq 'PIN_DRIFT') { return 5 }
    if ($Label -eq 'ARTIFACT_ACCOUNTING_MISMATCH') { return 7 }
    if ($Label -eq 'EXTERNAL_WALL_LIMIT_OVERRUN') { return 8 }
    return 2
}

try {
    if ((Get-Sha256 $freezePath) -ne $freezeExpected) { throw 'v3 freeze SHA differs from root-reviewed pin.' }
    $freezeShaBefore = Get-Sha256 $freezePath
    $freeze = Get-Content -LiteralPath $freezePath -Raw | ConvertFrom-Json
    if ($freeze.freeze_id -ne 'ownerfix_saved_npz_readback_recovery_v3') { throw 'Unexpected recovery freeze id.' }
    $mainRoot = Join-Path $repoRoot ([string]$freeze.output_root_relative_path)
    if (Test-Path -LiteralPath $mainRoot) { throw "Refusing to reuse existing candidate output: $mainRoot" }
    if (Test-Path -LiteralPath $receiptPath) { throw "Refusing to reuse existing watchdog receipt: $receiptPath" }
    $supervisorPath = Join-Path $repoRoot ([string]$freeze.supervisor_relative_path)
    if ((Get-Sha256 $supervisorPath) -ne [string]$freeze.source_sha256.'run_readback_recovery_supervisor_v3.ps1') { throw 'v3 supervisor source SHA mismatch.' }
    $sourceBefore = Get-RelativeHashMap $freeze.source_paths
    $inputBefore = Get-RelativeHashMap $freeze.input_paths
    $historyBefore = Get-RelativeHashMap $freeze.history_paths
    Test-ExpectedMap $sourceBefore $freeze.source_sha256 'source'
    Test-ExpectedMap $inputBefore $freeze.input_sha256 'input'
    Test-ExpectedMap $historyBefore $freeze.history_sha256 'history'
    $candidatePath = Join-Path $repoRoot ([string]$freeze.saved_candidate_npz_relative_path)
    $candidateShaBefore = Get-Sha256 $candidatePath
    if ($candidateShaBefore -ne [string]$freeze.saved_candidate_npz_sha256) { throw 'Saved candidate NPZ SHA mismatch.' }
    $hostExe = (Get-Process -Id $PID).Path
    $argv = @($hostExe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $supervisorPath, '-RootApprovedReadback')
    $supervisor = Start-Process -FilePath $hostExe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$supervisorPath,'-RootApprovedReadback') `
        -WorkingDirectory $repoRoot -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath `
        -PassThru -WindowStyle Hidden
    $childPid = $supervisor.Id
    while ($wall.ElapsedMilliseconds -lt $waitDeadlineMs) {
        $supervisor.Refresh()
        if ($supervisor.HasExited) { break }
        $bytesWhileRunning = Get-AggregateBytes
        if ($bytesWhileRunning -gt $artifactCapBytes) { $artifactCapTriggered = $true; break }
        Start-Sleep -Milliseconds 100
    }
    $supervisor.Refresh()
    if (!$supervisor.HasExited -and ($artifactCapTriggered -or $wall.ElapsedMilliseconds -ge $waitDeadlineMs)) {
        $supervisorTimedOut = !$artifactCapTriggered
        try { $supervisor.Kill($true); $treeKillIssued = $true }
        catch { & taskkill.exe /PID $supervisor.Id /T /F *> $null; $treeKillIssued = $true }
        [void]$supervisor.WaitForExit($cleanupWaitMs)
    }
    $supervisor.Refresh()
    if ($supervisor.HasExited) { $supervisorRc = [int]$supervisor.ExitCode }

    $sourceAfter = Get-RelativeHashMap $freeze.source_paths
    $inputAfter = Get-RelativeHashMap $freeze.input_paths
    $historyAfter = Get-RelativeHashMap $freeze.history_paths
    $freezeShaAfter = Get-Sha256 $freezePath
    $candidateShaAfter = Get-Sha256 $candidatePath
    $pinsUnchanged = (
        ($freezeShaAfter -eq $freezeShaBefore) -and
        (Test-MapsSame $sourceBefore $sourceAfter) -and (Test-MapsSame $sourceBefore $freeze.source_sha256) -and
        (Test-MapsSame $inputBefore $inputAfter) -and (Test-MapsSame $inputBefore $freeze.input_sha256) -and
        (Test-MapsSame $historyBefore $historyAfter) -and (Test-MapsSame $historyBefore $freeze.history_sha256) -and
        ($candidateShaAfter -eq $candidateShaBefore) -and ($candidateShaAfter -eq [string]$freeze.saved_candidate_npz_sha256)
    )
    $innerReceiptPath = Join-Path $mainRoot 'outer_runner_receipt.json'
    if (Test-Path -LiteralPath $innerReceiptPath -PathType Leaf) {
        try { $innerReceipt = Get-Content -LiteralPath $innerReceiptPath -Raw | ConvertFrom-Json; $workerRc = $innerReceipt.child_return_code } catch { $innerReceipt = $null }
    }
    $workerReceiptPath = Join-Path $mainRoot 'readback_result/readback_receipt.json'
    if (Test-Path -LiteralPath $workerReceiptPath -PathType Leaf) {
        try { $workerReceipt = Get-Content -LiteralPath $workerReceiptPath -Raw | ConvertFrom-Json } catch { $workerReceipt = $null }
    }
    $checksPath = Join-Path $mainRoot 'readback_result/readback_checks.json'
    if (Test-Path -LiteralPath $checksPath -PathType Leaf) {
        try { $checksReport = Get-Content -LiteralPath $checksPath -Raw | ConvertFrom-Json } catch { $checksReport = $null }
    }

    if ($artifactCapTriggered) { $finalStatus = 'ARTIFACT_CAP_TRIGGERED'; $finalRc = 125 }
    elseif ($supervisorTimedOut) { $finalStatus = 'SUPERVISOR_TIMEOUT'; $finalRc = 124 }
    elseif (!$pinsUnchanged) { $finalStatus = 'PIN_DRIFT'; $finalRc = 2 }
    elseif ($null -eq $supervisorRc) { $finalStatus = 'SUPERVISOR_RC_UNAVAILABLE'; $finalRc = 2 }
    elseif ($supervisorRc -eq 0) { $finalStatus = 'SUPERVISOR_EXITED_OK'; $finalRc = 0 }
    else { $finalStatus = 'SUPERVISOR_NONZERO_EXIT'; $finalRc = $supervisorRc }
} catch {
    $launchError = $_.Exception.ToString()
    if ($supervisor -and !$supervisor.HasExited) {
        try { $supervisor.Kill($true); $treeKillIssued = $true; [void]$supervisor.WaitForExit($cleanupWaitMs) } catch { }
    }
}

if ($freeze) {
    try {
        if (!$sourceAfter.Count) { $sourceAfter = Get-RelativeHashMap $freeze.source_paths }
        if (!$inputAfter.Count) { $inputAfter = Get-RelativeHashMap $freeze.input_paths }
        if (!$historyAfter.Count) { $historyAfter = Get-RelativeHashMap $freeze.history_paths }
        if (!$freezeShaAfter) { $freezeShaAfter = Get-Sha256 $freezePath }
        if (!$candidateShaAfter -and $candidatePath) { $candidateShaAfter = Get-Sha256 $candidatePath }
    } catch { if (!$launchError) { $launchError = $_.Exception.ToString() } }
}
$bytesBeforeReceipt = Get-AggregateBytes
$manifestBeforeReceipt = @(Get-Manifest $mainRoot 'candidate_output') + @(Get-Manifest $watchRoot 'external_watchdog')
$receipt = [ordered]@{
    watchdog_id = 'ownerfix_saved_npz_readback_external_watchdog_v3'
    status = ''.PadRight(40)
    status_code = '00'
    external_return_code = '000'
    actual_argv = @($argv)
    working_directory = $repoRoot
    started_at_utc = $startedAtUtc
    elapsed_ms_observed_before_final_receipt_write = ([Math]::Min(99999999, [long]$wall.ElapsedMilliseconds)).ToString('D8')
    external_wall_limit_ms = $hardWallMs
    supervisor_wait_deadline_ms = $waitDeadlineMs
    process_tree_cleanup_wait_ms = $cleanupWaitMs
    child_process_id = $childPid
    supervisor_return_code = if ($null -eq $supervisorRc) { 'NULL' } else { ([int]$supervisorRc).ToString('D4') }
    inner_worker_return_code = if ($null -eq $workerRc) { 'NULL' } else { ([int]$workerRc).ToString('D4') }
    supervisor_timed_out = $supervisorTimedOut
    artifact_cap_bytes = $artifactCapBytes
    artifact_cap_triggered_while_running = $artifactCapTriggered
    artifact_bytes_last_observed_while_running = ([long]$bytesWhileRunning).ToString('D12')
    artifact_bytes_before_receipt = ([long]$bytesBeforeReceipt).ToString('D12')
    artifact_bytes_after_final_receipt = '000000000000'
    artifact_count_stages = @('last aggregate byte count while supervisor active', 'aggregate candidate and external files after supervisor exit and before receipt', 'aggregate candidate and external files after final receipt write')
    artifact_manifest_before_receipt = $manifestBeforeReceipt
    source_input_history_pins_unchanged = $pinsUnchanged
    freeze_sha256_before = $freezeShaBefore
    freeze_sha256_after = $freezeShaAfter
    source_sha256_before = $sourceBefore
    source_sha256_after = $sourceAfter
    input_sha256_before = $inputBefore
    input_sha256_after = $inputAfter
    history_sha256_before = $historyBefore
    history_sha256_after = $historyAfter
    saved_candidate_npz_sha256_before = $candidateShaBefore
    saved_candidate_npz_sha256_after = $candidateShaAfter
    candidate_npz_sha256_expected = if ($freeze) { [string]$freeze.saved_candidate_npz_sha256 } else { $null }
    inner_runner_receipt_status = if ($innerReceipt) { [string]$innerReceipt.status } else { $null }
    inner_worker_return_code_recorded = if ($innerReceipt) { [string]$innerReceipt.child_return_code } else { $null }
    readback_receipt_status = if ($workerReceipt) { [string]$workerReceipt.status } else { $null }
    completion_label = if ($workerReceipt) { [string]$workerReceipt.completion_label } else { $null }
    numerical_status = if ($workerReceipt) { [string]$workerReceipt.numerical_status } else { $null }
    render_status = if ($workerReceipt) { [string]$workerReceipt.render_status.status } else { $null }
    focused_checks = if ($checksReport) { $checksReport.checks } else { $null }
    launch_error = $launchError
    tree_kill_issued = $treeKillIssued
}

$statusCode = Get-StatusCode $finalStatus
$placeholder = Encode-Receipt $receipt
$predictedTotal = [long]$bytesBeforeReceipt + [long]$placeholder.Length
if ($predictedTotal -gt $artifactCapBytes) { $finalStatus = 'ARTIFACT_CAP_EXCEEDED'; $finalRc = 125; $statusCode = 4 }
Set-ReceiptStatus $receipt $finalStatus $statusCode $finalRc $predictedTotal
[System.IO.File]::WriteAllBytes($receiptPath, (Encode-Receipt $receipt))
$bytesAfterReceipt = Get-AggregateBytes
if ($bytesAfterReceipt -gt $artifactCapBytes) { $finalStatus = 'ARTIFACT_CAP_EXCEEDED'; $finalRc = 125; $statusCode = 4 }
elseif ($bytesAfterReceipt -ne $predictedTotal) { $finalStatus = 'ARTIFACT_ACCOUNTING_MISMATCH'; $finalRc = 2; $statusCode = 7 }
Set-ReceiptStatus $receipt $finalStatus $statusCode $finalRc $bytesAfterReceipt
[System.IO.File]::WriteAllBytes($receiptPath, (Encode-Receipt $receipt))
$bytesAfterReceipt = Get-AggregateBytes
if ($bytesAfterReceipt -gt $artifactCapBytes) { $finalStatus = 'ARTIFACT_CAP_EXCEEDED'; $finalRc = 125; $statusCode = 4 }
if ($wall.ElapsedMilliseconds -gt $hardWallMs) { $finalStatus = 'EXTERNAL_WALL_LIMIT_OVERRUN'; $finalRc = 124; $statusCode = 8 }
Set-ReceiptStatus $receipt $finalStatus $statusCode $finalRc $bytesAfterReceipt
$receipt.elapsed_ms_observed_before_final_receipt_write = ([Math]::Min(99999999, [long]$wall.ElapsedMilliseconds)).ToString('D8')
[System.IO.File]::WriteAllBytes($receiptPath, (Encode-Receipt $receipt))
$bytesAfterReceipt = Get-AggregateBytes
if ($bytesAfterReceipt -gt $artifactCapBytes -and $finalStatus -ne 'ARTIFACT_CAP_EXCEEDED') {
    $finalStatus = 'ARTIFACT_CAP_EXCEEDED'; $finalRc = 125; $statusCode = 4
    Set-ReceiptStatus $receipt $finalStatus $statusCode $finalRc $bytesAfterReceipt
    [System.IO.File]::WriteAllBytes($receiptPath, (Encode-Receipt $receipt))
    $bytesAfterReceipt = Get-AggregateBytes
}
$wall.Stop()
Write-Output (Get-Content -LiteralPath $receiptPath -Raw)
exit $finalRc

