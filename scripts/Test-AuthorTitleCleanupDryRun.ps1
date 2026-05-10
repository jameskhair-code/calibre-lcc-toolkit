<#
.SYNOPSIS
Performs a read-only dry run for proposed Calibre author/title cleanup changes.

.DESCRIPTION
Reads a proposed author/title cleanup TSV, compares each row against current Calibre metadata,
and writes a dry-run report showing which rows would be eligible for apply.

This script is read-only and does not modify Calibre metadata.

Blank ProposedTitle means no title change is proposed.
Blank ProposedAuthors means no author change is proposed.

Rows are apply-eligible only when:
- CalibreId exists
- the Calibre record is found
- OriginalTitle matches the current Calibre title
- OriginalAuthors matches the current Calibre authors
- at least one proposed value differs from the current value
- Confidence is an allowed value
- ManualReviewRequired = No
- the row is not a duplicate CalibreId target
- no blocking conditions are present

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-AuthorTitleCleanupDryRun.ps1 `
  -InputTsv ".\input\author-title-cleanup-import-j-russell-major-prize.tsv" `
  -ReportCsv ".\reports\author-title-cleanup-dryrun-j-russell-major-prize.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$InputTsv = ".\input\author-title-cleanup-import-batch.tsv",

    [string]$ReportCsv = ".\reports\author-title-cleanup-dryrun-batch.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe"
)

$AllowedConfidenceValues = @(
    "High",
    "Medium",
    "Low"
)

function Convert-ToFlatArray {
    param(
        [AllowNull()]
        $Value
    )

    if ($null -eq $Value) {
        return @()
    }

    $items = @()

    foreach ($item in @($Value)) {
        if ($null -eq $item) {
            continue
        }

        if ($item -is [System.Array]) {
            foreach ($nestedItem in $item) {
                if ($null -ne $nestedItem) {
                    $items += $nestedItem
                }
            }
        }
        else {
            $items += $item
        }
    }

    if ($items.Count -eq 1 -and $items[0] -is [System.Array]) {
        return @(Convert-ToFlatArray -Value $items[0])
    }

    return @($items)
}

function Normalize-ComparableValue {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return (($Value.Trim()) -replace '\s+', ' ')
}

function Normalize-YesNo {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $text = $Value.Trim()

    if ($text -ieq "yes") {
        return "Yes"
    }

    if ($text -ieq "no") {
        return "No"
    }

    return $text
}

function Invoke-CalibreDb {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $allArgs = @()

    if (-not [string]::IsNullOrWhiteSpace($LibraryPath)) {
        $allArgs += @("--with-library", $LibraryPath)
    }

    $allArgs += $Arguments

    & $CalibreDb @allArgs
}

function Format-Authors {
    param($Authors)

    if ($null -eq $Authors) {
        return ""
    }

    if ($Authors -is [System.Array]) {
        return ($Authors -join "; ")
    }

    return [string]$Authors
}

function Test-RequiredColumns {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string[]]$RequiredColumns
    )

    if ($Rows.Count -eq 0) {
        throw "Input TSV has no data rows."
    }

    $availableColumns = @($Rows[0].PSObject.Properties.Name)

    $missingColumns = @(
        $RequiredColumns | Where-Object {
            $_ -notin $availableColumns
        }
    )

    if ($missingColumns.Count -gt 0) {
        throw "Input TSV is missing required column(s): $($missingColumns -join ', ')"
    }
}

function Get-ConfidenceStatus {
    param(
        [AllowNull()]
        [string]$Confidence
    )

    if ([string]::IsNullOrWhiteSpace($Confidence)) {
        return "Missing"
    }

    foreach ($allowedValue in $AllowedConfidenceValues) {
        if ($Confidence.Trim() -eq $allowedValue) {
            return "Expected"
        }
    }

    return "Unexpected"
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not (Test-Path $InputTsv)) {
    throw "Input TSV was not found: $InputTsv"
}

Write-Host "Running author/title cleanup dry run..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Input: $InputTsv"
Write-Host "Report: $ReportCsv"

$inputRows = @(Import-Csv -Path $InputTsv -Delimiter "`t")

$requiredColumns = @(
    "CalibreId",
    "OriginalTitle",
    "ProposedTitle",
    "OriginalAuthors",
    "ProposedAuthors",
    "ChangeReason",
    "Confidence",
    "ManualReviewRequired"
)

