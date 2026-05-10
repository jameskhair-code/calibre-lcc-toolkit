<#
.SYNOPSIS
Exports a read-only identifier inventory from Calibre.

.DESCRIPTION
Reads Calibre metadata using calibredb list --for-machine and inventories identifier
coverage across the library.

This script is read-only and does not modify Calibre metadata.

Outputs:
- Source TSV with one row per book
- Coverage summary CSV
- Identifier type count CSV
- Weird / potentially malformed identifier value CSV

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Export-IdentifierInventory.ps1 `
  -OutputTsv ".\input\identifier-inventory-source.tsv" `
  -CoverageSummaryCsv ".\reports\identifier-coverage-summary.csv" `
  -IdentifierTypeCountsCsv ".\reports\identifier-type-counts.csv" `
  -WeirdValuesCsv ".\reports\identifier-weird-values.csv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$OutputTsv = ".\input\identifier-inventory-source.tsv",

    [string]$CoverageSummaryCsv = ".\reports\identifier-coverage-summary.csv",

    [string]$IdentifierTypeCountsCsv = ".\reports\identifier-type-counts.csv",

    [string]$WeirdValuesCsv = ".\reports\identifier-weird-values.csv",

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
        return ($Authors -join " & ")
    }

    return [string]$Authors
}

function Convert-IdentifierObjectToMap {
    param(
        [AllowNull()]
        $Identifiers
    )

    $map = [ordered]@{}

    if ($null -eq $Identifiers) {
        return $map
    }

    foreach ($property in $Identifiers.PSObject.Properties) {
        $name = ([string]$property.Name).Trim().ToLowerInvariant()
        $value = ([string]$property.Value).Trim()

        if (-not [string]::IsNullOrWhiteSpace($name) -and -not [string]::IsNullOrWhiteSpace($value)) {
            $map[$name] = $value
        }
    }

    return $map
}

function Join-IdentifierMap {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Map
    )

    $parts = @()

    foreach ($key in ($Map.Keys | Sort-Object)) {
        $parts += "$key`:$($Map[$key])"
    }

    return ($parts -join ", ")
}

function Test-LooksLikeIsbn {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    $clean = ($Value -replace '[\s-]', '').ToUpperInvariant()

    return ($clean -match '^(97[89][0-9]{10}|[0-9]{9}[0-9X])$')
}

