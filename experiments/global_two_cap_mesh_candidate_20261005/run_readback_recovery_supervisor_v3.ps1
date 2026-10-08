param([switch]$RootApprovedReadback)

$ErrorActionPreference = 'Stop'
$clock = [System.Diagnostics.Stopwatch]::StartNew()
if (!$RootApprovedReadback) {
    Write-Error 'Root coordination switch is required: pass -RootApprovedReadback after source review.'
    exit 2
}

$hardWallMs = 60000
$runnerDeadlineMs = 55000
$cleanupReserveMs = 3000
$artifactLimitBytes = 20MB
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$freezePath = Join-Path $PSScriptRoot 'READBACK_RECOVERY_FREEZE_v3.json'
$innerProcess = $null
$timeout = $false
$artifactLimitTriggered = $false
$treeKillIssued = $false
$childRc = $null
$status = 'PREPARATION_FAILED'
$finalRc = 2
$rootOut = $null
$innerPath = $null
$hostExe = (Get-Process -Id $PID).Path
$finalArtifactBytes = 0L

function Get-TreeBytes([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Container)) { return 0L }
    $files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force)
    if ($files.Count -eq 0) { return 0L }
    return [long](($files | Measure-Object -Property Length -Sum).Sum)
}

try {
    $freeze = Get-Content -LiteralPath $freezePath -Raw | ConvertFrom-Json
    if ($freeze.freeze_id -ne 'ownerfix_saved_npz_readback_recovery_v3') { throw 'Unexpected v3 freeze id.' }
    $supervisorRelative = [string]$freeze.supervisor_relative_path
    $supervisorPath = Join-Path $repoRoot $supervisorRelative
    $actualSupervisorSha = (Get-FileHash -LiteralPath $supervisorPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedSupervisorSha = [string]$freeze.source_sha256.'run_readback_recovery_supervisor_v3.ps1'
    if ($actualSupervisorSha -ne $expectedSupervisorSha) { throw 'Supervisor source differs from the reviewed v3 freeze.' }

    $rootOut = Join-Path $repoRoot ([string]$freeze.output_root_relative_path)
    if (Test-Path -LiteralPath $rootOut) { throw "Refusing to reuse the v3 output directory: $rootOut" }
    $innerPath = Join-Path $repoRoot ([string]$freeze.inner_runner_relative_path)
    $argumentLine = "-NoProfile -ExecutionPolicy Bypass -File `"$innerPath`" -RootApprovedReadback"
    $innerProcess = Start-Process -FilePath $hostExe -ArgumentList $argumentLine -WorkingDirectory $repoRoot `
        -PassThru -WindowStyle Hidden

    while ($clock.ElapsedMilliseconds -lt $runnerDeadlineMs) {
        $innerProcess.Refresh()
        if ($innerProcess.HasExited) { break }
        if ((Get-TreeBytes $rootOut) -gt $artifactLimitBytes) {
            $artifactLimitTriggered = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
    $innerProcess.Refresh()
    if (!$innerProcess.HasExited -and ($artifactLimitTriggered -or $clock.ElapsedMilliseconds -ge $runnerDeadlineMs)) {
        $timeout = !$artifactLimitTriggered
        try {
            $innerProcess.Kill($true)
            $treeKillIssued = $true
        } catch {
            & taskkill.exe /PID $innerProcess.Id /T /F *> $null
            $treeKillIssued = $true
        }
        [void]$innerProcess.WaitForExit($cleanupReserveMs)
    }
    $innerProcess.Refresh()
    if ($innerProcess.HasExited) { $childRc = [int]$innerProcess.ExitCode }
    $finalArtifactBytes = Get-TreeBytes $rootOut

    if ($artifactLimitTriggered -or $finalArtifactBytes -gt $artifactLimitBytes) {
        $status = 'ARTIFACT_CAP_EXCEEDED'
        $finalRc = 125
    } elseif ($timeout) {
        $status = 'SUPERVISOR_TIMEOUT'
        $finalRc = 124
    } elseif ($null -eq $childRc) {
        $status = 'INNER_RUNNER_RC_UNAVAILABLE'
        $finalRc = 2
    } else {
        $status = 'INNER_RUNNER_EXITED'
        $finalRc = $childRc
    }
    if ($clock.ElapsedMilliseconds -gt $hardWallMs -and !$artifactLimitTriggered) {
        $status = 'SUPERVISOR_HARD_LIMIT_OVERRUN'
        $finalRc = 124
    }
} catch {
    $status = 'SUPERVISOR_ERROR'
    $finalRc = 2
    Write-Output ("SUPERVISOR_ERROR " + $_.Exception.ToString())
}

$clock.Stop()
$result = [ordered]@{
    supervisor_id = 'ownerfix_saved_npz_readback_supervisor_v3'
    status = $status
    return_code = $finalRc
    inner_runner_return_code = $childRc
    actual_argv = @($hostExe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $innerPath, '-RootApprovedReadback')
    hard_wall_limit_ms = $hardWallMs
    elapsed_ms = $clock.ElapsedMilliseconds
    wait_deadline_from_supervisor_start_ms = $runnerDeadlineMs
    process_tree_kill_wait_ms = $cleanupReserveMs
    process_tree_kill_issued = $treeKillIssued
    timed_out = $timeout
    artifact_limit_bytes = $artifactLimitBytes
    artifact_limit_triggered_while_running = $artifactLimitTriggered
    final_artifact_bytes = $finalArtifactBytes
    final_artifact_bytes_measured_after_inner_exit = $true
}
Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)
exit $finalRc