Test-RequiredColumns -Rows $inputRows -RequiredColumns $requiredColumns

Write-Host "Rows loaded from TSV: $($inputRows.Count)"

$fieldList = @(
    "id",
    "title",
    "authors"
) -join ","

$args = @(
    "list",
    "--for-machine",
    "--fields", $fieldList
)

Write-Host "Reading current Calibre title/author metadata..."

$jsonLines = Invoke-CalibreDb -Arguments $args
$jsonText = ($jsonLines -join "`n").Trim()

if ([string]::IsNullOrWhiteSpace($jsonText)) {
    throw "No output returned from calibredb."
}

$converted = $jsonText | ConvertFrom-Json
$currentBooks = @(Convert-ToFlatArray -Value $converted)

$currentBookMap = @{}

foreach ($book in $currentBooks) {
    $idText = [string]$book.id

    if (-not [string]::IsNullOrWhiteSpace($idText)) {
        $currentBookMap[$idText] = $book
    }
}

Write-Host "Current Calibre records available for comparison: $($currentBookMap.Count)"

$idCounts = @{}

foreach ($row in $inputRows) {
    $idText = ([string]$row.CalibreId).Trim()

    if ([string]::IsNullOrWhiteSpace($idText)) {
        continue
    }

    if (-not $idCounts.ContainsKey($idText)) {
        $idCounts[$idText] = 0
    }

    $idCounts[$idText]++
}

$duplicateIds = @(
    $idCounts.Keys | Where-Object {
        $idCounts[$_] -gt 1
    }
)

$reportRows = foreach ($row in $inputRows) {
    $blockingReasons = @()

    $calibreId = ([string]$row.CalibreId).Trim()

    $originalTitle = [string]$row.OriginalTitle
    $proposedTitle = [string]$row.ProposedTitle
    $originalAuthors = [string]$row.OriginalAuthors
    $proposedAuthors = [string]$row.ProposedAuthors
    $changeReason = [string]$row.ChangeReason
    $confidence = ([string]$row.Confidence).Trim()
    $manualReviewRequired = Normalize-YesNo -Value $row.ManualReviewRequired

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }

    $isDuplicateCalibreId = $false

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and $duplicateIds -contains $calibreId) {
        $isDuplicateCalibreId = $true
        $blockingReasons += "Duplicate CalibreId in input TSV"
    }

    $currentBook = $null
    $currentTitle = ""
    $currentAuthors = ""

    if (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        if ($currentBookMap.ContainsKey($calibreId)) {
            $currentBook = $currentBookMap[$calibreId]
            $currentTitle = [string]$currentBook.title
            $currentAuthors = Format-Authors $currentBook.authors
        }
        else {
            $blockingReasons += "CalibreId not found in current Calibre metadata"
        }
    }

    $titleOriginalMatchesCurrent = $false
    $authorsOriginalMatchesCurrent = $false

    if ($null -ne $currentBook) {
        $titleOriginalMatchesCurrent =
            (Normalize-ComparableValue $originalTitle) -ceq (Normalize-ComparableValue $currentTitle)

        $authorsOriginalMatchesCurrent =
            (Normalize-ComparableValue $originalAuthors) -ceq (Normalize-ComparableValue $currentAuthors)

        if (-not $titleOriginalMatchesCurrent) {
            $blockingReasons += "OriginalTitle does not match current Calibre title"
        }

        if (-not $authorsOriginalMatchesCurrent) {
            $blockingReasons += "OriginalAuthors does not match current Calibre authors"
        }
    }

    $hasProposedTitle = -not [string]::IsNullOrWhiteSpace($proposedTitle)
    $hasProposedAuthors = -not [string]::IsNullOrWhiteSpace($proposedAuthors)

    $titleChangeDetected = $false
    $authorsChangeDetected = $false

    if ($null -ne $currentBook -and $hasProposedTitle) {
        $titleChangeDetected =
            (Normalize-ComparableValue $proposedTitle) -cne (Normalize-ComparableValue $currentTitle)
    }

    if ($null -ne $currentBook -and $hasProposedAuthors) {
        $authorsChangeDetected =
            (Normalize-ComparableValue $proposedAuthors) -cne (Normalize-ComparableValue $currentAuthors)
    }

    $hasAnyProposedChange = $titleChangeDetected -or $authorsChangeDetected

    if ($hasAnyProposedChange) {
        $confidenceStatus = Get-ConfidenceStatus -Confidence $confidence
    }
    else {
        $confidenceStatus = "NotRequired"
    }

    if ($hasAnyProposedChange -and $confidenceStatus -ne "Expected") {
        $blockingReasons += "Confidence is missing or unexpected"
    }

    if ($hasAnyProposedChange -and $manualReviewRequired -notin @("Yes", "No")) {
        $blockingReasons += "ManualReviewRequired must be Yes or No"
    }

    if ($hasAnyProposedChange -and $manualReviewRequired -eq "Yes") {
        $blockingReasons += "Manual review required"
    }

    if ($hasAnyProposedChange -and [string]::IsNullOrWhiteSpace($changeReason)) {
        $blockingReasons += "Missing ChangeReason"
    }

    $applyEligible = "No"

    if ($hasAnyProposedChange -and $blockingReasons.Count -eq 0) {
        $applyEligible = "Yes"
    }

    [pscustomobject]@{
        CalibreId                   = $calibreId
        CurrentTitle                = $currentTitle
        OriginalTitle               = $originalTitle
        ProposedTitle               = $proposedTitle
        TitleChangeDetected         = if ($titleChangeDetected) { "Yes" } else { "No" }
        CurrentAuthors              = $currentAuthors
        OriginalAuthors             = $originalAuthors
        ProposedAuthors             = $proposedAuthors
        AuthorsChangeDetected       = if ($authorsChangeDetected) { "Yes" } else { "No" }
        ChangeReason                = $changeReason
        Confidence                  = $confidence
        ConfidenceStatus            = $confidenceStatus
        ManualReviewRequired        = $manualReviewRequired
        TitleOriginalMatchesCurrent = if ($titleOriginalMatchesCurrent) { "Yes" } else { "No" }
        AuthorsOriginalMatchesCurrent = if ($authorsOriginalMatchesCurrent) { "Yes" } else { "No" }
        DuplicateCalibreId          = if ($isDuplicateCalibreId) { "Yes" } else { "No" }
        ApplyEligible               = $applyEligible
        BlockingReasons             = ($blockingReasons -join "; ")
    }
}

