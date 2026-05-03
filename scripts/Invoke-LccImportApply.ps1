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

    $output = & $CalibreDb @(
        $(if (-not [string]::IsNullOrWhiteSpace($LibraryPath)) { "--with-library"; $LibraryPath }),
        "set_custom",
        $ColumnLabel,
        $BookId,
        $Value
    ) 2>&1

    $exitCode = $LASTEXITCODE

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = ($output -join "`n")
    }
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
        [string]$Message
    )

    [pscustomobject]@{
        InputTitle    = $InputTitle
        ISBN          = $ISBN
        CalibreId     = $CalibreId
        CalibreTitle  = $CalibreTitle
        FieldName     = $FieldName
        ColumnLabel   = $ColumnLabel
        ExistingValue = $ExistingValue
        ProposedValue = $ProposedValue
        WouldUpdate   = $WouldUpdate
        Status        = $Status
        Message       = $Message
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

$rows = Import-Csv -Path $DryRunReportCsv

$results = foreach ($row in $rows) {
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
            -Message "MatchStatus was '$($row.MatchStatus)'"
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
                -Message "Dry-run said no update needed"
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
                -Message "Proposed value was blank"
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
                    -Message $setResult.Output
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
                    -Message "calibredb exit code $($setResult.ExitCode): $($setResult.Output)"
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
                -Message $_.Exception.Message
        }
    }
}

$results | Export-Csv -Path $ApplyReportCsv -NoTypeInformation -Encoding UTF8
$results | Format-Table -AutoSize

Write-Host ""
Write-Host "Apply complete. Report written to: $ApplyReportCsv"