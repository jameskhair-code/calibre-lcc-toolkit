<#
.SYNOPSIS
Marks MQG-05 Description / Comments complete for records verified by the Comments workflow.

.DESCRIPTION
Reads a Comments verification CSV and marks the Calibre custom field #mqg_description true
only for rows where the final Calibre comments metadata has been verified.

The verify report is treated as the source of truth.

Rows that are mismatched, missing, skipped, duplicate, manually blocked, or otherwise
unverified are not marked complete.

A complete Comments gate requires:
- successful comments apply
- verified title
- verified authors
- verified comments hash
- nonblank final comments
- expected and actual comments hashes matching
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$VerifyReportCsv = ".\reports\comments-verify-batch.csv",

    [string]$MqgReportCsv = ".\reports\comments-mqg-complete-batch.csv",

    [string]$MqgFieldName = "#mqg_description",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "MARK COMMENTS MQG COMPLETE",

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
    throw "Comments verify report CSV was not found: $VerifyReportCsv"
}

Write-Host "Comments MQG complete marker"
Write-Host "============================"
Write-Host ""
Write-Host "WARNING: This script can modify Calibre metadata."
Write-Host "Verify report CSV: $VerifyReportCsv"
Write-Host "MQG report CSV: $MqgReportCsv"
Write-Host "MQG field: $MqgFieldName"
Write-Host "Required verification: ApplyStatus Succeeded, title/authors/comments verified, matching comments hash."
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
    $title = Get-RowValue -Row $row -Names @("Title")
    $authors = Get-RowValue -Row $row -Names @("Authors")
    $commentsMode = Normalize-Value -Value (Get-RowValue -Row $row -Names @("CommentsMode"))
    $applyStatus = Normalize-Value -Value (Get-RowValue -Row $row -Names @("ApplyStatus"))
    $verificationStatus = Normalize-Value -Value (Get-RowValue -Row $row -Names @("VerificationStatus"))
    $titleVerified = Normalize-Value -Value (Get-RowValue -Row $row -Names @("TitleVerified"))
    $authorsVerified = Normalize-Value -Value (Get-RowValue -Row $row -Names @("AuthorsVerified"))
    $commentsVerified = Normalize-Value -Value (Get-RowValue -Row $row -Names @("CommentsVerified"))
    $expectedHash = Normalize-Value -Value (Get-RowValue -Row $row -Names @("ExpectedFinalCommentsHash"))
    $actualHash = Normalize-Value -Value (Get-RowValue -Row $row -Names @("ActualCommentsHash"))
    $expectedLengthText = Normalize-Value -Value (Get-RowValue -Row $row -Names @("ExpectedFinalLength"))
    $actualLengthText = Normalize-Value -Value (Get-RowValue -Row $row -Names @("ActualCommentsLength"))
    $verificationNotes = Get-RowValue -Row $row -Names @("VerificationNotes")

    $expectedLength = 0
    $actualLength = 0
    [void][int]::TryParse($expectedLengthText, [ref]$expectedLength)
    [void][int]::TryParse($actualLengthText, [ref]$actualLength)

    $blockingReasons = @()

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and $idCounts[$calibreId] -gt 1) {
        $blockingReasons += "Duplicate CalibreId in verify report"
    }

    if ($applyStatus -ne "Succeeded") {
        $blockingReasons += "ApplyStatus is not Succeeded"
    }

    if ($verificationStatus -ne "Verified") {
        $blockingReasons += "VerificationStatus is not Verified"
    }

    if ($titleVerified -ne "Yes") {
        $blockingReasons += "TitleVerified is not Yes"
    }

    if ($authorsVerified -ne "Yes") {
        $blockingReasons += "AuthorsVerified is not Yes"
    }

    if ($commentsVerified -ne "Yes") {
        $blockingReasons += "CommentsVerified is not Yes"
    }

    if ([string]::IsNullOrWhiteSpace($expectedHash)) {
        $blockingReasons += "ExpectedFinalCommentsHash is blank"
    }

    if ([string]::IsNullOrWhiteSpace($actualHash)) {
        $blockingReasons += "ActualCommentsHash is blank"
    }

    if (-not [string]::IsNullOrWhiteSpace($expectedHash) -and
        -not [string]::IsNullOrWhiteSpace($actualHash) -and
        $expectedHash -ne $actualHash) {
        $blockingReasons += "ActualCommentsHash does not match ExpectedFinalCommentsHash"
    }

    if ($expectedLength -le 0) {
        $blockingReasons += "ExpectedFinalLength is zero or invalid"
    }

    if ($actualLength -le 0) {
        $blockingReasons += "ActualCommentsLength is zero or invalid"
    }

    if ($expectedLength -gt 0 -and $actualLength -gt 0 -and $expectedLength -ne $actualLength) {
        $blockingReasons += "ActualCommentsLength does not match ExpectedFinalLength"
    }

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
        CalibreId                 = $calibreId
        Title                     = $title
        Authors                   = $authors
        CommentsMode              = $commentsMode
        ApplyStatus               = $applyStatus
        VerificationStatus        = $verificationStatus
        TitleVerified             = $titleVerified
        AuthorsVerified           = $authorsVerified
        CommentsVerified          = $commentsVerified
        ExpectedFinalCommentsHash = $expectedHash
        ActualCommentsHash        = $actualHash
        ExpectedFinalLength       = $expectedLengthText
        ActualCommentsLength      = $actualLengthText
        VerificationNotes         = $verificationNotes
        MarkEligible              = if ($eligible) { "Yes" } else { "No" }
        MarkStatus                = $markStatus
        ReadBackStatus            = $currentReadBackStatus
        BlockingReasons           = $blockingReasons -join "; "
        CalibreOutput             = ""
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

