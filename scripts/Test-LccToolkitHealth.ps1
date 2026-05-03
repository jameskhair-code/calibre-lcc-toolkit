<#
.SYNOPSIS
Runs a health check for the Calibre LCC Toolkit.

.DESCRIPTION
Validates the toolkit folder structure, config file, canonical mapping files,
required scripts, calibredb.exe path, and whether Calibre appears to be running.

This script does not modify Calibre metadata.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-LccToolkitHealth.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-LccToolkitHealth.ps1 `
  -ReportTxt ".\reports\lcc-toolkit-health.txt"
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = ".\config\lcc-toolkit.config.json",

    [string]$ReportTxt = ""
)

function Get-ToolkitRoot {
    $scriptFolder = Split-Path -Parent $PSCommandPath
    return Split-Path -Parent $scriptFolder
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

function Add-HealthCheck {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message = "",
        [string]$Path = ""
    )

    $script:healthChecks += [pscustomobject]@{
        Name    = $Name
        Status  = $Status
        Message = $Message
        Path    = $Path
    }
}

function Test-CsvColumns {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CsvPath,

        [Parameter(Mandatory = $true)]
        [string[]]$RequiredColumns
    )

    if (-not (Test-Path $CsvPath)) {
        return [pscustomobject]@{
            Success = $false
            Message = "File not found"
        }
    }

    try {
        $rows = @(Import-Csv $CsvPath)

        if ($rows.Count -eq 0) {
            return [pscustomobject]@{
                Success = $false
                Message = "CSV contains no rows"
            }
        }

        $actualColumns = @($rows[0].PSObject.Properties.Name)
        $missingColumns = @()

        foreach ($requiredColumn in $RequiredColumns) {
            if ($actualColumns -notcontains $requiredColumn) {
                $missingColumns += $requiredColumn
            }
        }

        if ($missingColumns.Count -gt 0) {
            return [pscustomobject]@{
                Success = $false
                Message = "Missing column(s): $($missingColumns -join ', ')"
            }
        }

        $blankCanonicalRows = @(
            $rows | Where-Object {
                [string]::IsNullOrWhiteSpace($_.Code) -or
                [string]::IsNullOrWhiteSpace($_.CanonicalValue)
            }
        )

        if ($blankCanonicalRows.Count -gt 0) {
            return [pscustomobject]@{
                Success = $false
                Message = "Rows with blank Code or CanonicalValue: $($blankCanonicalRows.Count)"
            }
        }

        $duplicateCodes = @(
            $rows |
                Group-Object Code |
                Where-Object { $_.Count -gt 1 }
        )

        if ($duplicateCodes.Count -gt 0) {
            return [pscustomobject]@{
                Success = $false
                Message = "Duplicate Code value(s): $($duplicateCodes.Name -join ', ')"
            }
        }

        return [pscustomobject]@{
            Success = $true
            Message = "Rows: $($rows.Count)"
        }
    }
    catch {
        return [pscustomobject]@{
            Success = $false
            Message = $_.Exception.Message
        }
    }
}

$toolkitRoot = Get-ToolkitRoot
$healthChecks = @()

Add-HealthCheck `
    -Name "Toolkit root" `
    -Status "PASS" `
    -Message "Toolkit root detected" `
    -Path $toolkitRoot

$configFullPath = Resolve-ToolkitPath -Path $ConfigPath -ToolkitRoot $toolkitRoot

if (Test-Path $configFullPath) {
    Add-HealthCheck `
        -Name "Config file" `
        -Status "PASS" `
        -Message "Config file found" `
        -Path $configFullPath

    try {
        $config = Get-Content $configFullPath -Raw | ConvertFrom-Json
        Add-HealthCheck `
            -Name "Config parse" `
            -Status "PASS" `
            -Message "Config JSON parsed successfully" `
            -Path $configFullPath
    }
    catch {
        Add-HealthCheck `
            -Name "Config parse" `
            -Status "FAIL" `
            -Message $_.Exception.Message `
            -Path $configFullPath

        $config = $null
    }
}
else {
    Add-HealthCheck `
        -Name "Config file" `
        -Status "FAIL" `
        -Message "Config file not found" `
        -Path $configFullPath

    $config = $null
}

if ($null -ne $config) {
    $folderProperties = @(
        "InputFolder",
        "ReportsFolder",
        "ScriptsFolder",
        "DocsFolder"
    )

    foreach ($folderProperty in $folderProperties) {
        $folderValue = [string]$config.$folderProperty
        $folderPath = Resolve-ToolkitPath -Path $folderValue -ToolkitRoot $toolkitRoot

        if (Test-Path $folderPath) {
            Add-HealthCheck `
                -Name $folderProperty `
                -Status "PASS" `
                -Message "Folder found" `
                -Path $folderPath
        }
        else {
            Add-HealthCheck `
                -Name $folderProperty `
                -Status "FAIL" `
                -Message "Folder not found" `
                -Path $folderPath
        }
    }

    $calibreDbPath = [string]$config.CalibreDbPath

    if (Test-Path $calibreDbPath) {
        Add-HealthCheck `
            -Name "calibredb.exe" `
            -Status "PASS" `
            -Message "calibredb.exe found" `
            -Path $calibreDbPath
    }
    else {
        Add-HealthCheck `
            -Name "calibredb.exe" `
            -Status "FAIL" `
            -Message "calibredb.exe not found" `
            -Path $calibreDbPath
    }

    $primaryCanonicalPath = Resolve-ToolkitPath -Path ([string]$config.PrimaryClassCanonicalFile) -ToolkitRoot $toolkitRoot
    $secondaryCanonicalPath = Resolve-ToolkitPath -Path ([string]$config.SecondaryClassCanonicalFile) -ToolkitRoot $toolkitRoot

    $requiredCanonicalColumns = @("Code", "CanonicalValue", "LegacyValues")

    $primaryCsvCheck = Test-CsvColumns `
        -CsvPath $primaryCanonicalPath `
        -RequiredColumns $requiredCanonicalColumns

    if ($primaryCsvCheck.Success) {
        Add-HealthCheck `
            -Name "Primary canonical CSV" `
            -Status "PASS" `
            -Message $primaryCsvCheck.Message `
            -Path $primaryCanonicalPath
    }
    else {
        Add-HealthCheck `
            -Name "Primary canonical CSV" `
            -Status "FAIL" `
            -Message $primaryCsvCheck.Message `
            -Path $primaryCanonicalPath
    }

    $secondaryCsvCheck = Test-CsvColumns `
        -CsvPath $secondaryCanonicalPath `
        -RequiredColumns $requiredCanonicalColumns

    if ($secondaryCsvCheck.Success) {
        Add-HealthCheck `
            -Name "Secondary canonical CSV" `
            -Status "PASS" `
            -Message $secondaryCsvCheck.Message `
            -Path $secondaryCanonicalPath
    }
    else {
        Add-HealthCheck `
            -Name "Secondary canonical CSV" `
            -Status "FAIL" `
            -Message $secondaryCsvCheck.Message `
            -Path $secondaryCanonicalPath
    }
}

$requiredScripts = @(
    ".\scripts\Export-CalibreBatchForLcc.ps1",
    ".\scripts\Test-LccImportDryRun.ps1",
    ".\scripts\Invoke-LccImportApply.ps1",
    ".\scripts\Convert-LccImportToCanonical.ps1",
    ".\scripts\Write-LccBatchSummary.ps1",
    ".\scripts\Test-LccToolkitHealth.ps1"
)

foreach ($requiredScript in $requiredScripts) {
    $scriptPath = Resolve-ToolkitPath -Path $requiredScript -ToolkitRoot $toolkitRoot

    if (Test-Path $scriptPath) {
        Add-HealthCheck `
            -Name "Script: $(Split-Path -Leaf $scriptPath)" `
            -Status "PASS" `
            -Message "Script found" `
            -Path $scriptPath
    }
    else {
        Add-HealthCheck `
            -Name "Script: $(Split-Path -Leaf $scriptPath)" `
            -Status "FAIL" `
            -Message "Script not found" `
            -Path $scriptPath
    }
}

$calibreProcesses = @(
    Get-Process calibre* -ErrorAction SilentlyContinue
)

if ($calibreProcesses.Count -gt 0) {
    Add-HealthCheck `
        -Name "Calibre process check" `
        -Status "WARN" `
        -Message "Calibre-related process(es) running: $($calibreProcesses.ProcessName -join ', ')" `
        -Path ""
}
else {
    Add-HealthCheck `
        -Name "Calibre process check" `
        -Status "PASS" `
        -Message "No Calibre-related processes detected" `
        -Path ""
}

$failCount = @($healthChecks | Where-Object { $_.Status -eq "FAIL" }).Count
$warnCount = @($healthChecks | Where-Object { $_.Status -eq "WARN" }).Count
$passCount = @($healthChecks | Where-Object { $_.Status -eq "PASS" }).Count

Write-Host ""
Write-Host "Calibre LCC Toolkit Health Check"
Write-Host "================================"
Write-Host ""
$healthChecks | Format-Table Name, Status, Message -AutoSize
Write-Host ""
Write-Host "Summary"
Write-Host "-------"
Write-Host "PASS: $passCount"
Write-Host "WARN: $warnCount"
Write-Host "FAIL: $failCount"

if ($failCount -eq 0 -and $warnCount -eq 0) {
    Write-Host "Status: HEALTHY"
}
elseif ($failCount -eq 0 -and $warnCount -gt 0) {
    Write-Host "Status: HEALTHY WITH WARNINGS"
}
else {
    Write-Host "Status: NEEDS ATTENTION"
}

if (-not [string]::IsNullOrWhiteSpace($ReportTxt)) {
    $reportFullPath = Resolve-ToolkitPath -Path $ReportTxt -ToolkitRoot $toolkitRoot
    $reportFolder = Split-Path -Parent $reportFullPath

    if ($reportFolder -and -not (Test-Path $reportFolder)) {
        New-Item -ItemType Directory -Force -Path $reportFolder | Out-Null
    }

    $lines = @()
    $lines += "Calibre LCC Toolkit Health Check"
    $lines += "================================"
    $lines += ""
    $lines += "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $lines += "Toolkit Root: $toolkitRoot"
    $lines += ""
    $lines += "Checks"
    $lines += "------"

    foreach ($check in $healthChecks) {
        $lines += "$($check.Status) - $($check.Name) - $($check.Message)"
        if (-not [string]::IsNullOrWhiteSpace($check.Path)) {
            $lines += "  Path: $($check.Path)"
        }
    }

    $lines += ""
    $lines += "Summary"
    $lines += "-------"
    $lines += "PASS: $passCount"
    $lines += "WARN: $warnCount"
    $lines += "FAIL: $failCount"

    if ($failCount -eq 0 -and $warnCount -eq 0) {
        $lines += "Status: HEALTHY"
    }
    elseif ($failCount -eq 0 -and $warnCount -gt 0) {
        $lines += "Status: HEALTHY WITH WARNINGS"
    }
    else {
        $lines += "Status: NEEDS ATTENTION"
    }

    $lines | Set-Content -Path $reportFullPath -Encoding UTF8

    Write-Host ""
    Write-Host "Health report written to: $reportFullPath"
}

if ($failCount -gt 0) {
    exit 1
}

exit 0