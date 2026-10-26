# Measures DeskCal's startup time, memory, idle CPU and size, as listed in README.md.
#
#   powershell -ExecutionPolicy Bypass -File tools\benchmark.ps1 [path\to\DeskCal.exe]
#
# Quit DeskCal first: only one copy can run at a time. The test copy uses a temporary,
# empty data folder, so your own data is never touched.

param([string]$Exe = (Join-Path $PSScriptRoot "..\build\dist\DeskCal\DeskCal.exe"))

if (-not (Test-Path $Exe)) { throw "DeskCal.exe not found: $Exe (run tools\build.py or pass a path)" }
if (Get-Process DeskCal -ErrorAction SilentlyContinue) { throw "Quit DeskCal before running the benchmark." }

$tmp = Join-Path $env:TEMP ("deskcal_bench_" + [guid]::NewGuid().ToString("N").Substring(0, 6))
New-Item -ItemType Directory $tmp | Out-Null
$env:DESKCAL_DIR = $tmp
$times = @(); $mems = @()
try {
  foreach ($i in 1..3) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process $Exe -ArgumentList "--float" -PassThru
    # DeskCal writes a start line ending in its version once the window is shown
    while (-not ((Test-Path "$tmp\error.log") -and (Select-String -Path "$tmp\error.log" -Pattern " v\d+\.\d+" -Quiet))) {
      Start-Sleep -Milliseconds 25
      if ($sw.Elapsed.TotalSeconds -gt 30) { throw "DeskCal did not start within 30 s" }
    }
    $times += $sw.Elapsed.TotalSeconds
    Start-Sleep -Seconds 5
    $p.Refresh(); $mems += $p.PrivateMemorySize64 / 1MB
    if ($i -eq 3) {
      $c0 = $p.TotalProcessorTime.TotalMilliseconds; $t0 = Get-Date
      Start-Sleep -Seconds 60; $p.Refresh()
      $idle = ($p.TotalProcessorTime.TotalMilliseconds - $c0) / ((Get-Date) - $t0).TotalMilliseconds * 100
    }
    Stop-Process -Id $p.Id -Confirm:$false
    Start-Sleep -Milliseconds 800
    Remove-Item "$tmp\error.log" -ErrorAction SilentlyContinue
  }
} finally {
  $env:DESKCAL_DIR = $null
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

$folder = Split-Path $Exe
$size = (Get-ChildItem $folder -Recurse -File | Measure-Object Length -Sum).Sum
"Startup to window : " + (($times | ForEach-Object { "{0:n2} s" -f $_ }) -join ", ")
"Memory after 5 s  : " + (($mems | ForEach-Object { "{0:n0} MB" -f $_ }) -join ", ")
"Idle CPU (60 s)   : {0:n2} % of one core" -f $idle
"Folder size       : {0:n1} MB" -f ($size / 1MB)
"Machine           : " + (Get-CimInstance Win32_Processor | Select-Object -First 1).Name.Trim() +
  ", {0:n0} GB RAM" -f ((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
