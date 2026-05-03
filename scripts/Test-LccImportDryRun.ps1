<#
.SYNOPSIS
Dry-run checker for importing LCC metadata into Calibre.

.DESCRIPTION
Reads a TSV containing Title, Author/Author(s), ISBN, LCC, LCC Primary Class,
LCC Secondary Class, and LCC Classification Path.

Searches the Calibre library by ISBN.
Reports what would be updated.
Performs NO metadata writes.

This script intentionally does not call calibredb set_custom or modify metadata.
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$InputTsv = ".\input\lcc-import-smoketest.tsv",

    [string]$ReportCsv = ".\reports\lcc-dryrun-report.csv",

    [string]$CalibreDb = "C:\Program Files\Calibre2\calibredb.exe",

    [string]$LccColumn = "lcc",

    [string]$LccPathColumn = "lcc_class_path",

    [string]$LccPrimaryClassColumn = "lcc_primary_class",

    [string]$LccSecondaryClassColumn = "lcc_secondary_class"
)

function Normalize-Isbn {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return (($Value -replace '[^\dXx]', '').Trim()).ToUpper()
}

function Get-RowValue {
    param(
        [Parameter(Mandatory = $true)]
        $Row,

        [Parameter(Mandatory = $true)]
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $prop = $Row.PSObject.Properties[$name]
        if ($null -ne $prop) {
            return [string]$prop.Value
        }
    }

    return ""
}

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
        [Parameter(Mandatory = $true)]
        $Book,

        [Parameter(Mandatory = $true)]
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

function Test-WouldUpdate {
    param(
        [string]$ExistingValue,
        [string]$ProposedValue
    )

    if (
        -not [string]::IsNullOrWhiteSpace($ProposedValue) -and
        $ExistingValue -ne $ProposedValue
    ) {
        return "Yes"
    }

    return "No"
}

function Get-CalibreMatchesByIsbn {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Isbn
    )

    $query = "isbn:$Isbn"

    $fieldList = @(
        "id",
        "title",
        "authors",
        "isbn",
        "identifiers",
        "*$LccColumn",
        "*$LccPathColumn",
        "*$LccPrimaryClassColumn",
        "*$LccSecondaryClassColumn"
    ) -join ","

    $jsonLines = Invoke-CalibreDb -Arguments @(
        "list",
        "--for-machine",
        "--fields", $fieldList,
        "--search", $query
    )

    $jsonText = ($jsonLines -join "`n").Trim()

    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        return [pscustomobject]@{
            Query   = $query
            Matches = @()
        }
    }

    $converted = $jsonText | ConvertFrom-Json
    $matches = @(Convert-ToFlatArray -Value $converted)

    return [pscustomobject]@{
        Query   = $query
        Matches = $matches
    }
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not [string]::IsNullOrWhiteSpace($LibraryPath) -and -not (Test-Path $LibraryPath)) {
    throw "Library path was not found: $LibraryPath"
}

if (-not (Test-Path $InputTsv)) {
    throw "Input TSV was not found: $InputTsv"
}

$reportFolder = Split-Path -Path $ReportCsv -Parent
if ($reportFolder -and -not (Test-Path $reportFolder)) {
    New-Item -ItemType Directory -Force -Path $reportFolder | Out-Null
}

$rows = Import-Csv -Path $InputTsv -Delimiter "`t"

