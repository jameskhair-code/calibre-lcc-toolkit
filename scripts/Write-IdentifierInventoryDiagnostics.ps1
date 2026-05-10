<#
.SYNOPSIS
Writes deeper read-only diagnostics from the identifier inventory export.

.DESCRIPTION
Reads identifier-inventory-source.tsv and identifier-type-counts.csv, then produces
focused MQG-02 diagnostic reports.

This script is read-only and does not modify Calibre metadata.
#>

[CmdletBinding()]
param(
    [string]$InventoryTsv = ".\input\identifier-inventory-source.tsv",

    [string]$IdentifierTypeCountsCsv = ".\reports\identifier-type-counts.csv",

    [string]$MissingCoreCsv = ".\reports\identifier-missing-core.csv",

    [string]$SuspiciousTypesCsv = ".\reports\identifier-suspicious-types.csv",

    [string]$DuplicateIsbnCsv = ".\reports\identifier-duplicate-isbn.csv",

    [string]$DuplicateGoodreadsCsv = ".\reports\identifier-duplicate-goodreads.csv",

    [string]$DuplicateAmazonCsv = ".\reports\identifier-duplicate-amazon.csv",

    [string]$Mqg02CandidateSummaryCsv = ".\reports\identifier-mqg02-candidate-summary.csv"
)

function Get-FirstNonBlank {
    param(
        [AllowNull()]
        [string[]]$Values
    )

    foreach ($value in $Values) {
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
    }

    return ""
}

function Test-SuspiciousIdentifierTypeName {
    param(
        [AllowNull()]
        [string]$IdentifierType
    )

    if ([string]::IsNullOrWhiteSpace($IdentifierType)) {
        return $false
    }

    $value = $IdentifierType.Trim().ToLowerInvariant()

    if ($value -in @("isbn", "isbn10", "isbn13", "isbn-10")) {
        return $false
    }

    return ($value -match '^(97[89][0-9]{10}|isbn97[89]|urnisbn/|p978|urnuuid)')
}

function New-DuplicateRows {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [scriptblock]$KeyScript,

        [Parameter(Mandatory = $true)]
        [string]$ValueName
    )

    $expanded = foreach ($row in $Rows) {
        $key = & $KeyScript $row

        if (-not [string]::IsNullOrWhiteSpace($key)) {
            [pscustomobject]@{
                IdentifierValue = $key.Trim()
                CalibreId       = $row.CalibreId
                Title           = $row.Title
                Authors         = $row.Authors
                IdentifierTypes = $row.IdentifierTypes
                IdentifiersRaw  = $row.IdentifiersRaw
            }
        }
    }

    $duplicateValues = @(
        $expanded |
            Group-Object IdentifierValue |
            Where-Object { $_.Count -gt 1 } |
            Select-Object -ExpandProperty Name
    )

    return @(
        $expanded |
            Where-Object { $_.IdentifierValue -in $duplicateValues } |
            Sort-Object IdentifierValue, Title |
            ForEach-Object {
                [pscustomobject]@{
                    IdentifierKind  = $ValueName
                    IdentifierValue = $_.IdentifierValue
                    CalibreId       = $_.CalibreId
                    Title           = $_.Title
                    Authors         = $_.Authors
                    IdentifierTypes = $_.IdentifierTypes
                    IdentifiersRaw  = $_.IdentifiersRaw
                }
            }
    )
}

if (-not (Test-Path $InventoryTsv)) {
    throw "Inventory TSV not found: $InventoryTsv"
}

if (-not (Test-Path $IdentifierTypeCountsCsv)) {
    throw "Identifier type counts CSV not found: $IdentifierTypeCountsCsv"
}

Write-Host "Identifier inventory diagnostics"
Write-Host "================================"
Write-Host ""
Write-Host "This operation is read-only and does not modify Calibre metadata."

$rows = @(Import-Csv -Path $InventoryTsv -Delimiter "`t")
$typeRows = @(Import-Csv -Path $IdentifierTypeCountsCsv)

