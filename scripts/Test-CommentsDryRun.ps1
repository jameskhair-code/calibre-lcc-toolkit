<#
.SYNOPSIS
Performs a read-only dry run for proposed Calibre comments changes.

.DESCRIPTION
Reads a proposed comments TSV, compares each row against current Calibre metadata,
validates comments workflow fields, checks existing comments hashes, performs simple
HTML safety validation, and writes a dry-run report.

This script is read-only and does not modify Calibre metadata.

For v0.6, the comments module is intentionally limited to:
Export -> Dry Run -> Summary

Apply and verify are deferred to a later milestone.
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$InputTsv = ".\input\comments-import-batch.tsv",

    [string]$ReportCsv = ".\reports\comments-dryrun-batch.csv",

    [int]$CommentsPreviewLength = 300,

    [int]$SubstantialExistingCommentsThreshold = 300,

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe"
)

$AllowedTemplateProfiles = @(
    "Scholarly Nonfiction",
    "General Nonfiction",
    "Fiction",
    "Speculative Fiction",
    "Reference",
    "Poetry / Drama",
    "Edited Collection / Anthology",
    "Gaming / Technical / Manual"
)

$AllowedCommentsModes = @(
    "Replace",
    "Append",
    "Prepend",
    "Skip"
)

$AllowedConfidenceValues = @(
    "High - Source Grounded",
    "Medium - Source Supported",
    "Low - Manual Review Recommended"
)

$BlockedHtmlPatterns = @(
    "<h1",
    "</h1",
    "<h2",
    "</h2",
    "<table",
    "</table",
    "<div",
    "</div",
    "<span style=",
    "<script",
    "</script",
    "<img",
    "<iframe",
    "</iframe",
    "<style",
    "</style",
    "onload=",
    "onclick="
)

