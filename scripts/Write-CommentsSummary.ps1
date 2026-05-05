<#
.SYNOPSIS
Writes a human-readable summary for a comments dry-run report.

.DESCRIPTION
Reads the CSV produced by Test-CommentsDryRun.ps1 and writes a plain-text
batch summary showing apply eligibility, blocking counts, existing comments risk,
comments mode counts, confidence status, HTML validation status, source notes
coverage, and preview rows.

This script is read-only and does not modify Calibre metadata.

For v0.6, the comments module is intentionally limited to:
Export -> Dry Run -> Summary
#>

[CmdletBinding()]
param(
    [string]$DryRunCsv = ".\reports\comments-dryrun-batch.csv",

    [string]$SummaryTxt = ".\reports\comments-summary-batch.txt"
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

function Get-GroupedCounts {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    return @(
        $Rows |
            Group-Object -Property $PropertyName |
            Sort-Object -Property @{ Expression = "Count"; Descending = $true }, Name |
            Select-Object Count, Name
    )
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

Write-Host "Writing comments dry-run summary..."
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

$missingProposedRows = Count-Rows -Rows $rows -Predicate { $_.BlockingReasons -match "Missing ProposedComments" }
$highRiskExistingRows = Count-Rows -Rows $rows -Predicate { $_.ExistingCommentsRisk -like "High*" }
$mediumRiskExistingRows = Count-Rows -Rows $rows -Predicate { $_.ExistingCommentsRisk -like "Medium*" }
$lowRiskExistingRows = Count-Rows -Rows $rows -Predicate { $_.ExistingCommentsRisk -like "Low*" }

$hashMismatchRows = Count-Rows -Rows $rows -Predicate { $_.CommentsHashMatchesCurrent -ne "Yes" }
$htmlBlockedRows = Count-Rows -Rows $rows -Predicate { $_.HtmlValidationStatus -eq "Blocked" }
$htmlAllowedRows = Count-Rows -Rows $rows -Predicate { $_.HtmlValidationStatus -eq "Allowed" }
$htmlMissingRows = Count-Rows -Rows $rows -Predicate { $_.HtmlValidationStatus -eq "Missing" }

$sourceNotesPresentRows = Count-Rows -Rows $rows -Predicate { $_.SourceNotesPresent -eq "Yes" }
$sourceNotesMissingRows = Count-Rows -Rows $rows -Predicate { $_.SourceNotesPresent -ne "Yes" }
$sourceNotesHtmlPresentRows = Count-Rows -Rows $rows -Predicate { $_.SourceNotesHtmlPresent -eq "Yes" }
$sourceNotesHtmlMissingRows = Count-Rows -Rows $rows -Predicate { $_.SourceNotesHtmlPresent -ne "Yes" }

$manualReviewRows = Count-Rows -Rows $rows -Predicate { $_.ManualReviewRequired -eq "Yes" }
$duplicateRows = Count-Rows -Rows $rows -Predicate { $_.DuplicateCalibreId -eq "Yes" }
$titleMismatchRows = Count-Rows -Rows $rows -Predicate { $_.TitleMatchesCurrent -ne "Yes" }
$authorsMismatchRows = Count-Rows -Rows $rows -Predicate { $_.AuthorsMatchCurrent -ne "Yes" }

$templateProfileGroups = Get-GroupedCounts -Rows $rows -PropertyName "CommentsTemplateProfileStatus"
$commentsModeGroups = Get-GroupedCounts -Rows $rows -PropertyName "CommentsModeStatus"
$commentsModeValueGroups = Get-GroupedCounts -Rows $rows -PropertyName "CommentsMode"
$confidenceGroups = Get-GroupedCounts -Rows $rows -PropertyName "ConfidenceStatus"
$existingRiskGroups = Get-GroupedCounts -Rows $rows -PropertyName "ExistingCommentsRisk"
$htmlGroups = Get-GroupedCounts -Rows $rows -PropertyName "HtmlValidationStatus"
$placeholderGroups = Get-GroupedCounts -Rows $rows -PropertyName "PlaceholderStatus"
$topBlockingReasons = Get-TopBlockingReasons -Rows $rows

$eligiblePreviewRows = @(
    $rows |
        Where-Object { $_.ApplyEligible -eq "Yes" } |
        Select-Object -First 15
)

$blockedPreviewRows = @(
    $rows |
        Where-Object { $_.ApplyEligible -ne "Yes" } |
        Select-Object -First 20
)

$highRiskPreviewRows = @(
    $rows |
        Where-Object { $_.ExistingCommentsRisk -like "High*" } |
        Sort-Object { [int]$_.CurrentCommentsLength } -Descending |
        Select-Object -First 15
)

$lines = [System.Collections.Generic.List[string]]::new()

Add-Line -Lines $lines -Text "Comments Dry-Run Summary"
Add-Line -Lines $lines -Text "========================"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Add-Line -Lines $lines -Text "Dry-run CSV: $DryRunCsv"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Safety Note"
Add-Line -Lines $lines -Text "-----------"
Add-Line -Lines $lines -Text "This summary is read-only. It does not modify Calibre metadata."
Add-Line -Lines $lines -Text "For v0.6, the Comments module is limited to Export -> Dry Run -> Summary."
Add-Line -Lines $lines -Text "Comments apply/verify behavior is intentionally deferred to a later milestone."
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Batch Totals"
Add-Line -Lines $lines -Text "------------"
Add-Line -Lines $lines -Text "Rows reviewed: $totalRows"
Add-Line -Lines $lines -Text "Rows eligible for apply: $eligibleRows"
Add-Line -Lines $lines -Text "Rows blocked: $blockedRows"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Core Safety Counts"
Add-Line -Lines $lines -Text "------------------"
Add-Line -Lines $lines -Text "Rows missing proposed comments: $missingProposedRows"
Add-Line -Lines $lines -Text "Rows with comments hash mismatch: $hashMismatchRows"
Add-Line -Lines $lines -Text "Rows with duplicate CalibreId: $duplicateRows"
Add-Line -Lines $lines -Text "Rows where title does not match current Calibre title: $titleMismatchRows"
Add-Line -Lines $lines -Text "Rows where authors do not match current Calibre authors: $authorsMismatchRows"
Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Existing Comments Risk"
Add-Line -Lines $lines -Text "----------------------"
Add-Line -Lines $lines -Text "High-risk existing comments: $highRiskExistingRows"
Add-Line -Lines $lines -Text "Medium-risk existing comments: $mediumRiskExistingRows"
Add-Line -Lines $lines -Text "Low-risk existing comments: $lowRiskExistingRows"

foreach ($group in $existingRiskGroups) {
    Add-Line -Lines $lines -Text "$($group.Count) - $($group.Name)"
}

Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Template / Mode / Confidence"
Add-Line -Lines $lines -Text "----------------------------"
Add-Line -Lines $lines -Text "Template profile status:"

foreach ($group in $templateProfileGroups) {
    Add-Line -Lines $lines -Text "  $($group.Count) - $($group.Name)"
}

Add-Line -Lines $lines -Text "Comments mode status:"

foreach ($group in $commentsModeGroups) {
    Add-Line -Lines $lines -Text "  $($group.Count) - $($group.Name)"
}

Add-Line -Lines $lines -Text "Comments mode values:"

foreach ($group in $commentsModeValueGroups) {
    $name = $group.Name

    if ([string]::IsNullOrWhiteSpace($name)) {
        $name = "(blank)"
    }

    Add-Line -Lines $lines -Text "  $($group.Count) - $name"
}

Add-Line -Lines $lines -Text "Confidence status:"

foreach ($group in $confidenceGroups) {
    Add-Line -Lines $lines -Text "  $($group.Count) - $($group.Name)"
}

Add-Line -Lines $lines
Add-Line -Lines $lines -Text "HTML / Placeholder / Source Notes"
Add-Line -Lines $lines -Text "---------------------------------"
Add-Line -Lines $lines -Text "HTML allowed rows: $htmlAllowedRows"
Add-Line -Lines $lines -Text "HTML blocked rows: $htmlBlockedRows"
Add-Line -Lines $lines -Text "HTML missing rows: $htmlMissingRows"

foreach ($group in $htmlGroups) {
    Add-Line -Lines $lines -Text "$($group.Count) - HTML $($group.Name)"
}

foreach ($group in $placeholderGroups) {
    Add-Line -Lines $lines -Text "$($group.Count) - Placeholder $($group.Name)"
}

Add-Line -Lines $lines -Text "Rows with SourceNotes field present: $sourceNotesPresentRows"
Add-Line -Lines $lines -Text "Rows missing SourceNotes field: $sourceNotesMissingRows"
Add-Line -Lines $lines -Text "Rows with Source Notes HTML section present: $sourceNotesHtmlPresentRows"
Add-Line -Lines $lines -Text "Rows missing Source Notes HTML section: $sourceNotesHtmlMissingRows"
Add-Line -Lines $lines -Text "Rows marked manual review: $manualReviewRows"
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
        Add-Line -Lines $lines -Text "CalibreId $($row.CalibreId): $($row.Title)"
        Add-Line -Lines $lines -Text "  Mode: $($row.CommentsMode)"
        Add-Line -Lines $lines -Text "  Profile: $($row.CommentsTemplateProfile)"
        Add-Line -Lines $lines -Text "  Confidence: $($row.Confidence)"
        Add-Line -Lines $lines -Text "  Proposed length: $($row.ProposedCommentsLength)"
        Add-Line -Lines $lines -Text "  Existing comments risk: $($row.ExistingCommentsRisk)"
        Add-Line -Lines $lines -Text "  Proposed preview: $($row.ProposedCommentsPreview)"
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
        Add-Line -Lines $lines -Text "CalibreId $($row.CalibreId): $($row.Title)"
        Add-Line -Lines $lines -Text "  Blocking reasons: $($row.BlockingReasons)"
    }
}