function Test-WeirdIdentifierValue {
    param(
        [string]$IdentifierType,
        [string]$IdentifierValue
    )

    if ([string]::IsNullOrWhiteSpace($IdentifierType) -or [string]::IsNullOrWhiteSpace($IdentifierValue)) {
        return $true
    }

    if ($IdentifierValue.Length -gt 250) {
        return $true
    }

    if ($IdentifierValue -match '\s{2,}') {
        return $true
    }

    if ($IdentifierValue -match '[<>"]') {
        return $true
    }

    if ($IdentifierType -eq "isbn" -and -not (Test-LooksLikeIsbn -Value $IdentifierValue)) {
        return $true
    }

    if ($IdentifierType -in @("amazon", "asin") -and $IdentifierValue -notmatch '^[A-Z0-9]{10}$') {
        return $true
    }

    if ($IdentifierType -eq "goodreads" -and $IdentifierValue -notmatch '^[0-9]+$') {
        return $true
    }

    return $false
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

Write-Host "Identifier inventory export"
Write-Host "==========================="
Write-Host ""
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Output TSV: $OutputTsv"
Write-Host "Coverage summary CSV: $CoverageSummaryCsv"
Write-Host "Identifier type counts CSV: $IdentifierTypeCountsCsv"
Write-Host "Weird values CSV: $WeirdValuesCsv"
Write-Host ""

$fieldList = @(
    "id",
    "title",
    "authors",
    "isbn",
    "identifiers"
) -join ","

$args = @(
    "list",
    "--for-machine",
    "--fields", $fieldList
)

Write-Host "Reading Calibre metadata..."
$jsonLines = Invoke-CalibreDb -Arguments $args
$jsonText = ($jsonLines -join "`n").Trim()

if ([string]::IsNullOrWhiteSpace($jsonText)) {
    throw "No output returned from calibredb."
}

$converted = $jsonText | ConvertFrom-Json
$books = @(Convert-ToFlatArray -Value $converted)

Write-Host "Books loaded: $($books.Count)"

$inventoryRows = @()
$typeRows = @()
$weirdRows = @()

foreach ($book in $books) {
    $id = [string]$book.id
    $title = [string]$book.title
    $authors = Format-Authors $book.authors
    $isbnColumn = ([string]$book.isbn).Trim()

    $identifierMap = Convert-IdentifierObjectToMap -Identifiers $book.identifiers
    $identifierTypes = @($identifierMap.Keys | Sort-Object)

    $isbnIdentifier = ""
    $amazonIdentifier = ""
    $asinIdentifier = ""
    $goodreadsIdentifier = ""

    if ($identifierMap.Contains("isbn")) {
        $isbnIdentifier = [string]$identifierMap["isbn"]
    }

    if ($identifierMap.Contains("amazon")) {
        $amazonIdentifier = [string]$identifierMap["amazon"]
    }

    if ($identifierMap.Contains("asin")) {
        $asinIdentifier = [string]$identifierMap["asin"]
    }

    if ($identifierMap.Contains("goodreads")) {
        $goodreadsIdentifier = [string]$identifierMap["goodreads"]
    }

    $hasAnyIdentifier = ($identifierTypes.Count -gt 0)
    $hasIsbn = (-not [string]::IsNullOrWhiteSpace($isbnColumn) -or -not [string]::IsNullOrWhiteSpace($isbnIdentifier))
    $hasAmazon = (-not [string]::IsNullOrWhiteSpace($amazonIdentifier) -or -not [string]::IsNullOrWhiteSpace($asinIdentifier))
    $hasGoodreads = (-not [string]::IsNullOrWhiteSpace($goodreadsIdentifier))
    $titleLooksLikeIsbn = Test-LooksLikeIsbn -Value $title

    $inventoryRows += [pscustomobject]@{
        CalibreId             = $id
        Title                 = $title
        Authors               = $authors
        IsbnColumn            = $isbnColumn
        IsbnIdentifier        = $isbnIdentifier
        AmazonIdentifier      = $amazonIdentifier
        AsinIdentifier        = $asinIdentifier
        GoodreadsIdentifier   = $goodreadsIdentifier
        IdentifierTypes       = ($identifierTypes -join "; ")
        IdentifierCount       = $identifierTypes.Count
        IdentifiersRaw        = Join-IdentifierMap -Map $identifierMap
        HasAnyIdentifier      = if ($hasAnyIdentifier) { "Yes" } else { "No" }
        HasIsbn               = if ($hasIsbn) { "Yes" } else { "No" }
        HasAmazon             = if ($hasAmazon) { "Yes" } else { "No" }
        HasGoodreads          = if ($hasGoodreads) { "Yes" } else { "No" }
        TitleLooksLikeIsbn    = if ($titleLooksLikeIsbn) { "Yes" } else { "No" }
        IdentifierIssueHint   = ""
    }

    foreach ($key in $identifierTypes) {
        $value = [string]$identifierMap[$key]

        $typeRows += [pscustomobject]@{
            IdentifierType  = $key
            CalibreId       = $id
            Title           = $title
            Authors         = $authors
            IdentifierValue = $value
        }

        if (Test-WeirdIdentifierValue -IdentifierType $key -IdentifierValue $value) {
            $weirdRows += [pscustomobject]@{
                CalibreId        = $id
                Title            = $title
                Authors          = $authors
                IdentifierType   = $key
                IdentifierValue  = $value
                IssueHint        = "Potentially malformed or unusual identifier value"
            }
        }
    }

    if ($titleLooksLikeIsbn) {
        $weirdRows += [pscustomobject]@{
            CalibreId        = $id
            Title            = $title
            Authors          = $authors
            IdentifierType   = "title"
            IdentifierValue  = $title
            IssueHint        = "Title appears to be an ISBN"
        }
    }

    if (-not $hasAnyIdentifier) {
        $weirdRows += [pscustomobject]@{
            CalibreId        = $id
            Title            = $title
            Authors          = $authors
            IdentifierType   = ""
            IdentifierValue  = ""
            IssueHint        = "No identifiers present"
        }
    }
}

$typeCounts = @(
    $typeRows |
        Group-Object IdentifierType |
        Sort-Object -Property @{ Expression = "Count"; Descending = $true }, @{ Expression = "Name"; Ascending = $true } |
        ForEach-Object {
            [pscustomobject]@{
                IdentifierType = $_.Name
                Count          = $_.Count
            }
        }
)

$totalBooks = $inventoryRows.Count

$coverageRows = @(
    [pscustomobject]@{ Metric = "TotalBooks"; Count = $totalBooks },
    [pscustomobject]@{ Metric = "BooksWithAnyIdentifier"; Count = @($inventoryRows | Where-Object { $_.HasAnyIdentifier -eq "Yes" }).Count },
    [pscustomobject]@{ Metric = "BooksWithNoIdentifiers"; Count = @($inventoryRows | Where-Object { $_.HasAnyIdentifier -ne "Yes" }).Count },
    [pscustomobject]@{ Metric = "BooksWithIsbn"; Count = @($inventoryRows | Where-Object { $_.HasIsbn -eq "Yes" }).Count },
    [pscustomobject]@{ Metric = "BooksWithAmazonOrAsin"; Count = @($inventoryRows | Where-Object { $_.HasAmazon -eq "Yes" }).Count },
    [pscustomobject]@{ Metric = "BooksWithGoodreads"; Count = @($inventoryRows | Where-Object { $_.HasGoodreads -eq "Yes" }).Count },
    [pscustomobject]@{ Metric = "BooksWithTitleThatLooksLikeIsbn"; Count = @($inventoryRows | Where-Object { $_.TitleLooksLikeIsbn -eq "Yes" }).Count },
    [pscustomobject]@{ Metric = "PotentialWeirdIdentifierRows"; Count = $weirdRows.Count }
)

$outputFolders = @(
    (Split-Path -Path $OutputTsv -Parent),
    (Split-Path -Path $CoverageSummaryCsv -Parent),
    (Split-Path -Path $IdentifierTypeCountsCsv -Parent),
    (Split-Path -Path $WeirdValuesCsv -Parent)
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

foreach ($folder in $outputFolders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

$inventoryRows | Export-Csv -Path $OutputTsv -Delimiter "`t" -NoTypeInformation -Encoding UTF8
$coverageRows | Export-Csv -Path $CoverageSummaryCsv -NoTypeInformation -Encoding UTF8
$typeCounts | Export-Csv -Path $IdentifierTypeCountsCsv -NoTypeInformation -Encoding UTF8
$weirdRows | Export-Csv -Path $WeirdValuesCsv -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "Identifier inventory complete."
Write-Host "Rows exported: $($inventoryRows.Count)"
Write-Host "Identifier types found: $($typeCounts.Count)"
Write-Host "Potential weird rows: $($weirdRows.Count)"
Write-Host ""
Write-Host "Files written:"
Write-Host "  $OutputTsv"
Write-Host "  $CoverageSummaryCsv"
Write-Host "  $IdentifierTypeCountsCsv"
Write-Host "  $WeirdValuesCsv"

