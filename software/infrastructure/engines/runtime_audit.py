"""Recognize signed Windows security injection, never application dependencies."""
import os,subprocess,json,base64
from pathlib import Path
from app.runtime_paths import logical_path

def security_module_candidate(path,program_data):
    path=logical_path(Path(path));base=Path(program_data)/'Microsoft/Windows Defender/Platform'
    return path.name.casefold()=='mpoav.dll' and path.is_relative_to(base) and len(path.relative_to(base).parts)==2

def verify_security_module(path):
    if not security_module_candidate(path,os.environ.get('ProgramData','C:/ProgramData')):return None
    literal=str(path).replace("'","''")
    command="$s=Get-AuthenticodeSignature -LiteralPath '"+literal+"';[pscustomobject]@{status=[string]$s.Status;subject=$s.SignerCertificate.Subject;sha256=(Get-FileHash -LiteralPath '"+literal+"').Hash.ToLowerInvariant()}|ConvertTo-Json -Compress"
    encoded=base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    shell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    env={k:v for k,v in os.environ.items() if k.casefold() not in ('psmodulepath','pshome')}
    process=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],env=env,capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if process.returncode:return None
    signature=json.loads(process.stdout)
    if signature.get('status')!='Valid' or signature.get('subject')!='CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US':return None
    return dict(path=str(path),**signature,origin='WINDOWS_DEFENDER_INJECTION')
