<#
.SYNOPSIS
Creates a reusable Calibre Toolkit batch manifest.

.DESCRIPTION
Resolves a Calibre batch from a Calibre search string, explicit Calibre IDs, or a
Calibre ID file, then writes a stable CSV manifest with one row per selected book.

This script is read-only and does not modify Calibre metadata.

The manifest is intended to become the stable source of truth for a batch after
initial selection. Downstream toolkit modules can use the manifest's CalibreId
column instead of re-running a Calibre search that may change as metadata is updated.

Selection behavior:
- Search only: exports all records matching the search.
- IDs only / ID file only: resolves those IDs directly.
- Search plus IDs / ID file: applies the explicit ID list as a local filter against
  the search result.
- ExactAwardProgram: optional local exact-match filter for Award Programs.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\New-ToolkitBatchManifest.ps1 `
  -BatchSlug "french-history-title-author" `
  -Search '#mqg_title_author:false and tags:"French History"' `
  -OutputCsv ".\input\batch-french-history-title-author.csv" `
  -ReportCsv ".\reports\batch-french-history-title-author-selection-summary.csv"

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\New-ToolkitBatchManifest.ps1 `
  -BatchSlug "leo-gershoy-smoketest" `
  -CalibreIds "5374,5375,5376" `
  -OutputCsv ".\input\batch-leo-gershoy-smoketest.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$Search = "",

    [string]$ExactAwardProgram = "",

    [string]$CalibreIds = "",

    [string]$CalibreIdFile = "",

    [string]$BatchSlug = "batch",

    [string]$OutputCsv = ".\input\batch-manifest.csv",

    [string]$ReportCsv = ".\reports\batch-manifest-summary.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [switch]$Overwrite
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

    $text = Normalize-ComparableValue -Value ([string]$Value)

    if ($text -match '^(true|yes|1)$') {
        return "Yes"
    }

    return "No"
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
        Output   = ($output | ForEach-Object { [string]$_ }) -join "`n"
    }
}

