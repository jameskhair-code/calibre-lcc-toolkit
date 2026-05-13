<#
.SYNOPSIS
Evaluates Author/Title source TSV rows against the MQG-01 rule profile.

.DESCRIPTION
Reads the Author/Title source TSV created by Export-CalibreBatchForAuthorTitleCleanup.ps1
and writes a rule-evaluation TSV with proposed changes, proposal status, reasons,
confidence, manual-review flags, and review actions.

This script is read-only. It does not modify Calibre metadata.

The output intentionally preserves the columns required by Test-AuthorTitleCleanupDryRun.ps1:
- CalibreId
- OriginalTitle
- ProposedTitle
- OriginalAuthors
- ProposedAuthors
- ChangeReason
- Confidence
- ManualReviewRequired

Additional MQG-01 workbench columns are appended for review and future workflow use.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Test-AuthorTitleRuleEvaluation.ps1 `
  -InputTsv ".\input\author-title-cleanup-source-v0125-smoke-mqg01-4058.tsv" `
  -OutputTsv ".\reports\mqg01-rule-evaluation-v0126-smoke-mqg01-4058.tsv"
#>

[CmdletBinding()]
param(
    [string]$InputTsv = ".\input\author-title-cleanup-source-batch.tsv",

    [string]$OutputTsv = ".\reports\mqg01-rule-evaluation-batch.tsv",

    [string]$RulesConfig = ".\config\author-title-normalization-rules.json"
)

function Test-ColumnExists {
    param(
        [Parameter(Mandatory = $true)]
        $Row,

        [Parameter(Mandatory = $true)]
        [string]$ColumnName
    )

    foreach ($property in $Row.PSObject.Properties) {
        if ($property.Name -eq $ColumnName) {
            return $true
        }
    }

    return $false
}

function Test-RequiredColumns {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string[]]$RequiredColumns
    )

    if ($Rows.Count -eq 0) {
        throw "Input TSV contains no rows."
    }

    $firstRow = $Rows | Select-Object -First 1
    $missingColumns = @()

    foreach ($columnName in $RequiredColumns) {
        if (-not (Test-ColumnExists -Row $firstRow -ColumnName $columnName)) {
            $missingColumns += $columnName
        }
    }

    if ($missingColumns.Count -gt 0) {
        throw "Input TSV is missing required columns: $($missingColumns -join ', ')"
    }
}

function Normalize-Whitespace {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ($null -eq $Value) {
        return ""
    }

    return (($Value.Trim()) -replace '\s+', ' ')
}

function Add-UniqueValue {
    param(
        [AllowNull()]
        [string[]]$Values,

        [AllowNull()]
        [string]$Value
    )

    $currentValues = @($Values)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @($currentValues)
    }

    if ($currentValues -notcontains $Value) {
        $currentValues += $Value
    }

    return @($currentValues)
}

function Get-RuleConfigValue {
    param(
        [AllowNull()]
        $Object,

        [Parameter(Mandatory = $true)]
        [string]$PropertyName,

        [Parameter(Mandatory = $true)]
        $DefaultValue
    )

    if ($null -eq $Object) {
        return $DefaultValue
    }

    $property = $Object.PSObject.Properties |
        Where-Object { $_.Name -eq $PropertyName } |
        Select-Object -First 1

    if ($null -eq $property) {
        return $DefaultValue
    }

    if ($null -eq $property.Value) {
        return $DefaultValue
    }

    return $property.Value
}

function Remove-TrailingLiteral {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,

        [Parameter(Mandatory = $true)]
        [string]$Literal
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Value
    }

    if ([string]::IsNullOrWhiteSpace($Literal)) {
        return $Value
    }

    $escapedLiteral = [regex]::Escape($Literal)
    $pattern = "(?i)$escapedLiteral\s*$"

    return (($Value -replace $pattern, "").Trim())
}

