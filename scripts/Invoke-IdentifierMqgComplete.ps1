<#
.SYNOPSIS
Marks MQG-02 Identifiers complete for rows proven safe by the Identifier MQG-02 completion preflight.

.DESCRIPTION
Reads identifier-mqg02-completion-preflight.csv and marks the Calibre custom field
#mqg_identifiers true only for rows that remain safe at apply time.

The I5 preflight report is treated as the source evidence artifact.

This script does not repair, normalize, add, delete, or rewrite identifier values.
It only marks MQG-02 complete after:
- the I5 preflight row is ready,
- the current Calibre record still exists,
- current title/authors have not drifted,
- current #mqg_identifiers is still false/no,
- no preflight issues are present,
- and the operator enters the explicit confirmation phrase.

Rows that are stale, already complete, blocked, duplicated, missing, or unsafe are skipped and reported.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-IdentifierMqgComplete.ps1 `
  -PreflightCsv ".\reports\identifier-mqg02-completion-preflight.csv" `
  -MqgReportCsv ".\reports\identifier-mqg02-completion-apply.csv" `
  -PreflightOnly

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-IdentifierMqgComplete.ps1 `
  -PreflightCsv ".\reports\identifier-mqg02-completion-preflight.csv" `
  -MqgReportCsv ".\reports\identifier-mqg02-completion-apply.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$PreflightCsv = ".\reports\identifier-mqg02-completion-preflight.csv",

    [string]$MqgReportCsv = ".\reports\identifier-mqg02-completion-apply.csv",

    [string]$MqgFieldName = "#mqg_identifiers",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "MARK MQG-02 COMPLETE",

    [switch]$PreflightOnly
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

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = ($output | ForEach-Object { [string]$_ }) -join " "
    }
}

function Format-Authors {
    param(
        [AllowNull()]
        $Authors
    )

    if ($null -eq $Authors) {
        return ""
    }

    if ($Authors -is [System.Array]) {
        return ($Authors -join " & ")
    }

    return [string]$Authors
}

function Normalize-Value {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return $Value.Trim()
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

    if ([string]::IsNullOrWhiteSpace($text)) {
        return "No"
    }

    if ($text -in @("True", "true", "TRUE", "Yes", "yes", "YES", "1")) {
        return "Yes"
    }

    return "No"
}

function Add-BlockingReason {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    if ([string]::IsNullOrWhiteSpace($Row.BlockingReasons)) {
        $Row.BlockingReasons = $Reason
    }
    else {
        $Row.BlockingReasons += "; $Reason"
    }
}

function Test-MqgFieldTrue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CalibreId,

        [Parameter(Mandatory = $true)]
        [string]$MqgFieldName
    )

    $result = Invoke-CalibreDb -Arguments @(
        "show_metadata",
        $CalibreId,
        "--as-opf"
    )

    if ($result.ExitCode -ne 0) {
        return [pscustomobject]@{
            IsTrue = $false
            Status = "Readback failed with exit code $($result.ExitCode)"
        }
    }

    $fieldPattern = [regex]::Escape("calibre:user_metadata:$MqgFieldName") +
        ".*?" +
        [regex]::Escape("&quot;#value#&quot;") +
        "\s*:\s*true"

    if ($result.Output -match $fieldPattern) {
        return [pscustomobject]@{
            IsTrue = $true
            Status = "Confirmed true"
        }
    }

    return [pscustomobject]@{
        IsTrue = $false
        Status = "Field was not confirmed true during readback"
    }
}

function Get-CurrentBookMap {
    $fieldList = @(
        "id",
        "title",
        "authors",
        "*mqg_title_author",
        "*mqg_identifiers"
    ) -join ","

    $result = Invoke-CalibreDb -Arguments @(
        "list",
        "--for-machine",
        "--fields",
        $fieldList
    )

    if ($result.ExitCode -ne 0) {
        throw "calibredb list failed with exit code $($result.ExitCode). Output: $($result.Output)"
    }

    $jsonText = $result.Output.Trim()

    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw "No output returned from calibredb while reading current metadata."
    }

    try {
        $converted = $jsonText | ConvertFrom-Json
    }
    catch {
        throw "Could not parse calibredb JSON output: $($_.Exception.Message)"
    }

    $books = @(Convert-ToFlatArray -Value $converted)
    $bookMap = @{}

    foreach ($book in $books) {
        $idText = Normalize-Value -Value ([string]$book.id)

        if (-not [string]::IsNullOrWhiteSpace($idText)) {
            $bookMap[$idText] = $book
        }
    }

    return $bookMap
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not (Test-Path $PreflightCsv)) {
    throw "Identifier MQG-02 completion preflight CSV was not found: $PreflightCsv"
}

Write-Host "Identifier MQG-02 complete marker"
Write-Host "================================="
Write-Host ""
Write-Host "WARNING: This script can modify Calibre metadata."
Write-Host "Preflight CSV: $PreflightCsv"
Write-Host "MQG report CSV: $MqgReportCsv"
Write-Host "MQG field: $MqgFieldName"
Write-Host "Scope: mark MQG-02 complete only; identifier values are not modified."
Write-Host ""

if ($PreflightOnly) {
    Write-Host "Mode: Preflight only. No Calibre metadata will be modified." -ForegroundColor Yellow
}
else {
    Write-Host "Mode: Apply. Calibre metadata may be modified after confirmation." -ForegroundColor Yellow
}

Write-Host ""

$rows = @(Import-Csv -Path $PreflightCsv)

if ($rows.Count -eq 0) {
    throw "Preflight CSV has no data rows: $PreflightCsv"
}

$requiredColumns = @(
    "CalibreId",
    "Title",
    "Authors",
    "CurrentTitle",
    "CurrentAuthors",
    "CurrentMqgTitleAuthor",
    "CurrentMqgIdentifiers",
    "FutureApplyEligible",
    "PreflightStatus",
    "PreflightIssueCount",
    "PreflightIssues"
)

$availableColumns = @($rows[0].PSObject.Properties.Name)
$missingColumns = @($requiredColumns | Where-Object { $_ -notin $availableColumns })

if ($missingColumns.Count -gt 0) {
    throw "Preflight CSV is missing required columns: $($missingColumns -join ', ')"
}

Write-Host "Rows loaded from preflight CSV: $($rows.Count)"
Write-Host "Reading current Calibre MQG status..."

$currentBookMap = Get-CurrentBookMap

Write-Host "Current Calibre records available: $($currentBookMap.Count)"
Write-Host ""

$idCounts = @{}

foreach ($row in $rows) {
    $idText = Get-RowValue -Row $row -Name "CalibreId"

    if (-not [string]::IsNullOrWhiteSpace($idText)) {
        if (-not $idCounts.ContainsKey($idText)) {
            $idCounts[$idText] = 0
        }

        $idCounts[$idText]++
    }
}

$preApplyRows = foreach ($row in $rows) {
    $calibreId = Get-RowValue -Row $row -Name "CalibreId"
    $title = Get-RowValue -Row $row -Name "Title"
    $authors = Get-RowValue -Row $row -Name "Authors"
    $sourceCurrentTitle = Get-RowValue -Row $row -Name "CurrentTitle"
    $sourceCurrentAuthors = Get-RowValue -Row $row -Name "CurrentAuthors"
    $sourceCurrentMqgTitleAuthor = Get-RowValue -Row $row -Name "CurrentMqgTitleAuthor"
    $sourceCurrentMqgIdentifiers = Get-RowValue -Row $row -Name "CurrentMqgIdentifiers"
    $futureApplyEligible = Get-RowValue -Row $row -Name "FutureApplyEligible"
    $preflightStatus = Get-RowValue -Row $row -Name "PreflightStatus"
    $preflightIssueCountText = Get-RowValue -Row $row -Name "PreflightIssueCount"
    $preflightIssues = Get-RowValue -Row $row -Name "PreflightIssues"
    $preflightIssueCount = Convert-ToIntSafe -Value $preflightIssueCountText

    $blockingReasons = @()

    $currentTitle = ""
    $currentAuthors = ""
    $currentMqgTitleAuthor = "No"
    $currentMqgIdentifiers = "No"

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }
    elseif ($idCounts[$calibreId] -gt 1) {
        $blockingReasons += "Duplicate CalibreId in preflight CSV"
    }

    if ($preflightStatus -ne "Ready - Future MQG-02 Apply") {
        $blockingReasons += "PreflightStatus is not Ready - Future MQG-02 Apply"
    }

    if ($futureApplyEligible -ne "Yes") {
        $blockingReasons += "FutureApplyEligible is not Yes"
    }

    if ($null -eq $preflightIssueCount) {
        $blockingReasons += "PreflightIssueCount is not numeric"
        $preflightIssueCount = -1
    }
    elseif ($preflightIssueCount -ne 0) {
        $blockingReasons += "PreflightIssueCount is not 0"
    }

    if (-not [string]::IsNullOrWhiteSpace($preflightIssues)) {
        $blockingReasons += "PreflightIssues is not blank"
    }

    if (-not [string]::IsNullOrWhiteSpace($sourceCurrentMqgIdentifiers) -and $sourceCurrentMqgIdentifiers -ne "No") {
        $blockingReasons += "Preflight CurrentMqgIdentifiers was not No"
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and -not $currentBookMap.ContainsKey($calibreId)) {
        $blockingReasons += "CalibreId not found in current Calibre metadata"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        $currentBook = $currentBookMap[$calibreId]
        $currentTitle = [string]$currentBook.title
        $currentAuthors = Format-Authors -Authors $currentBook.authors
        $currentMqgTitleAuthor = Convert-ToYesNo -Value $currentBook.'*mqg_title_author'
        $currentMqgIdentifiers = Convert-ToYesNo -Value $currentBook.'*mqg_identifiers'

        $expectedTitleForDrift = $sourceCurrentTitle

        if ([string]::IsNullOrWhiteSpace($expectedTitleForDrift)) {
            $expectedTitleForDrift = $title
        }

        $expectedAuthorsForDrift = $sourceCurrentAuthors

        if ([string]::IsNullOrWhiteSpace($expectedAuthorsForDrift)) {
            $expectedAuthorsForDrift = $authors
        }

        if ((Normalize-ComparableValue $currentTitle) -cne (Normalize-ComparableValue $expectedTitleForDrift)) {
            $blockingReasons += "Current title no longer matches preflight evidence"
        }

        if ((Normalize-ComparableValue $currentAuthors) -cne (Normalize-ComparableValue $expectedAuthorsForDrift)) {
            $blockingReasons += "Current authors no longer match preflight evidence"
        }
    }

    $alreadyComplete = ($currentMqgIdentifiers -eq "Yes")

    $eligible = ($blockingReasons.Count -eq 0)

    $markStatus = if ($alreadyComplete) {
        "Already Complete"
    }
    elseif (-not $eligible) {
        "Skipped"
    }
    else {
        "Ready"
    }

    [pscustomobject]@{
        CalibreId                    = $calibreId
        Title                        = $title
        Authors                      = $authors
        SourceCurrentTitle           = $sourceCurrentTitle
        SourceCurrentAuthors         = $sourceCurrentAuthors
        CurrentTitle                 = $currentTitle
        CurrentAuthors               = $currentAuthors
        SourceCurrentMqgTitleAuthor  = $sourceCurrentMqgTitleAuthor
        CurrentMqgTitleAuthor        = $currentMqgTitleAuthor
        SourceCurrentMqgIdentifiers  = $sourceCurrentMqgIdentifiers
        CurrentMqgIdentifiers        = $currentMqgIdentifiers
        PreflightStatus              = $preflightStatus
        FutureApplyEligible          = $futureApplyEligible
        PreflightIssueCount          = $preflightIssueCount
        MarkEligible                 = if ($eligible) { "Yes" } else { "No" }
        MarkStatus                   = $markStatus
        ReadBackStatus               = ""
        BlockingReasons              = $blockingReasons -join "; "
        CalibreOutput                = ""
        PreflightBasis               = Get-RowValue -Row $row -Name "PreflightBasis"
        ExistingIsbn                 = Get-RowValue -Row $row -Name "ExistingIsbn"
        ExistingAmazonOrAsin         = Get-RowValue -Row $row -Name "ExistingAmazonOrAsin"
        ExistingGoodreads            = Get-RowValue -Row $row -Name "ExistingGoodreads"
        IdentifierTypes              = Get-RowValue -Row $row -Name "IdentifierTypes"
        IdentifiersRaw               = Get-RowValue -Row $row -Name "IdentifiersRaw"
        SourcePreflightIssues        = $preflightIssues
    }
}

$eligibleRows = @($preApplyRows | Where-Object { $_.MarkEligible -eq "Yes" })
$readyRows = @($preApplyRows | Where-Object { $_.MarkStatus -eq "Ready" })
$alreadyCompleteRows = @($preApplyRows | Where-Object { $_.MarkStatus -eq "Already Complete" })
$skippedRows = @($preApplyRows | Where-Object { $_.MarkStatus -eq "Skipped" })

Write-Host "Rows reviewed: $($preApplyRows.Count)"
Write-Host "Rows passing evidence/current-state checks: $($eligibleRows.Count)"
Write-Host "Rows ready to mark complete: $($readyRows.Count)"
Write-Host "Rows already complete: $($alreadyCompleteRows.Count)"
Write-Host "Rows skipped: $($skippedRows.Count)"
Write-Host ""

if ($readyRows.Count -gt 0) {
    Write-Host "Ready rows:"
    foreach ($row in $readyRows | Select-Object -First 20) {
        Write-Host "  $($row.CalibreId) - $($row.Title) - $($row.Authors)"
    }

    if ($readyRows.Count -gt 20) {
        Write-Host "  ... $($readyRows.Count - 20) more ready row(s)"
    }
}

if ($skippedRows.Count -gt 0) {
    Write-Host ""
    Write-Host "Skipped rows:"
    foreach ($row in $skippedRows | Select-Object -First 20) {
        Write-Host "  $($row.CalibreId) - $($row.PreflightStatus) - $($row.BlockingReasons)"
    }

    if ($skippedRows.Count -gt 20) {
        Write-Host "  ... $($skippedRows.Count - 20) more skipped row(s)"
    }
}

$outputFolder = Split-Path -Path $MqgReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

if ($PreflightOnly) {
    foreach ($row in $preApplyRows) {
        if ($row.MarkStatus -eq "Ready") {
            $row.MarkStatus = "Not Run - Preflight Only"
        }
    }

    $preApplyRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "Preflight complete."
    Write-Host "MQG report: $MqgReportCsv"
    Write-Host ""
    Write-Host "PreflightOnly was specified. No Calibre metadata was modified."
    return
}

if ($readyRows.Count -eq 0) {
    $preApplyRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "No Identifier MQG-02 rows need to be marked complete."
    Write-Host "Rows already complete: $($alreadyCompleteRows.Count)"
    Write-Host "Rows skipped: $($skippedRows.Count)"
    Write-Host "MQG report: $MqgReportCsv"
    return
}

Write-Host ""
Write-Host "About to mark MQG-02 Identifiers complete for $($readyRows.Count) row(s)."
Write-Host "Close Calibre before continuing."
Write-Host "Type the exact confirmation phrase to continue:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -ne $ConfirmationPhrase) {
    throw "Identifier MQG-02 complete mark cancelled. Confirmation phrase did not match."
}

Write-Host ""
Write-Host "Marking verified Identifier records complete..."

$finalRows = foreach ($row in $preApplyRows) {
    if ($row.MarkStatus -ne "Ready") {
        $row
        continue
    }

    $fieldArgument = "${MqgFieldName}:true"

    $result = Invoke-CalibreDb -Arguments @(
        "set_metadata",
        "--field",
        $fieldArgument,
        $row.CalibreId
    )

    $row.CalibreOutput = $result.Output

    if ($result.ExitCode -ne 0) {
        $row.MarkStatus = "Failed"
        Add-BlockingReason -Row $row -Reason "calibredb set_metadata failed with exit code $($result.ExitCode)"
        $row
        continue
    }

    $readBack = Test-MqgFieldTrue -CalibreId $row.CalibreId -MqgFieldName $MqgFieldName
    $row.ReadBackStatus = $readBack.Status

    if ($readBack.IsTrue) {
        $row.MarkStatus = "Succeeded"
    }
    else {
        $row.MarkStatus = "Failed"
        Add-BlockingReason -Row $row -Reason $readBack.Status
    }

    $row
}

$finalRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

$markedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Succeeded" }).Count
$alreadyCompleteCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Already Complete" }).Count
$failedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Failed" }).Count
$skippedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Skipped" }).Count

Write-Host ""
Write-Host "Identifier MQG-02 complete mark finished."
Write-Host "Rows newly marked complete: $markedCount"
Write-Host "Rows already complete: $alreadyCompleteCount"
Write-Host "Rows failed: $failedCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host "MQG report: $MqgReportCsv"

if ($failedCount -gt 0) {
    throw "One or more Identifier MQG-02 complete mark operations failed. Review the MQG report."
}