$outputFolder = Split-Path -Path $ReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$reportRows | Export-Csv -Path $ReportCsv -NoTypeInformation -Encoding UTF8

$eligibleCount = @($reportRows | Where-Object { $_.ApplyEligible -eq "Yes" }).Count
$proposedChangeRows = @(
    $reportRows | Where-Object {
        $_.TitleChangeDetected -eq "Yes" -or $_.AuthorsChangeDetected -eq "Yes"
    }
)
$noChangeCount = @(
    $reportRows | Where-Object {
        $_.TitleChangeDetected -ne "Yes" -and $_.AuthorsChangeDetected -ne "Yes"
    }
).Count
$blockedCount = @($proposedChangeRows | Where-Object { $_.ApplyEligible -ne "Yes" }).Count
$titleChangeCount = @($reportRows | Where-Object { $_.TitleChangeDetected -eq "Yes" }).Count
$authorsChangeCount = @($reportRows | Where-Object { $_.AuthorsChangeDetected -eq "Yes" }).Count
$manualReviewCount = @($proposedChangeRows | Where-Object { $_.ManualReviewRequired -eq "Yes" }).Count
$unexpectedConfidenceCount = @($proposedChangeRows | Where-Object { $_.ConfidenceStatus -eq "Unexpected" }).Count
$missingConfidenceCount = @($proposedChangeRows | Where-Object { $_.ConfidenceStatus -eq "Missing" }).Count

Write-Host "Dry run complete: $ReportCsv"
Write-Host "Rows reviewed: $($reportRows.Count)"
Write-Host "Rows with no proposed/effective changes: $noChangeCount"
Write-Host "Rows eligible for apply: $eligibleCount"
Write-Host "Rows blocked: $blockedCount"
Write-Host "Rows with title changes: $titleChangeCount"
Write-Host "Rows with author changes: $authorsChangeCount"
Write-Host "Rows marked manual review: $manualReviewCount"
Write-Host "Rows with unexpected confidence: $unexpectedConfidenceCount"
Write-Host "Rows with missing confidence: $missingConfidenceCount"
Write-Host ""
Write-Host "This was a dry run only. No Calibre metadata was modified."
