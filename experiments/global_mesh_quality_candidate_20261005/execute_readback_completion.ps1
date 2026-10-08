$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$experiment = Join-Path $repo 'vesselforge\experiments\global_mesh_quality_candidate_20261005'
$review = Join-Path $repo 'vesselforge\tmp\review_20261005\global_mesh_quality_candidate'
$completion = Join-Path $review 'completion_review'
$freezePath = Join-Path $experiment 'READBACK_COMPLETION_SOURCE_FREEZE.json'
$adapterPath = Join-Path $experiment 'readback_completion_adapter.py'
$pythonPath = Join-Path $repo 'third_party\vesselforge-runtime\venv\Scripts\python.exe'
$maxSeconds = 120.0
$postProcessReserveSeconds = 2.0
$startedAt = [DateTimeOffset]::UtcNow.ToString('o')
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$childStarted = $false
$childExitCode = $null
$timedOut = $false
$stdoutText = ''
$stderrText = ''
$sourceBefore = @()
$sourceAfter = @()
$inputBefore = @()
$inputAfter = @()
$freezeShaBefore = $null
$freezeShaAfter = $null
$pythonShaBefore = $null
$pythonShaAfter = $null
$errorText = $null

function Get-FileRow([string]$RelativePath) {
  $absolute = Join-Path $repo $RelativePath
  $item = Get-Item -LiteralPath $absolute
  $sha = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()
  return [pscustomobject]@{ path = $RelativePath; sha256 = $sha; bytes = [long]$item.Length }
}

function Test-RowsEqual($Left, $Right) {
  if ($Left.Count -ne $Right.Count) { return $false }
  for ($i = 0; $i -lt $Left.Count; $i++) {
    if ($Left[$i].path -ne $Right[$i].path -or $Left[$i].sha256 -ne $Right[$i].sha256 -or $Left[$i].bytes -ne $Right[$i].bytes) {
      return $false
    }
  }
  return $true
}