if ($rows.Count -eq 0) {
    throw "Inventory TSV has no rows: $InventoryTsv"
}

$missingCoreRows = @(
    $rows |
        Where-Object {
            $_.HasIsbn -ne "Yes" -or
            $_.HasAmazon -ne "Yes" -or
            $_.HasGoodreads -ne "Yes"
        } |
        Select-Object CalibreId,Title,Authors,HasIsbn,HasAmazon,HasGoodreads,IdentifierTypes,IdentifiersRaw
)

$suspiciousTypeRows = @(
    $typeRows |
        Where-Object { Test-SuspiciousIdentifierTypeName -IdentifierType $_.IdentifierType } |
        Sort-Object IdentifierType
)

$duplicateIsbnRows = New-DuplicateRows -Rows $rows -ValueName "ISBN" -KeyScript {
    param($row)
    Get-FirstNonBlank -Values @($row.IsbnIdentifier, $row.IsbnColumn)
}

$duplicateGoodreadsRows = New-DuplicateRows -Rows $rows -ValueName "Goodreads" -KeyScript {
    param($row)
    $row.GoodreadsIdentifier
}

$duplicateAmazonRows = New-DuplicateRows -Rows $rows -ValueName "AmazonOrASIN" -KeyScript {
    param($row)
    Get-FirstNonBlank -Values @($row.AmazonIdentifier, $row.AsinIdentifier)
}

$duplicateIsbnValues = @($duplicateIsbnRows | Select-Object -ExpandProperty IdentifierValue -Unique)
$duplicateGoodreadsValues = @($duplicateGoodreadsRows | Select-Object -ExpandProperty IdentifierValue -Unique)
$duplicateAmazonValues = @($duplicateAmazonRows | Select-Object -ExpandProperty IdentifierValue -Unique)

