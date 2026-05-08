<#
.SYNOPSIS
Applies validated proposed comments to Calibre metadata.

.DESCRIPTION
Reads a comments import TSV and matching comments dry-run CSV, rechecks current Calibre
metadata, builds final comments HTML according to CommentsMode, and writes the standard
Calibre comments field using calibredb set_metadata --field comments:<html>.

This script modifies Calibre metadata unless -PreflightOnly is used.

Safety model:
- Requires both InputTsv and DryRunCsv.
- Requires the dry-run CSV to be fully clean.
- Requires at least one ApplyEligible row.
- Rechecks title, authors, and current comments hash before writing.
- Refuses stale or unsafe rows.
- Requires exact confirmation phrase before write.
- Writes an apply report.

Recommended workflow:
Export -> Generate Proposed Comments -> Dry Run -> Summary -> HTML Review -> Apply -> Verify
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$InputTsv = ".\input\comments-import-batch.tsv",

    [string]$DryRunCsv = ".\reports\comments-dryrun-batch.csv",

    [string]$ApplyReportCsv = ".\reports\comments-apply-batch.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "APPLY COMMENTS",

    [string]$PrependExistingHeaderHtml = "<hr/><h3>Original Comments</h3>",

    [string]$AppendProposedHeaderHtml = "<hr/><h3>Additional Curator Comments</h3>",

    [switch]$PreflightOnly,

    [switch]$AllowReplaceNonBlank
)

$AllowedCommentsModes = @(
    "Replace",
    "Append",
    "Prepend"
)

$UnsafeTextPatterns = @(
    "DO NOT APPLY",
    "PLACEHOLDER",
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

function Get-FieldValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $property = $Row.PSObject.Properties |
        Where-Object { $_.Name -eq $Name } |
        Select-Object -First 1

    if ($null -eq $property) {
        return ""
    }

    return [string]$property.Value
}

function Test-RequiredColumns {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string[]]$RequiredColumns,

        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    if ($Rows.Count -eq 0) {
        throw "$SourceName has no data rows."
    }

    $availableColumns = @($Rows[0].PSObject.Properties.Name)

    $missingColumns = @(
        $RequiredColumns | Where-Object {
            $_ -notin $availableColumns
        }
    )

    if ($missingColumns.Count -gt 0) {
        throw "$SourceName is missing required column(s): $($missingColumns -join ', ')"
    }
}

function Get-DuplicateIds {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows
    )

    $idCounts = @{}

    foreach ($row in $Rows) {
        $idText = (Get-FieldValue -Row $row -Name "CalibreId").Trim()

        if ([string]::IsNullOrWhiteSpace($idText)) {
            continue
        }

        if (-not $idCounts.ContainsKey($idText)) {
            $idCounts[$idText] = 0
        }

        $idCounts[$idText]++
    }

    return @(
        $idCounts.Keys | Where-Object {
            $idCounts[$_] -gt 1
        }
    )
}

function Join-CommentsHtml {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Mode,

        [AllowNull()]
        [string]$ExistingComments,

        [Parameter(Mandatory = $true)]
        [string]$ProposedComments,

        [string]$PrependExistingHeaderHtml = "<hr/><h3>Original Comments</h3>",

        [string]$AppendProposedHeaderHtml = "<hr/><h3>Additional Curator Comments</h3>"
    )

    $existing = ""
    $proposed = ""

    if ($null -ne $ExistingComments) {
        $existing = $ExistingComments.Trim()
    }

    if ($null -ne $ProposedComments) {
        $proposed = $ProposedComments.Trim()
    }

    if ($Mode -eq "Replace") {
        return $proposed
    }

    if ($Mode -eq "Prepend") {
        if ([string]::IsNullOrWhiteSpace($existing)) {
            return $proposed
        }

        return $proposed + $PrependExistingHeaderHtml + $existing
    }

    if ($Mode -eq "Append") {
        if ([string]::IsNullOrWhiteSpace($existing)) {
            return $proposed
        }

        return $existing + $AppendProposedHeaderHtml + $proposed
    }

    throw "Unsupported CommentsMode: $Mode"
}

function New-RowMap {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    $map = @{}

    foreach ($row in $Rows) {
        $idText = (Get-FieldValue -Row $row -Name "CalibreId").Trim()

        if ([string]::IsNullOrWhiteSpace($idText)) {
            throw "$SourceName contains a row with blank CalibreId."
        }

        if ($map.ContainsKey($idText)) {
            throw "$SourceName contains duplicate CalibreId: $idText"
        }

        $map[$idText] = $row
    }

    return $map
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not (Test-Path $InputTsv)) {
    throw "Input TSV was not found: $InputTsv"
}

