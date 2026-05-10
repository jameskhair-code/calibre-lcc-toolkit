<#
.SYNOPSIS
Applies approved Calibre author/title cleanup changes after a clean dry run.

.DESCRIPTION
Reads the CSV produced by Test-AuthorTitleCleanupDryRun.ps1 and applies eligible title
and/or author changes to Calibre using calibredb set_metadata.

This script modifies Calibre metadata.

Safety behavior:
- Refuses to run if any proposed-change row in the dry-run CSV is blocked.
- Refuses to run if zero rows are eligible for apply.
- Refuses to run if any proposed value contains "DO NOT APPLY".
- Re-checks current Calibre title/author values before writing.
- Requires an exact confirmation phrase before writing metadata.
- Writes an apply report after execution.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-AuthorTitleCleanupApply.ps1 `
  -DryRunCsv ".\reports\author-title-cleanup-dryrun-batch.csv" `
  -ApplyReportCsv ".\reports\author-title-cleanup-apply-batch.csv"

.NOTES
Do not run this script unless the dry-run report and summary are clean.
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$DryRunCsv = ".\reports\author-title-cleanup-dryrun-batch.csv",

    [string]$ApplyReportCsv = ".\reports\author-title-cleanup-apply-batch.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "APPLY AUTHOR TITLE CLEANUP",

    [switch]$AllowDoNotApplyText
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

function Test-DoNotApplyMarker {
    param(
        [AllowNull()]
        [string[]]$Values
    )

    foreach ($value in @($Values)) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        if ($value -match 'DO NOT APPLY') {
            return $true
        }
    }

    return $false
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

Write-Host "Author/title cleanup APPLY"
Write-Host "=========================="
Write-Host ""
Write-Host "WARNING: This script modifies Calibre metadata."
Write-Host "Dry-run CSV: $DryRunCsv"
Write-Host "Apply report: $ApplyReportCsv"
Write-Host ""

$rows = @(Import-Csv -Path $DryRunCsv)

if ($rows.Count -eq 0) {
    throw "Dry-run CSV has no data rows: $DryRunCsv"
}

$proposedChangeRows = @(
    $rows | Where-Object {
        $_.TitleChangeDetected -eq "Yes" -or $_.AuthorsChangeDetected -eq "Yes"
    }
)

$noChangeRows = @(
    $rows | Where-Object {
        $_.TitleChangeDetected -ne "Yes" -and $_.AuthorsChangeDetected -ne "Yes"
    }
)

$blockedRows = @($proposedChangeRows | Where-Object { $_.ApplyEligible -ne "Yes" })
$eligibleRows = @($rows | Where-Object { $_.ApplyEligible -eq "Yes" })

if ($blockedRows.Count -gt 0) {
    Write-Host "Apply blocked."
    Write-Host "Rows in dry-run CSV: $($rows.Count)"
    Write-Host "Rows with no proposed/effective changes: $($noChangeRows.Count)"
    Write-Host "Rows eligible for apply: $($eligibleRows.Count)"
    Write-Host "Proposed-change rows blocked: $($blockedRows.Count)"
    Write-Host ""
    Write-Host "This script requires all proposed-change rows to be clean. No-change rows are ignored by apply."
    throw "Apply refused because the dry-run CSV contains blocked proposed-change rows."
}

if ($eligibleRows.Count -eq 0) {
    throw "Apply refused because there are zero eligible rows."
}

$markerRows = @(
    $eligibleRows | Where-Object {
        Test-DoNotApplyMarker -Values @(
            $_.ProposedTitle,
            $_.ProposedAuthors,
            $_.ChangeReason
        )
    }
)

if ($markerRows.Count -gt 0 -and -not $AllowDoNotApplyText) {
    Write-Host "Apply blocked."
    Write-Host "One or more proposed values contain DO NOT APPLY."
    Write-Host "This usually indicates a smoke-test TSV/report was used."
    throw "Apply refused because DO NOT APPLY marker text was found."
}

Write-Host "Rows in dry-run CSV: $($rows.Count)"
Write-Host "Rows with no proposed/effective changes: $($noChangeRows.Count)"
Write-Host "Rows eligible for apply: $($eligibleRows.Count)"
Write-Host "Proposed-change rows blocked: $($blockedRows.Count)"
Write-Host ""
Write-Host "Planned changes:"
Write-Host ""

