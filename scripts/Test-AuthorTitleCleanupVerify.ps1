<#
.SYNOPSIS
Verifies Calibre author/title cleanup results after apply.

.DESCRIPTION
Reads the CSV produced by Test-AuthorTitleCleanupDryRun.ps1 and compares expected
post-apply title/author values against current Calibre metadata.

This script is read-only and does not modify Calibre metadata.

Rows that were not apply-eligible in the dry-run report are skipped.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-AuthorTitleCleanupVerify.ps1 `
  -DryRunCsv ".\reports\author-title-cleanup-dryrun-batch.csv" `
  -VerifyReportCsv ".\reports\author-title-cleanup-verify-batch.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$DryRunCsv = ".\reports\author-title-cleanup-dryrun-batch.csv",

    [string]$VerifyReportCsv = ".\reports\author-title-cleanup-verify-batch.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe"
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

    $output = & $CalibreDb @allArgs 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        throw "calibredb failed with exit code $exitCode. Output: $($output -join "`n")"
    }

    return $output
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

function Get-CurrentBookMap {
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

    $jsonLines = Invoke-CalibreDb -Arguments $args
    $jsonText = ($jsonLines -join "`n").Trim()

    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw "No output returned from calibredb while reading current metadata."
    }

    $converted = $jsonText | ConvertFrom-Json
    $books = @(Convert-ToFlatArray -Value $converted)

    $bookMap = @{}

    foreach ($book in $books) {
        $idText = [string]$book.id

        if (-not [string]::IsNullOrWhiteSpace($idText)) {
            $bookMap[$idText] = $book
        }
    }

    return $bookMap
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not (Test-Path $DryRunCsv)) {
    throw "Dry-run CSV was not found: $DryRunCsv"
}

Write-Host "Running author/title cleanup verification..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Dry-run CSV: $DryRunCsv"
Write-Host "Verify report: $VerifyReportCsv"

$rows = @(Import-Csv -Path $DryRunCsv)

if ($rows.Count -eq 0) {
    throw "Dry-run CSV has no data rows: $DryRunCsv"
}

Write-Host "Rows loaded from dry-run CSV: $($rows.Count)"
Write-Host "Reading current Calibre title/author metadata..."

$currentBookMap = Get-CurrentBookMap

Write-Host "Current Calibre records available for verification: $($currentBookMap.Count)"

$verifyRows = foreach ($row in $rows) {
    $calibreId = ([string]$row.CalibreId).Trim()
    $notes = @()

    $expectedTitle = [string]$row.CurrentTitle
    $expectedAuthors = [string]$row.CurrentAuthors

    if (-not [string]::IsNullOrWhiteSpace($row.ProposedTitle)) {
        $expectedTitle = [string]$row.ProposedTitle
    }

    if (-not [string]::IsNullOrWhiteSpace($row.ProposedAuthors)) {
        $expectedAuthors = [string]$row.ProposedAuthors
    }

    $actualTitle = ""
    $actualAuthors = ""

    $titleVerified = "No"
    $authorsVerified = "No"
    $verificationStatus = "Mismatch"

    if ($row.ApplyEligible -ne "Yes") {
        $titleVerified = "Skipped"
        $authorsVerified = "Skipped"
        $verificationStatus = "Skipped - Not Apply Eligible"
        $notes += "Row was not apply-eligible in dry-run report."
    }
    elseif ([string]::IsNullOrWhiteSpace($calibreId)) {
        $verificationStatus = "Missing"
        $notes += "Missing CalibreId."
    }
    elseif (-not $currentBookMap.ContainsKey($calibreId)) {
        $verificationStatus = "Missing"
        $notes += "CalibreId not found in current Calibre metadata."
    }
    else {
        $currentBook = $currentBookMap[$calibreId]
        $actualTitle = [string]$currentBook.title
        $actualAuthors = Format-Authors $currentBook.authors

        if ((Normalize-ComparableValue $actualTitle) -ceq (Normalize-ComparableValue $expectedTitle)) {
            $titleVerified = "Yes"
        }
        else {
            $notes += "Title does not match expected value."
        }

        if ((Normalize-ComparableValue $actualAuthors) -ceq (Normalize-ComparableValue $expectedAuthors)) {
            $authorsVerified = "Yes"
        }
        else {
            $notes += "Authors do not match expected value."
        }

        if ($titleVerified -eq "Yes" -and $authorsVerified -eq "Yes") {
            $verificationStatus = "Verified"
        }
    }

    [pscustomobject]@{
        CalibreId          = $calibreId
        ApplyEligible      = $row.ApplyEligible
        ExpectedTitle      = $expectedTitle
        ActualTitle        = $actualTitle
        TitleVerified      = $titleVerified
        ExpectedAuthors    = $expectedAuthors
        ActualAuthors      = $actualAuthors
        AuthorsVerified    = $authorsVerified
        VerificationStatus = $verificationStatus
        VerificationNotes  = ($notes -join "; ")
    }
}

$outputFolder = Split-Path -Path $VerifyReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$verifyRows | Export-Csv -Path $VerifyReportCsv -NoTypeInformation -Encoding UTF8

$verifiedCount = @($verifyRows | Where-Object { $_.VerificationStatus -eq "Verified" }).Count
$mismatchCount = @($verifyRows | Where-Object { $_.VerificationStatus -eq "Mismatch" }).Count
$missingCount = @($verifyRows | Where-Object { $_.VerificationStatus -eq "Missing" }).Count
$skippedCount = @($verifyRows | Where-Object { $_.VerificationStatus -like "Skipped*" }).Count

Write-Host "Verification complete: $VerifyReportCsv"
Write-Host "Rows reviewed: $($verifyRows.Count)"
Write-Host "Rows verified: $verifiedCount"
Write-Host "Rows mismatched: $mismatchCount"
Write-Host "Rows missing: $missingCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host ""
Write-Host "This was a verification operation only. No Calibre metadata was modified."