if (-not (Test-Path $DryRunCsv)) {
    throw "Dry-run CSV was not found: $DryRunCsv"
}

Write-Host "Comments APPLY"
Write-Host "=============="
Write-Host ""
Write-Host "WARNING: This script can modify Calibre metadata."
Write-Host "Input TSV: $InputTsv"
Write-Host "Dry-run CSV: $DryRunCsv"
Write-Host "Apply report: $ApplyReportCsv"

if ($PreflightOnly) {
    Write-Host "Mode: Preflight only. No Calibre metadata will be modified."
}
else {
    Write-Host "Mode: Apply. Calibre metadata may be modified after confirmation."
}

$inputRows = @(Import-Csv -Path $InputTsv -Delimiter "`t")
$dryRunRows = @(Import-Csv -Path $DryRunCsv)

$requiredInputColumns = @(
    "CalibreId",
    "Title",
    "Authors",
    "ExistingCommentsHash",
    "ProposedComments",
    "CommentsMode"
)

$requiredDryRunColumns = @(
    "CalibreId",
    "Title",
    "Authors",
    "CurrentTitle",
    "CurrentAuthors",
    "CurrentCommentsHash",
    "CommentsHashMatchesCurrent",
    "CommentsMode",
    "ApplyEligible",
    "BlockingReasons"
)

Test-RequiredColumns -Rows $inputRows -RequiredColumns $requiredInputColumns -SourceName "Input TSV"
Test-RequiredColumns -Rows $dryRunRows -RequiredColumns $requiredDryRunColumns -SourceName "Dry-run CSV"

if ($inputRows.Count -ne $dryRunRows.Count) {
    throw "Input TSV row count ($($inputRows.Count)) does not match dry-run CSV row count ($($dryRunRows.Count))."
}

$duplicateInputIds = @(Get-DuplicateIds -Rows $inputRows)
$duplicateDryRunIds = @(Get-DuplicateIds -Rows $dryRunRows)

if ($duplicateInputIds.Count -gt 0) {
    throw "Input TSV contains duplicate CalibreId value(s): $($duplicateInputIds -join ', ')"
}

if ($duplicateDryRunIds.Count -gt 0) {
    throw "Dry-run CSV contains duplicate CalibreId value(s): $($duplicateDryRunIds -join ', ')"
}

$inputMap = New-RowMap -Rows $inputRows -SourceName "Input TSV"
$dryRunMap = New-RowMap -Rows $dryRunRows -SourceName "Dry-run CSV"

$inputIds = @($inputMap.Keys | Sort-Object)
$dryRunIds = @($dryRunMap.Keys | Sort-Object)

$idDifference = @(
    Compare-Object -ReferenceObject $inputIds -DifferenceObject $dryRunIds |
        ForEach-Object { $_.InputObject }
)

if ($idDifference.Count -gt 0) {
    throw "Input TSV and dry-run CSV do not contain the same CalibreId set: $($idDifference -join ', ')"
}

$blockedDryRunRows = @(
    $dryRunRows | Where-Object {
        $_.ApplyEligible -ne "Yes" -or
        -not [string]::IsNullOrWhiteSpace([string]$_.BlockingReasons)
    }
)

$eligibleDryRunRows = @(
    $dryRunRows | Where-Object {
        $_.ApplyEligible -eq "Yes" -and
        [string]::IsNullOrWhiteSpace([string]$_.BlockingReasons)
    }
)

if ($blockedDryRunRows.Count -gt 0) {
    throw "Apply refused because the dry-run CSV contains blocked rows. Blocked rows: $($blockedDryRunRows.Count)"
}

if ($eligibleDryRunRows.Count -eq 0) {
    throw "Apply refused because the dry-run CSV contains zero apply-eligible rows."
}

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

Write-Host ""
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

