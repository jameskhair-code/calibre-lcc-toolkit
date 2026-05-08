<#
.SYNOPSIS
Writes a local HTML review page for proposed Calibre comments.

.DESCRIPTION
Reads a comments import TSV and renders the ProposedComments field for each row into
a browser-friendly HTML review page.

This script is read-only. It does not modify Calibre metadata.

The review page is intended to support the v0.7 workflow:

Export -> Generate Proposed Comments -> Dry Run -> Summary -> HTML Review -> Apply -> Verify

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\Write-CommentsReviewHtml.ps1 `
  -InputTsv ".\input\comments-import-pilot-j-russell-major-prize-5books.tsv" `
  -OutputHtml ".\reports\comments-review-j-russell-major-prize-5books.html" `
  -Open
#>

[CmdletBinding()]
param(
    [string]$InputTsv = ".\input\comments-import-batch.tsv",

    [string]$OutputHtml = ".\reports\comments-review-batch.html",

    [switch]$Open,

    [switch]$IncludeExistingComments,

    [int]$ExistingCommentsPreviewLength = 700
)

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
        # If HtmlDecode is unavailable, continue with stripped text.
    }

    return (($text.Trim()) -replace '\s+', ' ')
}

function Get-TextPreview {
    param(
        [AllowNull()]
        [string]$Text,

        [int]$MaxLength = 700
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

function Encode-Html {
    param(
        [AllowNull()]
        [string]$Text
    )

    if ($null -eq $Text) {
        return ""
    }

    return [System.Net.WebUtility]::HtmlEncode($Text)
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

if (-not (Test-Path $InputTsv)) {
    throw "Input TSV was not found: $InputTsv"
}

Write-Host "Writing comments HTML review page..."
Write-Host "This operation is read-only and does not modify Calibre metadata."
Write-Host "Input TSV: $InputTsv"
Write-Host "Output HTML: $OutputHtml"

$rows = @(Import-Csv -Path $InputTsv -Delimiter "`t")

if ($rows.Count -eq 0) {
    throw "Input TSV has no data rows: $InputTsv"
}

$outputFolder = Split-Path -Path $OutputHtml -Parent

if ($outputFolder -and -not (Test-Path $outputFolder)) {
    New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
}

$generatedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$totalRows = $rows.Count
$rowsWithProposedComments = @(
    $rows | Where-Object {
        -not [string]::IsNullOrWhiteSpace((Get-FieldValue -Row $_ -Name "ProposedComments"))
    }
).Count

$rowsWithoutProposedComments = $totalRows - $rowsWithProposedComments

$htmlParts = [System.Collections.Generic.List[string]]::new()

$htmlParts.Add("<!DOCTYPE html>") | Out-Null
$htmlParts.Add("<html>") | Out-Null
$htmlParts.Add("<head>") | Out-Null
$htmlParts.Add("<meta charset='utf-8'>") | Out-Null
$htmlParts.Add("<title>Comments Review - Calibre Metadata Toolkit</title>") | Out-Null
$htmlParts.Add("<style>") | Out-Null
$htmlParts.Add("body { font-family: Segoe UI, Arial, sans-serif; max-width: 1100px; margin: 40px auto; line-height: 1.55; color: #222; }") | Out-Null
$htmlParts.Add("header { margin-bottom: 28px; }") | Out-Null
$htmlParts.Add("article { border: 1px solid #cfcfcf; border-radius: 12px; padding: 24px; margin-bottom: 32px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }") | Out-Null
$htmlParts.Add("h1 { margin-bottom: 8px; }") | Out-Null
$htmlParts.Add("h2 { border-bottom: 1px solid #ddd; padding-bottom: 8px; margin-top: 0; }") | Out-Null
$htmlParts.Add("h3 { margin-top: 24px; margin-bottom: 8px; }") | Out-Null
$htmlParts.Add("li { margin-bottom: 6px; }") | Out-Null
$htmlParts.Add(".meta { color: #555; font-size: 0.95em; margin-bottom: 18px; }") | Out-Null
$htmlParts.Add(".summary { border: 1px solid #ddd; border-radius: 10px; padding: 16px; background: #f7f7f7; margin: 18px 0 28px 0; }") | Out-Null
$htmlParts.Add(".warning { border-left: 4px solid #b35c00; background: #fff8ef; padding: 10px 14px; margin: 14px 0; }") | Out-Null
$htmlParts.Add(".existing { border-top: 1px dashed #bbb; margin-top: 28px; padding-top: 16px; color: #444; }") | Out-Null
$htmlParts.Add(".missing { color: #8a1f11; font-weight: 600; }") | Out-Null
$htmlParts.Add("code { background: #eee; padding: 1px 4px; border-radius: 4px; }") | Out-Null
$htmlParts.Add("</style>") | Out-Null
$htmlParts.Add("</head>") | Out-Null
$htmlParts.Add("<body>") | Out-Null