Add-Line -Lines $lines
Add-Line -Lines $lines -Text "High-Risk Existing Comments Preview"
Add-Line -Lines $lines -Text "-----------------------------------"

if ($highRiskPreviewRows.Count -eq 0) {
    Add-Line -Lines $lines -Text "No high-risk existing comments detected."
}
else {
    foreach ($row in $highRiskPreviewRows) {
        Add-Line -Lines $lines -Text "CalibreId $($row.CalibreId): $($row.Title)"
        Add-Line -Lines $lines -Text "  Current comments length: $($row.CurrentCommentsLength)"
        Add-Line -Lines $lines -Text "  Risk: $($row.ExistingCommentsRisk)"
        Add-Line -Lines $lines -Text "  Preview: $($row.CurrentCommentsPreview)"
        Add-Line -Lines $lines
    }
}

Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Operating Recommendation"
Add-Line -Lines $lines -Text "------------------------"

if ($eligibleRows -eq 0) {
    Add-Line -Lines $lines -Text "No rows are currently eligible. This is expected for a source export with no proposed comments."
}
elseif ($blockedRows -gt 0) {
    Add-Line -Lines $lines -Text "Do not apply this batch. Fix blocked rows, rerun dry run, and regenerate this summary."
}
else {
    Add-Line -Lines $lines -Text "The dry-run report has no blocked rows. For v0.6, review this result manually; apply behavior is deferred."
}

Add-Line -Lines $lines
Add-Line -Lines $lines -Text "Reminder"
Add-Line -Lines $lines -Text "--------"
Add-Line -Lines $lines -Text "Do not overwrite substantial existing comments without intentional review."
Add-Line -Lines $lines -Text "SourceNotes should be present both as a workflow field and as a visible Source Notes HTML section."
Add-Line -Lines $lines -Text "CommentsMode should be explicit. Blank mode values are intentionally blocked."

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