$report = foreach ($row in $rows) {
    $inputTitle = Get-RowValue -Row $row -Names @("Title")
    $inputAuthor = Get-RowValue -Row $row -Names @("Author", "Author(s)", "Authors")
    $isbn = Normalize-Isbn (Get-RowValue -Row $row -Names @("ISBN", "Isbn", "isbn"))

    $proposedLcc = Get-RowValue -Row $row -Names @("LCC", "Lcc", "lcc")
    $proposedPrimaryClass = Get-RowValue -Row $row -Names @("LCC Primary Class", "LCC Primary", "lcc_primary_class")
    $proposedSecondaryClass = Get-RowValue -Row $row -Names @("LCC Secondary Class", "LCC Secondary", "lcc_secondary_class")
    $proposedPath = Get-RowValue -Row $row -Names @("LCC Classification Path", "LCC Path", "lcc_class_path")

    if ([string]::IsNullOrWhiteSpace($isbn)) {
        [pscustomobject]@{
            InputTitle                    = $inputTitle
            InputAuthor                   = $inputAuthor
            ISBN                          = ""
            MatchStatus                   = "Skipped - missing ISBN"
            SearchQuery                   = ""
            CalibreId                     = ""
            CalibreTitle                  = ""
            CalibreAuthors                = ""

            ExistingLCC                   = ""
            ProposedLCC                   = $proposedLcc
            WouldUpdateLCC                = "No"

            ExistingLCCPrimaryClass       = ""
            ProposedLCCPrimaryClass       = $proposedPrimaryClass
            WouldUpdateLCCPrimaryClass    = "No"

            ExistingLCCSecondaryClass     = ""
            ProposedLCCSecondaryClass     = $proposedSecondaryClass
            WouldUpdateLCCSecondaryClass  = "No"

            ExistingLCCPath               = ""
            ProposedLCCPath               = $proposedPath
            WouldUpdateLCCPath            = "No"

            Warning                       = "No ISBN provided"
        }
        continue
    }

    $result = Get-CalibreMatchesByIsbn -Isbn $isbn
    $matches = @(Convert-ToFlatArray -Value $result.Matches)

    if ($matches.Count -eq 0) {
        [pscustomobject]@{
            InputTitle                    = $inputTitle
            InputAuthor                   = $inputAuthor
            ISBN                          = $isbn
            MatchStatus                   = "No match"
            SearchQuery                   = $result.Query
            CalibreId                     = ""
            CalibreTitle                  = ""
            CalibreAuthors                = ""

            ExistingLCC                   = ""
            ProposedLCC                   = $proposedLcc
            WouldUpdateLCC                = "No"

            ExistingLCCPrimaryClass       = ""
            ProposedLCCPrimaryClass       = $proposedPrimaryClass
            WouldUpdateLCCPrimaryClass    = "No"

            ExistingLCCSecondaryClass     = ""
            ProposedLCCSecondaryClass     = $proposedSecondaryClass
            WouldUpdateLCCSecondaryClass  = "No"

            ExistingLCCPath               = ""
            ProposedLCCPath               = $proposedPath
            WouldUpdateLCCPath            = "No"

            Warning                       = "No Calibre book matched this ISBN"
        }
        continue
    }

    if ($matches.Count -gt 1) {
        [pscustomobject]@{
            InputTitle                    = $inputTitle
            InputAuthor                   = $inputAuthor
            ISBN                          = $isbn
            MatchStatus                   = "Multiple matches - skipped"
            SearchQuery                   = $result.Query
            CalibreId                     = ($matches.id -join ", ")
            CalibreTitle                  = ($matches.title -join " | ")
            CalibreAuthors                = (($matches.authors) -join " | ")

            ExistingLCC                   = ""
            ProposedLCC                   = $proposedLcc
            WouldUpdateLCC                = "No"

            ExistingLCCPrimaryClass       = ""
            ProposedLCCPrimaryClass       = $proposedPrimaryClass
            WouldUpdateLCCPrimaryClass    = "No"

            ExistingLCCSecondaryClass     = ""
            ProposedLCCSecondaryClass     = $proposedSecondaryClass
            WouldUpdateLCCSecondaryClass  = "No"

            ExistingLCCPath               = ""
            ProposedLCCPath               = $proposedPath
            WouldUpdateLCCPath            = "No"

            Warning                       = "Multiple Calibre books matched this ISBN; manual review needed"
        }
        continue
    }

    $book = $matches[0]

    $existingLcc = Get-CustomValue -Book $book -ColumnLabel $LccColumn
    $existingPath = Get-CustomValue -Book $book -ColumnLabel $LccPathColumn
    $existingPrimaryClass = Get-CustomValue -Book $book -ColumnLabel $LccPrimaryClassColumn
    $existingSecondaryClass = Get-CustomValue -Book $book -ColumnLabel $LccSecondaryClassColumn

    [pscustomobject]@{
        InputTitle                    = $inputTitle
        InputAuthor                   = $inputAuthor
        ISBN                          = $isbn
        MatchStatus                   = "Matched"
        SearchQuery                   = $result.Query
        CalibreId                     = $book.id
        CalibreTitle                  = $book.title
        CalibreAuthors                = (($book.authors) -join "; ")

        ExistingLCC                   = $existingLcc
        ProposedLCC                   = $proposedLcc
        WouldUpdateLCC                = Test-WouldUpdate -ExistingValue $existingLcc -ProposedValue $proposedLcc

        ExistingLCCPrimaryClass       = $existingPrimaryClass
        ProposedLCCPrimaryClass       = $proposedPrimaryClass
        WouldUpdateLCCPrimaryClass    = Test-WouldUpdate -ExistingValue $existingPrimaryClass -ProposedValue $proposedPrimaryClass

        ExistingLCCSecondaryClass     = $existingSecondaryClass
        ProposedLCCSecondaryClass     = $proposedSecondaryClass
        WouldUpdateLCCSecondaryClass  = Test-WouldUpdate -ExistingValue $existingSecondaryClass -ProposedValue $proposedSecondaryClass

        ExistingLCCPath               = $existingPath
        ProposedLCCPath               = $proposedPath
        WouldUpdateLCCPath            = Test-WouldUpdate -ExistingValue $existingPath -ProposedValue $proposedPath

        Warning                       = ""
    }
}

$report | Export-Csv -Path $ReportCsv -NoTypeInformation -Encoding UTF8
$report | Format-Table -AutoSize

Write-Host ""
Write-Host "Dry-run complete. Report written to: $ReportCsv"
Write-Host "No Calibre metadata was changed."