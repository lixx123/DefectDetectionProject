param([string]$ReferenceRoot="",[string]$BuildPython="",[string]$BuildName="engine_release_final")
$ErrorActionPreference='Stop'
$project=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if(!$ReferenceRoot){$ReferenceRoot=Join-Path (Split-Path $project) 'DefectDetectionProject'}
if(!$BuildPython){$BuildPython=Join-Path $project 'output/engine_build_env/Scripts/python.exe'}
$env:ENGINE_PROJECT=$project
$env:ENGINE_REFERENCE_ROOT=$ReferenceRoot
$env:ENGINE_PAYLOAD_OUT=Join-Path $project ('output/'+$BuildName+'_payload')
$env:ENGINE_BUILD_PYTHON=$BuildPython
& $BuildPython (Join-Path $PSScriptRoot 'prepare_engine_payload.py')
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $BuildPython (Join-Path $PSScriptRoot 'build_engine.py') $BuildName
exit $LASTEXITCODE
