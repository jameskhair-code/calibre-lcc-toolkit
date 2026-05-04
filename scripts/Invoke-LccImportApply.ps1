<#
.SYNOPSIS
Applies reviewed LCC metadata updates to Calibre from a dry-run report.

.DESCRIPTION
Reads the CSV report produced by Test-LccImportDryRun.ps1.
Applies only rows where MatchStatus is "Matched" and the relevant WouldUpdate field is "Yes".

This script updates custom Calibre fields using calibredb set_custom.

SAFETY:
- Requires the -Apply switch.
- Skips unmatched and multiple-match rows.
- Skips blank proposed values.
- Blocks apply when v0.4 audit fields indicate manual review is required.
- Blocks apply when LCCConfidenceStatus is Unexpected.
- Writes an apply report showing what happened.
#>

[CmdletBinding()]
param(
    [switch]$Apply,

    [string]$LibraryPath = "",

    [string]$DryRunReportCsv = ".\reports\lcc-dryrun-report.csv",

    [string]$ApplyReportCsv = ".\reports\lcc-apply-report.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$LccColumn = "lcc",

    [string]$LccPathColumn = "lcc_class_path",

    [string]$LccPrimaryClassColumn = "lcc_primary_class",

    [string]$LccSecondaryClassColumn = "lcc_secondary_class"
)

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

function Set-CalibreCustomValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ColumnLabel,

        [Parameter(Mandatory = $true)]
        [string]$BookId,

        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $arguments = @()

    if (-not [string]::IsNullOrWhiteSpace($LibraryPath)) {
        $arguments += @("--with-library", $LibraryPath)
    }

    $arguments += @(
        "set_custom",
        $ColumnLabel,
        $BookId,
        $Value
    )

    $output = & $CalibreDb @arguments 2>&1
    $exitCode = $LASTEXITCODE

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = ($output -join "`n")
    }
}

function Get-RowValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $property = $Row.PSObject.Properties[$name]

        if ($null -ne $property) {
            return [string]$property.Value
        }
    }

    return ""
}

function New-ApplyResult {
    param(
        [string]$InputTitle,
        [string]$ISBN,
        [string]$CalibreId,
        [string]$CalibreTitle,
        [string]$FieldName,
        [string]$ColumnLabel,
        [string]$ExistingValue,
        [string]$ProposedValue,
        [string]$WouldUpdate,
        [string]$Status,
        [string]$Message,
        [string]$LCCConfidence = "",
        [string]$LCCConfidenceStatus = "",
        [string]$LCCSourceNotes = "",
        [string]$ManualReviewRequired = ""
    )

    [pscustomobject]@{
        InputTitle             = $InputTitle
        ISBN                   = $ISBN
        CalibreId              = $CalibreId
        CalibreTitle           = $CalibreTitle
        FieldName              = $FieldName
        ColumnLabel            = $ColumnLabel
        ExistingValue          = $ExistingValue
        ProposedValue          = $ProposedValue
        WouldUpdate            = $WouldUpdate
        Status                 = $Status
        Message                = $Message
        LCCConfidence          = $LCCConfidence
        LCCConfidenceStatus    = $LCCConfidenceStatus
        LCCSourceNotes         = $LCCSourceNotes
        ManualReviewRequired   = $ManualReviewRequired
    }
}

function Get-AuditValues {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row
    )

    return [pscustomobject]@{
        LCCConfidence        = Get-RowValue -Row $Row -Names @("LCCConfidence", "LCC Confidence")
        LCCConfidenceStatus  = Get-RowValue -Row $Row -Names @("LCCConfidenceStatus")
        LCCSourceNotes       = Get-RowValue -Row $Row -Names @("LCCSourceNotes", "LCC Source Notes")
        ManualReviewRequired = Get-RowValue -Row $Row -Names @("ManualReviewRequired")
    }
}

if (-not $Apply) {
    throw "This script modifies Calibre metadata. Re-run with -Apply after reviewing the dry-run report."
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not [string]::IsNullOrWhiteSpace($LibraryPath) -and -not (Test-Path $LibraryPath)) {
    throw "Library path was not found: $LibraryPath"
}