$mqgRows = foreach ($row in $rows) {
    $isbnValue = Get-FirstNonBlank -Values @($row.IsbnIdentifier, $row.IsbnColumn)
    $amazonValue = Get-FirstNonBlank -Values @($row.AmazonIdentifier, $row.AsinIdentifier)
    $goodreadsValue = $row.GoodreadsIdentifier

    $identifierTypes = @(
        ([string]$row.IdentifierTypes) -split ';' |
            ForEach-Object { $_.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )

    $hasSuspiciousType = $false

    foreach ($type in $identifierTypes) {
        if (Test-SuspiciousIdentifierTypeName -IdentifierType $type) {
            $hasSuspiciousType = $true
            break
        }
    }

    $hasDuplicateIsbn = (-not [string]::IsNullOrWhiteSpace($isbnValue) -and $isbnValue -in $duplicateIsbnValues)
    $hasDuplicateGoodreads = (-not [string]::IsNullOrWhiteSpace($goodreadsValue) -and $goodreadsValue -in $duplicateGoodreadsValues)
    $hasDuplicateAmazon = (-not [string]::IsNullOrWhiteSpace($amazonValue) -and $amazonValue -in $duplicateAmazonValues)

    $issues = @()

    if ($row.HasIsbn -ne "Yes") {
        $issues += "Missing ISBN"
    }

    if ($row.HasAmazon -ne "Yes") {
        $issues += "Missing Amazon/ASIN"
    }

    if ($row.HasGoodreads -ne "Yes") {
        $issues += "Missing Goodreads"
    }

    if ($hasSuspiciousType) {
        $issues += "Suspicious identifier type"
    }

    if ($hasDuplicateIsbn) {
        $issues += "Duplicate ISBN"
    }

    if ($hasDuplicateGoodreads) {
        $issues += "Duplicate Goodreads"
    }

    if ($hasDuplicateAmazon) {
        $issues += "Duplicate Amazon/ASIN"
    }

    $recommendedStatus = "Ready - Strong Core"

    if ($issues -contains "Missing ISBN") {
        $recommendedStatus = "Review - Missing ISBN"
    }
    elseif ($hasSuspiciousType) {
        $recommendedStatus = "Review - Suspicious Identifier Type"
    }
    elseif ($hasDuplicateIsbn -or $hasDuplicateGoodreads -or $hasDuplicateAmazon) {
        $recommendedStatus = "Review - Duplicate Identifier"
    }
    elseif ($row.HasAmazon -ne "Yes" -and $row.HasGoodreads -ne "Yes") {
        $recommendedStatus = "Review - Missing External Link Targets"
    }
    elseif ($row.HasAmazon -ne "Yes" -or $row.HasGoodreads -ne "Yes") {
        $recommendedStatus = "Review - Missing One External Link Target"
    }

    [pscustomobject]@{
        CalibreId             = $row.CalibreId
        Title                 = $row.Title
        Authors               = $row.Authors
        HasIsbn               = $row.HasIsbn
        HasAmazon             = $row.HasAmazon
        HasGoodreads          = $row.HasGoodreads
        IsbnValue             = $isbnValue
        AmazonOrAsinValue     = $amazonValue
        GoodreadsValue        = $goodreadsValue
        HasSuspiciousType     = if ($hasSuspiciousType) { "Yes" } else { "No" }
        HasDuplicateIsbn      = if ($hasDuplicateIsbn) { "Yes" } else { "No" }
        HasDuplicateAmazon    = if ($hasDuplicateAmazon) { "Yes" } else { "No" }
        HasDuplicateGoodreads = if ($hasDuplicateGoodreads) { "Yes" } else { "No" }
        IssueCount            = $issues.Count
        IssueSummary          = ($issues -join "; ")
        RecommendedStatus     = $recommendedStatus
        IdentifierTypes       = $row.IdentifierTypes
        IdentifiersRaw        = $row.IdentifiersRaw
    }
}

$outputFolders = @(
    (Split-Path -Path $MissingCoreCsv -Parent),
    (Split-Path -Path $SuspiciousTypesCsv -Parent),
    (Split-Path -Path $DuplicateIsbnCsv -Parent),
    (Split-Path -Path $DuplicateGoodreadsCsv -Parent),
    (Split-Path -Path $DuplicateAmazonCsv -Parent),
    (Split-Path -Path $Mqg02CandidateSummaryCsv -Parent)
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

foreach ($folder in $outputFolders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

$missingCoreRows | Export-Csv -Path $MissingCoreCsv -NoTypeInformation -Encoding UTF8
$suspiciousTypeRows | Export-Csv -Path $SuspiciousTypesCsv -NoTypeInformation -Encoding UTF8
$duplicateIsbnRows | Export-Csv -Path $DuplicateIsbnCsv -NoTypeInformation -Encoding UTF8
$duplicateGoodreadsRows | Export-Csv -Path $DuplicateGoodreadsCsv -NoTypeInformation -Encoding UTF8
$duplicateAmazonRows | Export-Csv -Path $DuplicateAmazonCsv -NoTypeInformation -Encoding UTF8
$mqgRows | Export-Csv -Path $Mqg02CandidateSummaryCsv -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "Diagnostics complete."
Write-Host "Rows reviewed: $($rows.Count)"
Write-Host "Missing core rows: $($missingCoreRows.Count)"
Write-Host "Suspicious identifier type rows: $($suspiciousTypeRows.Count)"
Write-Host "Duplicate ISBN rows: $($duplicateIsbnRows.Count)"
Write-Host "Duplicate Goodreads rows: $($duplicateGoodreadsRows.Count)"
Write-Host "Duplicate Amazon/ASIN rows: $($duplicateAmazonRows.Count)"
Write-Host ""
Write-Host "Files written:"
Write-Host "  $MissingCoreCsv"
Write-Host "  $SuspiciousTypesCsv"
Write-Host "  $DuplicateIsbnCsv"
Write-Host "  $DuplicateGoodreadsCsv"
Write-Host "  $DuplicateAmazonCsv"
Write-Host "  $Mqg02CandidateSummaryCsv"
