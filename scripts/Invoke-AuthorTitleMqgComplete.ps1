<#
.SYNOPSIS
Marks MQG-01 Title & Author complete for records verified or cleanly reviewed by the Author / Title Cleanup workflow.

.DESCRIPTION
Reads an author/title cleanup verify report and marks the Calibre custom field
#mqg_title_author true for rows that are safe to mark complete.

Eligible rows:
- VerificationStatus = Verified
- OR clean no-change rows where:
  - VerificationStatus = Clean No-Change
  - TitleChangeDetected is not Yes
  - AuthorsChangeDetected is not Yes
  - ApplyEligible is not Yes
  - BlockingReasons is blank
  - expected and actual title/author values still match

This script does not trust export, dry run, summary, or apply reports directly.
The verify report is the source of truth.

Rows that are mismatched, missing, duplicate, blocked, or otherwise unsafe are not marked complete.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-AuthorTitleMqgComplete.ps1 `
  -VerifyReportCsv ".\reports\author-title-cleanup-verify-batch.csv" `
  -MqgReportCsv ".\reports\author-title-cleanup-mqg-complete-batch.csv" `
  -PreflightOnly

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-AuthorTitleMqgComplete.ps1 `
  -VerifyReportCsv ".\reports\author-title-cleanup-verify-batch.csv" `
  -MqgReportCsv ".\reports\author-title-cleanup-mqg-complete-batch.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$VerifyReportCsv = ".\reports\author-title-cleanup-verify-batch.csv",

    [string]$MqgReportCsv = ".\reports\author-title-cleanup-mqg-complete-batch.csv",

    [string]$MqgFieldName = "#mqg_title_author",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "MARK MQG COMPLETE",

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

function Normalize-Status {
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

    return [string]$property.Value
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

function Test-CleanNoChangeRow {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$VerificationStatus
    )

    $titleChangeDetected = Get-RowValue -Row $Row -Name "TitleChangeDetected"
    $authorsChangeDetected = Get-RowValue -Row $Row -Name "AuthorsChangeDetected"
    $applyEligible = Get-RowValue -Row $Row -Name "ApplyEligible"
    $blockingReasons = Get-RowValue -Row $Row -Name "BlockingReasons"

    $expectedTitle = Get-RowValue -Row $Row -Name "ExpectedTitle"
    $actualTitle = Get-RowValue -Row $Row -Name "ActualTitle"
    $expectedAuthors = Get-RowValue -Row $Row -Name "ExpectedAuthors"
    $actualAuthors = Get-RowValue -Row $Row -Name "ActualAuthors"

    if ($VerificationStatus -ne "Clean No-Change") {
        return $false
    }

    if ($titleChangeDetected -eq "Yes" -or $authorsChangeDetected -eq "Yes") {
        return $false
    }

    if ($applyEligible -eq "Yes") {
        return $false
    }

    if (-not [string]::IsNullOrWhiteSpace($blockingReasons)) {
        return $false
    }

    if ((Normalize-ComparableValue $expectedTitle) -cne (Normalize-ComparableValue $actualTitle)) {
        return $false
    }

    if ((Normalize-ComparableValue $expectedAuthors) -cne (Normalize-ComparableValue $actualAuthors)) {
        return $false
    }

    return $true
}

if (-not (Test-Path $VerifyReportCsv)) {
    throw "Verify report CSV was not found: $VerifyReportCsv"
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

Write-Host "Author/Title MQG complete marker"
Write-Host "================================"
Write-Host ""
Write-Host "WARNING: This script can modify Calibre metadata."
Write-Host "Verify report CSV: $VerifyReportCsv"
Write-Host "MQG report CSV: $MqgReportCsv"
Write-Host "MQG field: $MqgFieldName"
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
    $idText = ([string]$row.CalibreId).Trim()

    if (-not [string]::IsNullOrWhiteSpace($idText)) {
        if (-not $idCounts.ContainsKey($idText)) {
            $idCounts[$idText] = 0
        }

        $idCounts[$idText]++
    }
}

$preflightRows = foreach ($row in $rows) {
    $calibreId = ([string]$row.CalibreId).Trim()
    $verificationStatus = Normalize-Status -Value $row.VerificationStatus
    $blockingReasons = @()
    $completionBasis = ""

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }

    $isVerified = ($verificationStatus -eq "Verified")
    $isCleanNoChange = Test-CleanNoChangeRow -Row $row -VerificationStatus $verificationStatus

    if ($isVerified) {
        $completionBasis = "Verified"
    }
    elseif ($isCleanNoChange) {
        $completionBasis = "Clean No-Change"
    }
    else {
        $blockingReasons += "VerificationStatus is not Verified or clean no-change"
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and $idCounts[$calibreId] -gt 1) {
        $blockingReasons += "Duplicate CalibreId in verify report"
    }

    $eligible = ($blockingReasons.Count -eq 0)

    [pscustomobject]@{
        CalibreId          = $calibreId
        ExpectedTitle      = [string]$row.ExpectedTitle
        ActualTitle        = [string]$row.ActualTitle
        ExpectedAuthors    = [string]$row.ExpectedAuthors
        ActualAuthors      = [string]$row.ActualAuthors
        VerificationStatus = $verificationStatus
        VerificationNotes  = [string]$row.VerificationNotes
        CompletionBasis    = $completionBasis
        MarkEligible       = if ($eligible) { "Yes" } else { "No" }
        MarkStatus         = if ($eligible) { "Ready" } else { "Skipped" }
        ReadBackStatus     = ""
        BlockingReasons    = $blockingReasons -join "; "
        CalibreOutput      = ""
    }
}

$eligibleRows = @($preflightRows | Where-Object { $_.MarkEligible -eq "Yes" })
$skippedRows = @($preflightRows | Where-Object { $_.MarkEligible -ne "Yes" })
$verifiedEligibleRows = @($eligibleRows | Where-Object { $_.CompletionBasis -eq "Verified" })
$cleanNoChangeEligibleRows = @($eligibleRows | Where-Object { $_.CompletionBasis -eq "Clean No-Change" })

Write-Host "Rows reviewed: $($preflightRows.Count)"
Write-Host "Rows eligible to mark complete: $($eligibleRows.Count)"
Write-Host "Rows eligible from verified changes: $($verifiedEligibleRows.Count)"
Write-Host "Rows eligible from clean no-change review: $($cleanNoChangeEligibleRows.Count)"
Write-Host "Rows skipped: $($skippedRows.Count)"
Write-Host ""

if ($eligibleRows.Count -eq 0) {
    $outputFolder = Split-Path -Path $MqgReportCsv -Parent

    if ($outputFolder -and -not (Test-Path $outputFolder)) {
        New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
    }

    $preflightRows | Export-Csv -Path $MqgReportCsv -NoTypeInformation -Encoding UTF8

    throw "No rows are eligible to mark MQG complete."
}

Write-Host "Eligible rows:"
foreach ($row in $eligibleRows) {
    Write-Host "  $($row.CalibreId) - $($row.CompletionBasis) - $($row.ActualTitle) - $($row.ActualAuthors)"
}

if ($skippedRows.Count -gt 0) {
    Write-Host ""
    Write-Host "Skipped rows:"
    foreach ($row in $skippedRows) {
        Write-Host "  $($row.CalibreId) - $($row.VerificationStatus) - $($row.BlockingReasons)"
    }
}

if ($PreflightOnly) {
    foreach ($row in $preflightRows) {
        if ($row.MarkEligible -eq "Yes") {
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

Write-Host ""
Write-Host "About to mark MQG-01 Title & Author complete for $($eligibleRows.Count) row(s)."
Write-Host "Type the exact confirmation phrase to continue:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -ne $ConfirmationPhrase) {
    throw "MQG complete mark cancelled. Confirmation phrase did not match."
}

Write-Host ""
Write-Host "Marking Author/Title MQG complete records..."

$finalRows = foreach ($row in $preflightRows) {
    if ($row.MarkEligible -ne "Yes") {
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
$failedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Failed" }).Count
$skippedCount = @($finalRows | Where-Object { $_.MarkStatus -eq "Skipped" }).Count

Write-Host ""
Write-Host "MQG complete mark finished."
Write-Host "Rows marked complete: $markedCount"
Write-Host "Rows failed: $failedCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host "MQG report: $MqgReportCsv"

if ($failedCount -gt 0) {
    throw "One or more MQG complete mark operations failed. Review the MQG report."
}