if (-not (Test-Path $DryRunReportCsv)) {
    throw "Dry-run report was not found: $DryRunReportCsv"
}

$applyFolder = Split-Path -Path $ApplyReportCsv -Parent
if ($applyFolder -and -not (Test-Path $applyFolder)) {
    New-Item -ItemType Directory -Force -Path $applyFolder | Out-Null
}

$rows = @(Import-Csv -Path $DryRunReportCsv)

if ($rows.Count -eq 0) {
    throw "Dry-run report contains no rows: $DryRunReportCsv"
}

$matchedRows = @($rows | Where-Object { $_.MatchStatus -eq "Matched" })

$pendingLccUpdates = @($matchedRows | Where-Object { $_.WouldUpdateLCC -eq "Yes" }).Count
$pendingPrimaryUpdates = @($matchedRows | Where-Object { $_.WouldUpdateLCCPrimaryClass -eq "Yes" }).Count
$pendingSecondaryUpdates = @($matchedRows | Where-Object { $_.WouldUpdateLCCSecondaryClass -eq "Yes" }).Count
$pendingPathUpdates = @($matchedRows | Where-Object { $_.WouldUpdateLCCPath -eq "Yes" }).Count

$pendingFieldUpdates =
    $pendingLccUpdates +
    $pendingPrimaryUpdates +
    $pendingSecondaryUpdates +
    $pendingPathUpdates

$skippedRowCount = @($rows | Where-Object { $_.MatchStatus -ne "Matched" }).Count

$manualReviewRows = @(
    $rows | Where-Object {
        (Get-RowValue -Row $_ -Names @("ManualReviewRequired")) -eq "Yes"
    }
)

$unexpectedConfidenceRows = @(
    $rows | Where-Object {
        (Get-RowValue -Row $_ -Names @("LCCConfidenceStatus")) -eq "Unexpected"
    }
)

$manualReviewCount = $manualReviewRows.Count
$unexpectedConfidenceCount = $unexpectedConfidenceRows.Count

Write-Host ""
Write-Host "Apply Preflight Summary"
Write-Host "======================="
Write-Host "Dry-run report: $DryRunReportCsv"
Write-Host "Apply report:   $ApplyReportCsv"
Write-Host ""
Write-Host "Rows in report:        $($rows.Count)"
Write-Host "Matched rows:          $($matchedRows.Count)"
Write-Host "Non-matched rows:      $skippedRowCount"
Write-Host ""
Write-Host "Pending field updates:"
Write-Host "  LCC:                 $pendingLccUpdates"
Write-Host "  Primary Class:       $pendingPrimaryUpdates"
Write-Host "  Secondary Class:     $pendingSecondaryUpdates"
Write-Host "  Classification Path: $pendingPathUpdates"
Write-Host "  Total:               $pendingFieldUpdates"
Write-Host ""
Write-Host "LCC enrichment audit:"
Write-Host "  Manual review required rows: $manualReviewCount"
Write-Host "  Unexpected confidence rows:  $unexpectedConfidenceCount"
Write-Host ""

if ($manualReviewCount -gt 0 -or $unexpectedConfidenceCount -gt 0) {
    Write-Host "Apply blocked by LCC enrichment audit safety gate." -ForegroundColor Yellow
    Write-Host ""

    if ($manualReviewCount -gt 0) {
        Write-Host "Manual review required rows:"
        $manualReviewRows |
            Select-Object InputTitle, ISBN, LCCConfidence, LCCConfidenceStatus, ManualReviewRequired, Warning |
            Format-Table -AutoSize
    }

    if ($unexpectedConfidenceCount -gt 0) {
        Write-Host ""
        Write-Host "Unexpected confidence rows:"
        $unexpectedConfidenceRows |
            Select-Object InputTitle, ISBN, LCCConfidence, LCCConfidenceStatus, ManualReviewRequired, Warning |
            Format-Table -AutoSize
    }

    throw "Apply blocked. Resolve manual-review or unexpected-confidence rows, then rerun dry run and apply."
}

