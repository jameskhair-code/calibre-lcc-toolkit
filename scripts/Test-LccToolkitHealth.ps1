<#
.SYNOPSIS
Runs a health check for the Calibre LCC Toolkit.

.DESCRIPTION
Validates that the toolkit folder structure, configuration file, canonical mapping
files, required scripts, and calibredb.exe are available.

This script is read-only. It does not modify Calibre metadata or toolkit files,
except for optionally writing a health report text file.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-LccToolkitHealth.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-LccToolkitHealth.ps1 `
  -ConfigPath ".\config\lcc-toolkit.config.json" `
  -ReportTxt ".\reports\lcc-toolkit-health.txt"
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = ".\config\lcc-toolkit.config.json",

    [string]$ReportTxt = ".\reports\lcc-toolkit-health.txt",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe"
)

function Get-ToolkitRoot {
    if ($PSScriptRoot) {
        return Split-Path -Parent $PSScriptRoot
    }

    return (Get-Location).Path
}

function Resolve-ToolkitPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ToolkitRoot
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $ToolkitRoot $Path
}

function Add-HealthResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "WARN", "FAIL")]
        [string]$Status,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $script:HealthResults += [pscustomobject]@{
        Name    = $Name
        Status  = $Status
        Message = $Message
    }
}

function Test-Folder {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path $Path) {
        Add-HealthResult -Name $Name -Status "PASS" -Message "Folder found"
    }
    else {
        Add-HealthResult -Name $Name -Status "FAIL" -Message "Folder not found: $Path"
    }
}

function Test-Script {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,

        [Parameter(Mandatory = $true)]
        [string]$ToolkitRoot
    )

    $scriptPath = Resolve-ToolkitPath -Path $RelativePath -ToolkitRoot $ToolkitRoot
    $scriptName = Split-Path -Leaf $RelativePath

    if (Test-Path $scriptPath) {
        Add-HealthResult -Name "Script: $scriptName" -Status "PASS" -Message "Script found"
    }
    else {
        Add-HealthResult -Name "Script: $scriptName" -Status "FAIL" -Message "Script not found: $scriptPath"
    }
}

function Get-CsvRowCount {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    try {
        $rows = @(Import-Csv -Path $Path)
        return $rows.Count
    }
    catch {
        return $null
    }
}

function Write-HealthReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [object[]]$Results,

        [Parameter(Mandatory = $true)]
        [int]$PassCount,

        [Parameter(Mandatory = $true)]
        [int]$WarnCount,

        [Parameter(Mandatory = $true)]
        [int]$FailCount,

        [Parameter(Mandatory = $true)]
        [string]$OverallStatus
    )

    $reportFolder = Split-Path -Path $Path -Parent

    if ($reportFolder -and -not (Test-Path $reportFolder)) {
        New-Item -ItemType Directory -Force -Path $reportFolder | Out-Null
    }

    $lines = New-Object System.Collections.Generic.List[string]

    $lines.Add("Calibre LCC Toolkit Health Check")
    $lines.Add("================================")
    $lines.Add("")
    $lines.Add("Generated: $(Get-Date)")
    $lines.Add("")
    $lines.Add("Results")
    $lines.Add("-------")

    foreach ($result in $Results) {
        $resultLine = "{0} [{1}] {2}" -f $result.Name, $result.Status, $result.Message
		$lines.Add($resultLine)
    }

    $lines.Add("")
    $lines.Add("Summary")
    $lines.Add("-------")
    $lines.Add("PASS: $PassCount")
    $lines.Add("WARN: $WarnCount")
    $lines.Add("FAIL: $FailCount")
    $lines.Add("Status: $OverallStatus")

    $lines | Set-Content -Path $Path -Encoding UTF8
}

$script:HealthResults = @()

$toolkitRoot = Get-ToolkitRoot

$configFullPath = Resolve-ToolkitPath -Path $ConfigPath -ToolkitRoot $toolkitRoot
$reportFullPath = Resolve-ToolkitPath -Path $ReportTxt -ToolkitRoot $toolkitRoot

$inputFolder = Resolve-ToolkitPath -Path ".\input" -ToolkitRoot $toolkitRoot
$reportsFolder = Resolve-ToolkitPath -Path ".\reports" -ToolkitRoot $toolkitRoot
$scriptsFolder = Resolve-ToolkitPath -Path ".\scripts" -ToolkitRoot $toolkitRoot
$docsFolder = Resolve-ToolkitPath -Path ".\docs" -ToolkitRoot $toolkitRoot

$primaryCanonicalCsv = Resolve-ToolkitPath -Path ".\config\lcc-primary-canonical.csv" -ToolkitRoot $toolkitRoot
$secondaryCanonicalCsv = Resolve-ToolkitPath -Path ".\config\lcc-secondary-canonical.csv" -ToolkitRoot $toolkitRoot

Write-Host ""
Write-Host "Calibre LCC Toolkit Health Check"
Write-Host "================================"
Write-Host ""

