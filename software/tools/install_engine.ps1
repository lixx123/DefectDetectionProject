param([ValidateSet('list','install','select')][string]$Command='list',[string]$Package='', [string]$EngineId='reference',[string]$EngineVersion='1.0.0')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$report=Join-Path $root 'output/runtime/engine_tool_receipt.json'
$argsList=@('--engine-tool','--release-root',$root,'--report',$report,$Command)
if($Command -eq 'install') {if(!$Package){throw 'Package is required'};$argsList+=$Package}
if($Command -eq 'select') {$argsList+=@($EngineId,$EngineVersion)}
$escaped=$argsList | ForEach-Object {'"'+$_+'"'}
$p=Start-Process -FilePath (Join-Path $root 'DefectInspectionSoftware.exe') -ArgumentList $escaped -WindowStyle Hidden -Wait -PassThru
if($p.ExitCode -ne 0){throw 'Engine operation failed. See output/runtime/launcher_error.log'}
Get-Content -LiteralPath $report -Encoding UTF8