function New-RuleEvaluation {
    param(
        [Parameter(Mandatory = $true)]
        $Row,

        [Parameter(Mandatory = $true)]
        $Rules
    )

    $calibreId = ([string]$Row.CalibreId).Trim()
    $originalTitle = [string]$Row.OriginalTitle
    $originalAuthors = [string]$Row.OriginalAuthors

    $proposedTitleValue = $originalTitle
    $proposedAuthorsValue = $originalAuthors

    $ruleIds = @()
    $reasons = @()

    $hasSafeChange = $false
    $hasReviewChange = $false
    $hasManualReviewFlag = $false
    $hasError = $false

    $reviewAction = "No action needed under current rules."

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $hasError = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "E01")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Missing CalibreId.")
    }

    if ([string]::IsNullOrWhiteSpace($originalTitle)) {
        $hasManualReviewFlag = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "M01")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Missing title requires manual review.")
    }

    if ([string]::IsNullOrWhiteSpace($originalAuthors)) {
        $hasManualReviewFlag = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "M02")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Missing author field requires manual review.")
    }

    $normalizedTitle = Normalize-Whitespace -Value $originalTitle

    if (-not [string]::IsNullOrWhiteSpace($originalTitle) -and $normalizedTitle -cne $originalTitle) {
        $proposedTitleValue = $normalizedTitle
        $hasSafeChange = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "S01")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Trimmed title whitespace and normalized repeated spaces.")
    }

    $normalizedAuthors = Normalize-Whitespace -Value $originalAuthors

    if (-not [string]::IsNullOrWhiteSpace($originalAuthors) -and $normalizedAuthors -cne $originalAuthors) {
        $proposedAuthorsValue = $normalizedAuthors
        $hasSafeChange = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "S02")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Trimmed author whitespace and normalized repeated spaces.")
    }

    $titleRules = $Rules.TitleRules
    $removeGenericFictionFormatSubtitles = [bool](Get-RuleConfigValue -Object $titleRules -PropertyName "RemoveGenericFictionFormatSubtitles" -DefaultValue $true)
    $genericFictionFormatSubtitles = @(Get-RuleConfigValue -Object $titleRules -PropertyName "GenericFictionFormatSubtitles" -DefaultValue @(": A Novel", ": A Story"))
    $removeAwardMarketingParentheticals = [bool](Get-RuleConfigValue -Object $titleRules -PropertyName "RemoveAwardMarketingParentheticals" -DefaultValue $true)
    $removeEditionAnniversaryText = [bool](Get-RuleConfigValue -Object $titleRules -PropertyName "RemoveEditionAnniversaryText" -DefaultValue $true)

    if ($removeGenericFictionFormatSubtitles -and -not [string]::IsNullOrWhiteSpace($proposedTitleValue)) {
        foreach ($genericSubtitle in $genericFictionFormatSubtitles) {
            $candidateTitle = Remove-TrailingLiteral -Value $proposedTitleValue -Literal ([string]$genericSubtitle)

            if ($candidateTitle -cne $proposedTitleValue -and -not [string]::IsNullOrWhiteSpace($candidateTitle)) {
                $proposedTitleValue = $candidateTitle
                $hasReviewChange = $true
                $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "T01")
                $reasons = @(Add-UniqueValue -Values $reasons -Value "Removed generic fiction format subtitle.")
                break
            }
        }
    }

    if ($removeAwardMarketingParentheticals -and -not [string]::IsNullOrWhiteSpace($proposedTitleValue)) {
        $awardPattern = '(?i)\s*\([^)]*(award|winner|prize|pulitzer|booker|national book|hugo|nebula|locus|clarke)[^)]*\)\s*$'

        if ($proposedTitleValue -match $awardPattern) {
            $candidateTitle = ($proposedTitleValue -replace $awardPattern, "").Trim()

            if (-not [string]::IsNullOrWhiteSpace($candidateTitle)) {
                $proposedTitleValue = $candidateTitle
                $hasReviewChange = $true
                $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "T02")
                $reasons = @(Add-UniqueValue -Values $reasons -Value "Removed award or marketing parenthetical from title.")
            }
        }
    }

    if ($removeEditionAnniversaryText -and -not [string]::IsNullOrWhiteSpace($proposedTitleValue)) {
        $editionPattern = '(?i)\s*\([^)]*(edition|anniversary|revised|updated)[^)]*\)\s*'

        if ($proposedTitleValue -match $editionPattern) {
            $candidateTitle = ($proposedTitleValue -replace $editionPattern, " ").Trim()
            $candidateTitle = Normalize-Whitespace -Value $candidateTitle

            if (-not [string]::IsNullOrWhiteSpace($candidateTitle) -and $candidateTitle -cne $proposedTitleValue) {
                $proposedTitleValue = $candidateTitle
                $hasReviewChange = $true
                $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "T03")
                $reasons = @(Add-UniqueValue -Values $reasons -Value "Removed edition or anniversary text from title.")
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($proposedTitleValue) -and $proposedTitleValue -match '[\[\]]') {
        $hasManualReviewFlag = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "M03")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Title contains bracketed text that requires manual review.")
    }

    if (-not [string]::IsNullOrWhiteSpace($proposedTitleValue) -and $proposedTitleValue -match '(?i)\([^)]*\)') {
        $hasManualReviewFlag = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "M04")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Title contains parenthetical text not handled by current safe rules.")
    }

    if (-not [string]::IsNullOrWhiteSpace($originalAuthors) -and $originalAuthors -match '(?i)\b(editor|edited by|translator|translated by|illustrator|foreword|introduction|preface)\b') {
        $hasManualReviewFlag = $true
        $ruleIds = @(Add-UniqueValue -Values $ruleIds -Value "M05")
        $reasons = @(Add-UniqueValue -Values $reasons -Value "Author field may contain contributor role text.")
    }

    $titleWouldChange = "No"
    $authorsWouldChange = "No"
    $proposedTitle = ""
    $proposedAuthors = ""

    if (-not [string]::IsNullOrWhiteSpace($proposedTitleValue) -and $proposedTitleValue -cne $originalTitle) {
        $titleWouldChange = "Yes"
        $proposedTitle = $proposedTitleValue
    }

    if (-not [string]::IsNullOrWhiteSpace($proposedAuthorsValue) -and $proposedAuthorsValue -cne $originalAuthors) {
        $authorsWouldChange = "Yes"
        $proposedAuthors = $proposedAuthorsValue
    }

    if ($titleWouldChange -eq "No" -and $authorsWouldChange -eq "No") {
        $hasSafeChange = $false
        $hasReviewChange = $false
    }

    $proposalStatus = "No Change"
    $confidence = "High"
    $manualReviewRequired = "No"

    if ($hasError) {
        $proposalStatus = "Error"
        $confidence = "Low"
        $manualReviewRequired = "Yes"
        $reviewAction = "Resolve the error before continuing."
    }
    elseif ($hasManualReviewFlag) {
        $proposalStatus = "Manual Review"
        $confidence = "Low"
        $manualReviewRequired = "Yes"
        $reviewAction = "Review manually before any dry run or apply step."
    }
    elseif ($hasReviewChange) {
        $proposalStatus = "Change Proposed"
        $confidence = "Medium"
        $manualReviewRequired = "Yes"
        $reviewAction = "Review the proposed change before dry run."
    }
    elseif ($hasSafeChange) {
        $proposalStatus = "Safe Mechanical Change"
        $confidence = "High"
        $manualReviewRequired = "No"
        $reviewAction = "Eligible for future safe-only dry run after review."
    }
    else {
        $proposalStatus = "No Change"
        $confidence = "High"
        $manualReviewRequired = "No"
        $reviewAction = "No action needed under current rules."
    }

    if ($reasons.Count -eq 0) {
        $reasons += "No change recommended under current rules."
    }

    [pscustomobject]@{
        CalibreId              = $calibreId
        OriginalTitle          = $originalTitle
        ProposedTitle          = $proposedTitle
        OriginalAuthors        = $originalAuthors
        ProposedAuthors        = $proposedAuthors
        ChangeReason           = ($reasons -join " ")
        Confidence             = $confidence
        ManualReviewRequired   = $manualReviewRequired
        ProposalStatus         = $proposalStatus
        RuleIds                = ($ruleIds -join "; ")
        ReviewAction           = $reviewAction
        TitleWouldChange       = $titleWouldChange
        AuthorsWouldChange     = $authorsWouldChange
        ISBN                   = [string]$Row.ISBN
        Identifiers            = [string]$Row.Identifiers
        Publisher              = [string]$Row.Publisher
        Published              = [string]$Row.Published
        Series                 = [string]$Row.Series
        SeriesIndex            = [string]$Row.SeriesIndex
        Tags                   = [string]$Row.Tags
        "Award Programs"       = [string]$Row.'Award Programs'
        "MQG LCC"              = [string]$Row.'MQG LCC'
        "Existing LCC"         = [string]$Row.'Existing LCC'
    }
}

