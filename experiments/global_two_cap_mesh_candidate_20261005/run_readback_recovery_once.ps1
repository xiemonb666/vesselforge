param()

$ErrorActionPreference = 'Stop'
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$startedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$freezePath = Join-Path $PSScriptRoot 'READBACK_RECOVERY_FREEZE.json'
$freezeShaBefore = $null
$sourceBefore = @{}
$sourceAfter = @{}
$inputBefore = @{}
$inputAfter = @{}
$historyBefore = @{}
$historyAfter = @{}
$childPid = $null
$childRc = $null
$childTimedOut = $false
$artifactCapTriggered = $false
$processTreeKillIssued = $false
$launchError = $null
$status = 'PREPARATION_FAILED'
$outerRc = 2
$recoveryRoot = $null
$createdRecoveryRoot = $false
$freezeShaAfter = $null
$stdoutPath = $null
$stderrPath = $null
$outputDir = $null
$artifactBytesBeforeReceipt = 0
$artifactBytesAfterReceipt = 0
$artifactManifestBeforeReceipt = @()
$maxArtifactBytes = 20MB
$hardTotalMs = 60000
$childWaitDeadlineMs = 50000

function Get-Sha256([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required pinned file is missing: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-RelativeHashMap($PathObject, [string]$BasePath) {
    $result = @{}
    foreach ($entry in $PathObject.PSObject.Properties) {
        $relative = [string]$entry.Name
        $full = Join-Path $BasePath ([string]$entry.Value)
        $result[$relative] = Get-Sha256 $full
    }
    return $result
}

function Get-TreeArtifactBytes([string]$Directory) {
    if (!(Test-Path -LiteralPath $Directory -PathType Container)) { return 0L }
    $files = @(Get-ChildItem -LiteralPath $Directory -File -Recurse -Force)
    if ($files.Count -eq 0) { return 0L }
    return [long](($files | Measure-Object -Property Length -Sum).Sum)
}

function Get-TreeManifest([string]$Directory) {
    $items = @()
    if (Test-Path -LiteralPath $Directory -PathType Container) {
        foreach ($file in (Get-ChildItem -LiteralPath $Directory -File -Recurse -Force | Sort-Object FullName)) {
            $items += [pscustomobject]@{
                path = $file.FullName.Substring($Directory.Length).TrimStart('\','/')
                bytes = [long]$file.Length
                sha256 = Get-Sha256 $file.FullName
            }
        }
    }
    return ,$items
}

function Test-HashMapsEqual($Left, $Right) {
    if ($Left.Count -ne $Right.Count) { return $false }
    foreach ($key in $Left.Keys) {
        if ($Left[$key] -ne $Right[$key]) { return $false }
    }
    return $true
}

try {
    if (!(Test-Path -LiteralPath $freezePath -PathType Leaf)) { throw 'Readback recovery freeze is missing.' }
    $freezeShaBefore = Get-Sha256 $freezePath
    $freeze = Get-Content -LiteralPath $freezePath -Raw | ConvertFrom-Json
    if ($freeze.freeze_id -ne 'ownerfix_saved_npz_readback_recovery_v1') { throw 'Unexpected recovery freeze id.' }
    $pythonPath = Join-Path $repoRoot ([string]$freeze.vf_python_relative_path)
    if ((Get-Sha256 $pythonPath) -ne [string]$freeze.vf_python_sha256) { throw 'VesselForge Python SHA differs from freeze.' }

    $sourceBefore = Get-RelativeHashMap $freeze.source_paths $repoRoot
    $inputBefore = Get-RelativeHashMap $freeze.input_paths $repoRoot
    $historyBefore = Get-RelativeHashMap $freeze.history_paths $repoRoot
    foreach ($pathMap in @(
        @{ Actual = $sourceBefore; Expected = $freeze.source_sha256; Label = 'source' },
        @{ Actual = $inputBefore; Expected = $freeze.input_sha256; Label = 'input' },
        @{ Actual = $historyBefore; Expected = $freeze.history_sha256; Label = 'history' }
    )) {
        foreach ($entry in $pathMap.Expected.PSObject.Properties) {
            if ($pathMap.Actual[$entry.Name] -ne [string]$entry.Value) {
                throw "$($pathMap.Label) SHA mismatch for $($entry.Name)."
            }
        }
        if ($pathMap.Actual.Count -ne $pathMap.Expected.PSObject.Properties.Count) {
            throw "$($pathMap.Label) pin set differs from freeze."
        }
    }
    $candidatePath = Join-Path $repoRoot ([string]$freeze.saved_candidate_npz_relative_path)
    if ((Get-Sha256 $candidatePath) -ne [string]$freeze.saved_candidate_npz_sha256) { throw 'Saved run02 NPZ SHA differs from freeze.' }

    $recoveryRoot = Join-Path $repoRoot ([string]$freeze.output_root_relative_path)
    if (Test-Path -LiteralPath $recoveryRoot) { throw "Refusing to reuse existing recovery output: $recoveryRoot" }
    $outputDir = Join-Path $recoveryRoot 'readback_result'
    $stdoutPath = Join-Path $recoveryRoot 'outer_stdout.log'
    $stderrPath = Join-Path $recoveryRoot 'outer_stderr.log'
    New-Item -ItemType Directory -Path $recoveryRoot | Out-Null
    $createdRecoveryRoot = $true

    $workerPath = Join-Path $repoRoot ([string]$freeze.worker_relative_path)
    $argumentLine = "-B `"$workerPath`" --root-approved-readback --output-dir `"$outputDir`""
    $process = Start-Process -FilePath $pythonPath -ArgumentList $argumentLine -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru -WindowStyle Hidden
    $childPid = $process.Id
    while ($timer.ElapsedMilliseconds -lt $childWaitDeadlineMs) {
        $process.Refresh()
        if ($process.HasExited) { break }
        if ((Get-TreeArtifactBytes $recoveryRoot) -gt $maxArtifactBytes) {
            $artifactCapTriggered = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
    $process.Refresh()
    if (!$process.HasExited -and ($artifactCapTriggered -or $timer.ElapsedMilliseconds -ge $childWaitDeadlineMs)) {
        $childTimedOut = !$artifactCapTriggered
        try {
            $process.Kill($true)
            $processTreeKillIssued = $true
        } catch {
            & taskkill.exe /PID $process.Id /T /F *> $null
            $processTreeKillIssued = $true
        }
        [void]$process.WaitForExit(3000)
    }
    $process.Refresh()
    if ($process.HasExited) { $childRc = [int]$process.ExitCode }

    $sourceAfter = Get-RelativeHashMap $freeze.source_paths $repoRoot
    $inputAfter = Get-RelativeHashMap $freeze.input_paths $repoRoot
    $historyAfter = Get-RelativeHashMap $freeze.history_paths $repoRoot
    $freezeShaAfter = Get-Sha256 $freezePath
    $candidateShaAfter = Get-Sha256 $candidatePath
    $pinsUnchanged = (
        ($freezeShaAfter -eq $freezeShaBefore) -and
        (Test-HashMapsEqual $sourceBefore $sourceAfter) -and
        (Test-HashMapsEqual $inputBefore $inputAfter) -and
        (Test-HashMapsEqual $historyBefore $historyAfter) -and
        ($candidateShaAfter -eq [string]$freeze.saved_candidate_npz_sha256)
    )
    if ($artifactCapTriggered) {
        $status = 'ARTIFACT_CAP_TRIGGERED'
        $outerRc = 125
    } elseif ($childTimedOut) {
        $status = 'CHILD_TIMEOUT'
        $outerRc = 124
    } elseif (!$pinsUnchanged) {
        $status = 'PIN_DRIFT'
        $outerRc = 2
    } elseif ($null -eq $childRc) {
        $status = 'CHILD_RC_UNAVAILABLE'
        $outerRc = 2
    } else {
        $status = 'CHILD_EXITED'
        $outerRc = $childRc
    }
} catch {
    $launchError = $_.Exception.ToString()
    if ($timer.ElapsedMilliseconds -ge $hardTotalMs) {
        $status = 'OUTER_HARD_TIMEOUT'
        $outerRc = 124
    }
}

if ($createdRecoveryRoot -and $null -ne $recoveryRoot -and (Test-Path -LiteralPath $recoveryRoot -PathType Container)) {
    $artifactManifestBeforeReceipt = Get-TreeManifest $recoveryRoot
    $artifactBytesBeforeReceipt = Get-TreeArtifactBytes $recoveryRoot
    $receipt = [ordered]@{
        runner_id = 'ownerfix_saved_npz_readback_outer_v1'
        status = $status
        actual_argv = @($pythonPath, '-B', $workerPath, '--root-approved-readback', '--output-dir', $outputDir)
        working_directory = $repoRoot
        started_at_utc = $startedAtUtc
        elapsed_ms_before_receipt_write = $timer.ElapsedMilliseconds
        completed_at_utc_before_receipt = (Get-Date).ToUniversalTime().ToString('o')
        hard_total_cap_ms_including_cleanup_and_recording = $hardTotalMs
        child_wait_deadline_ms = $childWaitDeadlineMs
        child_pid = $childPid
        child_return_code = $childRc
        child_timed_out = $childTimedOut
        artifact_cap_bytes = $maxArtifactBytes
        artifact_cap_triggered_while_running = $artifactCapTriggered
        artifact_tree_bytes_before_receipt = $artifactBytesBeforeReceipt
        artifact_manifest_before_receipt = $artifactManifestBeforeReceipt
        process_tree_kill_issued = $processTreeKillIssued
        freeze_sha256_before = $freezeShaBefore
        freeze_sha256_after = $freezeShaAfter
        source_sha256_before = $sourceBefore
        source_sha256_after = $sourceAfter
        input_sha256_before = $inputBefore
        input_sha256_after = $inputAfter
        history_sha256_before = $historyBefore
        history_sha256_after = $historyAfter
        launch_error = $launchError
    }
    $receiptPath = Join-Path $recoveryRoot 'outer_runner_receipt.json'
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    $artifactBytesAfterReceipt = Get-TreeArtifactBytes $recoveryRoot
    $receipt.artifact_tree_bytes_after_first_receipt_write = $artifactBytesAfterReceipt
    $receipt.post_run_over_20_mib = $artifactBytesAfterReceipt -gt $maxArtifactBytes
    $receipt.elapsed_ms_before_final_receipt_write = $timer.ElapsedMilliseconds
    $receipt.completed_at_utc_before_final_receipt_write = (Get-Date).ToUniversalTime().ToString('o')
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    $timer.Stop()
    if ($timer.ElapsedMilliseconds -gt $hardTotalMs) { $status = 'OUTER_HARD_CAP_OVERRUN'; $outerRc = 124 }
}

exit $outerRc
