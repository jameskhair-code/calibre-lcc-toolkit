<#
.SYNOPSIS
Exports a Calibre batch to TSV for LCC lookup/enrichment.

.DESCRIPTION
Uses calibredb list --for-machine to export selected fields from Calibre into a clean TSV.
This is read-only and does not modify Calibre metadata.

Supports an optional exact local Award Programs filter. This is useful because Calibre
search syntax can overmatch award fields when using broad text matching.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForLcc.ps1 `
  -Search '#award_programs:"AHA - J. Russell Major Prize" and #mqg_lcc:false' `
  -ExactAwardProgram "AHA - J. Russell Major Prize" `
  -OutputTsv ".\input\lcc-source-j-russell-major-prize.tsv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$Search = "",

    [string]$ExactAwardProgram = "",

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

    & $CalibreDb @allArgs
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

                # Some Calibre custom fields may serialize multiple values as delimited text.
                # These splits are intentionally conservative for award/filter matching.
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
    "*award_programs",
    "*mqg_lcc",
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

if (-not [string]::IsNullOrWhiteSpace($ExactAwardProgram)) {
    Write-Host "Exact Award Programs filter: $ExactAwardProgram"
}

Write-Host "Output: $OutputTsv"

$jsonLines = Invoke-CalibreDb -Arguments $args
$jsonText = ($jsonLines -join "`n").Trim()

if ([string]::IsNullOrWhiteSpace($jsonText)) {
    throw "No output returned from calibredb."
}

$converted = $jsonText | ConvertFrom-Json
$books = @(Convert-ToFlatArray -Value $converted)

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
    throw "No books matched the export criteria. Check the Calibre search string and/or exact Award Programs filter."
}

$exportRows = foreach ($book in $books) {
    [pscustomobject]@{
        CalibreId                          = $book.id
        Title                              = $book.title
        "Author(s)"                        = Format-Authors $book.authors
        ISBN                               = $book.isbn
        Publisher                          = $book.publisher
        Published                          = $book.pubdate
        "Award Programs"                   = Get-CustomValue -Book $book -ColumnLabel "award_programs"
        "MQG LCC"                          = Get-CustomValue -Book $book -ColumnLabel "mqg_lcc"
        "Existing LCC"                     = Get-CustomValue -Book $book -ColumnLabel "lcc"
        "Existing LCC Primary Class"       = Get-CustomValue -Book $book -ColumnLabel "lcc_primary_class"
        "Existing LCC Secondary Class"     = Get-CustomValue -Book $book -ColumnLabel "lcc_secondary_class"
        "Existing LCC Classification Path" = Get-CustomValue -Book $book -ColumnLabel "lcc_class_path"
    }
}

$outputFolder = Split-Path -Path $OutputTsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$exportRows | Export-Csv -Path $OutputTsv -Delimiter "`t" -NoTypeInformation -Encoding UTF8

Write-Host "Export complete: $OutputTsv"
Write-Host "Rows exported: $($exportRows.Count)"