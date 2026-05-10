<#
.SYNOPSIS
Exports a Calibre batch to TSV for author/title cleanup review.

.DESCRIPTION
Uses calibredb list --for-machine to export selected records from Calibre into a clean TSV.

This script is read-only and does not modify Calibre metadata.

The output TSV is designed as a starter review file for the Author / Title Cleanup workflow.
It includes current title/author values as OriginalTitle and OriginalAuthors, blank ProposedTitle
and ProposedAuthors columns, and supporting context fields for human review.

Supports batch selection by:
- Calibre search string
- explicit comma-separated Calibre IDs
- stable toolkit batch manifest CSV with a CalibreId column

Supports an optional exact local Award Programs filter. This is useful because Calibre search syntax
can overmatch award fields when using broad text matching.

Selection behavior:
- Search only: exports all records matching the search.
- BatchManifest / CalibreIds only: resolves those IDs directly.
- Search plus BatchManifest / CalibreIds: applies the ID list as a local filter/intersection against
  the search result.
- ExactAwardProgram: optional local exact-match filter for Award Programs.

.EXAMPLE
pwsh -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForAuthorTitleCleanup.ps1 `
  -Search '#award_programs:"AHA - J. Russell Major Prize"' `
  -ExactAwardProgram "AHA - J. Russell Major Prize" `
  -OutputTsv ".\input\author-title-cleanup-source-j-russell-major-prize.tsv"

.EXAMPLE
pwsh -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForAuthorTitleCleanup.ps1 `
  -BatchManifest ".\input\batch-search-smoketest.csv" `
  -OutputTsv ".\input\author-title-cleanup-source-search-smoketest.tsv"

.EXAMPLE
pwsh -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForAuthorTitleCleanup.ps1 `
  -CalibreIds "5374,5375,5376" `
  -OutputTsv ".\input\author-title-cleanup-source-leo-gershoy-smoketest.tsv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$Search = "",

    [string]$ExactAwardProgram = "",

    [string]$CalibreIds = "",

    [string]$BatchManifest = "",

    [string]$OutputTsv = ".\input\author-title-cleanup-source-batch.tsv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe"
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

function Format-ValueList {
    param(
        [AllowNull()]
        $Value
    )

    $values = @(Convert-ToValueList -Value $Value)

    if ($values.Count -eq 0) {
        return ""
    }

    return ($values -join "; ")
}

function Format-IdentifierValue {
    param(
        [AllowNull()]
        $Value
    )

    if ($null -eq $Value) {
        return ""
    }

    if ($Value -is [System.Array]) {
        $parts = @()

        foreach ($item in $Value) {
            $text = Format-IdentifierValue -Value $item

            if (-not [string]::IsNullOrWhiteSpace($text)) {
                $parts += $text
            }
        }

        return ($parts -join ", ")
    }

    return ([string]$Value).Trim()
}

function Format-Identifiers {
    param(
        [AllowNull()]
        $Identifiers
    )

    if ($null -eq $Identifiers) {
        return ""
    }

    if ($Identifiers -is [string]) {
        return $Identifiers.Trim()
    }

    $properties = $Identifiers.PSObject.Properties

    if ($null -eq $properties -or $properties.Count -eq 0) {
        return ([string]$Identifiers).Trim()
    }

    $pairs = @()

    foreach ($property in ($properties | Sort-Object Name)) {
        $valueText = Format-IdentifierValue -Value $property.Value

        if (-not [string]::IsNullOrWhiteSpace($valueText)) {
            $pairs += "$($property.Name):$valueText"
        }
    }

    return ($pairs -join "; ")
}

function Add-CalibreIdToSet {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$IdSet,

        [Parameter(Mandatory = $true)]
        [string]$IdValue,

        [string]$SourceLabel = "CalibreId"
    )

    $idText = ([string]$IdValue).Trim()

    if ([string]::IsNullOrWhiteSpace($idText)) {
        return
    }

    if ($idText -notmatch '^\d+$') {
        throw "Invalid $SourceLabel value: $idText. Calibre IDs must be numeric."
    }

    $IdSet[$idText] = $true
}

function Get-CalibreIdSelectionSet {
    param(
        [string]$CalibreIds = "",

        [string]$BatchManifest = ""
    )

    $idSet = @{}

    if (-not [string]::IsNullOrWhiteSpace($CalibreIds)) {
        foreach ($idValue in ($CalibreIds -split '[,\s;]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
            Add-CalibreIdToSet -IdSet $idSet -IdValue $idValue -SourceLabel "CalibreIds"
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($BatchManifest)) {
        if (-not (Test-Path $BatchManifest)) {
            throw "BatchManifest was not found: $BatchManifest"
        }

        $manifestRows = @(Import-Csv -Path $BatchManifest)

        if ($manifestRows.Count -eq 0) {
            throw "BatchManifest contained no rows: $BatchManifest"
        }

        $firstRow = $manifestRows | Select-Object -First 1
        $hasCalibreIdColumn = $false

        foreach ($property in $firstRow.PSObject.Properties) {
            if ($property.Name -eq "CalibreId") {
                $hasCalibreIdColumn = $true
                break
            }
        }

        if (-not $hasCalibreIdColumn) {
            throw "BatchManifest must contain a CalibreId column: $BatchManifest"
        }

        foreach ($row in $manifestRows) {
            Add-CalibreIdToSet -IdSet $idSet -IdValue $row.CalibreId -SourceLabel "BatchManifest CalibreId"
        }
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

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if ([string]::IsNullOrWhiteSpace($Search) -and
    [string]::IsNullOrWhiteSpace($CalibreIds) -and
    [string]::IsNullOrWhiteSpace($BatchManifest)) {
    throw "Provide a Calibre search string, explicit Calibre IDs, or a BatchManifest path."
}

$fieldList = @(
    "id",
    "title",
    "authors",
    "isbn",
    "publisher",
    "pubdate",
    "identifiers",
    "series",
    "series_index",
    "tags",
    "*award_programs",
    "*mqg_lcc",
    "*lcc"
) -join ","

$idSet = Get-CalibreIdSelectionSet -CalibreIds $CalibreIds -BatchManifest $BatchManifest

Write-Host "Running calibredb export for author/title cleanup..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Search: $Search"

if (-not [string]::IsNullOrWhiteSpace($BatchManifest)) {
    Write-Host "Batch manifest: $BatchManifest"
}

if ($idSet.Count -gt 0) {
    Write-Host "CalibreId selection count: $($idSet.Count)"
}

if (-not [string]::IsNullOrWhiteSpace($ExactAwardProgram)) {
    Write-Host "Exact Award Programs filter: $ExactAwardProgram"
}

Write-Host "Output: $OutputTsv"

if (-not [string]::IsNullOrWhiteSpace($Search)) {
    $books = @(Get-CalibreBooksBySearch -FieldList $fieldList -Search $Search)
    Write-Host "Books found from Calibre search: $($books.Count)"

    if ($idSet.Count -gt 0) {
        $books = @(
            $books | Where-Object {
                $idSet.ContainsKey(([string]$_.id).Trim())
            }
        )

        Write-Host "Books found after CalibreId intersection: $($books.Count)"
    }
}
else {
    $books = @(Get-CalibreBooksByIdSet -IdSet $idSet -FieldList $fieldList)
    Write-Host "Books resolved by CalibreId selection: $($books.Count)"
}

Write-Host "Books found before local filters: $($books.Count)"

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
    throw "No books matched the export criteria. Check the Calibre search string, batch manifest, explicit IDs, and/or exact Award Programs filter."
}

$duplicateGroups = @($books | Group-Object id | Where-Object { $_.Count -gt 1 })

if ($duplicateGroups.Count -gt 0) {
    $duplicateIds = ($duplicateGroups | ForEach-Object { $_.Name }) -join ", "
    throw "Duplicate Calibre IDs were found in the selected batch: $duplicateIds"
}

$exportRows = foreach ($book in ($books | Sort-Object id)) {
    $authorsText = Format-Authors $book.authors

    [pscustomobject]@{
        CalibreId              = $book.id
        OriginalTitle          = $book.title
        ProposedTitle          = ""
        OriginalAuthors        = $authorsText
        ProposedAuthors        = ""
        ChangeReason           = ""
        Confidence             = ""
        ManualReviewRequired   = ""
        ISBN                   = $book.isbn
        Identifiers            = Format-Identifiers $book.identifiers
        Publisher              = $book.publisher
        Published              = $book.pubdate
        Series                 = $book.series
        SeriesIndex            = $book.series_index
        Tags                   = Format-ValueList $book.tags
        "Award Programs"       = Get-CustomValue -Book $book -ColumnLabel "award_programs"
        "MQG LCC"              = Get-CustomValue -Book $book -ColumnLabel "mqg_lcc"
        "Existing LCC"         = Get-CustomValue -Book $book -ColumnLabel "lcc"
    }
}

$outputFolder = Split-Path -Path $OutputTsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$exportRows | Export-Csv -Path $OutputTsv -Delimiter "`t" -NoTypeInformation -Encoding UTF8

Write-Host "Export complete: $OutputTsv"
Write-Host "Rows exported: $($exportRows.Count)"

