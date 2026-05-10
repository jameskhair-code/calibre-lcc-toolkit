<#
.SYNOPSIS
Creates a read-only identifier proposal worksheet from MQG-02 candidate diagnostics.

.DESCRIPTION
Reads identifier-mqg02-candidate-summary.csv and creates a proposal/review worksheet
that classifies each Calibre record into an initial MQG-02 action bucket.

This script is read-only and does not modify Calibre metadata.

The proposal worksheet is intended to become the bridge between identifier inventory
diagnostics and future identifier enrichment/apply workflows.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\New-IdentifierProposalWorksheet.ps1 `
  -CandidateSummaryCsv ".\reports\identifier-mqg02-candidate-summary.csv" `
  -ProposalTsv ".\input\identifier-proposal-worksheet.tsv" `
  -ProposalSummaryCsv ".\reports\identifier-proposal-summary.csv"
#>

[CmdletBinding()]
param(
    [string]$CandidateSummaryCsv = ".\reports\identifier-mqg02-candidate-summary.csv",

    [string]$ProposalTsv = ".\input\identifier-proposal-worksheet.tsv",

    [string]$ProposalSummaryCsv = ".\reports\identifier-proposal-summary.csv"
)

function Get-MissingCoreFields {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row
    )

    $missing = @()

    if ($Row.HasIsbn -ne "Yes") {
        $missing += "ISBN"
    }

    if ($Row.HasAmazon -ne "Yes") {
        $missing += "Amazon/ASIN"
    }

    if ($Row.HasGoodreads -ne "Yes") {
        $missing += "Goodreads"
    }

    return ($missing -join "; ")
}

function New-IdentifierProposal {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row
    )

    $recommendedStatus = [string]$Row.RecommendedStatus
    $missingCoreFields = Get-MissingCoreFields -Row $Row

    $proposedAction = "Flag Review"
    $approvalStatus = "Proposed - Needs Human Review"
    $manualReviewRequired = "Yes"
    $confidence = "Medium"
    $mqg02CompletionCandidate = "No"
    $proposalBasis = ""
    $changeReason = ""
    $proposedIdentifierType = ""
    $proposedIdentifierValue = ""

    switch ($recommendedStatus) {
        "Ready - Strong Core" {
            $proposedAction = "Accept As-Is"
            $approvalStatus = "Proposed - Auto Eligible"
            $manualReviewRequired = "No"
            $confidence = "High"
            $mqg02CompletionCandidate = "Yes"
            $proposalBasis = "Record has strong core identifier coverage and no detected duplicate/suspicious identifier issues."
            $changeReason = "Initial diagnostics indicate the record is MQG-02 ready under the active identifier rules profile."
        }

        "Review - Missing ISBN" {
            $proposedAction = "Research Missing ISBN"
            $approvalStatus = "Proposed - Needs Human Review"
            $manualReviewRequired = "Yes"
            $confidence = "Low"
            $mqg02CompletionCandidate = "No"
            $proposalBasis = "Record is missing a primary ISBN anchor."
            $changeReason = "ISBN should be researched or explicitly accepted as unavailable/not applicable before MQG-02 completion."
        }

        "Review - Missing External Link Targets" {
            $proposedAction = "Review Missing External Link Targets"
            $approvalStatus = "Proposed - Needs Human Review"
            $manualReviewRequired = "Yes"
            $confidence = "Medium"
            $mqg02CompletionCandidate = "No"
            $proposalBasis = "Record has ISBN coverage but is missing both Amazon/ASIN and Goodreads link targets."
            $changeReason = "External link targets should be populated when confident matches exist, or accepted as-is when no reliable match is available."
        }

        "Review - Missing One External Link Target" {
            $proposedAction = "Review Missing One External Link Target"
            $approvalStatus = "Proposed - Needs Human Review"
            $manualReviewRequired = "Yes"
            $confidence = "Medium"
            $mqg02CompletionCandidate = "No"
            $proposalBasis = "Record is missing one preferred external link target."
            $changeReason = "Missing Amazon/ASIN or Goodreads should be populated when a confident match exists, or accepted as-is."
        }

        "Review - Duplicate Identifier" {
            $proposedAction = "Review Duplicate Identifier"
            $approvalStatus = "Proposed - Needs Human Review"
            $manualReviewRequired = "Yes"
            $confidence = "Medium"
            $mqg02CompletionCandidate = "No"
            $proposalBasis = "Record has at least one identifier value also present on another Calibre record."
            $changeReason = "Duplicate identifiers may indicate duplicate records, multi-volume edge cases, or metadata errors."
        }

        "Review - Suspicious Identifier Type" {
            $proposedAction = "Review Suspicious Identifier Type"
            $approvalStatus = "Proposed - Needs Human Review"
            $manualReviewRequired = "Yes"
            $confidence = "Medium"
            $mqg02CompletionCandidate = "No"
            $proposalBasis = "Record has an identifier type name that appears malformed or misplaced."
            $changeReason = "Suspicious identifier types should be normalized, removed, or accepted after review."
        }

        default {
            $proposedAction = "Flag Review"
            $approvalStatus = "Proposed - Needs Human Review"
            $manualReviewRequired = "Yes"
            $confidence = "Low"
            $mqg02CompletionCandidate = "No"
            $proposalBasis = "Record has an unrecognized MQG-02 candidate status."
            $changeReason = "Manual review required because the candidate status was not recognized by the proposal generator."
        }
    }

    [pscustomobject]@{
        CalibreId                 = $Row.CalibreId
        Title                     = $Row.Title
        Authors                   = $Row.Authors
        RecommendedStatus         = $recommendedStatus
        ProposedAction            = $proposedAction
        ApprovalStatus            = $approvalStatus
        ManualReviewRequired      = $manualReviewRequired
        Confidence                = $confidence
        Mqg02CompletionCandidate  = $mqg02CompletionCandidate
        MissingCoreFields         = $missingCoreFields
        ExistingIsbn              = $Row.IsbnValue
        ExistingAmazonOrAsin      = $Row.AmazonOrAsinValue
        ExistingGoodreads         = $Row.GoodreadsValue
        HasSuspiciousType         = $Row.HasSuspiciousType
        HasDuplicateIsbn          = $Row.HasDuplicateIsbn
        HasDuplicateAmazon        = $Row.HasDuplicateAmazon
        HasDuplicateGoodreads     = $Row.HasDuplicateGoodreads
        IssueCount                = $Row.IssueCount
        IssueSummary              = $Row.IssueSummary
        ProposedIdentifierType    = $proposedIdentifierType
        ProposedIdentifierValue   = $proposedIdentifierValue
        ProposalBasis             = $proposalBasis
        EvidenceUsed              = "Identifier inventory and diagnostics only; no external lookup performed."
        ChangeReason              = $changeReason
        ReviewerDecision          = ""
        ReviewerNotes             = ""
        IdentifierTypes           = $Row.IdentifierTypes
        IdentifiersRaw            = $Row.IdentifiersRaw
    }
}

if (-not (Test-Path $CandidateSummaryCsv)) {
    throw "Candidate summary CSV not found: $CandidateSummaryCsv"
}

Write-Host "Identifier proposal worksheet"
Write-Host "============================="
Write-Host ""
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Candidate summary CSV: $CandidateSummaryCsv"
Write-Host "Proposal TSV: $ProposalTsv"
Write-Host "Proposal summary CSV: $ProposalSummaryCsv"
Write-Host ""

$rows = @(Import-Csv -Path $CandidateSummaryCsv)

if ($rows.Count -eq 0) {
    throw "Candidate summary CSV has no rows: $CandidateSummaryCsv"
}

$proposalRows = @(
    foreach ($row in $rows) {
        New-IdentifierProposal -Row $row
    }
)

$summaryRows = @()

$summaryRows += $proposalRows |
    Group-Object ApprovalStatus |
    Sort-Object -Property @{ Expression = "Count"; Descending = $true }, @{ Expression = "Name"; Ascending = $true } |
    ForEach-Object {
        [pscustomobject]@{
            Metric = "ApprovalStatus"
            Name   = $_.Name
            Count  = $_.Count
        }
    }

$summaryRows += $proposalRows |
    Group-Object ProposedAction |
    Sort-Object -Property @{ Expression = "Count"; Descending = $true }, @{ Expression = "Name"; Ascending = $true } |
    ForEach-Object {
        [pscustomobject]@{
            Metric = "ProposedAction"
            Name   = $_.Name
            Count  = $_.Count
        }
    }

$summaryRows += $proposalRows |
    Group-Object ManualReviewRequired |
    Sort-Object -Property @{ Expression = "Count"; Descending = $true }, @{ Expression = "Name"; Ascending = $true } |
    ForEach-Object {
        [pscustomobject]@{
            Metric = "ManualReviewRequired"
            Name   = $_.Name
            Count  = $_.Count
        }
    }

$summaryRows += $proposalRows |
    Group-Object Mqg02CompletionCandidate |
    Sort-Object -Property @{ Expression = "Count"; Descending = $true }, @{ Expression = "Name"; Ascending = $true } |
    ForEach-Object {
        [pscustomobject]@{
            Metric = "Mqg02CompletionCandidate"
            Name   = $_.Name
            Count  = $_.Count
        }
    }

$outputFolders = @(
    (Split-Path -Path $ProposalTsv -Parent),
    (Split-Path -Path $ProposalSummaryCsv -Parent)
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

foreach ($folder in $outputFolders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

$proposalRows | Export-Csv -Path $ProposalTsv -Delimiter "`t" -NoTypeInformation -Encoding UTF8
$summaryRows | Export-Csv -Path $ProposalSummaryCsv -NoTypeInformation -Encoding UTF8

$autoEligibleCount = @($proposalRows | Where-Object { $_.ApprovalStatus -eq "Proposed - Auto Eligible" }).Count
$manualReviewCount = @($proposalRows | Where-Object { $_.ManualReviewRequired -eq "Yes" }).Count
$completionCandidateCount = @($proposalRows | Where-Object { $_.Mqg02CompletionCandidate -eq "Yes" }).Count

Write-Host "Proposal worksheet complete."
Write-Host "Rows reviewed: $($proposalRows.Count)"
Write-Host "Auto-eligible proposals: $autoEligibleCount"
Write-Host "Manual-review proposals: $manualReviewCount"
Write-Host "MQG-02 completion candidates: $completionCandidateCount"
Write-Host ""
Write-Host "Files written:"
Write-Host "  $ProposalTsv"
Write-Host "  $ProposalSummaryCsv"
