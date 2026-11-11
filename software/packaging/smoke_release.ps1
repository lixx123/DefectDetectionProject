param([Parameter(Mandatory=$true)][string]$ReleaseDir, [string]$EvidenceDir = "")
$ErrorActionPreference = 'Stop'
$exe = Join-Path (Resolve-Path -LiteralPath $ReleaseDir).Path 'DefectInspectionSoftware.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Missing release exe' }
if (!$EvidenceDir) { $EvidenceDir = Join-Path $env:TEMP ('DefectReleaseSmoke_' + [guid]::NewGuid().ToString('N')) }
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
$picture = Join-Path ([System.IO.Path]::GetFullPath($EvidenceDir)) 'release_smoke.png'
$proc = Start-Process -FilePath $exe -WorkingDirectory $env:TEMP -ArgumentList @('--smoke-test','--screenshot',('"' + $picture + '"')) -WindowStyle Hidden -PassThru
if (!$proc.WaitForExit(60000)) { $proc.Kill(); throw 'Release smoke timed out' }
if ($proc.ExitCode -ne 0 -or !(Test-Path -LiteralPath $picture)) { throw 'Release smoke failed' }
if (!(Test-Path -LiteralPath (Join-Path $ReleaseDir 'output/runtime/gui_errors.log'))) { throw 'Runtime log missing' }
Write-Output 'release_exe_smoke = PASS (visible Qt window checked and grabbed inside exe)'