if (Test-Path $toolkitRoot) {
    Add-HealthResult -Name "Toolkit root" -Status "PASS" -Message "Toolkit root detected"
}
else {
    Add-HealthResult -Name "Toolkit root" -Status "FAIL" -Message "Toolkit root not found: $toolkitRoot"
}

if (Test-Path $configFullPath) {
    Add-HealthResult -Name "Config file" -Status "PASS" -Message "Config file found"

    try {
        $config = Get-Content $configFullPath -Raw | ConvertFrom-Json
        Add-HealthResult -Name "Config parse" -Status "PASS" -Message "Config JSON parsed successfully"
    }
    catch {
        Add-HealthResult -Name "Config parse" -Status "FAIL" -Message "Config JSON failed to parse: $($_.Exception.Message)"
    }
}
else {
    Add-HealthResult -Name "Config file" -Status "FAIL" -Message "Config file not found"
}

Test-Folder -Name "InputFolder" -Path $inputFolder
Test-Folder -Name "ReportsFolder" -Path $reportsFolder
Test-Folder -Name "ScriptsFolder" -Path $scriptsFolder
Test-Folder -Name "DocsFolder" -Path $docsFolder

if (Test-Path $CalibreDb) {
    Add-HealthResult -Name "calibredb.exe" -Status "PASS" -Message "calibredb.exe found"
}
else {
    Add-HealthResult -Name "calibredb.exe" -Status "FAIL" -Message "calibredb.exe not found: $CalibreDb"
}

if (Test-Path $primaryCanonicalCsv) {
    $primaryCount = Get-CsvRowCount -Path $primaryCanonicalCsv

    if ($null -eq $primaryCount) {
        Add-HealthResult -Name "Primary canonical CSV" -Status "FAIL" -Message "Could not read CSV"
    }
    else {
        Add-HealthResult -Name "Primary canonical CSV" -Status "PASS" -Message "Rows: $primaryCount"
    }
}
else {
    Add-HealthResult -Name "Primary canonical CSV" -Status "FAIL" -Message "File not found: $primaryCanonicalCsv"
}

if (Test-Path $secondaryCanonicalCsv) {
    $secondaryCount = Get-CsvRowCount -Path $secondaryCanonicalCsv

    if ($null -eq $secondaryCount) {
        Add-HealthResult -Name "Secondary canonical CSV" -Status "FAIL" -Message "Could not read CSV"
    }
    else {
        Add-HealthResult -Name "Secondary canonical CSV" -Status "PASS" -Message "Rows: $secondaryCount"
    }
}
else {
    Add-HealthResult -Name "Secondary canonical CSV" -Status "FAIL" -Message "File not found: $secondaryCanonicalCsv"
}

$requiredScripts = @(
    ".\scripts\Export-CalibreBatchForLcc.ps1",
    ".\scripts\Test-LccImportDryRun.ps1",
    ".\scripts\Invoke-LccImportApply.ps1",
    ".\scripts\Convert-LccImportToCanonical.ps1",
    ".\scripts\Write-LccBatchSummary.ps1",
    ".\scripts\Show-LccLatestReports.ps1",
    ".\scripts\New-ToolkitBatchManifest.ps1",
    ".\scripts\Test-LccToolkitHealth.ps1"
)

foreach ($requiredScript in $requiredScripts) {
    Test-Script -RelativePath $requiredScript -ToolkitRoot $toolkitRoot
}

$calibreProcesses = @(Get-Process calibre* -ErrorAction SilentlyContinue)

if ($calibreProcesses.Count -eq 0) {
    Add-HealthResult -Name "Calibre process check" -Status "PASS" -Message "No Calibre-related processes detected"
}
else {
    $processNames = ($calibreProcesses | Select-Object -ExpandProperty ProcessName -Unique) -join ", "
    Add-HealthResult -Name "Calibre process check" -Status "WARN" -Message "Calibre-related process detected: $processNames"
}

$script:HealthResults | Format-Table Name, Status, Message -AutoSize

$passCount = @($script:HealthResults | Where-Object { $_.Status -eq "PASS" }).Count
$warnCount = @($script:HealthResults | Where-Object { $_.Status -eq "WARN" }).Count
$failCount = @($script:HealthResults | Where-Object { $_.Status -eq "FAIL" }).Count

if ($failCount -gt 0) {
    $overallStatus = "NEEDS ATTENTION"
}
elseif ($warnCount -gt 0) {
    $overallStatus = "HEALTHY WITH WARNINGS"
}
else {
    $overallStatus = "HEALTHY"
}

Write-Host ""
Write-Host ""
Write-Host "Summary"
Write-Host "-------"
Write-Host "PASS: $passCount"
Write-Host "WARN: $warnCount"
Write-Host "FAIL: $failCount"
Write-Host "Status: $overallStatus"

Write-HealthReport `
    -Path $reportFullPath `
    -Results $script:HealthResults `
    -PassCount $passCount `
    -WarnCount $warnCount `
    -FailCount $failCount `
    -OverallStatus $overallStatus

Write-Host ""
Write-Host "Health report written to: $reportFullPath"