function Get-CustomRawValue {
    param(
        $Book,
        [string]$ColumnLabel
    )

    if ($Book -is [System.Array] -and $Book.Count -eq 1) {
        $Book = $Book[0]
    }

    $propertyName = "*$ColumnLabel"

    $property = $Book.PSObject.Properties |
        Where-Object { $_.Name -eq $propertyName } |
        Select-Object -First 1

    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

function Convert-ToValueList {
    param(
        [AllowNull()]
        $Value
    )

    if ($null -eq $Value) {
        return @()
    }

    $values = @()

    foreach ($item in @(Convert-ToFlatArray -Value $Value)) {
        if ($null -eq $item) {
            continue
        }

        if ($item -is [string]) {
            $text = $item.Trim()

            if (-not [string]::IsNullOrWhiteSpace($text)) {
                $values += $text

                foreach ($splitValue in ($text -split '\s*;\s*')) {
                    if (-not [string]::IsNullOrWhiteSpace($splitValue)) {
                        $values += $splitValue.Trim()
                    }
                }

                foreach ($splitValue in ($text -split '\s*\|\s*')) {
                    if (-not [string]::IsNullOrWhiteSpace($splitValue)) {
                        $values += $splitValue.Trim()
                    }
                }
            }
        }
        else {
            $text = [string]$item

            if (-not [string]::IsNullOrWhiteSpace($text)) {
                $values += $text.Trim()
            }
        }
    }

    return @($values | Select-Object -Unique)
}

function Get-CustomValue {
    param(
        $Book,
        [string]$ColumnLabel
    )

    $rawValue = Get-CustomRawValue -Book $Book -ColumnLabel $ColumnLabel

    if ($null -eq $rawValue) {
        return ""
    }

    $values = @(Convert-ToValueList -Value $rawValue)

    if ($values.Count -eq 0) {
        return ""
    }

    return ($values -join "; ")
}

function Test-ExactCustomValue {
    param(
        $Book,

        [Parameter(Mandatory = $true)]
        [string]$ColumnLabel,

        [Parameter(Mandatory = $true)]
        [string]$ExactValue
    )

    $target = Normalize-ComparableValue $ExactValue

    if ([string]::IsNullOrWhiteSpace($target)) {
        return $true
    }

    $rawValue = Get-CustomRawValue -Book $Book -ColumnLabel $ColumnLabel
    $values = @(Convert-ToValueList -Value $rawValue)

    foreach ($value in $values) {
        if ((Normalize-ComparableValue $value) -ieq $target) {
            return $true
        }
    }

    return $false
}

function Get-CalibreIdSelectionSet {
    param(
        [string]$CalibreIds = "",

        [string]$CalibreIdFile = ""
    )

    $idValues = @()

    if (-not [string]::IsNullOrWhiteSpace($CalibreIds)) {
        $idValues += @(
            $CalibreIds -split '[,\s;]+' |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
    }

    if (-not [string]::IsNullOrWhiteSpace($CalibreIdFile)) {
        if (-not (Test-Path $CalibreIdFile)) {
            throw "CalibreIdFile was not found: $CalibreIdFile"
        }

        foreach ($line in (Get-Content -Path $CalibreIdFile)) {
            $cleanLine = (($line -replace '#.*$', '')).Trim()

            if ([string]::IsNullOrWhiteSpace($cleanLine)) {
                continue
            }

            $idValues += @(
                $cleanLine -split '[,\s;]+' |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            )
        }
    }

    $idSet = @{}

    foreach ($idValue in $idValues) {
        $idText = ([string]$idValue).Trim()

        if ([string]::IsNullOrWhiteSpace($idText)) {
            continue
        }

        if ($idText -notmatch '^\d+$') {
            throw "Invalid CalibreId value: $idText. Calibre IDs must be numeric."
        }

        $idSet[$idText] = $true
    }

    return $idSet
}

function Get-CalibreBooksBySearch {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FieldList,

        [string]$Search = ""
    )

    $arguments = @(
        "list",
        "--for-machine",
        "--fields",
        $FieldList
    )

    if (-not [string]::IsNullOrWhiteSpace($Search)) {
        $arguments += @("--search", $Search)
    }

    $result = Invoke-CalibreDb -Arguments $arguments

    if ($result.ExitCode -ne 0) {
        throw "calibredb list failed with exit code $($result.ExitCode): $($result.Output)"
    }

    if ([string]::IsNullOrWhiteSpace($result.Output)) {
        return @()
    }

    try {
        $converted = $result.Output | ConvertFrom-Json
        return @(Convert-ToFlatArray -Value $converted)
    }
    catch {
        throw "Could not parse calibredb JSON output: $($_.Exception.Message)"
    }
}

function Get-CalibreBooksByIdSet {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$IdSet,

        [Parameter(Mandatory = $true)]
        [string]$FieldList
    )

    $books = @()

    foreach ($id in ($IdSet.Keys | Sort-Object {[int]$_})) {
        $records = @(Get-CalibreBooksBySearch -FieldList $FieldList -Search "id:$id")

        if ($records.Count -eq 0) {
            Write-Warning "CalibreId was requested but not found: $id"
            continue
        }

        if ($records.Count -gt 1) {
            throw "CalibreId search returned more than one record for id:$id"
        }

        $books += $records[0]
    }

    return @($books)
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

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if ([string]::IsNullOrWhiteSpace($Search) -and
    [string]::IsNullOrWhiteSpace($CalibreIds) -and
    [string]::IsNullOrWhiteSpace($CalibreIdFile)) {
    throw "Provide a Calibre search string, explicit Calibre IDs, or a Calibre ID file."
}

if ([string]::IsNullOrWhiteSpace($BatchSlug)) {
    throw "BatchSlug is required."
}

if ((Test-Path $OutputCsv) -and -not $Overwrite) {
    throw "OutputCsv already exists: $OutputCsv. Re-run with -Overwrite to replace it."
}

if ((Test-Path $ReportCsv) -and -not $Overwrite) {
    throw "ReportCsv already exists: $ReportCsv. Re-run with -Overwrite to replace it."
}

$fieldList = @(
    "id",
    "title",
    "authors",
    "isbn",
    "publisher",
    "pubdate",
    "identifiers",
    "*award_programs",
    "*mqg_title_author",
    "*mqg_identifiers",
    "*mqg_lcc",
    "*mqg_awards",
    "*mqg_description",
    "*mqg_tags",
    "*mqg_cover",
    "*mqg_metadata_complete",
    "*lcc",
    "*lcc_primary_class",
    "*lcc_secondary_class",
    "*lcc_class_path"
) -join ","

$idSet = Get-CalibreIdSelectionSet -CalibreIds $CalibreIds -CalibreIdFile $CalibreIdFile
$startedAt = Get-Date
$exportedAt = $startedAt.ToString("s")

Write-Host "Creating toolkit batch manifest..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Batch name: $BatchSlug"
Write-Host "Search: $Search"

if ($idSet.Count -gt 0) {
    Write-Host "CalibreId selection count: $($idSet.Count)"
}

if (-not [string]::IsNullOrWhiteSpace($ExactAwardProgram)) {
    Write-Host "Exact Award Programs filter: $ExactAwardProgram"
}

Write-Host "Manifest output: $OutputCsv"
Write-Host "Summary report:  $ReportCsv"

if (-not [string]::IsNullOrWhiteSpace($Search)) {
    $books = @(Get-CalibreBooksBySearch -FieldList $fieldList -Search $Search)
    Write-Host "Books found from Calibre search: $($books.Count)"

    if ($idSet.Count -gt 0) {
        $books = @(
            $books | Where-Object {
                $idSet.ContainsKey(([string]$_.id))
            }
        )

        Write-Host "Books found after CalibreId intersection: $($books.Count)"
    }
}
else {
    $books = @(Get-CalibreBooksByIdSet -IdSet $idSet -FieldList $fieldList)
    Write-Host "Books resolved by CalibreId selection: $($books.Count)"
}

if (-not [string]::IsNullOrWhiteSpace($ExactAwardProgram)) {
    $books = @(
        $books | Where-Object {
            Test-ExactCustomValue `
                -Book $_ `
                -ColumnLabel "award_programs" `
                -ExactValue $ExactAwardProgram
        }
    )

    Write-Host "Books found after exact Award Programs filter: $($books.Count)"
}

if ($books.Count -eq 0) {
    throw "No books matched the batch selection criteria."
}

$duplicateGroups = @($books | Group-Object id | Where-Object { $_.Count -gt 1 })

if ($duplicateGroups.Count -gt 0) {
    $duplicateIds = ($duplicateGroups | ForEach-Object { $_.Name }) -join ", "
    throw "Duplicate Calibre IDs were found in the selected batch: $duplicateIds"
}

$selectionMethodParts = @()

if (-not [string]::IsNullOrWhiteSpace($Search)) {
    $selectionMethodParts += "Search"
}

if (-not [string]::IsNullOrWhiteSpace($CalibreIds)) {
    $selectionMethodParts += "ExplicitIds"
}

if (-not [string]::IsNullOrWhiteSpace($CalibreIdFile)) {
    $selectionMethodParts += "IdFile"
}

if (-not [string]::IsNullOrWhiteSpace($ExactAwardProgram)) {
    $selectionMethodParts += "ExactAwardProgram"
}

$selectionMethod = $selectionMethodParts -join "+"

$manifestRows = foreach ($book in ($books | Sort-Object id)) {
    [pscustomobject]@{
        BatchSlug                 = $BatchSlug
        CalibreId                 = $book.id
        Title                     = $book.title
        Authors                   = Format-Authors $book.authors
        ISBN                      = $book.isbn
        Identifiers               = Join-ArrayValue $book.identifiers
        Publisher                 = $book.publisher
        Published                 = $book.pubdate
        AwardPrograms             = Get-CustomValue -Book $book -ColumnLabel "award_programs"
        LCC                       = Get-CustomValue -Book $book -ColumnLabel "lcc"
        LCCPrimaryClass           = Get-CustomValue -Book $book -ColumnLabel "lcc_primary_class"
        LCCSecondaryClass         = Get-CustomValue -Book $book -ColumnLabel "lcc_secondary_class"
        LCCClassificationPath     = Get-CustomValue -Book $book -ColumnLabel "lcc_class_path"
        MqgTitleAuthor            = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_title_author")
        MqgIdentifiers            = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_identifiers")
        MqgLcc                    = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_lcc")
        MqgAwards                 = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_awards")
        MqgDescription            = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_description")
        MqgTags                   = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_tags")
        MqgCover                  = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_cover")
        MqgMetadataComplete       = Convert-ToYesNo (Get-CustomRawValue -Book $book -ColumnLabel "mqg_metadata_complete")
        SourceSelectionMethod     = $selectionMethod
        SourceSearch              = $Search
        SourceExactAwardProgram   = $ExactAwardProgram
        SourceCalibreIds          = $CalibreIds
        SourceCalibreIdFile       = $CalibreIdFile
        ExportedAt                = $exportedAt
    }
}

$outputFolder = Split-Path -Path $OutputCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$reportFolder = Split-Path -Path $ReportCsv -Parent

if ($reportFolder -and -not (Test-Path $reportFolder)) {
    New-Item -ItemType Directory -Force -Path $reportFolder | Out-Null
}

$manifestRows | Export-Csv -Path $OutputCsv -NoTypeInformation -Encoding UTF8

$missingRequestedIds = @()

if ($idSet.Count -gt 0) {
    $resolvedIdSet = @{}

    foreach ($row in $manifestRows) {
        $resolvedIdSet[([string]$row.CalibreId)] = $true
    }

    foreach ($requestedId in $idSet.Keys) {
        if (-not $resolvedIdSet.ContainsKey(([string]$requestedId))) {
            $missingRequestedIds += $requestedId
        }
    }
}

$summaryRows = @(
    [pscustomobject]@{
        BatchSlug               = $BatchSlug
        SelectionMethod          = $selectionMethod
        SourceSearch             = $Search
        SourceExactAwardProgram  = $ExactAwardProgram
        SourceCalibreIds         = $CalibreIds
        SourceCalibreIdFile      = $CalibreIdFile
        RequestedExplicitIdCount = $idSet.Count
        ManifestRowCount         = $manifestRows.Count
        MissingRequestedIds      = ($missingRequestedIds -join ",")
        OutputCsv                = $OutputCsv
        ExportedAt               = $exportedAt
    }
)

$summaryRows | Export-Csv -Path $ReportCsv -NoTypeInformation -Encoding UTF8

Write-Host "Batch manifest created: $OutputCsv"
Write-Host "Rows exported: $($manifestRows.Count)"
Write-Host "Selection summary written: $ReportCsv"

if ($missingRequestedIds.Count -gt 0) {
    Write-Warning "Some requested IDs were not included in the final manifest: $($missingRequestedIds -join ', ')"
}
