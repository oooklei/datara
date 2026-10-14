[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$remote = 'root@192.168.1.9'
$scriptPath = Join-Path $PSScriptRoot 'r3_audit_batch1_remote_verify.sh'
$scriptContent = [IO.File]::ReadAllText($scriptPath).Replace("`r", '')
$scriptContent | & ssh -o BatchMode=yes $remote 'bash -s'
if ($LASTEXITCODE -ne 0) { throw 'R3 audit batch 1 read-only remote verification failed.' }
