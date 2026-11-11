param([string]$Python = "", [string]$OutputRoot = "", [switch]$AllowDirtyProbe, [Parameter(Mandatory=$true)][string]$EnginePackage)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (!$Python) { $Python = Join-Path $project '.venv/Scripts/python.exe' }
if (!$OutputRoot) { $OutputRoot = Join-Path $project 'output/phase12_engine_gui' }
$dirty = & git -C $project status --porcelain
if ($LASTEXITCODE -ne 0) { exit 1 }
if ($dirty -and !$AllowDirtyProbe) { throw 'Commit and clean the source before a release build; use -AllowDirtyProbe only for non-deliverable diagnostics.' }
$buildRoot = [System.IO.Path]::GetFullPath($OutputRoot)
# An owned, marked workspace only. Never delete existing directories.
if (Test-Path -LiteralPath $buildRoot) { throw "Output already exists; use a fresh owned build directory: $buildRoot" }
New-Item -ItemType Directory -Path $buildRoot | Out-Null
Set-Content -LiteralPath (Join-Path $buildRoot '.phase12_owned') -Value 'Phase12 build workspace'
$head = (& git -C $project rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { exit 1 }
& $Python -m PyInstaller --noconfirm --workpath (Join-Path $buildRoot 'build') --distpath (Join-Path $buildRoot 'dist') (Join-Path $PSScriptRoot 'defect_inspection.spec')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python (Join-Path $PSScriptRoot 'finalize_release.py') --project $project --release (Join-Path $buildRoot 'dist/DefectInspectionSoftware') --commit $head --engine-package $EnginePackage
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Release: $(Join-Path $buildRoot 'dist/DefectInspectionSoftware')"
Write-Output "Build commit: $head"