if (-not (Test-Path $InputTsv)) {
    throw "InputTsv was not found: $InputTsv"
}

$rules = $null

if (Test-Path $RulesConfig) {
    try {
        $rules = Get-Content -Path $RulesConfig -Raw | ConvertFrom-Json
    }
    catch {
        throw "Could not parse RulesConfig JSON: $($_.Exception.Message)"
    }
}
else {
    Write-Warning "RulesConfig not found. Using built-in conservative defaults: $RulesConfig"
    $rules = [pscustomobject]@{
        ProfileName    = "Built-in conservative Author/Title defaults"
        ProfileVersion = "internal"
        Status         = "Fallback"
        TitleRules     = [pscustomobject]@{
            RemoveGenericFictionFormatSubtitles = $true
            GenericFictionFormatSubtitles       = @(": A Novel", ": A Story")
            RemoveAwardMarketingParentheticals  = $true
            RemoveEditionAnniversaryText        = $true
        }
    }
}

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

Write-Host "MQG-01 Author/Title rule evaluation"
Write-Host "==================================="
Write-Host ""
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Input:       $InputTsv"
Write-Host "Output:      $OutputTsv"
Write-Host "RulesConfig: $RulesConfig"
Write-Host ""

if ($null -ne $rules) {
    Write-Host "Rules profile: $($rules.ProfileName) $($rules.ProfileVersion) ($($rules.Status))"
}