if ($pendingFieldUpdates -gt 0) {
    Write-Host "This operation will modify Calibre metadata."
    Write-Host "Type APPLY to continue, or anything else to cancel."
    $confirmation = Read-Host "Confirmation"

    if ($confirmation -ne "APPLY") {
        throw "Apply cancelled. Confirmation text did not match APPLY."
    }

    Write-Host ""
    Write-Host "Confirmation accepted. Applying updates..."
}
else {
    Write-Host "No pending field updates found. No Calibre metadata changes will be attempted."
}

$results = foreach ($row in $rows) {
    $audit = Get-AuditValues -Row $row

    if ($row.MatchStatus -ne "Matched") {
        New-ApplyResult `
            -InputTitle $row.InputTitle `
            -ISBN $row.ISBN `
            -CalibreId $row.CalibreId `
            -CalibreTitle $row.CalibreTitle `
            -FieldName "Record" `
            -ColumnLabel "" `
            -ExistingValue "" `
            -ProposedValue "" `
            -WouldUpdate "No" `
            -Status "Skipped" `
            -Message "MatchStatus was '$($row.MatchStatus)'" `
            -LCCConfidence $audit.LCCConfidence `
            -LCCConfidenceStatus $audit.LCCConfidenceStatus `
            -LCCSourceNotes $audit.LCCSourceNotes `
            -ManualReviewRequired $audit.ManualReviewRequired
        continue
    }

    $fieldUpdates = @(
        [pscustomobject]@{
            FieldName     = "LCC"
            ColumnLabel   = $LccColumn
            ExistingValue = $row.ExistingLCC
            ProposedValue = $row.ProposedLCC
            WouldUpdate   = $row.WouldUpdateLCC
        },
        [pscustomobject]@{
            FieldName     = "LCC Primary Class"
            ColumnLabel   = $LccPrimaryClassColumn
            ExistingValue = $row.ExistingLCCPrimaryClass
            ProposedValue = $row.ProposedLCCPrimaryClass
            WouldUpdate   = $row.WouldUpdateLCCPrimaryClass
        },
        [pscustomobject]@{
            FieldName     = "LCC Secondary Class"
            ColumnLabel   = $LccSecondaryClassColumn
            ExistingValue = $row.ExistingLCCSecondaryClass
            ProposedValue = $row.ProposedLCCSecondaryClass
            WouldUpdate   = $row.WouldUpdateLCCSecondaryClass
        },
        [pscustomobject]@{
            FieldName     = "LCC Classification Path"
            ColumnLabel   = $LccPathColumn
            ExistingValue = $row.ExistingLCCPath
            ProposedValue = $row.ProposedLCCPath
            WouldUpdate   = $row.WouldUpdateLCCPath
        }
    )

    foreach ($field in $fieldUpdates) {
        if ($field.WouldUpdate -ne "Yes") {
            New-ApplyResult `
                -InputTitle $row.InputTitle `
                -ISBN $row.ISBN `
                -CalibreId $row.CalibreId `
                -CalibreTitle $row.CalibreTitle `
                -FieldName $field.FieldName `
                -ColumnLabel $field.ColumnLabel `
                -ExistingValue $field.ExistingValue `
                -ProposedValue $field.ProposedValue `
                -WouldUpdate $field.WouldUpdate `
                -Status "Skipped" `
                -Message "Dry-run said no update needed" `
                -LCCConfidence $audit.LCCConfidence `
                -LCCConfidenceStatus $audit.LCCConfidenceStatus `
                -LCCSourceNotes $audit.LCCSourceNotes `
                -ManualReviewRequired $audit.ManualReviewRequired
            continue
        }

        if ([string]::IsNullOrWhiteSpace($field.ProposedValue)) {
            New-ApplyResult `
                -InputTitle $row.InputTitle `
                -ISBN $row.ISBN `
                -CalibreId $row.CalibreId `
                -CalibreTitle $row.CalibreTitle `
                -FieldName $field.FieldName `
                -ColumnLabel $field.ColumnLabel `
                -ExistingValue $field.ExistingValue `
                -ProposedValue $field.ProposedValue `
                -WouldUpdate $field.WouldUpdate `
                -Status "Skipped" `
                -Message "Proposed value was blank" `
                -LCCConfidence $audit.LCCConfidence `
                -LCCConfidenceStatus $audit.LCCConfidenceStatus `
                -LCCSourceNotes $audit.LCCSourceNotes `
                -ManualReviewRequired $audit.ManualReviewRequired
            continue
        }

        try {
            $setResult = Set-CalibreCustomValue `
                -ColumnLabel $field.ColumnLabel `
                -BookId $row.CalibreId `
                -Value $field.ProposedValue

            if ($setResult.ExitCode -eq 0) {
                New-ApplyResult `
                    -InputTitle $row.InputTitle `
                    -ISBN $row.ISBN `
                    -CalibreId $row.CalibreId `
                    -CalibreTitle $row.CalibreTitle `
                    -FieldName $field.FieldName `
                    -ColumnLabel $field.ColumnLabel `
                    -ExistingValue $field.ExistingValue `
                    -ProposedValue $field.ProposedValue `
                    -WouldUpdate $field.WouldUpdate `
                    -Status "Updated" `
                    -Message $setResult.Output `
                    -LCCConfidence $audit.LCCConfidence `
                    -LCCConfidenceStatus $audit.LCCConfidenceStatus `
                    -LCCSourceNotes $audit.LCCSourceNotes `
                    -ManualReviewRequired $audit.ManualReviewRequired
            }
            else {
                New-ApplyResult `
                    -InputTitle $row.InputTitle `
                    -ISBN $row.ISBN `
                    -CalibreId $row.CalibreId `
                    -CalibreTitle $row.CalibreTitle `
                    -FieldName $field.FieldName `
                    -ColumnLabel $field.ColumnLabel `
                    -ExistingValue $field.ExistingValue `
                    -ProposedValue $field.ProposedValue `
                    -WouldUpdate $field.WouldUpdate `
                    -Status "Error" `
                    -Message "calibredb exit code $($setResult.ExitCode): $($setResult.Output)" `
                    -LCCConfidence $audit.LCCConfidence `
                    -LCCConfidenceStatus $audit.LCCConfidenceStatus `
                    -LCCSourceNotes $audit.LCCSourceNotes `
                    -ManualReviewRequired $audit.ManualReviewRequired
            }
        }
        catch {
            New-ApplyResult `
                -InputTitle $row.InputTitle `
                -ISBN $row.ISBN `
                -CalibreId $row.CalibreId `
                -CalibreTitle $row.CalibreTitle `
                -FieldName $field.FieldName `
                -ColumnLabel $field.ColumnLabel `
                -ExistingValue $field.ExistingValue `
                -ProposedValue $field.ProposedValue `
                -WouldUpdate $field.WouldUpdate `
                -Status "Error" `
                -Message $_.Exception.Message `
                -LCCConfidence $audit.LCCConfidence `
                -LCCConfidenceStatus $audit.LCCConfidenceStatus `
                -LCCSourceNotes $audit.LCCSourceNotes `
                -ManualReviewRequired $audit.ManualReviewRequired
        }
    }
}

$results | Export-Csv -Path $ApplyReportCsv -NoTypeInformation -Encoding UTF8

$statusSummary = $results |
    Group-Object Status |
    Sort-Object Name |
    Select-Object Name, Count

$updatedRows = @($results | Where-Object { $_.Status -eq "Updated" })
$errorRows = @($results | Where-Object { $_.Status -eq "Error" })
$skippedRows = @($results | Where-Object { $_.Status -eq "Skipped" })

Write-Host ""
Write-Host "Apply Result Summary"
Write-Host "===================="
Write-Host ""

$statusSummary | Format-Table -AutoSize

Write-Host ""
Write-Host "Updated fields: $($updatedRows.Count)"
Write-Host "Skipped fields: $($skippedRows.Count)"
Write-Host "Error fields:   $($errorRows.Count)"

if ($updatedRows.Count -gt 0) {
    Write-Host ""
    Write-Host "Updated field details:"
    $updatedRows |
        Select-Object InputTitle, ISBN, CalibreId, FieldName, ProposedValue, LCCConfidence |
        Format-Table -AutoSize
}

if ($errorRows.Count -gt 0) {
    Write-Host ""
    Write-Host "Errors:"
    $errorRows |
        Select-Object InputTitle, ISBN, CalibreId, FieldName, Message |
        Format-Table -AutoSize
}

Write-Host ""
Write-Host "Apply complete. Report written to: $ApplyReportCsv"