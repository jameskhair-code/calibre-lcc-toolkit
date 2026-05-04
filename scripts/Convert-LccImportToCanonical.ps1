<#
.SYNOPSIS
Normalizes an LCC import TSV against canonical LCC Primary and Secondary Class mappings.

.DESCRIPTION
Reads an import TSV containing LCC metadata and maps legacy/non-canonical
LCC Primary Class and LCC Secondary Class values to the approved canonical values
defined in config/lcc-primary-canonical.csv and config/lcc-secondary-canonical.csv.

This script also supports optional LCC enrichment audit fields:

- LCC Confidence
- LCC Source Notes

These audit fields are preserved in the canonical output TSV and included in the
canonicalization report, but they are not required and are not written to Calibre
by this script.

This script does not modify Calibre metadata. It only creates a new canonicalized TSV
and a validation/canonicalization report.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Convert-LccImportToCanonical.ps1 `
  -InputTsv ".\input\lcc-import-herbert-baxter-adams.tsv" `
  -OutputTsv ".\input\lcc-import-herbert-baxter-adams-canonical.tsv" `
  -ReportCsv ".\reports\lcc-canonicalize-herbert-baxter-adams.csv"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputTsv,

    [string]$OutputTsv = "",

    [string]$ReportCsv = "",

    [string]$ConfigPath = ".\config\lcc-toolkit.config.json",

    [switch]$Overwrite
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

function Normalize-Key {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return (($Value.Trim()) -replace '\s+', ' ')
}

function Add-MapValue {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Map,

        [Parameter(Mandatory = $true)]
        [string]$Key,

        [Parameter(Mandatory = $true)]
        [string]$CanonicalValue
    )

    $normalizedKey = Normalize-Key $Key

    if ([string]::IsNullOrWhiteSpace($normalizedKey)) {
        return
    }

    if (-not $Map.ContainsKey($normalizedKey)) {
        $Map[$normalizedKey] = $CanonicalValue
    }
}

function New-CanonicalMap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CsvPath
    )

    if (-not (Test-Path $CsvPath)) {
        throw "Canonical mapping file not found: $CsvPath"
    }

    $rows = Import-Csv $CsvPath
    $map = New-Object 'System.Collections.Hashtable' ([System.StringComparer]::OrdinalIgnoreCase)
    $allowed = New-Object 'System.Collections.Hashtable' ([System.StringComparer]::OrdinalIgnoreCase)

    foreach ($row in $rows) {
        $code = Normalize-Key $row.Code
        $canonicalValue = Normalize-Key $row.CanonicalValue
        $legacyValuesRaw = [string]$row.LegacyValues

        if ([string]::IsNullOrWhiteSpace($canonicalValue)) {
            continue
        }

        $allowed[$canonicalValue] = $true

        Add-MapValue -Map $map -Key $canonicalValue -CanonicalValue $canonicalValue

        if (-not [string]::IsNullOrWhiteSpace($code)) {
            Add-MapValue -Map $map -Key $code -CanonicalValue $canonicalValue
        }

        if (-not [string]::IsNullOrWhiteSpace($legacyValuesRaw)) {
            $legacyValues = $legacyValuesRaw -split '\|' |
                ForEach-Object { Normalize-Key $_ } |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

            foreach ($legacyValue in $legacyValues) {
                Add-MapValue -Map $map -Key $legacyValue -CanonicalValue $canonicalValue
            }
        }
    }

    return [pscustomobject]@{
        Map     = $map
        Allowed = $allowed
    }
}

function Convert-ToCanonicalValue {
    param(
        [AllowNull()]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [hashtable]$Map,

        [Parameter(Mandatory = $true)]
        [hashtable]$Allowed
    )

    $normalizedValue = Normalize-Key $Value

    if ([string]::IsNullOrWhiteSpace($normalizedValue)) {
        return [pscustomobject]@{
            OriginalValue  = ""
            CanonicalValue = ""
            Status         = "Missing"
            Warning        = "Value is blank"
        }
    }

    if ($Allowed.ContainsKey($normalizedValue)) {
        return [pscustomobject]@{
            OriginalValue  = $normalizedValue
            CanonicalValue = $normalizedValue
            Status         = "AlreadyCanonical"
            Warning        = ""
        }
    }

    if ($Map.ContainsKey($normalizedValue)) {
        return [pscustomobject]@{
            OriginalValue  = $normalizedValue
            CanonicalValue = $Map[$normalizedValue]
            Status         = "Mapped"
            Warning        = ""
        }
    }

    return [pscustomobject]@{
        OriginalValue  = $normalizedValue
        CanonicalValue = $normalizedValue
        Status         = "Unmapped"
        Warning        = "No canonical mapping found"
    }
}

function New-ConfidenceMap {
    $allowedConfidenceValues = @(
        "High - Catalog Confirmed",
        "Medium - Evidence Based",
        "Low - Manual Review Recommended"
    )

    $map = New-Object 'System.Collections.Hashtable' ([System.StringComparer]::OrdinalIgnoreCase)

    foreach ($confidenceValue in $allowedConfidenceValues) {
        $map[$confidenceValue] = $confidenceValue
    }

    return $map
}

function Convert-ToCanonicalConfidence {
    param(
        [AllowNull()]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [hashtable]$AllowedConfidence
    )

    $normalizedValue = Normalize-Key $Value

    if ([string]::IsNullOrWhiteSpace($normalizedValue)) {
        return [pscustomobject]@{
            OriginalValue  = ""
            CanonicalValue = ""
            Status         = "Unspecified"
            Warning        = ""
        }
    }

    if ($AllowedConfidence.ContainsKey($normalizedValue)) {
        return [pscustomobject]@{
            OriginalValue  = $normalizedValue
            CanonicalValue = $AllowedConfidence[$normalizedValue]
            Status         = "Valid"
            Warning        = ""
        }
    }

    return [pscustomobject]@{
        OriginalValue  = $normalizedValue
        CanonicalValue = $normalizedValue
        Status         = "Unexpected"
        Warning        = "Unexpected LCC Confidence value"
    }
}

function Assert-RequiredColumns {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string[]]$RequiredColumns
    )

    if ($Rows.Count -eq 0) {
        throw "Input TSV contains no rows."
    }

    $actualColumns = @($Rows[0].PSObject.Properties.Name)
    $missingColumns = @()

    foreach ($requiredColumn in $RequiredColumns) {
        if ($actualColumns -notcontains $requiredColumn) {
            $missingColumns += $requiredColumn
        }
    }

    if ($missingColumns.Count -gt 0) {
        throw "Input TSV is missing required column(s): $($missingColumns -join ', ')"
    }
}

function Test-ColumnExists {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$ColumnName
    )

    return ($Row.PSObject.Properties.Name -contains $ColumnName)
}

function Get-OptionalColumnValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$ColumnName
    )

    $property = $Row.PSObject.Properties[$ColumnName]

    if ($null -eq $property) {
        return ""
    }

    return [string]$property.Value
}

$toolkitRoot = Get-ToolkitRoot

$configFullPath = Resolve-ToolkitPath -Path $ConfigPath -ToolkitRoot $toolkitRoot

if (-not (Test-Path $configFullPath)) {
    throw "Config file not found: $configFullPath"
}

$config = Get-Content $configFullPath -Raw | ConvertFrom-Json

$inputFullPath = Resolve-ToolkitPath -Path $InputTsv -ToolkitRoot $toolkitRoot

if (-not (Test-Path $inputFullPath)) {
    throw "Input TSV not found: $inputFullPath"
}

if ([string]::IsNullOrWhiteSpace($OutputTsv)) {
    $inputFolder = Split-Path -Parent $inputFullPath
    $inputBaseName = [System.IO.Path]::GetFileNameWithoutExtension($inputFullPath)
    $OutputTsv = Join-Path $inputFolder "$inputBaseName-canonical.tsv"
}

if ([string]::IsNullOrWhiteSpace($ReportCsv)) {
    $reportsFolder = Resolve-ToolkitPath -Path $config.ReportsFolder -ToolkitRoot $toolkitRoot
    $inputBaseName = [System.IO.Path]::GetFileNameWithoutExtension($inputFullPath)
    $ReportCsv = Join-Path $reportsFolder "lcc-canonicalize-$inputBaseName.csv"
}

$outputFullPath = Resolve-ToolkitPath -Path $OutputTsv -ToolkitRoot $toolkitRoot
$reportFullPath = Resolve-ToolkitPath -Path $ReportCsv -ToolkitRoot $toolkitRoot

if ((Test-Path $outputFullPath) -and -not $Overwrite) {
    throw "Output TSV already exists. Use -Overwrite to replace it: $outputFullPath"
}

if ((Test-Path $reportFullPath) -and -not $Overwrite) {
    throw "Report CSV already exists. Use -Overwrite to replace it: $reportFullPath"
}

$outputFolder = Split-Path -Parent $outputFullPath
$reportFolder = Split-Path -Parent $reportFullPath

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

if ($reportFolder -and -not (Test-Path $reportFolder)) {
    New-Item -ItemType Directory -Force -Path $reportFolder | Out-Null
}

$primaryCanonicalPath = Resolve-ToolkitPath -Path $config.PrimaryClassCanonicalFile -ToolkitRoot $toolkitRoot
$secondaryCanonicalPath = Resolve-ToolkitPath -Path $config.SecondaryClassCanonicalFile -ToolkitRoot $toolkitRoot

$primaryMap = New-CanonicalMap -CsvPath $primaryCanonicalPath
$secondaryMap = New-CanonicalMap -CsvPath $secondaryCanonicalPath
$confidenceMap = New-ConfidenceMap

$rows = @(Import-Csv $inputFullPath -Delimiter "`t")

