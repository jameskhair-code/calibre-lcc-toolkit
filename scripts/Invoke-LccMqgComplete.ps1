<#
.SYNOPSIS
Marks MQG-03 LCC complete for records verified by the LCC workflow.

.DESCRIPTION
Reads an LCC verification CSV and marks the Calibre custom field #mqg_lcc true
only for rows where the final Calibre LCC metadata matches the proposed LCC metadata.

The verify report is treated as the source of truth.

Rows that are mismatched, missing, skipped, duplicate, manually blocked, or still show
pending LCC updates are not marked complete.

A complete LCC gate requires all four LCC fields:
- LCC
- LCC Classification Path
- LCC Primary Class
- LCC Secondary Class
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$VerifyReportCsv = ".\reports\lcc-verify-batch.csv",

    [string]$MqgReportCsv = ".\reports\lcc-mqg-complete-batch.csv",

    [string]$MqgFieldName = "#mqg_lcc",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "MARK LCC MQG COMPLETE",

    [switch]$PreflightOnly
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

    $output = & $CalibreDb @allArgs 2>&1
    $exitCode = $LASTEXITCODE

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = ($output | ForEach-Object { [string]$_ }) -join " "
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

function Test-LccFieldVerified {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FieldLabel,

        [AllowNull()]
        [string]$ExistingValue,

        [AllowNull()]
        [string]$ProposedValue,

        [AllowNull()]
        [string]$WouldUpdate
    )

    $reasons = @()

    $existing = Normalize-Value -Value $ExistingValue
    $proposed = Normalize-Value -Value $ProposedValue
    $wouldUpdateValue = Normalize-Value -Value $WouldUpdate

    if ([string]::IsNullOrWhiteSpace($proposed)) {
        $reasons += "$FieldLabel proposed value is blank"
    }

    if ([string]::IsNullOrWhiteSpace($existing)) {
        $reasons += "$FieldLabel existing value is blank"
    }

    if (-not [string]::IsNullOrWhiteSpace($existing) -and
        -not [string]::IsNullOrWhiteSpace($proposed) -and
        $existing -ne $proposed) {
        $reasons += "$FieldLabel existing value does not match proposed value"
    }

    if (-not [string]::IsNullOrWhiteSpace($wouldUpdateValue) -and $wouldUpdateValue -ne "No") {
        $reasons += "$FieldLabel still shows WouldUpdate = $wouldUpdateValue"
    }

    return $reasons
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

if (-not (Test-Path $VerifyReportCsv)) {
    throw "LCC verify report CSV was not found: $VerifyReportCsv"
}

Write-Host "LCC MQG complete marker"
Write-Host "======================="
Write-Host ""
Write-Host "WARNING: This script can modify Calibre metadata."
Write-Host "Verify report CSV: $VerifyReportCsv"
Write-Host "MQG report CSV: $MqgReportCsv"
Write-Host "MQG field: $MqgFieldName"
Write-Host "Required LCC fields: LCC, Classification Path, Primary Class, Secondary Class"
Write-Host ""

if ($PreflightOnly) {
    Write-Host "Mode: Preflight only. No Calibre metadata will be modified." -ForegroundColor Yellow
}
else {
    Write-Host "Mode: Apply. Calibre metadata may be modified after confirmation." -ForegroundColor Yellow
}

Write-Host ""

$rows = @(Import-Csv -Path $VerifyReportCsv)

if ($rows.Count -eq 0) {
    throw "Verify report CSV has no data rows: $VerifyReportCsv"
}

$idCounts = @{}

foreach ($row in $rows) {
    $idText = Normalize-Value -Value (Get-RowValue -Row $row -Names @("CalibreId"))

    if (-not [string]::IsNullOrWhiteSpace($idText)) {
        if (-not $idCounts.ContainsKey($idText)) {
            $idCounts[$idText] = 0
        }

        $idCounts[$idText]++
    }
}