$PlaceholderPatterns = @(
    "TODO",
    "TBD",
    "INSERT",
    "PLACEHOLDER",
    "DO NOT APPLY",
    "Lorem ipsum",
    "[fill in]"
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

function Get-Sha256Hash {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ($null -eq $Value) {
        $Value = ""
    }

    $sha256 = [System.Security.Cryptography.SHA256]::Create()

    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hashBytes = $sha256.ComputeHash($bytes)

        return (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
    }
}

function Convert-HtmlToPlainText {
    param(
        [AllowNull()]
        [string]$Html
    )

    if ([string]::IsNullOrWhiteSpace($Html)) {
        return ""
    }

    $text = $Html

    $text = $text -replace '(?is)<script.*?</script>', ' '
    $text = $text -replace '(?is)<style.*?</style>', ' '
    $text = $text -replace '(?is)<br\s*/?>', ' '
    $text = $text -replace '(?is)</p>', ' '
    $text = $text -replace '(?is)</li>', ' '
    $text = $text -replace '(?is)<.*?>', ' '

    try {
        $text = [System.Net.WebUtility]::HtmlDecode($text)
    }
    catch {
        # If HtmlDecode is unavailable for any reason, continue with stripped text.
    }

    return (($text.Trim()) -replace '\s+', ' ')
}

function Get-TextPreview {
    param(
        [AllowNull()]
        [string]$Text,

        [int]$MaxLength = 300
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    $clean = (($Text.Trim()) -replace '\s+', ' ')

    if ($clean.Length -le $MaxLength) {
        return $clean
    }

    return $clean.Substring(0, $MaxLength) + "..."
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

function Get-ListStatus {
    param(
        [AllowNull()]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [string[]]$AllowedValues,

        [string]$MissingStatus = "Missing",

        [string]$ExpectedStatus = "Expected",

        [string]$UnexpectedStatus = "Unexpected"
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $MissingStatus
    }

    $text = $Value.Trim()

    foreach ($allowedValue in $AllowedValues) {
        if ($text -eq $allowedValue) {
            return $ExpectedStatus
        }
    }

    return $UnexpectedStatus
}

function Get-ExistingCommentsRisk {
    param(
        [AllowNull()]
        [string]$Comments,

        [int]$Length,

        [int]$SubstantialThreshold = 300
    )

    if ([string]::IsNullOrWhiteSpace($Comments) -or $Length -eq 0) {
        return "Low - Blank"
    }

    $riskReasons = @()

    if ($Length -ge $SubstantialThreshold) {
        $riskReasons += "SubstantialLength"
    }

    if ($Comments -match '(?i)<h3') {
        $riskReasons += "StructuredHtml"
    }

    if ($Comments -match '(?i)Source Notes') {
        $riskReasons += "SourceNotes"
    }

    if ($Comments -match '(?i)\b(my notes|personal note|keith note|reading note|review note|user note)\b') {
        $riskReasons += "PossibleUserNotes"
    }

    if ($riskReasons.Count -gt 0) {
        return "High - " + ($riskReasons -join ",")
    }

    if ($Length -gt 0 -and $Length -lt $SubstantialThreshold) {
        return "Medium - Short Existing Comments"
    }

    return "Medium"
}

function Test-SourceNotesHtmlPresent {
    param(
        [AllowNull()]
        [string]$ProposedComments
    )

    if ([string]::IsNullOrWhiteSpace($ProposedComments)) {
        return $false
    }

    return ($ProposedComments -match '(?is)<h3>\s*Source Notes\s*</h3>')
}

function Get-HtmlValidationResult {
    param(
        [AllowNull()]
        [string]$Html
    )

    $issues = @()

    if ([string]::IsNullOrWhiteSpace($Html)) {
        return [pscustomobject]@{
            Status = "Missing"
            Issues = ""
        }
    }

    foreach ($pattern in $BlockedHtmlPatterns) {
        if ($Html.IndexOf($pattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $issues += "Blocked HTML pattern: $pattern"
        }
    }

    if ($Html -match '(?is)<[^>]+style\s*=') {
        $issues += "Inline style attribute detected"
    }

    if ($Html -match '(?is)<[^>]+on[a-z]+\s*=') {
        $issues += "Inline event handler detected"
    }

    $tagMatches = [regex]::Matches($Html, '(?is)</?\s*([a-zA-Z0-9]+)[^>]*>')
    $allowedTags = @(
        "h3",
        "p",
        "ul",
        "ol",
        "li",
        "i",
        "em",
        "b",
        "strong",
        "br"
    )

    foreach ($match in $tagMatches) {
        $tagName = $match.Groups[1].Value.ToLowerInvariant()

        if ($tagName -notin $allowedTags) {
            $issues += "Unsupported HTML tag: $tagName"
        }
    }

    if ($issues.Count -gt 0) {
        return [pscustomobject]@{
            Status = "Blocked"
            Issues = ($issues | Select-Object -Unique) -join "; "
        }
    }

    return [pscustomobject]@{
        Status = "Allowed"
        Issues = ""
    }
}

function Get-PlaceholderResult {
    param(
        [AllowNull()]
        [string]$Text
    )

    $matches = @()

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return [pscustomobject]@{
            Status = "None"
            Matches = ""
        }
    }

    foreach ($pattern in $PlaceholderPatterns) {
        if ($Text.IndexOf($pattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $matches += $pattern
        }
    }

    if ($matches.Count -gt 0) {
        return [pscustomobject]@{
            Status = "Found"
            Matches = ($matches | Select-Object -Unique) -join "; "
        }
    }

    return [pscustomobject]@{
        Status = "None"
        Matches = ""
    }
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not (Test-Path $InputTsv)) {
    throw "Input TSV was not found: $InputTsv"
}

Write-Host "Running comments dry run..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Input: $InputTsv"
Write-Host "Report: $ReportCsv"

$inputRows = @(Import-Csv -Path $InputTsv -Delimiter "`t")

$requiredColumns = @(
    "CalibreId",
    "Title",
    "Authors",
    "ExistingCommentsHash",
    "ExistingCommentsLength",
    "ProposedComments",
    "CommentsTemplateProfile",
    "CommentsMode",
    "ChangeReason",
    "Confidence",
    "ManualReviewRequired",
    "SourceNotes"
)

Test-RequiredColumns -Rows $inputRows -RequiredColumns $requiredColumns

Write-Host "Rows loaded from TSV: $($inputRows.Count)"

$fieldList = @(
    "id",
    "title",
    "authors",
    "comments"
) -join ","

$args = @(
    "list",
    "--for-machine",
    "--fields", $fieldList
)

Write-Host "Reading current Calibre title/author/comments metadata..."

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
    $title = [string]$row.Title
    $authors = [string]$row.Authors
    $existingCommentsHash = ([string]$row.ExistingCommentsHash).Trim()
    $existingCommentsLength = 0
    [void][int]::TryParse(([string]$row.ExistingCommentsLength), [ref]$existingCommentsLength)

    $proposedComments = [string]$row.ProposedComments
    $commentsTemplateProfile = ([string]$row.CommentsTemplateProfile).Trim()
    $commentsMode = ([string]$row.CommentsMode).Trim()
    $changeReason = [string]$row.ChangeReason
    $confidence = ([string]$row.Confidence).Trim()
    $manualReviewRequired = Normalize-YesNo -Value $row.ManualReviewRequired
    $sourceNotes = [string]$row.SourceNotes

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
    $currentComments = ""
    $currentCommentsLength = 0
    $currentCommentsHash = ""
    $currentCommentsPreview = ""

    if (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        if ($currentBookMap.ContainsKey($calibreId)) {
            $currentBook = $currentBookMap[$calibreId]
            $currentTitle = [string]$currentBook.title
            $currentAuthors = Format-Authors $currentBook.authors
            $currentComments = [string]$currentBook.comments
            $currentCommentsLength = $currentComments.Length
            $currentCommentsHash = Get-Sha256Hash -Value $currentComments
            $currentCommentsPreview = Get-TextPreview -Text (Convert-HtmlToPlainText -Html $currentComments) -MaxLength $CommentsPreviewLength
        }
        else {
            $blockingReasons += "CalibreId not found in current Calibre metadata"
        }
    }

    $titleMatchesCurrent = "No"
    $authorsMatchCurrent = "No"
    $commentsHashMatchesCurrent = "No"

    if ($null -ne $currentBook) {
        if ((Normalize-ComparableValue $title) -ceq (Normalize-ComparableValue $currentTitle)) {
            $titleMatchesCurrent = "Yes"
        }
        else {
            $blockingReasons += "Title does not match current Calibre title"
        }

        if ((Normalize-ComparableValue $authors) -ceq (Normalize-ComparableValue $currentAuthors)) {
            $authorsMatchCurrent = "Yes"
        }
        else {
            $blockingReasons += "Authors do not match current Calibre authors"
        }

        if ([string]::IsNullOrWhiteSpace($existingCommentsHash)) {
            $blockingReasons += "Missing ExistingCommentsHash"
        }
        elseif ($existingCommentsHash -eq $currentCommentsHash) {
            $commentsHashMatchesCurrent = "Yes"
        }
        else {
            $blockingReasons += "ExistingCommentsHash does not match current comments hash"
        }
    }

    $hasProposedComments = -not [string]::IsNullOrWhiteSpace($proposedComments)
    $proposedCommentsLength = 0

    if ($hasProposedComments) {
        $proposedCommentsLength = $proposedComments.Length
    }

    $proposedCommentsPreview = Get-TextPreview -Text (Convert-HtmlToPlainText -Html $proposedComments) -MaxLength $CommentsPreviewLength

    if (-not $hasProposedComments) {
        $blockingReasons += "Missing ProposedComments"
    }

    $templateProfileStatus = Get-ListStatus `
        -Value $commentsTemplateProfile `
        -AllowedValues $AllowedTemplateProfiles

    if ($templateProfileStatus -ne "Expected") {
        $blockingReasons += "CommentsTemplateProfile is missing or unexpected"
    }

    $commentsModeStatus = Get-ListStatus `
        -Value $commentsMode `
        -AllowedValues $AllowedCommentsModes

    if ($commentsModeStatus -ne "Expected") {
        $blockingReasons += "CommentsMode is missing or unexpected"
    }

    if ($commentsMode -eq "Skip") {
        $blockingReasons += "CommentsMode is Skip"
    }

    if ($commentsMode -eq "Merge") {
        $blockingReasons += "CommentsMode Merge is not supported in v0.6"
    }

    $confidenceStatus = Get-ListStatus `
        -Value $confidence `
        -AllowedValues $AllowedConfidenceValues

    if ($confidenceStatus -ne "Expected") {
        $blockingReasons += "Confidence is missing or unexpected"
    }

    if ($confidence -eq "Low - Manual Review Recommended") {
        $blockingReasons += "Low confidence requires manual review"
    }

    if ($manualReviewRequired -notin @("Yes", "No")) {
        $blockingReasons += "ManualReviewRequired must be Yes or No"
    }

    if ($manualReviewRequired -eq "Yes") {
        $blockingReasons += "Manual review required"
    }

    if ($hasProposedComments -and [string]::IsNullOrWhiteSpace($changeReason)) {
        $blockingReasons += "Missing ChangeReason"
    }

    $sourceNotesPresent = "No"

    if (-not [string]::IsNullOrWhiteSpace($sourceNotes)) {
        $sourceNotesPresent = "Yes"
    }
    else {
        $blockingReasons += "Missing SourceNotes"
    }

    $sourceNotesHtmlPresent = "No"

    if (Test-SourceNotesHtmlPresent -ProposedComments $proposedComments) {
        $sourceNotesHtmlPresent = "Yes"
    }
    elseif ($hasProposedComments) {
        $blockingReasons += "ProposedComments missing Source Notes HTML section"
    }

    $htmlValidation = Get-HtmlValidationResult -Html $proposedComments

    if ($htmlValidation.Status -eq "Blocked") {
        $blockingReasons += "ProposedComments contains blocked or unsupported HTML"
    }

    $placeholderResult = Get-PlaceholderResult -Text $proposedComments

    if ($placeholderResult.Status -eq "Found") {
        $blockingReasons += "ProposedComments contains placeholder or unsafe text"
    }

    $existingCommentsRisk = Get-ExistingCommentsRisk `
        -Comments $currentComments `
        -Length $currentCommentsLength `
        -SubstantialThreshold $SubstantialExistingCommentsThreshold

    if ($commentsMode -eq "Replace" -and $existingCommentsRisk -like "High*") {
        $blockingReasons += "Replace blocked for high-risk existing comments"
    }

    $applyEligible = "No"

    if ($blockingReasons.Count -eq 0) {
        $applyEligible = "Yes"
    }

    [pscustomobject]@{
        CalibreId                     = $calibreId
        Title                         = $title
        Authors                       = $authors
        CurrentTitle                  = $currentTitle
        CurrentAuthors                = $currentAuthors
        TitleMatchesCurrent           = $titleMatchesCurrent
        AuthorsMatchCurrent           = $authorsMatchCurrent

        ExistingCommentsLength        = $existingCommentsLength
        CurrentCommentsLength         = $currentCommentsLength
        ExistingCommentsHash          = $existingCommentsHash
        CurrentCommentsHash           = $currentCommentsHash
        CommentsHashMatchesCurrent    = $commentsHashMatchesCurrent
        ExistingCommentsRisk          = $existingCommentsRisk
        CurrentCommentsPreview        = $currentCommentsPreview

        ProposedCommentsLength        = $proposedCommentsLength
        ProposedCommentsPreview       = $proposedCommentsPreview
        CommentsTemplateProfile       = $commentsTemplateProfile
        CommentsTemplateProfileStatus = $templateProfileStatus
        CommentsMode                  = $commentsMode
        CommentsModeStatus            = $commentsModeStatus
        ChangeReason                  = $changeReason
        Confidence                    = $confidence
        ConfidenceStatus              = $confidenceStatus
        ManualReviewRequired          = $manualReviewRequired
        SourceNotesPresent            = $sourceNotesPresent
        SourceNotesHtmlPresent        = $sourceNotesHtmlPresent
        HtmlValidationStatus          = $htmlValidation.Status
        HtmlValidationIssues          = $htmlValidation.Issues
        PlaceholderStatus             = $placeholderResult.Status
        PlaceholderMatches            = $placeholderResult.Matches
        DuplicateCalibreId            = if ($isDuplicateCalibreId) { "Yes" } else { "No" }
        ApplyEligible                 = $applyEligible
        BlockingReasons               = ($blockingReasons | Select-Object -Unique) -join "; "
    }
}

$outputFolder = Split-Path -Path $ReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$reportRows | Export-Csv -Path $ReportCsv -NoTypeInformation -Encoding UTF8

$eligibleCount = @($reportRows | Where-Object { $_.ApplyEligible -eq "Yes" }).Count
$blockedCount = @($reportRows | Where-Object { $_.ApplyEligible -ne "Yes" }).Count
$missingProposedCount = @($reportRows | Where-Object { $_.BlockingReasons -match "Missing ProposedComments" }).Count
$highRiskExistingCount = @($reportRows | Where-Object { $_.ExistingCommentsRisk -like "High*" }).Count
$hashMismatchCount = @($reportRows | Where-Object { $_.CommentsHashMatchesCurrent -ne "Yes" }).Count
$htmlBlockedCount = @($reportRows | Where-Object { $_.HtmlValidationStatus -eq "Blocked" }).Count
$missingSourceNotesCount = @($reportRows | Where-Object { $_.SourceNotesPresent -ne "Yes" }).Count
$manualReviewCount = @($reportRows | Where-Object { $_.ManualReviewRequired -eq "Yes" }).Count

Write-Host "Dry run complete: $ReportCsv"
Write-Host "Rows reviewed: $(@($reportRows).Count)"
Write-Host "Rows eligible for apply: $eligibleCount"
Write-Host "Rows blocked: $blockedCount"
Write-Host "Rows missing proposed comments: $missingProposedCount"
Write-Host "Rows with high-risk existing comments: $highRiskExistingCount"
Write-Host "Rows with comments hash mismatch: $hashMismatchCount"
Write-Host "Rows with blocked HTML: $htmlBlockedCount"
Write-Host "Rows missing source notes: $missingSourceNotesCount"
Write-Host "Rows marked manual review: $manualReviewCount"
Write-Host ""
Write-Host "This was a dry run only. No Calibre metadata was modified."