Assert-RequiredColumns -Rows $rows -RequiredColumns $config.RequiredImportColumns

$hasConfidenceColumn = Test-ColumnExists -Row $rows[0] -ColumnName "LCC Confidence"
$hasSourceNotesColumn = Test-ColumnExists -Row $rows[0] -ColumnName "LCC Source Notes"

$reportRows = @()

foreach ($row in $rows) {
    $primaryResult = Convert-ToCanonicalValue `
        -Value $row.'LCC Primary Class' `
        -Map $primaryMap.Map `
        -Allowed $primaryMap.Allowed

    $secondaryResult = Convert-ToCanonicalValue `
        -Value $row.'LCC Secondary Class' `
        -Map $secondaryMap.Map `
        -Allowed $secondaryMap.Allowed

    $row.'LCC Primary Class' = $primaryResult.CanonicalValue
    $row.'LCC Secondary Class' = $secondaryResult.CanonicalValue

    $confidenceOriginal = ""
    $confidenceCanonical = ""
    $confidenceStatus = "NotProvided"
    $confidenceWarning = ""
    $sourceNotes = ""

    if ($hasConfidenceColumn) {
        $confidenceValue = Get-OptionalColumnValue -Row $row -ColumnName "LCC Confidence"

        $confidenceResult = Convert-ToCanonicalConfidence `
            -Value $confidenceValue `
            -AllowedConfidence $confidenceMap

        $confidenceOriginal = $confidenceResult.OriginalValue
        $confidenceCanonical = $confidenceResult.CanonicalValue
        $confidenceStatus = $confidenceResult.Status
        $confidenceWarning = $confidenceResult.Warning

        $row.'LCC Confidence' = $confidenceCanonical
    }

    if ($hasSourceNotesColumn) {
        $sourceNotes = Normalize-Key (Get-OptionalColumnValue -Row $row -ColumnName "LCC Source Notes")
        $row.'LCC Source Notes' = $sourceNotes
    }

    $warnings = @()

    if (-not [string]::IsNullOrWhiteSpace($primaryResult.Warning)) {
        $warnings += "Primary: $($primaryResult.Warning)"
    }

    if (-not [string]::IsNullOrWhiteSpace($secondaryResult.Warning)) {
        $warnings += "Secondary: $($secondaryResult.Warning)"
    }

    if (-not [string]::IsNullOrWhiteSpace($confidenceWarning)) {
        $warnings += "Confidence: $confidenceWarning"
    }

    $reportRows += [pscustomobject]@{
        Title                      = $row.Title
        Author                     = $row.Author
        ISBN                       = $row.ISBN
        OriginalLCCPrimaryClass    = $primaryResult.OriginalValue
        CanonicalLCCPrimaryClass   = $primaryResult.CanonicalValue
        PrimaryStatus              = $primaryResult.Status
        OriginalLCCSecondaryClass  = $secondaryResult.OriginalValue
        CanonicalLCCSecondaryClass = $secondaryResult.CanonicalValue
        SecondaryStatus            = $secondaryResult.Status
        LCCConfidenceOriginal      = $confidenceOriginal
        LCCConfidenceCanonical     = $confidenceCanonical
        LCCConfidenceStatus        = $confidenceStatus
        LCCSourceNotes             = $sourceNotes
        Warning                    = ($warnings -join "; ")
    }
}