try {
  if (Test-Path -LiteralPath $completion) { throw "completion_review already exists; refusing reuse: $completion" }
  $freeze = Get-Content -LiteralPath $freezePath -Raw | ConvertFrom-Json
  if ($freeze.state -ne 'SOURCE_ONLY_AWAITING_ROOT_REVIEW' -or $freeze.execution_authorized -ne $false) {
    throw 'readback completion freeze is not in its source-only pre-approval state'
  }
  $freezeShaBefore = (Get-FileHash -LiteralPath $freezePath -Algorithm SHA256).Hash.ToLowerInvariant()
  $sourceBefore = @($freeze.source_files | ForEach-Object { Get-FileRow $_.path })
  $inputBefore = @($freeze.immutable_files | ForEach-Object { Get-FileRow $_.path })
  for ($i = 0; $i -lt $sourceBefore.Count; $i++) {
    if ($sourceBefore[$i].sha256 -ne $freeze.source_files[$i].sha256) { throw "source pin mismatch: $($sourceBefore[$i].path)" }
  }
  for ($i = 0; $i -lt $inputBefore.Count; $i++) {
    if ($inputBefore[$i].sha256 -ne $freeze.immutable_files[$i].sha256) { throw "immutable file pin mismatch: $($inputBefore[$i].path)" }
  }
  if ($freeze.execution_cap_seconds -gt $maxSeconds) { throw 'frozen execution cap exceeds 120 seconds' }
  $pythonShaBefore = (Get-FileHash -LiteralPath $pythonPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($pythonShaBefore -ne $freeze.python_runtime_sha256) { throw 'VesselForge Python runtime hash differs from the reviewed pin' }
  $remainingWaitMs = [int](($maxSeconds - $postProcessReserveSeconds) * 1000 - $timer.Elapsed.TotalMilliseconds)
  if ($remainingWaitMs -le 0) { throw 'pre-launch verification consumed the fixed execution budget' }

  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $pythonPath
  $psi.Arguments = '-B "' + $adapterPath + '"'
  $psi.WorkingDirectory = $repo
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.EnvironmentVariables['MPLCONFIGDIR'] = Join-Path $completion '.matplotlib'
  $readbackProcess = [System.Diagnostics.Process]::new()
  $readbackProcess.StartInfo = $psi
  $null = $readbackProcess.Start()
  $childStarted = $true
  $stdoutTask = $readbackProcess.StandardOutput.ReadToEndAsync()
  $stderrTask = $readbackProcess.StandardError.ReadToEndAsync()
  $completedWithinCap = $readbackProcess.WaitForExit($remainingWaitMs)
  if (-not $completedWithinCap) {
    $timedOut = $true
    $readbackProcess.Kill()
    $readbackProcess.WaitForExit()
  }
  $childExitCode = [int]$readbackProcess.ExitCode
  $stdoutText = $stdoutTask.GetAwaiter().GetResult()
  $stderrText = $stderrTask.GetAwaiter().GetResult()
  $timer.Stop()
  $finishedAt = [DateTimeOffset]::UtcNow.ToString('o')

  if (-not (Test-Path -LiteralPath $completion)) { New-Item -ItemType Directory -Path $completion | Out-Null }
  [System.IO.File]::WriteAllText((Join-Path $completion 'runner_stdout.txt'), $stdoutText, [System.Text.UTF8Encoding]::new($false))
  [System.IO.File]::WriteAllText((Join-Path $completion 'runner_stderr.txt'), $stderrText, [System.Text.UTF8Encoding]::new($false))

  $sourceAfter = @($freeze.source_files | ForEach-Object { Get-FileRow $_.path })
  $inputAfter = @($freeze.immutable_files | ForEach-Object { Get-FileRow $_.path })
  $freezeShaAfter = (Get-FileHash -LiteralPath $freezePath -Algorithm SHA256).Hash.ToLowerInvariant()
  $pythonShaAfter = (Get-FileHash -LiteralPath $pythonPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $checks = [ordered]@{
    sources_unchanged = Test-RowsEqual $sourceBefore $sourceAfter
    immutable_files_unchanged = Test-RowsEqual $inputBefore $inputAfter
    source_freeze_unchanged = ($freezeShaBefore -eq $freezeShaAfter)
    python_runtime_unchanged = ($pythonShaBefore -eq $pythonShaAfter)
  }
  $outputFiles = @(Get-ChildItem -LiteralPath $completion -File -Recurse | Where-Object Name -ne 'execution_receipt.json' | ForEach-Object {
    [pscustomobject]@{
      path = $_.FullName.Substring($completion.Length + 1)
      bytes = [long]$_.Length
      sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
  })
  $stdoutRow = Get-FileRow 'vesselforge/tmp/review_20261005/global_mesh_quality_candidate/completion_review/runner_stdout.txt'
  $stderrRow = Get-FileRow 'vesselforge/tmp/review_20261005/global_mesh_quality_candidate/completion_review/runner_stderr.txt'
  $receipt = [ordered]@{
    completion_label = if ($childExitCode -eq 0 -and -not $timedOut) { 'RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN' } else { 'RECOVERED_READBACK_WITH_DISCREPANCY' }
    status = if ($timedOut) { 'TIMEOUT_TERMINATED' } elseif ($childExitCode -eq 0) { 'READBACK_EXECUTION_EXIT_0' } else { 'READBACK_EXECUTION_NONZERO' }
    run_id = 'run02_v2bugfix'
    child_process = [ordered]@{
      executable = $pythonPath
      argv = @($pythonPath, '-B', $adapterPath)
      exit_code = $childExitCode
      exit_code_source = 'System.Diagnostics.Process.ExitCode captured after WaitForExit'
      started = $childStarted
      timed_out = $timedOut
    }
    started_at_utc = $startedAt
    finished_at_utc = $finishedAt
    elapsed_seconds = [math]::Round($timer.Elapsed.TotalSeconds, 6)
    execution_cap_seconds = $maxSeconds
    post_process_reserve_seconds = $postProcessReserveSeconds
    source_freeze_sha256_before = $freezeShaBefore
    source_freeze_sha256_after = $freezeShaAfter
    python_runtime_sha256_before = $pythonShaBefore
    python_runtime_sha256_after = $pythonShaAfter
    hashes = $checks
    sources_before = $sourceBefore
    sources_after = $sourceAfter
    immutable_files_before = $inputBefore
    immutable_files_after = $inputAfter
    stdout = $stdoutRow
    stderr = $stderrRow
    output_files = $outputFiles
    original_run02_receipt_modified = $false
    candidate_generation_invoked = $false
    candidate_main_invoked = $false
    cad_or_solver_invoked = $false
    automatic_retry = $false
  }
  [System.IO.File]::WriteAllText((Join-Path $completion 'execution_receipt.json'), ($receipt | ConvertTo-Json -Depth 12), [System.Text.UTF8Encoding]::new($false))
  if ($timedOut) { exit 124 }
  exit $childExitCode
} catch {
  $errorText = $_.Exception.Message
  $timer.Stop()
  if (-not (Test-Path -LiteralPath $completion)) { New-Item -ItemType Directory -Path $completion | Out-Null }
  [System.IO.File]::WriteAllText((Join-Path $completion 'runner_stdout.txt'), $stdoutText, [System.Text.UTF8Encoding]::new($false))
  [System.IO.File]::WriteAllText((Join-Path $completion 'runner_stderr.txt'), $stderrText, [System.Text.UTF8Encoding]::new($false))
  $errorReceipt = [ordered]@{
    completion_label = 'RECOVERED_READBACK_WITH_DISCREPANCY'
    status = 'RUNNER_ERROR'
    error = $errorText
    child_process_started = $childStarted
    actual_child_exit_code = $childExitCode
    actual_child_exit_code_captured = ($childStarted -and $null -ne $childExitCode)
    started_at_utc = $startedAt
    finished_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    elapsed_seconds = [math]::Round($timer.Elapsed.TotalSeconds, 6)
    execution_cap_seconds = $maxSeconds
    candidate_generation_invoked = $false
    candidate_main_invoked = $false
    cad_or_solver_invoked = $false
    automatic_retry = $false
  }
  [System.IO.File]::WriteAllText((Join-Path $completion 'execution_receipt.json'), ($errorReceipt | ConvertTo-Json -Depth 10), [System.Text.UTF8Encoding]::new($false))
  exit 3
}
