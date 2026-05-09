<#
.SYNOPSIS
Marks MQG-07 Cover complete for manually reviewed cover metadata.

.DESCRIPTION
Reads selected Calibre IDs from either -CalibreIds or -InputCsv and marks the Calibre
custom field #mqg_cover true only after basic cover checks pass.

This is a manual-gate completion script. It does not download, generate, replace, or enrich covers.

The script checks:
- CalibreId exists
- duplicate IDs are blocked
- cover path is present unless -AllowNoCover is used
- cover path exists on disk unless -AllowNoCover is used
- current #mqg_cover state is read back
- already-complete rows are reported and not rewritten
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$CalibreIds = "",

    [string]$InputCsv = "",

    [string]$MqgReportCsv = ".\reports\cover-mqg-complete-batch.csv",

    [string]$MqgFieldName = "#mqg_cover",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$ConfirmationPhrase = "MARK COVER MQG COMPLETE",

    [switch]$PreflightOnly,

    [switch]$AllowNoCover
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
        Output   = ($output | ForEach-Object { [string]$_ }) -join "`n"
    }
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

function Join-ArrayValue {
    param(
        [AllowNull()]
        $Value
    )

    if ($null -eq $Value) {
        return ""
    }

    if ($Value -is [System.Array]) {
        return (@($Value | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join " | ")
    }

    return [string]$Value
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

function Get-SelectedCalibreIds {
    $ids = @()

    if (-not [string]::IsNullOrWhiteSpace($CalibreIds)) {
        $ids += $CalibreIds -split "," |
            ForEach-Object { $_.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }

    if (-not [string]::IsNullOrWhiteSpace($InputCsv)) {
        if (-not (Test-Path $InputCsv)) {
            throw "Input CSV was not found: $InputCsv"
        }

        $csvRows = @(Import-Csv -Path $InputCsv)

        foreach ($row in $csvRows) {
            $idProperty = $row.PSObject.Properties["CalibreId"]

            if ($null -eq $idProperty) {
                throw "Input CSV must contain a CalibreId column."
            }

            $idText = Normalize-Value -Value ([string]$idProperty.Value)

            if (-not [string]::IsNullOrWhiteSpace($idText)) {
                $ids += $idText
            }
        }
    }

    $ids = @($ids | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    if ($ids.Count -eq 0) {
        throw "No Calibre IDs were supplied. Use -CalibreIds or -InputCsv."
    }

    return $ids
}

function Get-CalibreCoverRecord {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CalibreId
    )

    $fields = "id,title,authors,cover"

    $result = Invoke-CalibreDb -Arguments @(
        "list",
        "--for-machine",
        "--fields",
        $fields,
        "--search",
        "id:$CalibreId"
    )

    if ($result.ExitCode -ne 0) {
        return [pscustomobject]@{
            Found = $false
            Error = "calibredb list failed with exit code $($result.ExitCode): $($result.Output)"
            Record = $null
        }
    }

    if ([string]::IsNullOrWhiteSpace($result.Output)) {
        return [pscustomobject]@{
            Found = $false
            Error = "No calibredb output returned."
            Record = $null
        }
    }

    try {
        $records = @($result.Output | ConvertFrom-Json)
    }
    catch {
        return [pscustomobject]@{
            Found = $false
            Error = "Could not parse calibredb JSON output: $($_.Exception.Message)"
            Record = $null
        }
    }

    if ($records.Count -eq 0) {
        return [pscustomobject]@{
            Found = $false
            Error = "CalibreId was not found."
            Record = $null
        }
    }

    if ($records.Count -gt 1) {
        return [pscustomobject]@{
            Found = $false
            Error = "Search returned more than one record."
            Record = $null
        }
    }

    return [pscustomobject]@{
        Found = $true
        Error = ""
        Record = $records[0]
    }
}

Write-Host "Cover MQG complete marker"
Write-Host "========================="
Write-Host ""
Write-Host "WARNING: This script can modify Calibre metadata."
Write-Host "MQG report CSV: $MqgReportCsv"
Write-Host "MQG field: $MqgFieldName"
Write-Host "Manual gate: cover must already be reviewed before marking complete."
Write-Host ""

if ($PreflightOnly) {
    Write-Host "Mode: Preflight only. No Calibre metadata will be modified." -ForegroundColor Yellow
}
else {
    Write-Host "Mode: Apply. Calibre metadata may be modified after confirmation." -ForegroundColor Yellow
}

Write-Host ""

$selectedIds = @(Get-SelectedCalibreIds)

$idCounts = @{}

foreach ($id in $selectedIds) {
    if (-not $idCounts.ContainsKey($id)) {
        $idCounts[$id] = 0
    }

    $idCounts[$id]++
}

$preflightRows = foreach ($id in $selectedIds) {
    $blockingReasons = @()
    $calibreId = Normalize-Value -Value $id

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and $idCounts[$calibreId] -gt 1) {
        $blockingReasons += "Duplicate CalibreId in input"
    }

    $recordResult = $null
    $record = $null

    if (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        $recordResult = Get-CalibreCoverRecord -CalibreId $calibreId

        if (-not $recordResult.Found) {
            $blockingReasons += $recordResult.Error
        }
        else {
            $record = $recordResult.Record
        }
    }

    $title = ""
    $authors = ""
    $coverPath = ""
    $coverExists = "No"

    if ($null -ne $record) {
        $title = [string]$record.title
        $authors = Join-ArrayValue -Value $record.authors
        $coverPath = Normalize-Value -Value ([string]$record.cover)

        if (-not [string]::IsNullOrWhiteSpace($coverPath) -and (Test-Path -Path $coverPath -PathType Leaf)) {
            $coverExists = "Yes"
        }
    }

    if (-not $AllowNoCover) {
        if ([string]::IsNullOrWhiteSpace($coverPath)) {
            $blockingReasons += "Cover path is blank"
        }
        elseif ($coverExists -ne "Yes") {
            $blockingReasons += "Cover file was not found on disk"
        }
    }

    $blockingReasons = @($blockingReasons | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)

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
        CalibreId       = $calibreId
        Title           = $title
        Authors         = $authors
        CoverPath       = $coverPath
        CoverExists     = $coverExists
        AllowNoCover    = if ($AllowNoCover) { "Yes" } else { "No" }
        MarkEligible    = if ($eligible) { "Yes" } else { "No" }
        MarkStatus      = $markStatus
        ReadBackStatus  = $currentReadBackStatus
        BlockingReasons = $blockingReasons -join "; "
        CalibreOutput   = ""
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
    throw "No Cover rows are eligible to mark MQG complete."
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
        Write-Host "  $($row.CalibreId) - $($row.BlockingReasons)"
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
    Write-Host "No new Cover MQG rows need to be marked complete."
    Write-Host "Rows already complete: $($alreadyCompleteRows.Count)"
    Write-Host "MQG report: $MqgReportCsv"
    return
}

Write-Host ""
Write-Host "About to mark MQG-07 Cover complete for $($readyRows.Count) row(s)."
Write-Host "Type the exact confirmation phrase to continue:"
Write-Host ""
Write-Host "  $ConfirmationPhrase"
Write-Host ""

$confirmation = Read-Host "Confirmation"

if ($confirmation -ne $ConfirmationPhrase) {
    throw "Cover MQG complete mark cancelled. Confirmation phrase did not match."
}

Write-Host ""
Write-Host "Marking reviewed Cover records complete..."

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
Write-Host "Cover MQG complete mark finished."
Write-Host "Rows newly marked complete: $markedCount"
Write-Host "Rows already complete: $alreadyCompleteCount"
Write-Host "Rows failed: $failedCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host "MQG report: $MqgReportCsv"

if ($failedCount -gt 0) {
    throw "One or more Cover MQG complete mark operations failed. Review the MQG report."
}
