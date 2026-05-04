<#
.SYNOPSIS
Shows the latest generated LCC Toolkit report files.

.DESCRIPTION
Displays the newest CSV and TXT report files from the reports folder, sorted by
LastWriteTime descending. This is read-only and does not modify Calibre metadata
or toolkit files.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Show-LccLatestReports.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Show-LccLatestReports.ps1 -MaxResults 15
#>

[CmdletBinding()]
param(
    [string]$ReportsFolder = ".\reports",

    [int]$MaxResults = 12
)

function Resolve-ToolkitPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path (Get-Location) $Path
}

function Get-ReportKind {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FileName
    )

    switch -Regex ($FileName) {
        "health"       { return "Health" }
        "canonicalize" { return "Canonicalize" }
        "dryrun"       { return "Dry Run" }
        "apply"        { return "Apply" }
        "verify"       { return "Verify" }
        "summary"      { return "Summary" }
        default        { return "Other" }
    }
}

$reportsFullPath = Resolve-ToolkitPath -Path $ReportsFolder

if (-not (Test-Path $reportsFullPath)) {
    throw "Reports folder not found: $reportsFullPath"
}

$reportFiles = @(
    Get-ChildItem -Path $reportsFullPath -File |
        Where-Object {
            $_.Extension -in @(".csv", ".txt")
        } |
        Sort-Object LastWriteTime -Descending
)

Write-Host ""
Write-Host "Latest LCC Toolkit Reports"
Write-Host "=========================="
Write-Host ""
Write-Host "Reports folder:"
Write-Host $reportsFullPath
Write-Host ""

if ($reportFiles.Count -eq 0) {
    Write-Host "No report files found."
    exit 0
}

$latestReports = $reportFiles |
    Select-Object -First $MaxResults |
    ForEach-Object {
        [pscustomobject]@{
            Kind          = Get-ReportKind -FileName $_.Name
            Name          = $_.Name
            LastWriteTime = $_.LastWriteTime
            SizeKB        = [math]::Round($_.Length / 1KB, 1)
        }
    }

$latestReports | Format-Table Kind, Name, LastWriteTime, SizeKB -AutoSize

Write-Host ""
Write-Host "Newest by report kind"
Write-Host "---------------------"

$reportFiles |
    Group-Object { Get-ReportKind -FileName $_.Name } |
    Sort-Object Name |
    ForEach-Object {
        $newest = $_.Group | Sort-Object LastWriteTime -Descending | Select-Object -First 1

        [pscustomobject]@{
            Kind          = $_.Name
            Name          = $newest.Name
            LastWriteTime = $newest.LastWriteTime
        }
    } |
    Format-Table Kind, Name, LastWriteTime -AutoSize