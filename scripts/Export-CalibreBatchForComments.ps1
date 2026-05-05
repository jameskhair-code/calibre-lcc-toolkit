<#
.SYNOPSIS
Exports a Calibre batch to TSV for structured comments generation.

.DESCRIPTION
Uses calibredb list --for-machine to export selected records from Calibre into a TSV
for the v0.6 Comments module.

This script is read-only and does not modify Calibre metadata.

The output TSV includes current book metadata, existing comments information, existing comments
hash/length/preview, and blank workflow columns for proposed comments.

Supports an optional exact local Award Programs filter. This is useful because Calibre search
syntax can overmatch award fields when using broad text matching.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Export-CalibreBatchForComments.ps1 `
  -Search '#award_programs:"AHA - J. Russell Major Prize"' `
  -ExactAwardProgram "AHA - J. Russell Major Prize" `
  -OutputTsv ".\input\comments-source-j-russell-major-prize.tsv"
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$Search = "",

    [string]$ExactAwardProgram = "",

    [string]$OutputTsv = ".\input\comments-source-batch.tsv",

    [string]$DefaultCommentsTemplateProfile = "",

    [string]$DefaultCommentsMode = "Replace",

    [int]$ExistingCommentsPreviewLength = 500,

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

function Convert-ToSingleLine {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrEmpty($Value)) {
        return ""
    }

    return (($Value -replace "`r", " ") -replace "`n", " ") -replace "`t", " "
}

function Convert-HtmlToPlainText {
    param(
        [AllowNull()]
        [string]$Html
    )

    if ([string]::IsNullOrWhiteSpace($Html)) {
        return ""
    }

    $text = $Html

    $text = $text -replace '(?is)<script.*?</script>', ' '
    $text = $text -replace '(?is)<style.*?</style>', ' '
    $text = $text -replace '(?is)<br\s*/?>', ' '
    $text = $text -replace '(?is)</p>', ' '
    $text = $text -replace '(?is)</li>', ' '
    $text = $text -replace '(?is)<.*?>', ' '

    try {
        $text = [System.Net.WebUtility]::HtmlDecode($text)
    }
    catch {
        # If HtmlDecode is unavailable for any reason, continue with the stripped text.
    }

    return (($text.Trim()) -replace '\s+', ' ')
}

function Get-TextPreview {
    param(
        [AllowNull()]
        [string]$Text,

        [int]$MaxLength = 500
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    $clean = (($Text.Trim()) -replace '\s+', ' ')

    if ($clean.Length -le $MaxLength) {
        return $clean
    }

    return $clean.Substring(0, $MaxLength) + "..."
}

function Get-Sha256Hash {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ($null -eq $Value) {
        $Value = ""
    }

    $sha256 = [System.Security.Cryptography.SHA256]::Create()

    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hashBytes = $sha256.ComputeHash($bytes)

        return (($hashBytes | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
    }
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if ($ExistingCommentsPreviewLength -lt 100) {
    throw "ExistingCommentsPreviewLength must be at least 100 characters."
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
    "comments",
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

Write-Host "Running calibredb export for comments generation..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
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

$exportRows = foreach ($book in ($books | Sort-Object id)) {
    $authorsText = Format-Authors $book.authors
    $existingComments = [string]$book.comments
    $existingCommentsSingleLine = Convert-ToSingleLine -Value $existingComments
    $existingCommentsPlainText = Convert-HtmlToPlainText -Html $existingComments
    $existingCommentsPreview = Get-TextPreview -Text $existingCommentsPlainText -MaxLength $ExistingCommentsPreviewLength
    $existingCommentsHash = Get-Sha256Hash -Value $existingComments

    [pscustomobject]@{
        CalibreId                        = $book.id
        Title                            = $book.title
        Authors                          = $authorsText

        ProposedComments                 = ""
        CommentsTemplateProfile          = $DefaultCommentsTemplateProfile
        CommentsMode                     = $DefaultCommentsMode
        ChangeReason                     = ""
        Confidence                       = ""
        ManualReviewRequired             = ""
        SourceNotes                      = ""

        ExistingCommentsHash             = $existingCommentsHash
        ExistingCommentsLength           = $existingComments.Length
        ExistingCommentsTextPreview      = $existingCommentsPreview
        ExistingComments                 = $existingCommentsSingleLine

        ISBN                             = $book.isbn
        Identifiers                      = Format-Identifiers $book.identifiers
        Publisher                        = $book.publisher
        Published                        = $book.pubdate
        Series                           = $book.series
        SeriesIndex                      = $book.series_index
        Tags                             = Format-ValueList $book.tags

        "Award Programs"                 = Get-CustomValue -Book $book -ColumnLabel "award_programs"
        "MQG LCC"                        = Get-CustomValue -Book $book -ColumnLabel "mqg_lcc"
        "Existing LCC"                   = Get-CustomValue -Book $book -ColumnLabel "lcc"
        "Existing LCC Primary Class"     = Get-CustomValue -Book $book -ColumnLabel "lcc_primary_class"
        "Existing LCC Secondary Class"   = Get-CustomValue -Book $book -ColumnLabel "lcc_secondary_class"
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
Write-Host ""
Write-Host "Next step: copy this TSV to a comments import TSV, fill ProposedComments and review fields, then run the future comments dry-run script."