Write-Host "Rows loaded: $($inputRows.Count)"
Write-Host ""

$evaluationRows = @(
    foreach ($row in $inputRows) {
        New-RuleEvaluation -Row $row -Rules $rules
    }
)

$outputFolder = Split-Path -Path $OutputTsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$evaluationRows | Export-Csv -Path $OutputTsv -Delimiter "`t" -NoTypeInformation -Encoding UTF8

$totalRows = $evaluationRows.Count
$noChangeCount = @($evaluationRows | Where-Object { $_.ProposalStatus -eq "No Change" }).Count
$safeMechanicalCount = @($evaluationRows | Where-Object { $_.ProposalStatus -eq "Safe Mechanical Change" }).Count
$changeProposedCount = @($evaluationRows | Where-Object { $_.ProposalStatus -eq "Change Proposed" }).Count
$manualReviewCount = @($evaluationRows | Where-Object { $_.ProposalStatus -eq "Manual Review" }).Count
$errorCount = @($evaluationRows | Where-Object { $_.ProposalStatus -eq "Error" }).Count
$titleChangeCount = @($evaluationRows | Where-Object { $_.TitleWouldChange -eq "Yes" }).Count
$authorsChangeCount = @($evaluationRows | Where-Object { $_.AuthorsWouldChange -eq "Yes" }).Count

Write-Host "Rule evaluation complete: $OutputTsv"
Write-Host "Rows evaluated:          $totalRows"
Write-Host "No change:               $noChangeCount"
Write-Host "Safe mechanical change:  $safeMechanicalCount"
Write-Host "Change proposed:         $changeProposedCount"
Write-Host "Manual review:           $manualReviewCount"
Write-Host "Errors:                  $errorCount"
Write-Host "Rows with title changes: $titleChangeCount"
Write-Host "Rows with author changes: $authorsChangeCount"
Write-Host ""
Write-Host "This was a rule evaluation only. No Calibre metadata was modified."