foreach ($row in $eligibleRows) {
    Write-Host "CalibreId $($row.CalibreId)"

    if (-not [string]::IsNullOrWhiteSpace($row.ProposedTitle)) {
        Write-Host "  Title:"
        Write-Host "    Current:  $($row.CurrentTitle)"
        Write-Host "    Proposed: $($row.ProposedTitle)"
    }

    if (-not [string]::IsNullOrWhiteSpace($row.ProposedAuthors)) {
        Write-Host "  Authors:"
        Write-Host "    Current:  $($row.CurrentAuthors)"
        Write-Host "    Proposed: $($row.ProposedAuthors)"
    }

    Write-Host "  Reason: $($row.ChangeReason)"
    Write-Host "  Confidence: $($row.Confidence)"
    Write-Host ""
}

Write-Host "To apply these changes, type the exact confirmation phrase:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -ne $ConfirmationPhrase) {
    throw "Apply cancelled. Confirmation phrase did not match."
}

Write-Host ""
Write-Host "Re-checking current Calibre metadata before apply..."

$currentBookMap = Get-CurrentBookMap

$preflightProblems = @()

foreach ($row in $eligibleRows) {
    $calibreId = ([string]$row.CalibreId).Trim()

    if (-not $currentBookMap.ContainsKey($calibreId)) {
        $preflightProblems += "CalibreId $calibreId was not found during pre-apply validation."
        continue
    }

    $currentBook = $currentBookMap[$calibreId]
    $actualCurrentTitle = [string]$currentBook.title
    $actualCurrentAuthors = Format-Authors $currentBook.authors

    if ((Normalize-ComparableValue $actualCurrentTitle) -cne (Normalize-ComparableValue $row.CurrentTitle)) {
        $preflightProblems += "CalibreId $calibreId title changed since dry run."
    }

    if ((Normalize-ComparableValue $actualCurrentAuthors) -cne (Normalize-ComparableValue $row.CurrentAuthors)) {
        $preflightProblems += "CalibreId $calibreId authors changed since dry run."
    }
}

if ($preflightProblems.Count -gt 0) {
    Write-Host "Apply blocked during pre-apply validation."
    foreach ($problem in $preflightProblems) {
        Write-Host " - $problem"
    }

    throw "Apply refused because current Calibre metadata no longer matches the dry-run report."
}

Write-Host "Pre-apply validation passed."
Write-Host "Applying changes..."

$applyRows = foreach ($row in $eligibleRows) {
    $calibreId = ([string]$row.CalibreId).Trim()
    $args = @("set_metadata")

    $titleApplied = "No"
    $authorsApplied = "No"

    if (-not [string]::IsNullOrWhiteSpace($row.ProposedTitle)) {
        $args += @("--field", ("title:{0}" -f $row.ProposedTitle))
        $titleApplied = "Yes"
    }

    if (-not [string]::IsNullOrWhiteSpace($row.ProposedAuthors)) {
        $args += @("--field", ("authors:{0}" -f $row.ProposedAuthors))
        $authorsApplied = "Yes"
    }

    $args += $calibreId

    $outputText = ""
    $status = "Applied"
    $errorMessage = ""

    try {
        $output = Invoke-CalibreDb -Arguments $args
        $outputText = ($output -join "`n")
    }
    catch {
        $status = "Failed"
        $errorMessage = $_.Exception.Message
    }

    [pscustomobject]@{
        CalibreId       = $calibreId
        TitleApplied    = $titleApplied
        AuthorsApplied  = $authorsApplied
        ProposedTitle   = $row.ProposedTitle
        ProposedAuthors = $row.ProposedAuthors
        ChangeReason    = $row.ChangeReason
        Confidence      = $row.Confidence
        ApplyStatus     = $status
        ErrorMessage    = $errorMessage
        CalibreDbOutput = $outputText
    }
}

$outputFolder = Split-Path -Path $ApplyReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$applyRows | Export-Csv -Path $ApplyReportCsv -NoTypeInformation -Encoding UTF8

$failedRows = @($applyRows | Where-Object { $_.ApplyStatus -ne "Applied" })

Write-Host ""
Write-Host "Apply complete: $ApplyReportCsv"
Write-Host "Rows attempted: $($applyRows.Count)"
Write-Host "Rows failed: $($failedRows.Count)"

if ($failedRows.Count -gt 0) {
    throw "One or more rows failed during apply. Review the apply report."
}

Write-Host ""
Write-Host "Next recommended step: run the future verify script to confirm final title/author values."
