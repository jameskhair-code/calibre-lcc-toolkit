<#
.SYNOPSIS
Verifies applied Calibre comments metadata against a comments apply report.

.DESCRIPTION
Reads the CSV produced by Invoke-CommentsApply.ps1, reads current Calibre metadata,
and verifies whether the current comments hash matches the expected final comments hash.

This script is read-only and does not modify Calibre metadata.

Recommended workflow:
Export -> Generate Proposed Comments -> Dry Run -> Summary -> HTML Review -> Apply -> Verify
#>

[CmdletBinding()]
param(
    [string]$LibraryPath = "",

    [string]$ApplyReportCsv = ".\reports\comments-apply-batch.csv",

    [string]$VerifyReportCsv = ".\reports\comments-verify-batch.csv",

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

function Get-FieldValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Row,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $property = $Row.PSObject.Properties |
        Where-Object { $_.Name -eq $Name } |
        Select-Object -First 1

    if ($null -eq $property) {
        return ""
    }

    return [string]$property.Value
}

function Test-RequiredColumns {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string[]]$RequiredColumns,

        [Parameter(Mandatory = $true)]
        [string]$SourceName
    )

    if ($Rows.Count -eq 0) {
        throw "$SourceName has no data rows."
    }

    $availableColumns = @($Rows[0].PSObject.Properties.Name)

    $missingColumns = @(
        $RequiredColumns | Where-Object {
            $_ -notin $availableColumns
        }
    )

    if ($missingColumns.Count -gt 0) {
        throw "$SourceName is missing required column(s): $($missingColumns -join ', ')"
    }
}

if (-not (Test-Path $CalibreDb)) {
    throw "calibredb.exe was not found at: $CalibreDb"
}

if (-not (Test-Path $ApplyReportCsv)) {
    throw "Apply report CSV was not found: $ApplyReportCsv"
}

Write-Host "Running comments apply verification..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Apply report CSV: $ApplyReportCsv"
Write-Host "Verify report CSV: $VerifyReportCsv"

$applyRows = @(Import-Csv -Path $ApplyReportCsv)

$requiredColumns = @(
    "CalibreId",
    "Title",
    "Authors",
    "CommentsMode",
    "ExpectedFinalCommentsHash",
    "FinalCommentsLength",
    "ApplyStatus"
)

Test-RequiredColumns -Rows $applyRows -RequiredColumns $requiredColumns -SourceName "Apply report CSV"

$fieldList = @(
    "id",
    "title",
    "authors",
    "comments"
) -join ","

$args = @(
    "list",
    "--for-machine",
    "--fields", $fieldList
)

Write-Host "Reading current Calibre title/author/comments metadata..."

$jsonLines = Invoke-CalibreDb -Arguments $args
$jsonText = ($jsonLines -join "`n").Trim()

if ([string]::IsNullOrWhiteSpace($jsonText)) {
    throw "No output returned from calibredb."
}

$converted = $jsonText | ConvertFrom-Json
$currentBooks = @(Convert-ToFlatArray -Value $converted)

$currentBookMap = @{}

foreach ($book in $currentBooks) {
    $idText = [string]$book.id

    if (-not [string]::IsNullOrWhiteSpace($idText)) {
        $currentBookMap[$idText] = $book
    }
}