$outputFolder = Split-Path -Path $MqgReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

if ($eligibleRows.Count -eq 0) {
    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8
    throw "No verified Comments rows are eligible to mark MQG complete."
}

Write-Host "Eligible rows:"
foreach ($row in $eligibleRows | Select-Object -First 20) {
    Write-Host "  $($row.CalibreId) - $($row.Title)"
}

if ($eligibleRows.Count -gt 20) {
    Write-Host "  ... $($eligibleRows.Count - 20) more eligible row(s)"
}

if ($skippedRows.Count -gt 0) {
    Write-Host ""
    Write-Host "Skipped rows:"
    foreach ($row in $skippedRows | Select-Object -First 20) {
        Write-Host "  $($row.CalibreId) - $($row.VerificationStatus) - $($row.BlockingReasons)"
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

    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "Preflight complete."
    Write-Host "MQG report: $MqgReportCsv"
    Write-Host ""
    Write-Host "PreflightOnly was specified. No Calibre metadata was modified."
    return
}

if ($readyRows.Count -eq 0) {
    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    Write-Host ""
    Write-Host "No new Comments MQG rows need to be marked complete."
    Write-Host "Rows already complete: $($alreadyCompleteRows.Count)"
    Write-Host "MQG report: $MqgReportCsv"
    return
}

Write-Host ""
Write-Host "About to mark MQG-05 Description / Comments complete for $($readyRows.Count) row(s)."
Write-Host "Type the exact confirmation phrase to continue:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -ne $ConfirmationPhrase) {
    throw "Comments MQG complete mark cancelled. Confirmation phrase did not match."
}

Write-Host ""
Write-Host "Marking verified Comments records complete..."

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

$finalRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

$markedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Succeeded" }).Count
$alreadyCompleteCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Already Complete" }).Count
$failedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Failed" }).Count
$skippedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Skipped" }).Count

Write-Host ""
Write-Host "Comments MQG complete mark finished."
Write-Host "Rows newly marked complete: $markedCount"
Write-Host "Rows already complete: $alreadyCompleteCount"
Write-Host "Rows failed: $failedCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host "MQG report: $MqgReportCsv"

if ($failedCount -gt 0) {
    throw "One or more Comments MQG complete mark operations failed. Review the MQG report."
}