$preflightRows = foreach ($row in $rows) {
    $calibreId = Normalize-Value -Value (Get-RowValue -Row $row -Names @("CalibreId"))
    $matchStatus = Normalize-Value -Value (Get-RowValue -Row $row -Names @("MatchStatus"))
    $warning = Normalize-Value -Value (Get-RowValue -Row $row -Names @("Warning"))
    $manualReviewRequired = Normalize-Value -Value (Get-RowValue -Row $row -Names @("ManualReviewRequired"))
    $confidenceStatus = Normalize-Value -Value (Get-RowValue -Row $row -Names @("LCCConfidenceStatus"))

    $blockingReasons = @()

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and $idCounts[$calibreId] -gt 1) {
        $blockingReasons += "Duplicate CalibreId in verify report"
    }

    if ($matchStatus -ne "Matched") {
        $blockingReasons += "MatchStatus is not Matched"
    }

    if (-not [string]::IsNullOrWhiteSpace($warning)) {
        $blockingReasons += "Warning is not blank"
    }

    if ($manualReviewRequired -eq "Yes") {
        $blockingReasons += "ManualReviewRequired is Yes"
    }

    if ($confidenceStatus -eq "Unexpected") {
        $blockingReasons += "LCCConfidenceStatus is Unexpected"
    }

    $blockingReasons += Test-LccFieldVerified `
        -FieldLabel "LCC" `
        -ExistingValue (Get-RowValue -Row $row -Names @("ExistingLCC")) `
        -ProposedValue (Get-RowValue -Row $row -Names @("ProposedLCC")) `
        -WouldUpdate (Get-RowValue -Row $row -Names @("WouldUpdateLCC"))

    $blockingReasons += Test-LccFieldVerified `
        -FieldLabel "LCC Primary Class" `
        -ExistingValue (Get-RowValue -Row $row -Names @("ExistingLCCPrimaryClass")) `
        -ProposedValue (Get-RowValue -Row $row -Names @("ProposedLCCPrimaryClass")) `
        -WouldUpdate (Get-RowValue -Row $row -Names @("WouldUpdateLCCPrimaryClass"))

    $blockingReasons += Test-LccFieldVerified `
        -FieldLabel "LCC Secondary Class" `
        -ExistingValue (Get-RowValue -Row $row -Names @("ExistingLCCSecondaryClass")) `
        -ProposedValue (Get-RowValue -Row $row -Names @("ProposedLCCSecondaryClass")) `
        -WouldUpdate (Get-RowValue -Row $row -Names @("WouldUpdateLCCSecondaryClass"))

    $blockingReasons += Test-LccFieldVerified `
        -FieldLabel "LCC Classification Path" `
        -ExistingValue (Get-RowValue -Row $row -Names @("ExistingLCCPath")) `
        -ProposedValue (Get-RowValue -Row $row -Names @("ProposedLCCPath")) `
        -WouldUpdate (Get-RowValue -Row $row -Names @("WouldUpdateLCCPath"))

    $blockingReasons = @($blockingReasons | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    $eligible = ($blockingReasons.Count -eq 0)

    $currentReadBackStatus = ""
    $alreadyComplete = $false

    if ($eligible -and -not [string]::IsNullOrWhiteSpace($calibreId)) {
        $currentReadBack = Test-MqgFieldTrue -CalibreId $calibreId -MqgFieldName $MqgFieldName
        $currentReadBackStatus = $currentReadBack.Status
        $alreadyComplete = $currentReadBack.IsTrue
    }

    $markStatus = if (-not $eligible) {
        "Skipped"
    }
    elseif ($alreadyComplete) {
        "Already Complete"
    }
    else {
        "Ready"
    }

    [pscustomobject]@{
        CalibreId                     = $calibreId
        CalibreTitle                  = Get-RowValue -Row $row -Names @("CalibreTitle")
        CalibreAuthors                = Get-RowValue -Row $row -Names @("CalibreAuthors")
        MatchStatus                   = $matchStatus
        ExistingLCC                   = Get-RowValue -Row $row -Names @("ExistingLCC")
        ProposedLCC                   = Get-RowValue -Row $row -Names @("ProposedLCC")
        ExistingLCCPrimaryClass       = Get-RowValue -Row $row -Names @("ExistingLCCPrimaryClass")
        ProposedLCCPrimaryClass       = Get-RowValue -Row $row -Names @("ProposedLCCPrimaryClass")
        ExistingLCCSecondaryClass     = Get-RowValue -Row $row -Names @("ExistingLCCSecondaryClass")
        ProposedLCCSecondaryClass     = Get-RowValue -Row $row -Names @("ProposedLCCSecondaryClass")
        ExistingLCCPath               = Get-RowValue -Row $row -Names @("ExistingLCCPath")
        ProposedLCCPath               = Get-RowValue -Row $row -Names @("ProposedLCCPath")
        MarkEligible                  = if ($eligible) { "Yes" } else { "No" }
        MarkStatus                    = $markStatus
        ReadBackStatus                = $currentReadBackStatus
        BlockingReasons               = $blockingReasons -join "; "
        CalibreOutput                 = ""
    }
}

