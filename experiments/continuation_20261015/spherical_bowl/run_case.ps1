param(
    [Parameter(Mandatory = $true)][string]$PythonExecutable,
    [Parameter(Mandatory = $true)][string]$CaseFile,
    [Parameter(Mandatory = $true)][string]$RunDirectory
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$runner = Join-Path $PSScriptRoot 'run_case.py'
$pythonPath = [System.IO.Path]::GetFullPath($PythonExecutable)
$casePath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $CaseFile))
$runPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $RunDirectory))

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw "Python executable not found: $pythonPath" }
if (-not (Test-Path -LiteralPath $casePath -PathType Leaf)) { throw "Case file not found: $casePath" }
if (Test-Path -LiteralPath $runPath) { throw "Refusing to overwrite existing run directory: $runPath" }
New-Item -ItemType Directory -Path $runPath | Out-Null

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $pythonPath
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.ArgumentList.Add($runner)
$startInfo.ArgumentList.Add('--case')
$startInfo.ArgumentList.Add($casePath)
$startInfo.ArgumentList.Add('--run-dir')
$startInfo.ArgumentList.Add($runPath)

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $startInfo
if (-not $process.Start()) { throw 'Failed to start spherical-bowl case process.' }
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$finished = $process.WaitForExit(60000)
if (-not $finished) {
    $process.Kill($true)
    $process.WaitForExit()
    [System.IO.File]::WriteAllText((Join-Path $runPath 'stdout.txt'), $stdoutTask.GetAwaiter().GetResult(), [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $runPath 'stderr.txt'), $stderrTask.GetAwaiter().GetResult(), [System.Text.UTF8Encoding]::new($false))
    $timeout = [ordered]@{ status = 'TIMEOUT'; wall_seconds_limit = 60; process_id = $process.Id }
    [System.IO.File]::WriteAllText((Join-Path $runPath 'timeout_record.json'), ($timeout | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    exit 124
}
$stdout = $stdoutTask.GetAwaiter().GetResult()
$stderr = $stderrTask.GetAwaiter().GetResult()
[System.IO.File]::WriteAllText((Join-Path $runPath 'stdout.txt'), $stdout, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $runPath 'stderr.txt'), $stderr, [System.Text.UTF8Encoding]::new($false))
exit $process.ExitCode
