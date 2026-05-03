<#
.SYNOPSIS
Exports a Calibre batch to TSV for LCC lookup/enrichment.

.DESCRIPTION
Uses calibredb list --for-machine to export selected fields from Calibre into a clean TSV.

This script is read-only and does not modify Calibre metadata.
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$Search = "",

    [string]$OutputTsv = ".\input\lcc-source-batch.tsv",

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

    & $CalibreDb @allArgs
}

function Get-CustomValue {
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

    if ($null -eq $property -or $null -eq $property.Value) {
        return ""
    }

    return [string]$property.Value
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

$fieldList = @(
    "id",
    "title",
    "authors",
    "isbn",
    "publisher",
    "pubdate",
    "identifiers",
    "*lcc",
    "*lcc_primary_class",
    "*lcc_secondary_class",
    "*lcc_class_path"
) -join ","

$args = @(
    "list",
    "--for-machine",
    "--fields", $fieldList
)

if (-not [string]::IsNullOrWhiteSpace($Search)) {
    $args += @("--search", $Search)
}

Write-Host "Running calibredb export..."
Write-Host "Search: $Search"
Write-Host "Output: $OutputTsv"

$jsonLines = Invoke-CalibreDb -Arguments $args
$jsonText = ($jsonLines -join "`n").Trim()

if ([string]::IsNullOrWhiteSpace($jsonText)) {
    throw "No output returned from calibredb."
}

$converted = $jsonText | ConvertFrom-Json
$books = @(Convert-ToFlatArray -Value $converted)

Write-Host "Books found: $($books.Count)"

$exportRows = @(
foreach ($book in $books) {
    [pscustomobject]@{
        CalibreId                          = $book.id
        Title                              = $book.title
        "Author(s)"                        = Format-Authors $book.authors
        ISBN                               = $book.isbn
        Publisher                          = $book.publisher
        Published                          = $book.pubdate
        "Existing LCC"                     = Get-CustomValue -Book $book -ColumnLabel "lcc"
        "Existing LCC Primary Class"       = Get-CustomValue -Book $book -ColumnLabel "lcc_primary_class"
        "Existing LCC Secondary Class"     = Get-CustomValue -Book $book -ColumnLabel "lcc_secondary_class"
        "Existing LCC Classification Path" = Get-CustomValue -Book $book -ColumnLabel "lcc_class_path"
    }
}
)

$outputFolder = Split-Path -Path $OutputTsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$exportRows | Export-Csv -Path $OutputTsv -Delimiter "`t" -NoTypeInformation -Encoding UTF8

Write-Host "Export complete: $OutputTsv"
Write-Host "Rows exported: $($exportRows.Count)"