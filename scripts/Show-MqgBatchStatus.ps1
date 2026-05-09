<#
.SYNOPSIS
Writes a read-only MQG batch status and readiness report.

.DESCRIPTION
Reads selected Calibre IDs from either -CalibreIds or -InputCsv and reports the current
Metadata Quality Gate checkbox state for each record.

This script does not modify Calibre metadata.

It reports:
- current MQG gate states
- completed gate count
- missing required gates
- whether a record is ready for MQG-99
- whether a record is already metadata complete
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$CalibreIds = "",

    [string]$InputCsv = "",

    [string]$ReportCsv = ".\reports\mqg-batch-status.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe"
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

    $text = Normalize-Value -Value ([string]$Value)

    if ($text -match '^(true|yes|1)$') {
        return "Yes"
    }

    return "No"
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

function Get-CalibreMqgRecord {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CalibreId
    )

    $fields = @(
        "id",
        "title",
        "authors",
        "*mqg_title_author",
        "*mqg_identifiers",
        "*mqg_lcc",
        "*mqg_awards",
        "*mqg_description",
        "*mqg_tags",
        "*mqg_cover",
        "*mqg_metadata_complete"
    ) -join ","

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

Write-Host "MQG batch status report"
Write-Host "======================="
Write-Host ""
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Report CSV: $ReportCsv"
Write-Host ""

$selectedIds = @(Get-SelectedCalibreIds)

$idCounts = @{}

foreach ($id in $selectedIds) {
    if (-not $idCounts.ContainsKey($id)) {
        $idCounts[$id] = 0
    }

    $idCounts[$id]++
}

$requiredGateNames = @(
    "MQG-01 Title & Author",
    "MQG-02 Identifiers",
    "MQG-03 LCC",
    "MQG-04 Awards",
    "MQG-05 Description / Comments",
    "MQG-06 Tags",
    "MQG-07 Cover"
)

$reportRows = foreach ($id in $selectedIds) {
    $calibreId = Normalize-Value -Value $id
    $blockingReasons = @()

    if ([string]::IsNullOrWhiteSpace($calibreId)) {
        $blockingReasons += "Missing CalibreId"
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreId) -and $idCounts[$calibreId] -gt 1) {
        $blockingReasons += "Duplicate CalibreId in input"
    }

    $recordResult = $null
    $record = $null

    if (-not [string]::IsNullOrWhiteSpace($calibreId)) {
        $recordResult = Get-CalibreMqgRecord -CalibreId $calibreId

        if (-not $recordResult.Found) {
            $blockingReasons += $recordResult.Error
        }
        else {
            $record = $recordResult.Record
        }
    }

    $title = ""
    $authors = ""

    $mqgTitleAuthor = "No"
    $mqgIdentifiers = "No"
    $mqgLcc = "No"
    $mqgAwards = "No"
    $mqgDescription = "No"
    $mqgTags = "No"
    $mqgCover = "No"
    $mqgMetadataComplete = "No"

    if ($null -ne $record) {
        $title = [string]$record.title
        $authors = Join-ArrayValue -Value $record.authors

        $mqgTitleAuthor = Convert-ToYesNo -Value $record.'*mqg_title_author'
        $mqgIdentifiers = Convert-ToYesNo -Value $record.'*mqg_identifiers'
        $mqgLcc = Convert-ToYesNo -Value $record.'*mqg_lcc'
        $mqgAwards = Convert-ToYesNo -Value $record.'*mqg_awards'
        $mqgDescription = Convert-ToYesNo -Value $record.'*mqg_description'
        $mqgTags = Convert-ToYesNo -Value $record.'*mqg_tags'
        $mqgCover = Convert-ToYesNo -Value $record.'*mqg_cover'
        $mqgMetadataComplete = Convert-ToYesNo -Value $record.'*mqg_metadata_complete'
    }

    $requiredGates = [ordered]@{
        "MQG-01 Title & Author"           = $mqgTitleAuthor
        "MQG-02 Identifiers"             = $mqgIdentifiers
        "MQG-03 LCC"                     = $mqgLcc
        "MQG-04 Awards"                  = $mqgAwards
        "MQG-05 Description / Comments"  = $mqgDescription
        "MQG-06 Tags"                    = $mqgTags
        "MQG-07 Cover"                   = $mqgCover
    }

    $completedRequiredGates = @(
        foreach ($gateName in $requiredGates.Keys) {
            if ($requiredGates[$gateName] -eq "Yes") {
                $gateName
            }
        }
    )

    $missingRequiredGates = @(
        foreach ($gateName in $requiredGates.Keys) {
            if ($requiredGates[$gateName] -ne "Yes") {
                $gateName
            }
        }
    )

    $readyForMqg99 = if ($missingRequiredGates.Count -eq 0 -and $blockingReasons.Count -eq 0) {
        "Yes"
    }
    else {
        "No"
    }

    $statusSummary = if ($blockingReasons.Count -gt 0) {
        "Blocked"
    }
    elseif ($mqgMetadataComplete -eq "Yes") {
        "Metadata Complete"
    }
    elseif ($readyForMqg99 -eq "Yes") {
        "Ready for MQG-99"
    }
    else {
        "In Progress"
    }

    [pscustomobject]@{
        CalibreId              = $calibreId
        Title                  = $title
        Authors                = $authors
        MqgTitleAuthor         = $mqgTitleAuthor
        MqgIdentifiers         = $mqgIdentifiers
        MqgLcc                 = $mqgLcc
        MqgAwards              = $mqgAwards
        MqgDescription         = $mqgDescription
        MqgTags                = $mqgTags
        MqgCover               = $mqgCover
        MqgMetadataComplete    = $mqgMetadataComplete
        CompletedGateCount     = $completedRequiredGates.Count
        RequiredGateCount      = $requiredGateNames.Count
        MissingRequiredGates   = $missingRequiredGates -join "; "
        ReadyForMqg99          = $readyForMqg99
        StatusSummary          = $statusSummary
        BlockingReasons        = $blockingReasons -join "; "
    }
}

$outputFolder = Split-Path -Path $ReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$reportRows | Export-Csv -Path $ReportCsv -NoTypeInformation -Encoding UTF8

$rowsReviewed = @($reportRows).Count
$rowsBlocked = @($reportRows | Where-Object { $_.StatusSummary -eq "Blocked" }).Count
$rowsReadyForMqg99 = @($reportRows | Where-Object { $_.ReadyForMqg99 -eq "Yes" -and $_.MqgMetadataComplete -ne "Yes" }).Count
$rowsMetadataComplete = @($reportRows | Where-Object { $_.MqgMetadataComplete -eq "Yes" }).Count
$rowsInProgress = @($reportRows | Where-Object { $_.StatusSummary -eq "In Progress" }).Count

Write-Host "Rows reviewed: $rowsReviewed"
Write-Host "Rows blocked: $rowsBlocked"
Write-Host "Rows in progress: $rowsInProgress"
Write-Host "Rows ready for MQG-99: $rowsReadyForMqg99"
Write-Host "Rows already metadata complete: $rowsMetadataComplete"
Write-Host ""
Write-Host "Report written: $ReportCsv"
Write-Host ""
Write-Host "Status preview:"

$reportRows |
    Select-Object CalibreId,Title,CompletedGateCount,RequiredGateCount,ReadyForMqg99,MqgMetadataComplete,StatusSummary,MissingRequiredGates |
    Format-Table -AutoSize