$htmlParts.Add("<header>") | Out-Null
$htmlParts.Add("<h1>Comments Review</h1>") | Out-Null
$htmlParts.Add("<p class='meta'>Generated: $(Encode-Html $generatedAt)<br>Input TSV: <code>$(Encode-Html $InputTsv)</code><br>Output HTML: <code>$(Encode-Html $OutputHtml)</code></p>") | Out-Null
$htmlParts.Add("<div class='summary'>") | Out-Null
$htmlParts.Add("<b>Batch Summary</b><br>") | Out-Null
$htmlParts.Add("Rows reviewed: $totalRows<br>") | Out-Null
$htmlParts.Add("Rows with proposed comments: $rowsWithProposedComments<br>") | Out-Null
$htmlParts.Add("Rows missing proposed comments: $rowsWithoutProposedComments<br>") | Out-Null
$htmlParts.Add("This review page is read-only. It does not modify Calibre metadata.") | Out-Null
$htmlParts.Add("</div>") | Out-Null
$htmlParts.Add("</header>") | Out-Null

foreach ($row in $rows) {
    $calibreId = Get-FieldValue -Row $row -Name "CalibreId"
    $title = Get-FieldValue -Row $row -Name "Title"
    $authors = Get-FieldValue -Row $row -Name "Authors"
    $profile = Get-FieldValue -Row $row -Name "CommentsTemplateProfile"
    $mode = Get-FieldValue -Row $row -Name "CommentsMode"
    $confidence = Get-FieldValue -Row $row -Name "Confidence"
    $manualReview = Get-FieldValue -Row $row -Name "ManualReviewRequired"
    $sourceNotes = Get-FieldValue -Row $row -Name "SourceNotes"
    $proposedComments = Get-FieldValue -Row $row -Name "ProposedComments"
    $existingComments = Get-FieldValue -Row $row -Name "ExistingComments"
    $existingCommentsLength = Get-FieldValue -Row $row -Name "ExistingCommentsLength"

    $htmlParts.Add("<article>") | Out-Null
    $htmlParts.Add("<h2>$(Encode-Html $title)</h2>") | Out-Null

    $htmlParts.Add("<div class='meta'>") | Out-Null
    $htmlParts.Add("<b>CalibreId:</b> $(Encode-Html $calibreId)<br>") | Out-Null
    $htmlParts.Add("<b>Authors:</b> $(Encode-Html $authors)<br>") | Out-Null
    $htmlParts.Add("<b>Template Profile:</b> $(Encode-Html $profile)<br>") | Out-Null
    $htmlParts.Add("<b>Comments Mode:</b> $(Encode-Html $mode)<br>") | Out-Null
    $htmlParts.Add("<b>Confidence:</b> $(Encode-Html $confidence)<br>") | Out-Null
    $htmlParts.Add("<b>Manual Review Required:</b> $(Encode-Html $manualReview)<br>") | Out-Null
    $htmlParts.Add("<b>Existing Comments Length:</b> $(Encode-Html $existingCommentsLength)<br>") | Out-Null
    $htmlParts.Add("<b>Workflow SourceNotes:</b> $(Encode-Html $sourceNotes)") | Out-Null
    $htmlParts.Add("</div>") | Out-Null

    if ([string]::IsNullOrWhiteSpace($proposedComments)) {
        $htmlParts.Add("<p class='missing'>No ProposedComments value found for this row.</p>") | Out-Null
    }
    else {
        $htmlParts.Add($proposedComments) | Out-Null
    }

    if ($IncludeExistingComments) {
        $existingPreview = Get-TextPreview -Text (Convert-HtmlToPlainText -Html $existingComments) -MaxLength $ExistingCommentsPreviewLength

        $htmlParts.Add("<div class='existing'>") | Out-Null
        $htmlParts.Add("<h3>Existing Comments Preview</h3>") | Out-Null

        if ([string]::IsNullOrWhiteSpace($existingPreview)) {
            $htmlParts.Add("<p>No existing comments detected.</p>") | Out-Null
        }
        else {
            $htmlParts.Add("<p>$(Encode-Html $existingPreview)</p>") | Out-Null
        }

        $htmlParts.Add("</div>") | Out-Null
    }

    $htmlParts.Add("</article>") | Out-Null
}

$htmlParts.Add("</body>") | Out-Null
$htmlParts.Add("</html>") | Out-Null

$htmlParts | Set-Content -Path $OutputHtml -Encoding UTF8

Write-Host "HTML review complete: $OutputHtml"
Write-Host "Rows reviewed: $totalRows"
Write-Host "Rows with proposed comments: $rowsWithProposedComments"
Write-Host "Rows missing proposed comments: $rowsWithoutProposedComments"
Write-Host ""
Write-Host "This was a review operation only. No Calibre metadata was modified."

if ($Open) {
    Start-Process $OutputHtml
}