$verifyRows = foreach ($row in $applyRows) {
    $calibreId = (Get-FieldValue -Row $row -Name "CalibreId").Trim()
    $expectedTitle = Get-FieldValue -Row $row -Name "Title"
    $expectedAuthors = Get-FieldValue -Row $row -Name "Authors"
    $expectedHash = (Get-FieldValue -Row $row -Name "ExpectedFinalCommentsHash").Trim()
    $expectedLength = Get-FieldValue -Row $row -Name "FinalCommentsLength"
    $applyStatus = Get-FieldValue -Row $row -Name "ApplyStatus"

    $actualTitle = ""
    $actualAuthors = ""
    $actualComments = ""
    $actualHash = ""
    $actualLength = 0
    $titleVerified = "Skipped"
    $authorsVerified = "Skipped"
    $commentsVerified = "Skipped"
    $verificationStatus = "Skipped"
    $verificationNotes = ""

    if ($applyStatus -ne "Succeeded") {
        $verificationStatus = "Skipped - Apply Not Successful"
        $verificationNotes = "ApplyStatus was '$applyStatus'. Verification requires ApplyStatus = Succeeded."
    }
    elseif (-not $currentBookMap.ContainsKey($calibreId)) {
        $verificationStatus = "Missing"
        $verificationNotes = "CalibreId was not found in current Calibre metadata."
    }
    else {
        $book = $currentBookMap[$calibreId]
        $actualTitle = [string]$book.title
        $actualAuthors = Format-Authors $book.authors
        $actualComments = [string]$book.comments
        $actualHash = Get-Sha256Hash -Value $actualComments
        $actualLength = $actualComments.Length

        if ((Normalize-ComparableValue $actualTitle) -ceq (Normalize-ComparableValue $expectedTitle)) {
            $titleVerified = "Yes"
        }
        else {
            $titleVerified = "No"
        }

        if ((Normalize-ComparableValue $actualAuthors) -ceq (Normalize-ComparableValue $expectedAuthors)) {
            $authorsVerified = "Yes"
        }
        else {
            $authorsVerified = "No"
        }

        if ([string]::IsNullOrWhiteSpace($expectedHash)) {
            $commentsVerified = "No"
            $verificationStatus = "Mismatch"
            $verificationNotes = "ExpectedFinalCommentsHash is blank."
        }
        elseif ($actualHash -eq $expectedHash) {
            $commentsVerified = "Yes"
            $verificationStatus = "Verified"
            $verificationNotes = "Current comments hash matches expected final comments hash."
        }
        else {
            $commentsVerified = "No"
            $verificationStatus = "Mismatch"
            $verificationNotes = "Current comments hash does not match expected final comments hash."
        }

        if ($titleVerified -ne "Yes") {
            if (-not [string]::IsNullOrWhiteSpace($verificationNotes)) {
                $verificationNotes += " "
            }

            $verificationNotes += "Title does not match expected value."
        }

        if ($authorsVerified -ne "Yes") {
            if (-not [string]::IsNullOrWhiteSpace($verificationNotes)) {
                $verificationNotes += " "
            }

            $verificationNotes += "Authors do not match expected value."
        }

        if ($verificationStatus -eq "Verified" -and ($titleVerified -ne "Yes" -or $authorsVerified -ne "Yes")) {
            $verificationStatus = "Mismatch"
        }
    }

    [pscustomobject]@{
        CalibreId                 = $calibreId
        Title                     = $expectedTitle
        Authors                   = $expectedAuthors
        CommentsMode              = Get-FieldValue -Row $row -Name "CommentsMode"
        ApplyStatus               = $applyStatus
        ExpectedFinalCommentsHash = $expectedHash
        ActualCommentsHash        = $actualHash
        ExpectedFinalLength       = $expectedLength
        ActualCommentsLength      = $actualLength
        TitleVerified             = $titleVerified
        AuthorsVerified           = $authorsVerified
        CommentsVerified          = $commentsVerified
        VerificationStatus        = $verificationStatus
        VerificationNotes         = $verificationNotes
    }
}

$outputFolder = Split-Path -Path $VerifyReportCsv -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$verifyRows | Export-Csv -Path $VerifyReportCsv -NoTypeInformation -Encoding UTF8

$verifiedCount = @($verifyRows | Where-Object { $_.VerificationStatus -eq "Verified" }).Count
$mismatchCount = @($verifyRows | Where-Object { $_.VerificationStatus -eq "Mismatch" }).Count
$missingCount = @($verifyRows | Where-Object { $_.VerificationStatus -eq "Missing" }).Count
$skippedCount = @($verifyRows | Where-Object { $_.VerificationStatus -like "Skipped*" }).Count

Write-Host "Verification complete: $VerifyReportCsv"
Write-Host "Rows reviewed: $($verifyRows.Count)"
Write-Host "Rows verified: $verifiedCount"
Write-Host "Rows mismatched: $mismatchCount"
Write-Host "Rows missing: $missingCount"
Write-Host "Rows skipped: $skippedCount"
Write-Host ""
Write-Host "This was a verification operation only. No Calibre metadata was modified."