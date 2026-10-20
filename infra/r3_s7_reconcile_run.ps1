[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][int]$ProjectId,
    [Parameter(Mandatory = $true)][int]$SourceAssetId,
    [Parameter(Mandatory = $true)][int]$TargetAssetId,
    [Parameter(Mandatory = $true)][int]$TagId,
    [Parameter(Mandatory = $true)][int]$QualityRuleId,
    [Parameter(Mandatory = $true)][int]$LineageId,
    [Parameter(Mandatory = $true)][int]$StandardId,
    [Parameter(Mandatory = $true)][int]$MetricId,
    [Parameter(Mandatory = $true)][string]$AuditFrom,
    [Parameter(Mandatory = $true)][string]$AuditTo
)

$ErrorActionPreference = 'Stop'
$remote = 'root@192.168.1.9'
$scriptPath = Join-Path $PSScriptRoot 'r3_s7_reconcile_run.sh'
$remoteCommand = "bash -s -- $ProjectId $SourceAssetId $TargetAssetId $TagId $QualityRuleId $LineageId $StandardId $MetricId '$AuditFrom' '$AuditTo'"
$scriptContent = [IO.File]::ReadAllText($scriptPath).Replace("`r", '')
$scriptContent | & ssh -o BatchMode=yes $remote $remoteCommand
if ($LASTEXITCODE -ne 0) { throw 'Read-only R3 UI-run reconciliation failed.' }
