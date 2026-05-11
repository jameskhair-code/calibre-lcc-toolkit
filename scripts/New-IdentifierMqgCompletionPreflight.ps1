<#
.SYNOPSIS
Creates a read-only MQG-02 completion preflight report for identifier validation results.

.DESCRIPTION
Reads identifier-proposal-validation.csv and current Calibre metadata, then classifies
which rows are safe candidates for a future MQG-02 Identifiers completion write.

This script is read-only and does not modify Calibre metadata.

It checks:
- validation status and completion eligibility
- current Calibre record existence
- title/author drift between validation report and current Calibre state
- current MQG-01 Title & Author status
- current MQG-02 Identifiers status

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\New-IdentifierMqgCompletionPreflight.ps1 `
  -ValidationCsv ".\reports\identifier-proposal-validation.csv" `
  -PreflightCsv ".\reports\identifier-mqg02-completion-preflight.csv" `
  -PreflightSummaryCsv ".\reports\identifier-mqg02-completion-preflight-summary.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$ValidationCsv = ".\reports\identifier-proposal-validation.csv",

    [string]$PreflightCsv = ".\reports\identifier-mqg02-completion-preflight.csv",

    [string]$PreflightSummaryCsv = ".\reports\identifier-mqg02-completion-preflight-summary.csv",

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
        return ($Authors -join " & ")
    }

    return [string]$Authors
}

function Convert-ToYesNo {
    param(
        [AllowNull()]
        $Value
    )

    if ($null -eq $Value) {
        return "No"
    }

    if ($Value -is [bool]) {
        if ($Value) {
            return "Yes"
        }

        return "No"
    }

    $text = ([string]$Value).Trim()

    if ($text -match '^(true|yes|1)$') {
        return "Yes"
    }

    return "No"
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

function Get-RowValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $property = $Row.PSObject.Properties[$Name]

    if ($null -eq $property) {
        return ""
    }

    return ([string]$property.Value).Trim()
}

function Convert-ToIntSafe {
    param(
        [AllowNull()]
        [string]$Value
    )

    $number = 0

    if ([int]::TryParse($Value, [ref]$number)) {
        return $number
    }

    return $null
}

function Get-CurrentBookMap {
    $fieldList = @(
        "id",
        "title",
        "authors",
        "*mqg_title_author",
        "*mqg_identifiers"
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

if (-not (Test-Path $ValidationCsv)) {
    throw "Validation CSV not found: $ValidationCsv"
}

Write-Host "Identifier MQG-02 completion preflight"
Write-Host "======================================"
Write-Host ""
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Validation CSV: $ValidationCsv"
Write-Host "Preflight CSV: $PreflightCsv"
Write-Host "Preflight summary CSV: $PreflightSummaryCsv"
Write-Host ""

$rows = @(Import-Csv -Path $ValidationCsv)

if ($rows.Count -eq 0) {
    throw "Validation CSV has no rows: $ValidationCsv"
}

$requiredColumns = @(
    "CalibreId",
    "Title",
    "Authors",
    "ValidationStatus",
    "CompletionPreflightEligible",
    "ValidationIssueCount",
    "ValidationIssues",
    "ExistingIsbn",
    "ExistingAmazonOrAsin",
    "ExistingGoodreads"
)

$availableColumns = @($rows[0].PSObject.Properties.Name)
$missingColumns = @($requiredColumns | Where-Object { $_ -notin $availableColumns })

if ($missingColumns.Count -gt 0) {
    throw "Validation CSV is missing required columns: $($missingColumns -join ', ')"
}

Write-Host "Rows loaded from validation CSV: $($rows.Count)"
Write-Host "Reading current Calibre MQG status..."

$currentBookMap = Get-CurrentBookMap

Write-Host "Current Calibre records available: $($currentBookMap.Count)"
Write-Host ""

$idCounts = @{}

foreach ($row in $rows) {
    $calibreId = Get-RowValue -Row $row -Name "CalibreId"

    if (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        if (-not $idCounts.ContainsKey($calibreId)) {
            $idCounts[$calibreId] = 0
        }

        $idCounts[$calibreId]++
    }
}

$preflightRows = foreach ($row in $rows) {
    $calibreId = Get-RowValue -Row $row -Name "CalibreId"
    $expectedTitle = Get-RowValue -Row $row -Name "Title"
    $expectedAuthors = Get-RowValue -Row $row -Name "Authors"
    $validationStatus = Get-RowValue -Row $row -Name "ValidationStatus"
    $completionPreflightEligible = Get-RowValue -Row $row -Name "CompletionPreflightEligible"
    $validationIssueCountText = Get-RowValue -Row $row -Name "ValidationIssueCount"
    $validationIssueCount = Convert-ToIntSafe -Value $validationIssueCountText

    $currentTitle = ""
    $currentAuthors = ""
    $currentMqgTitleAuthor = "No"
    $currentMqgIdentifiers = "No"

    $issues = @()
    $preflightBasis = ""

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $issues += "Missing CalibreId"
    }
    elseif ($idCounts[$calibreId] -gt 1) {
        $issues += "Duplicate CalibreId in validation CSV"
    }

    if ($null -eq $validationIssueCount) {
        $issues += "ValidationIssueCount is not numeric"
        $validationIssueCount = -1
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and -not $currentBookMap.ContainsKey($calibreId)) {
        $issues += "CalibreId not found in current Calibre metadata"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        $currentBook = $currentBookMap[$calibreId]
        $currentTitle = [string]$currentBook.title
        $currentAuthors = Format-Authors $currentBook.authors
        $currentMqgTitleAuthor = Convert-ToYesNo -Value $currentBook.'*mqg_title_author'
        $currentMqgIdentifiers = Convert-ToYesNo -Value $currentBook.'*mqg_identifiers'

        if ((Normalize-ComparableValue $currentTitle) -cne (Normalize-ComparableValue $expectedTitle)) {
            $issues += "Current title no longer matches validation report"
        }

        if ((Normalize-ComparableValue $currentAuthors) -cne (Normalize-ComparableValue $expectedAuthors)) {
            $issues += "Current authors no longer match validation report"
        }
    }

    $validationReady = (
        $validationStatus -eq "Ready - MQG-02 Completion Preflight" -and
        $completionPreflightEligible -eq "Yes" -and
        $validationIssueCount -eq 0
    )

    if (-not $validationReady -and $validationStatus -ne "Manual Review Required") {
        $issues += "Validation row is not ready and is not a normal manual-review row"
    }

    $preflightStatus = "Manual Review Required"
    $futureApplyEligible = "No"

    if ($issues.Count -gt 0) {
        $preflightStatus = "Blocked - Preflight Error"
        $futureApplyEligible = "No"
        $preflightBasis = "Preflight detected structural, current-state, or source-drift issues."
    }
    elseif ($currentMqgIdentifiers -eq "Yes") {
        $preflightStatus = "Already MQG-02 Complete"
        $futureApplyEligible = "No"
        $preflightBasis = "Current Calibre metadata already has #mqg_identifiers set to true."
    }
    elseif ($validationReady) {
        $preflightStatus = "Ready - Future MQG-02 Apply"
        $futureApplyEligible = "Yes"
        $preflightBasis = "Validation report and current Calibre state support future MQG-02 completion."
    }
    else {
        $preflightStatus = "Manual Review Required"
        $futureApplyEligible = "No"
        $preflightBasis = "Validation report indicates manual review is required before MQG-02 completion."
    }

    [pscustomobject]@{
        CalibreId                   = $calibreId
        Title                       = $expectedTitle
        Authors                     = $expectedAuthors
        CurrentTitle                = $currentTitle
        CurrentAuthors              = $currentAuthors
        CurrentMqgTitleAuthor       = $currentMqgTitleAuthor
        CurrentMqgIdentifiers       = $currentMqgIdentifiers
        ValidationStatus            = $validationStatus
        CompletionPreflightEligible = $completionPreflightEligible
        FutureApplyEligible         = $futureApplyEligible
        PreflightStatus             = $preflightStatus
        PreflightIssueCount         = $issues.Count
        PreflightIssues             = ($issues -join "; ")
        PreflightBasis              = $preflightBasis
        ExistingIsbn                = Get-RowValue -Row $row -Name "ExistingIsbn"
        ExistingAmazonOrAsin        = Get-RowValue -Row $row -Name "ExistingAmazonOrAsin"
        ExistingGoodreads           = Get-RowValue -Row $row -Name "ExistingGoodreads"
        ValidationIssues            = Get-RowValue -Row $row -Name "ValidationIssues"
        IdentifierTypes             = Get-RowValue -Row $row -Name "IdentifierTypes"
        IdentifiersRaw              = Get-RowValue -Row $row -Name "IdentifiersRaw"
    }
}

$summaryRows = @()

foreach ($metricName in @("PreflightStatus", "FutureApplyEligible", "CurrentMqgTitleAuthor", "CurrentMqgIdentifiers", "ValidationStatus")) {
    $summaryRows += $preflightRows |
        Group-Object $metricName |
        Sort-Object -Property @{ Expression = "Count"; Descending = $true }, @{ Expression = "Name"; Ascending = $true } |
        ForEach-Object {
            [pscustomobject]@{
                Metric = $metricName
                Name   = $_.Name
                Count  = $_.Count
            }
        }
}

$outputFolders = @(
    (Split-Path -Path $PreflightCsv -Parent),
    (Split-Path -Path $PreflightSummaryCsv -Parent)
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

foreach ($folder in $outputFolders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

$preflightRows | Export-Csv -Path $PreflightCsv -NoTypeInformation -Encoding UTF8
$summaryRows | Export-Csv -Path $PreflightSummaryCsv -NoTypeInformation -Encoding UTF8

$readyCount = @($preflightRows | Where-Object { $_.PreflightStatus -eq "Ready - Future MQG-02 Apply" }).Count
$alreadyCompleteCount = @($preflightRows | Where-Object { $_.PreflightStatus -eq "Already MQG-02 Complete" }).Count
$manualReviewCount = @($preflightRows | Where-Object { $_.PreflightStatus -eq "Manual Review Required" }).Count
$blockedCount = @($preflightRows | Where-Object { $_.PreflightStatus -eq "Blocked - Preflight Error" }).Count

Write-Host "MQG-02 completion preflight complete."
Write-Host "Rows reviewed: $($preflightRows.Count)"
Write-Host "Ready for future MQG-02 apply: $readyCount"
Write-Host "Already MQG-02 complete: $alreadyCompleteCount"
Write-Host "Manual review required: $manualReviewCount"
Write-Host "Blocked / preflight error: $blockedCount"
Write-Host ""
Write-Host "Files written:"
Write-Host "  $PreflightCsv"
Write-Host "  $PreflightSummaryCsv"
