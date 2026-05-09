<#
.SYNOPSIS
Writes a human-readable summary for an author/title cleanup dry-run report.

.DESCRIPTION
Reads the CSV produced by Test-AuthorTitleCleanupDryRun.ps1 and writes a plain-text
batch summary showing proposed changes, apply eligibility, blocking counts, confidence
status, and common blocking reasons.

This script is read-only and does not modify Calibre metadata.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Write-AuthorTitleCleanupSummary.ps1 `
  -DryRunCsv ".\reports\author-title-cleanup-dryrun-j-russell-major-prize.csv" `
  -SummaryTxt ".\reports\author-title-cleanup-summary-j-russell-major-prize.txt"
#>

[CmdletBinding()]
param(
    [string]$DryRunCsv = ".\reports\author-title-cleanup-dryrun-batch.csv",

    [string]$SummaryTxt = ".\reports\author-title-cleanup-summary-batch.txt"
)

function Add-Line {
    param(
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[string]]$Lines,

        [AllowEmptyString()]
        [string]$Text = ""
    )

    if ($null -eq $Lines) {
        throw "Lines collection was not initialized."
    }

    $Lines.Add($Text) | Out-Null
}

function Count-Rows {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Predicate
    )

    return @($Rows | Where-Object $Predicate).Count
}

function Get-TopBlockingReasons {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows
    )

    $reasons = @()

    foreach ($row in $Rows) {
        $blockingText = [string]$row.BlockingReasons

        if ([string]::IsNullOrWhiteSpace($blockingText)) {
            continue
        }

        foreach ($reason in ($blockingText -split '\s*;\s*')) {
            if (-not [string]::IsNullOrWhiteSpace($reason)) {
                $reasons += $reason.Trim()
            }
        }
    }

    return @(
        $reasons |
            Group-Object |
            Sort-Object -Property @{ Expression = "Count"; Descending = $true }, Name |
            Select-Object Count, Name
    )
}

if (-not (Test-Path $DryRunCsv)) {
    throw "Dry-run CSV was not found: $DryRunCsv"
}

Write-Host "Writing author/title cleanup summary..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Dry run CSV: $DryRunCsv"
Write-Host "Summary TXT: $SummaryTxt"

$rows = @(Import-Csv -Path $DryRunCsv)

if ($rows.Count -eq 0) {
    throw "Dry-run CSV has no data rows: $DryRunCsv"
}

$totalRows = $rows.Count
$eligibleRows = Count-Rows -Rows $rows -Predicate { $_.ApplyEligible -eq "Yes" }
$blockedRows = Count-Rows -Rows $rows -Predicate { $_.ApplyEligible -ne "Yes" }

$titleChangeRows = Count-Rows -Rows $rows -Predicate { $_.TitleChangeDetected -eq "Yes" }
$authorsChangeRows = Count-Rows -Rows $rows -Predicate { $_.AuthorsChangeDetected -eq "Yes" }
$bothChangeRows = Count-Rows -Rows $rows -Predicate {
    $_.TitleChangeDetected -eq "Yes" -and $_.AuthorsChangeDetected -eq "Yes"
}
$titleOnlyRows = Count-Rows -Rows $rows -Predicate {
    $_.TitleChangeDetected -eq "Yes" -and $_.AuthorsChangeDetected -ne "Yes"
}
$authorsOnlyRows = Count-Rows -Rows $rows -Predicate {
    $_.TitleChangeDetected -ne "Yes" -and $_.AuthorsChangeDetected -eq "Yes"
}
$noChangeRows = Count-Rows -Rows $rows -Predicate {
    $_.TitleChangeDetected -ne "Yes" -and $_.AuthorsChangeDetected -ne "Yes"
}

$manualReviewRows = Count-Rows -Rows $rows -Predicate { $_.ManualReviewRequired -eq "Yes" }
$confidenceExpectedRows = Count-Rows -Rows $rows -Predicate { $_.ConfidenceStatus -eq "Expected" }
$confidenceMissingRows = Count-Rows -Rows $rows -Predicate { $_.ConfidenceStatus -eq "Missing" }
$confidenceUnexpectedRows = Count-Rows -Rows $rows -Predicate { $_.ConfidenceStatus -eq "Unexpected" }

$titleMismatchRows = Count-Rows -Rows $rows -Predicate { $_.TitleOriginalMatchesCurrent -ne "Yes" }
$authorsMismatchRows = Count-Rows -Rows $rows -Predicate { $_.AuthorsOriginalMatchesCurrent -ne "Yes" }
$duplicateIdRows = Count-Rows -Rows $rows -Predicate { $_.DuplicateCalibreId -eq "Yes" }

$eligiblePreviewRows = @(
    $rows |
        Where-Object { $_.ApplyEligible -eq "Yes" } |
        Select-Object -First 20
)

$blockedPreviewRows = @(
    $rows |
        Where-Object { $_.ApplyEligible -ne "Yes" } |
        Select-Object -First 20
)

$topBlockingReasons = @(Get-TopBlockingReasons -Rows $rows)