$eligibleRows = @($preflightRows | Where-Object { $_.MarkEligible -eq "Yes" })
$skippedRows = @($preflightRows | Where-Object { $_.MarkEligible -ne "Yes" })
$alreadyCompleteRows = @($preflightRows | Where-Object { $_.MarkStatus -eq "Already Complete" })
$readyRows = @($preflightRows | Where-Object { $_.MarkStatus -eq "Ready" })

Write-Host "Rows reviewed: $($preflightRows.Count)"
Write-Host "Rows eligible to mark complete: $($eligibleRows.Count)"
Write-Host "Rows already complete: $($alreadyCompleteRows.Count)"
Write-Host "Rows ready to mark complete: $($readyRows.Count)"
Write-Host "Rows skipped: $($skippedRows.Count)"
Write-Host ""

if ($eligibleRows.Count -eq 0) {
    $outputFolder = Split-Path -Path $MqgReportCsv -Parent

    if ($outputFolder -and -not (Test-Path $outputFolder)) {
        New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
    }

    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    throw "No verified LCC rows are eligible to mark MQG complete."
}

Write-Host "Eligible rows:"
foreach ($row in $eligibleRows | Select-Object -First 20) {
    Write-Host "  $($row.CalibreId) - $($row.CalibreTitle) - $($row.ProposedLCC)"
}

if ($eligibleRows.Count -gt 20) {
    Write-Host "  ... $($eligibleRows.Count - 20) more eligible row(s)"
}

if ($skippedRows.Count -gt 0) {
    Write-Host ""
    Write-Host "Skipped rows:"
    foreach ($row in $skippedRows | Select-Object -First 20) {
        Write-Host "  $($row.CalibreId) - $($row.MatchStatus) - $($row.BlockingReasons)"
    }

    if ($skippedRows.Count -gt 20) {
        Write-Host "  ... $($skippedRows.Count - 20) more skipped row(s)"
    }
}

if ($PreflightOnly) {
    foreach ($row in $preflightRows) {
        if ($row.MarkStatus -eq "Ready") {
            $row.MarkStatus = "Not Run - Preflight Only"
        }
    }

    $outputFolder = Split-Path -Path $MqgReportCsv -Parent

    if ($outputFolder -and -not (Test-Path $outputFolder)) {
        New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
    }

    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "Preflight complete."
    Write-Host "MQG report: $MqgReportCsv"
    Write-Host ""
    Write-Host "PreflightOnly was specified. No Calibre metadata was modified."
    return
}

if ($readyRows.Count -eq 0) {
    $outputFolder = Split-Path -Path $MqgReportCsv -Parent

    if ($outputFolder -and -not (Test-Path $outputFolder)) {
        New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
    }

    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "No new LCC MQG rows need to be marked complete."
    Write-Host "Rows already complete: $($alreadyCompleteRows.Count)"
    Write-Host "MQG report: $MqgReportCsv"
    return
}

Write-Host ""
Write-Host "About to mark MQG-03 LCC complete for $($readyRows.Count) row(s)."
Write-Host "Type the exact confirmation phrase to continue:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -ne $ConfirmationPhrase) {
    throw "LCC MQG complete mark cancelled. Confirmation phrase did not match."
}

Write-Host ""
Write-Host "Marking verified LCC records complete..."

$finalRows = foreach ($row in $preflightRows) {
    if ($row.MarkEligible -ne "Yes") {
        $row
        continue
    }

    if ($row.MarkStatus -eq "Already Complete") {
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

$outputFolder = Split-Path -Path $MqgReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$finalRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

$markedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Succeeded" }).Count
$alreadyCompleteCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Already Complete" }).Count
$failedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Failed" }).Count
$skippedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Skipped" }).Count

Write-Host ""
Write-Host "LCC MQG complete mark finished."
Write-Host "Rows newly marked complete: $markedCount"
Write-Host "Rows already complete: $alreadyCompleteCount"
Write-Host "Rows failed: $failedCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host "MQG report: $MqgReportCsv"

if ($failedCount -gt 0) {
    throw "One or more LCC MQG complete mark operations failed. Review the MQG report."
}