$rows | Export-Csv -Path $outputFullPath -Delimiter "`t" -NoTypeInformation -Encoding UTF8
$reportRows | Export-Csv -Path $reportFullPath -NoTypeInformation -Encoding UTF8

$primaryGroups = $reportRows | Group-Object PrimaryStatus | Sort-Object Name
$secondaryGroups = $reportRows | Group-Object SecondaryStatus | Sort-Object Name
$confidenceGroups = $reportRows | Group-Object LCCConfidenceStatus | Sort-Object Name
$warningsCount = @($reportRows | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Warning) }).Count

Write-Host ""
Write-Host "Canonicalization complete."
Write-Host "Input:  $inputFullPath"
Write-Host "Output: $outputFullPath"
Write-Host "Report: $reportFullPath"
Write-Host ""
Write-Host "Rows processed: $($rows.Count)"
Write-Host ""
Write-Host "Primary class status:"
$primaryGroups | Select-Object Name, Count | Format-Table -AutoSize
Write-Host "Secondary class status:"
$secondaryGroups | Select-Object Name, Count | Format-Table -AutoSize

if ($hasConfidenceColumn) {
    Write-Host "LCC confidence status:"
    $confidenceGroups | Select-Object Name, Count | Format-Table -AutoSize
}
else {
    Write-Host "LCC confidence status:"
    Write-Host "Not provided"
}

Write-Host "Warnings: $warningsCount"

if ($warningsCount -gt 0) {
    Write-Host ""
    Write-Host "Review warnings before dry run."
}