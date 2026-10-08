param([switch]$RootApprovedReadback)

$ErrorActionPreference = 'Stop'
if (!$RootApprovedReadback) {
    Write-Error 'Invoke only from the root-coordinated source review with -RootApprovedReadback.'
    exit 2
}
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$startedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$freezePath = Join-Path $PSScriptRoot 'READBACK_RECOVERY_FREEZE_v3.json'
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
$childWaitDeadlineMs = 50000
$cleanupWaitMs = 3000

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

function Convert-ReceiptToBytes($Receipt) {
    $json = $Receipt | ConvertTo-Json -Depth 16
    return ,([System.Text.Encoding]::UTF8.GetBytes($json + [Environment]::NewLine))
}

function Set-FinalReceiptStatus($Receipt, [string]$Label, [int]$Code, [int]$ReturnCode, [long]$ArtifactBytes) {
    if ($Label.Length -gt 40) { throw 'Final receipt status label exceeds its reserved width.' }
    $Receipt.status_label = $Label.PadRight(40)
    $Receipt.status_code = $Code.ToString('D2')
    $Receipt.outer_return_code = $ReturnCode.ToString('D3')
    $Receipt.artifact_bytes_after_final_receipt = $ArtifactBytes.ToString('D12')
}

try {
    if (!(Test-Path -LiteralPath $freezePath -PathType Leaf)) { throw 'Readback recovery freeze is missing.' }
    $freezeShaBefore = Get-Sha256 $freezePath
    $freeze = Get-Content -LiteralPath $freezePath -Raw | ConvertFrom-Json
    if ($freeze.freeze_id -ne 'ownerfix_saved_npz_readback_recovery_v3') { throw 'Unexpected recovery freeze id.' }
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
        if ($pathMap.Actual.Count -ne @($pathMap.Expected.PSObject.Properties).Count) {
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
}

if ($createdRecoveryRoot -and $null -ne $recoveryRoot -and (Test-Path -LiteralPath $recoveryRoot -PathType Container)) {
    $artifactManifestBeforeReceipt = Get-TreeManifest $recoveryRoot
    $artifactBytesBeforeReceipt = Get-TreeArtifactBytes $recoveryRoot
    $receipt = [ordered]@{
        runner_id = 'ownerfix_saved_npz_readback_inner_runner_v3'
        status_label = ''.PadRight(40)
        status_code = '00'
        outer_return_code = '000'
        actual_argv = @($pythonPath, '-B', $workerPath, '--root-approved-readback', '--output-dir', $outputDir)
        working_directory = $repoRoot
        started_at_utc = $startedAtUtc
        elapsed_ms_before_runner_receipt = $timer.ElapsedMilliseconds
        inner_worker_wait_deadline_ms = $childWaitDeadlineMs
        inner_worker_cleanup_wait_ms = $cleanupWaitMs
        independent_outer_supervisor_required = $true
        child_pid = $childPid
        child_return_code = $childRc
        child_timed_out = $childTimedOut
        artifact_cap_bytes = $maxArtifactBytes
        artifact_cap_triggered_during_worker = $artifactCapTriggered
        artifact_bytes_after_worker_before_runner_receipt = [long]$artifactBytesBeforeReceipt
        artifact_manifest_before_runner_receipt = $artifactManifestBeforeReceipt
        artifact_bytes_after_final_receipt = '000000000000'
        artifact_count_stage = 'predicted from exact UTF-8 receipt bytes, then measured after final receipt write'
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
    $baseStatus = $status
    $baseRc = $outerRc
    $baseCode = 2
    if ($artifactCapTriggered -or $artifactBytesBeforeReceipt -gt $maxArtifactBytes) {
        $baseStatus = 'ARTIFACT_CAP_EXCEEDED'
        $baseRc = 125
        $baseCode = 4
    } elseif ($childTimedOut) {
        $baseStatus = 'WORKER_TIMEOUT'
        $baseRc = 124
        $baseCode = 3
    } elseif (!$pinsUnchanged) {
        $baseStatus = 'PIN_DRIFT'
        $baseRc = 2
        $baseCode = 5
    } elseif ($null -eq $childRc) {
        $baseStatus = 'WORKER_RC_UNAVAILABLE'
        $baseRc = 2
        $baseCode = 6
    } elseif ($childRc -eq 0) {
        $baseStatus = 'CHILD_EXITED_OK'
        $baseRc = 0
        $baseCode = 0
    } else {
        $baseStatus = 'CHILD_NONZERO_EXIT'
        $baseRc = $childRc
        $baseCode = 1
    }

    # The count field and status field have fixed widths, so the receipt size
    # is stable when a final cap failure must be reflected in the same receipt.
    Set-FinalReceiptStatus $receipt $baseStatus $baseCode $baseRc 0
    $placeholderBytes = Convert-ReceiptToBytes $receipt
    $predictedFinalBytes = [long]$artifactBytesBeforeReceipt + [long]$placeholderBytes.Length
    if ($predictedFinalBytes -gt $maxArtifactBytes) {
        $baseStatus = 'ARTIFACT_CAP_EXCEEDED'
        $baseRc = 125
        $baseCode = 4
    }
    Set-FinalReceiptStatus $receipt $baseStatus $baseCode $baseRc $predictedFinalBytes
    $encodedReceipt = Convert-ReceiptToBytes $receipt
    $predictedFinalBytes = [long]$artifactBytesBeforeReceipt + [long]$encodedReceipt.Length
    if ($predictedFinalBytes -gt $maxArtifactBytes) {
        $baseStatus = 'ARTIFACT_CAP_EXCEEDED'
        $baseRc = 125
        $baseCode = 4
        Set-FinalReceiptStatus $receipt $baseStatus $baseCode $baseRc $predictedFinalBytes
        $encodedReceipt = Convert-ReceiptToBytes $receipt
    }
    [System.IO.File]::WriteAllBytes($receiptPath, $encodedReceipt)
    $artifactBytesAfterReceipt = Get-TreeArtifactBytes $recoveryRoot
    if ($artifactBytesAfterReceipt -gt $maxArtifactBytes) {
        $baseStatus = 'ARTIFACT_CAP_EXCEEDED'
        $baseRc = 125
        $baseCode = 4
    } elseif ($artifactBytesAfterReceipt -ne $predictedFinalBytes) {
        $baseStatus = 'ARTIFACT_ACCOUNTING_MISMATCH'
        $baseRc = 2
        $baseCode = 7
    }
    Set-FinalReceiptStatus $receipt $baseStatus $baseCode $baseRc $artifactBytesAfterReceipt
    $encodedReceipt = Convert-ReceiptToBytes $receipt
    [System.IO.File]::WriteAllBytes($receiptPath, $encodedReceipt)
    $finalArtifactBytes = Get-TreeArtifactBytes $recoveryRoot
    if ($finalArtifactBytes -gt $maxArtifactBytes) {
        $baseStatus = 'ARTIFACT_CAP_EXCEEDED'
        $baseRc = 125
        $baseCode = 4
    } elseif ($finalArtifactBytes -ne $artifactBytesAfterReceipt) {
        $baseStatus = 'ARTIFACT_ACCOUNTING_MISMATCH'
        $baseRc = 2
        $baseCode = 7
    }
    Set-FinalReceiptStatus $receipt $baseStatus $baseCode $baseRc $finalArtifactBytes
    $encodedReceipt = Convert-ReceiptToBytes $receipt
    [System.IO.File]::WriteAllBytes($receiptPath, $encodedReceipt)
    $finalArtifactBytes = Get-TreeArtifactBytes $recoveryRoot
    $status = $baseStatus
    $outerRc = $baseRc
}

exit $outerRc