$preflightRows = foreach ($dryRow in $eligibleDryRunRows) {
    $blockingReasons = @()

    $calibreId = ([string]$dryRow.CalibreId).Trim()
    $inputRow = $inputMap[$calibreId]

    $inputTitle = Get-FieldValue -Row $inputRow -Name "Title"
    $inputAuthors = Get-FieldValue -Row $inputRow -Name "Authors"
    $inputExistingCommentsHash = (Get-FieldValue -Row $inputRow -Name "ExistingCommentsHash").Trim()
    $proposedComments = Get-FieldValue -Row $inputRow -Name "ProposedComments"
    $commentsMode = (Get-FieldValue -Row $inputRow -Name "CommentsMode").Trim()

    $dryCurrentTitle = Get-FieldValue -Row $dryRow -Name "CurrentTitle"
    $dryCurrentAuthors = Get-FieldValue -Row $dryRow -Name "CurrentAuthors"
    $dryCurrentCommentsHash = (Get-FieldValue -Row $dryRow -Name "CurrentCommentsHash").Trim()
    $dryCommentsMode = (Get-FieldValue -Row $dryRow -Name "CommentsMode").Trim()

    $currentBook = $null
    $currentTitle = ""
    $currentAuthors = ""
    $currentComments = ""
    $currentCommentsHash = ""
    $currentCommentsLength = 0
    $finalComments = ""
    $finalCommentsHash = ""
    $finalCommentsLength = 0

    if ($currentBookMap.ContainsKey($calibreId)) {
        $currentBook = $currentBookMap[$calibreId]
        $currentTitle = [string]$currentBook.title
        $currentAuthors = Format-Authors $currentBook.authors
        $currentComments = [string]$currentBook.comments
        $currentCommentsHash = Get-Sha256Hash -Value $currentComments
        $currentCommentsLength = $currentComments.Length
    }
    else {
        $blockingReasons += "CalibreId not found in current Calibre metadata"
    }

    if ($commentsMode -notin $AllowedCommentsModes) {
        $blockingReasons += "Unsupported CommentsMode for apply: $commentsMode"
    }

    if ($commentsMode -ne $dryCommentsMode) {
        $blockingReasons += "Input TSV CommentsMode does not match dry-run CSV CommentsMode"
    }

    if ([string]::IsNullOrWhiteSpace($proposedComments)) {
        $blockingReasons += "Missing ProposedComments"
    }

    foreach ($unsafePattern in $UnsafeTextPatterns) {
        if ($proposedComments.IndexOf($unsafePattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $blockingReasons += "ProposedComments contains unsafe text pattern: $unsafePattern"
        }
    }

    if ($null -ne $currentBook) {
        if ((Normalize-ComparableValue $currentTitle) -cne (Normalize-ComparableValue $inputTitle)) {
            $blockingReasons += "Current title does not match input TSV title"
        }

        if ((Normalize-ComparableValue $currentAuthors) -cne (Normalize-ComparableValue $inputAuthors)) {
            $blockingReasons += "Current authors do not match input TSV authors"
        }

        if ((Normalize-ComparableValue $currentTitle) -cne (Normalize-ComparableValue $dryCurrentTitle)) {
            $blockingReasons += "Current title does not match dry-run current title"
        }

        if ((Normalize-ComparableValue $currentAuthors) -cne (Normalize-ComparableValue $dryCurrentAuthors)) {
            $blockingReasons += "Current authors do not match dry-run current authors"
        }

        if ([string]::IsNullOrWhiteSpace($inputExistingCommentsHash)) {
            $blockingReasons += "Input TSV missing ExistingCommentsHash"
        }
        elseif ($inputExistingCommentsHash -ne $currentCommentsHash) {
            $blockingReasons += "Current comments hash does not match input TSV ExistingCommentsHash"
        }

        if ([string]::IsNullOrWhiteSpace($dryCurrentCommentsHash)) {
            $blockingReasons += "Dry-run CSV missing CurrentCommentsHash"
        }
        elseif ($dryCurrentCommentsHash -ne $currentCommentsHash) {
            $blockingReasons += "Current comments hash does not match dry-run CurrentCommentsHash"
        }

        if ($commentsMode -eq "Replace" -and $currentCommentsLength -gt 0 -and -not $AllowReplaceNonBlank) {
            $blockingReasons += "Replace against non-blank existing comments requires -AllowReplaceNonBlank"
        }

        if ($blockingReasons.Count -eq 0) {
            $finalComments = Join-CommentsHtml `
                -Mode $commentsMode `
                -ExistingComments $currentComments `
                -ProposedComments $proposedComments `
                -PrependExistingHeaderHtml $PrependExistingHeaderHtml `
                -AppendProposedHeaderHtml $AppendProposedHeaderHtml

            $finalCommentsHash = Get-Sha256Hash -Value $finalComments
            $finalCommentsLength = $finalComments.Length
        }
    }

    [pscustomobject]@{
        CalibreId                = $calibreId
        Title                    = $inputTitle
        Authors                  = $inputAuthors
        CommentsMode             = $commentsMode
        CurrentCommentsLength    = $currentCommentsLength
        ProposedCommentsLength   = $proposedComments.Length
        FinalCommentsLength      = $finalCommentsLength
        ExistingCommentsHash     = $inputExistingCommentsHash
        CurrentCommentsHash      = $currentCommentsHash
        ExpectedFinalCommentsHash = $finalCommentsHash
        PreflightStatus          = if ($blockingReasons.Count -eq 0) { "Ready" } else { "Blocked" }
        ApplyStatus              = if ($PreflightOnly) { "Not Run - Preflight Only" } else { "Pending" }
        BlockingReasons          = ($blockingReasons | Select-Object -Unique) -join "; "
        CalibreOutput            = ""
    }
}

$blockedPreflightRows = @(
    $preflightRows | Where-Object {
        $_.PreflightStatus -ne "Ready"
    }
)

$outputFolder = Split-Path -Path $ApplyReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

if ($blockedPreflightRows.Count -gt 0) {
    $preflightRows | Export-Csv -Path $ApplyReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "Apply blocked during preflight."
    Write-Host "Rows reviewed: $($preflightRows.Count)"
    Write-Host "Rows ready: $(@($preflightRows | Where-Object { $_.PreflightStatus -eq 'Ready' }).Count)"
    Write-Host "Rows blocked: $($blockedPreflightRows.Count)"
    Write-Host "Apply report: $ApplyReportCsv"

    throw "Apply refused because one or more rows failed preflight."
}

$preflightRows | Export-Csv -Path $ApplyReportCsv -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "Preflight complete."
Write-Host "Rows ready for apply: $($preflightRows.Count)"
Write-Host "Apply report: $ApplyReportCsv"

if ($PreflightOnly) {
    Write-Host ""
    Write-Host "PreflightOnly was specified. No Calibre metadata was modified."
    return
}

Write-Host ""
Write-Host "About to modify Calibre comments for $($preflightRows.Count) row(s)."
Write-Host "Type the exact confirmation phrase to continue:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -cne $ConfirmationPhrase) {
    throw "Apply cancelled. Confirmation phrase did not match exactly."
}

Write-Host ""
Write-Host "Applying comments metadata..."

$applyResults = foreach ($preflightRow in $preflightRows) {
    $calibreId = [string]$preflightRow.CalibreId
    $inputRow = $inputMap[$calibreId]
    $currentBook = $currentBookMap[$calibreId]
    $currentComments = [string]$currentBook.comments
    $proposedComments = Get-FieldValue -Row $inputRow -Name "ProposedComments"
    $commentsMode = (Get-FieldValue -Row $inputRow -Name "CommentsMode").Trim()

    $finalComments = Join-CommentsHtml `
        -Mode $commentsMode `
        -ExistingComments $currentComments `
        -ProposedComments $proposedComments `
        -PrependExistingHeaderHtml $PrependExistingHeaderHtml `
        -AppendProposedHeaderHtml $AppendProposedHeaderHtml

    $fieldArgument = "comments:$finalComments"

    $setArgs = @(
        "set_metadata",
        $calibreId,
        "--field",
        $fieldArgument
    )

    $calibreOutput = ""
    $applyStatus = "Succeeded"

    try {
        $output = Invoke-CalibreDb -Arguments $setArgs 2>&1
        $calibreOutput = ($output | ForEach-Object { [string]$_ }) -join " "

        if ($LASTEXITCODE -ne 0) {
            $applyStatus = "Failed"
        }
    }
    catch {
        $applyStatus = "Failed"
        $calibreOutput = [string]$_.Exception.Message
    }

    [pscustomobject]@{
        CalibreId                = $preflightRow.CalibreId
        Title                    = $preflightRow.Title
        Authors                  = $preflightRow.Authors
        CommentsMode             = $preflightRow.CommentsMode
        CurrentCommentsLength    = $preflightRow.CurrentCommentsLength
        ProposedCommentsLength   = $preflightRow.ProposedCommentsLength
        FinalCommentsLength      = $finalComments.Length
        ExistingCommentsHash     = $preflightRow.ExistingCommentsHash
        CurrentCommentsHash      = $preflightRow.CurrentCommentsHash
        ExpectedFinalCommentsHash = Get-Sha256Hash -Value $finalComments
        PreflightStatus          = "Ready"
        ApplyStatus              = $applyStatus
        BlockingReasons          = ""
        CalibreOutput            = $calibreOutput
    }
}

$applyResults | Export-Csv -Path $ApplyReportCsv -NoTypeInformation -Encoding UTF8

$successCount = @($applyResults | Where-Object { $_.ApplyStatus -eq "Succeeded" }).Count
$failedCount = @($applyResults | Where-Object { $_.ApplyStatus -ne "Succeeded" }).Count

Write-Host ""
Write-Host "Apply complete."
Write-Host "Rows attempted: $($applyResults.Count)"
Write-Host "Rows succeeded: $successCount"
Write-Host "Rows failed: $failedCount"
Write-Host "Apply report: $ApplyReportCsv"

if ($failedCount -gt 0) {
    throw "One or more comments apply operations failed. Review the apply report."
}

Write-Host ""
Write-Host "Next step: run the comments verify script after it is available."