$lines = [System.Collections.Generic.List[string]]::new()

Add-Line -Lines $lines -Text "Author / Title Cleanup Summary"
Add-Line -Lines $lines -Text "================================"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Add-Line -Lines $lines -Text "Dry-run CSV: $DryRunCsv"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Safety Note"
Add-Line -Lines $lines -Text "-----------"
Add-Line -Lines $lines -Text "This summary is read-only. It does not modify Calibre metadata."
Add-Line -Lines $lines -Text "Only the Author / Title apply script should write title or author changes."
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Batch Totals"
Add-Line -Lines $lines -Text "------------"
Add-Line -Lines $lines -Text "Rows reviewed: $totalRows"
Add-Line -Lines $lines -Text "Rows eligible for apply: $eligibleRows"
Add-Line -Lines $lines -Text "Rows blocked: $blockedRows"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Change Counts"
Add-Line -Lines $lines -Text "-------------"
Add-Line -Lines $lines -Text "Rows with title changes: $titleChangeRows"
Add-Line -Lines $lines -Text "Rows with author changes: $authorsChangeRows"
Add-Line -Lines $lines -Text "Rows with both title and author changes: $bothChangeRows"
Add-Line -Lines $lines -Text "Rows with title-only changes: $titleOnlyRows"
Add-Line -Lines $lines -Text "Rows with author-only changes: $authorsOnlyRows"
Add-Line -Lines $lines -Text "Rows with no proposed changes: $noChangeRows"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Review / Confidence"
Add-Line -Lines $lines -Text "-------------------"
Add-Line -Lines $lines -Text "Rows marked manual review: $manualReviewRows"
Add-Line -Lines $lines -Text "Rows with expected confidence: $confidenceExpectedRows"
Add-Line -Lines $lines -Text "Rows with missing confidence: $confidenceMissingRows"
Add-Line -Lines $lines -Text "Rows with unexpected confidence: $confidenceUnexpectedRows"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Safety Checks"
Add-Line -Lines $lines -Text "-------------"
Add-Line -Lines $lines -Text "Rows where OriginalTitle does not match current title: $titleMismatchRows"
Add-Line -Lines $lines -Text "Rows where OriginalAuthors does not match current authors: $authorsMismatchRows"
Add-Line -Lines $lines -Text "Rows with duplicate CalibreId: $duplicateIdRows"
Add-Line -Lines $lines

Add-Line -Lines $lines -Text "Top Blocking Reasons"
Add-Line -Lines $lines -Text "--------------------"

if ($topBlockingReasons.Count -eq 0) {
    Add-Line -Lines $lines -Text "None."
}
else {
    foreach ($reason in $topBlockingReasons) {
        Add-Line -Lines $lines -Text "$($reason.Count) - $($reason.Name)"
    }
}

Add-Line -Lines $lines

Add-Line -Lines $lines -Text "Eligible Rows Preview"
Add-Line -Lines $lines -Text "---------------------"

if ($eligiblePreviewRows.Count -eq 0) {
    Add-Line -Lines $lines -Text "No rows are currently eligible for apply."
}
else {
    foreach ($row in $eligiblePreviewRows) {
        Add-Line -Lines $lines -Text "CalibreId $($row.CalibreId):"
        Add-Line -Lines $lines -Text "  CurrentTitle: $($row.CurrentTitle)"
        Add-Line -Lines $lines -Text "  ProposedTitle: $($row.ProposedTitle)"
        Add-Line -Lines $lines -Text "  CurrentAuthors: $($row.CurrentAuthors)"
        Add-Line -Lines $lines -Text "  ProposedAuthors: $($row.ProposedAuthors)"
        Add-Line -Lines $lines -Text "  ChangeReason: $($row.ChangeReason)"
        Add-Line -Lines $lines -Text "  Confidence: $($row.Confidence)"
        Add-Line -Lines $lines
    }
}

Add-Line -Lines $lines

Add-Line -Lines $lines -Text "Blocked Rows Preview"
Add-Line -Lines $lines -Text "--------------------"

if ($blockedPreviewRows.Count -eq 0) {
    Add-Line -Lines $lines -Text "No rows are currently blocked."
}
else {
    foreach ($row in $blockedPreviewRows) {
        Add-Line -Lines $lines -Text "CalibreId $($row.CalibreId): $($row.BlockingReasons)"
    }
}

Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Operating Reminder"
Add-Line -Lines $lines -Text "------------------"
Add-Line -Lines $lines -Text "If rows are blocked, fix the TSV and dry run again."
Add-Line -Lines $lines -Text "Do not apply title/author changes until the dry-run report and summary are clean."

$outputFolder = Split-Path -Path $SummaryTxt -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$lines | Set-Content -Path $SummaryTxt -Encoding UTF8

Write-Host "Summary complete: $SummaryTxt"
Write-Host "Rows reviewed: $totalRows"
Write-Host "Rows eligible for apply: $eligibleRows"
Write-Host "Rows blocked: $blockedRows"
Write-Host ""
Write-Host "This was a summary operation only. No Calibre metadata was modified."



