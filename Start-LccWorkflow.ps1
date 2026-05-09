<#
.SYNOPSIS
Interactive launcher for the Calibre LCC Toolkit.

.DESCRIPTION
Provides a menu-driven workflow for the Calibre LCC Toolkit.

The launcher organizes the LCC workflow into clear operational phases:

1. Preflight
2. Export
3. Prepare
4. Validate
5. Apply
6. Verify

This launcher does not directly modify Calibre metadata. Metadata changes only
occur through Invoke-LccImportApply.ps1, which requires the -Apply switch and an
explicit APPLY confirmation when updates are pending.
#>

[CmdletBinding()]
param(
    [string]$ConfigPath = ".\config\lcc-toolkit.config.json"
)

function Get-ToolkitRoot {
    return Split-Path -Parent $PSCommandPath
}

function Resolve-ToolkitPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ToolkitRoot
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $ToolkitRoot $Path
}

function Get-ToolkitScriptPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptName
    )

    $scriptPath = Join-Path $script:ToolkitRoot "scripts\$ScriptName"

    if (-not (Test-Path $scriptPath)) {
        throw "Toolkit script not found: $scriptPath"
    }

    return $scriptPath
}

function Read-ToolkitInput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt,

        [string]$Default = ""
    )

    if ([string]::IsNullOrWhiteSpace($Default)) {
        return Read-Host $Prompt
    }

    $value = Read-Host "$Prompt [$Default]"

    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }

    return $value
}

function Read-RequiredInput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt
    )

    do {
        $value = Read-Host $Prompt

        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }

        Write-Host "Value is required." -ForegroundColor Yellow
    } while ($true)
}

function Read-BatchSlug {
    $defaultBatchSlug = $script:CurrentBatchSlug

    if ([string]::IsNullOrWhiteSpace($defaultBatchSlug)) {
        $batchSlug = Read-RequiredInput "Batch file slug, example j-russell-major-prize"
    }
    else {
        $batchSlug = Read-ToolkitInput `
            -Prompt "Batch file slug" `
            -Default $defaultBatchSlug
    }

    $script:CurrentBatchSlug = $batchSlug
    return $batchSlug
}

function Pause-Toolkit {
    Write-Host ""
    Read-Host "Press Enter to continue" | Out-Null
}

function Get-DefaultImportPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BatchSlug
    )

    $canonicalPath = ".\input\lcc-import-$BatchSlug-canonical.tsv"
    $standardPath = ".\input\lcc-import-$BatchSlug.tsv"

    $canonicalFullPath = Resolve-ToolkitPath -Path $canonicalPath -ToolkitRoot $script:ToolkitRoot

    if (Test-Path $canonicalFullPath) {
        return $canonicalPath
    }

    return $standardPath
}

function Show-Header {
    Clear-Host
    Write-Host "Calibre LCC Toolkit v0.7" -ForegroundColor Cyan
    Write-Host "========================"
    Write-Host ""
    Write-Host "Toolkit root:"
    Write-Host $script:ToolkitRoot
    Write-Host ""

    if ([string]::IsNullOrWhiteSpace($script:CurrentBatchSlug)) {
        Write-Host "Current batch file slug: <not set>" -ForegroundColor DarkGray
    }
    else {
        Write-Host "Current batch file slug: $script:CurrentBatchSlug" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "LCC Workflow: Preflight -> Export -> Enrich -> Prepare -> Validate -> Apply -> Verify" -ForegroundColor DarkGray
    Write-Host "Comments Workflow: Export -> Generate -> Dry Run -> Summary -> HTML Review -> Apply -> Verify" -ForegroundColor DarkGray
    Write-Host "Tip: The batch file slug is only used for default filenames." -ForegroundColor DarkGray
    Write-Host "Tip: Press Enter at prompts to accept the default value shown in brackets." -ForegroundColor DarkGray
    Write-Host ""
}

function Show-Menu {
    Show-Header

    Write-Host "1. Preflight: Run toolkit health check"
    Write-Host "2. Export: Create source TSV from Calibre"
    Write-Host "3. Prepare: Canonicalize completed LCC import TSV"
    Write-Host "4. Validate: Dry run import and write summary"
    Write-Host "5. Apply: Write approved LCC metadata to Calibre"
    Write-Host "6. Verify: Confirm final state and write summary"
    Write-Host "7. Open input folder"
    Write-Host "8. Open reports folder"
    Write-Host "9. Open workflow documentation"
    Write-Host "10. Reports: Show latest report files"
    Write-Host "11. Show Git status"
    Write-Host ""
    Write-Host "Author / Title Cleanup Module" -ForegroundColor Cyan
    Write-Host "A1. Author/Title: Export source TSV"
    Write-Host "A2. Author/Title: Dry run cleanup TSV"
    Write-Host "A3. Author/Title: Write dry-run summary"
    Write-Host "A4. Author/Title: Apply cleanup metadata"
    Write-Host "A5. Author/Title: Verify cleanup results"
    Write-Host ""
    Write-Host "Comments Module" -ForegroundColor Cyan
    Write-Host "C1. Comments: Export source TSV"
    Write-Host "C2. Comments: Dry run import TSV"
    Write-Host "C3. Comments: Write dry-run summary"
    Write-Host "C4. Comments: Write HTML review"
    Write-Host "C5. Comments: Apply comments metadata"
    Write-Host "C6. Comments: Verify comments apply report"
    Write-Host ""
    Write-Host "0. Exit"
    Write-Host ""
}

function Start-HealthCheck {
    $defaultReport = ".\reports\lcc-toolkit-health.txt"

    $configFullPath = Resolve-ToolkitPath `
        -Path ".\config\lcc-toolkit.config.json" `
        -ToolkitRoot $script:ToolkitRoot

    $reportFullPath = Resolve-ToolkitPath `
        -Path $defaultReport `
        -ToolkitRoot $script:ToolkitRoot

    $healthScriptPath = Get-ToolkitScriptPath -ScriptName "Test-LccToolkitHealth.ps1"

    Write-Host ""
    Write-Host "Preflight: toolkit health check" -ForegroundColor Cyan
    Write-Host "Config path:        $configFullPath"
    Write-Host "Health report path: $reportFullPath"
    Write-Host ""

    & $healthScriptPath `
        -ConfigPath $configFullPath `
        -ReportTxt $reportFullPath

    Pause-Toolkit
}

function Start-ExportSourceBatch {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Export: create source TSV from Calibre" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads Calibre and creates a source TSV for LCC enrichment." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Paste the Calibre search string exactly as used in Calibre." -ForegroundColor DarkGray
    Write-Host "For award batches, the loose award search usually works best here." -ForegroundColor DarkGray
    Write-Host "Example: #award_programs:`"AHA - J. Russell Major Prize`" and #mqg_lcc:false" -ForegroundColor DarkGray
    Write-Host ""

    $search = Read-RequiredInput "Calibre search string"

    Write-Host ""
    Write-Host "Optional exact Award Programs filter:" -ForegroundColor DarkGray
    Write-Host "- Leave blank for normal exports." -ForegroundColor DarkGray
    Write-Host "- Use this for award batches when Calibre search overmatches." -ForegroundColor DarkGray
    Write-Host "Example: AHA - J. Russell Major Prize" -ForegroundColor DarkGray
    Write-Host ""

    $exactAwardProgram = Read-ToolkitInput `
        -Prompt "Exact Award Programs filter, blank to skip" `
        -Default ""

    $defaultOutput = ".\input\lcc-source-$batchSlug.tsv"

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output source TSV" `
        -Default $defaultOutput

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $exportScriptPath = Get-ToolkitScriptPath -ScriptName "Export-CalibreBatchForLcc.ps1"

    Write-Host ""
    Write-Host "Running: Export-CalibreBatchForLcc.ps1" -ForegroundColor Cyan
    Write-Host ""

    if ([string]::IsNullOrWhiteSpace($libraryPath)) {
        & $exportScriptPath `
            -Search $search `
            -ExactAwardProgram $exactAwardProgram `
            -OutputTsv $outputTsv
    }
    else {
        & $exportScriptPath `
            -Search $search `
            -ExactAwardProgram $exactAwardProgram `
            -OutputTsv $outputTsv `
            -LibraryPath $libraryPath
    }

    Write-Host ""
    Write-Host "Next step:" -ForegroundColor Cyan
    Write-Host "Send the source TSV for LCC enrichment, then save the completed import TSV as:"
    Write-Host ".\input\lcc-import-$batchSlug.tsv"

    Pause-Toolkit
}

function Start-PrepareImport {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Prepare: canonicalize completed LCC import TSV" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step normalizes LCC Primary and Secondary Class values against the approved dropdown lists." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $defaultInput = ".\input\lcc-import-$batchSlug.tsv"
    $defaultOutput = ".\input\lcc-import-$batchSlug-canonical.tsv"
    $defaultReport = ".\reports\lcc-canonicalize-$batchSlug.csv"

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input completed import TSV" `
        -Default $defaultInput

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output canonical import TSV" `
        -Default $defaultOutput

    $reportCsv = Read-ToolkitInput `
        -Prompt "Canonicalization report CSV" `
        -Default $defaultReport

    $overwriteAnswer = Read-ToolkitInput `
        -Prompt "Overwrite existing output/report? Type YES to overwrite" `
        -Default "NO"

    $canonicalizeScriptPath = Get-ToolkitScriptPath -ScriptName "Convert-LccImportToCanonical.ps1"

    Write-Host ""
    Write-Host "Running: Convert-LccImportToCanonical.ps1" -ForegroundColor Cyan
    Write-Host ""

    if ($overwriteAnswer -eq "YES") {
        & $canonicalizeScriptPath `
            -InputTsv $inputTsv `
            -OutputTsv $outputTsv `
            -ReportCsv $reportCsv `
            -Overwrite
    }
    else {
        & $canonicalizeScriptPath `
            -InputTsv $inputTsv `
            -OutputTsv $outputTsv `
            -ReportCsv $reportCsv
    }

    Pause-Toolkit
}

function Invoke-DryRunReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputTsv,

        [Parameter(Mandatory = $true)]
        [string]$ReportCsv
    )

    $dryRunScriptPath = Get-ToolkitScriptPath -ScriptName "Test-LccImportDryRun.ps1"

    Write-Host ""
    Write-Host "Running: Test-LccImportDryRun.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $dryRunScriptPath `
        -InputTsv $InputTsv `
        -ReportCsv $ReportCsv
}

function Invoke-SummaryReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReportCsv,

        [Parameter(Mandatory = $true)]
        [string]$SummaryTxt,

        [Parameter(Mandatory = $true)]
        [string]$BatchSlug
    )

    $summaryScriptPath = Get-ToolkitScriptPath -ScriptName "Write-LccBatchSummary.ps1"

    Write-Host ""
    Write-Host "Running: Write-LccBatchSummary.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $summaryScriptPath `
        -ReportCsv $ReportCsv `
        -SummaryTxt $SummaryTxt `
        -BatchName $BatchSlug
}

function Start-ValidateImport {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Validate: dry run import and write summary" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step shows what would change before Calibre metadata is modified." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $defaultInput = Get-DefaultImportPath -BatchSlug $batchSlug
    $defaultReport = ".\reports\lcc-dryrun-$batchSlug.csv"
    $defaultSummary = ".\reports\lcc-summary-$batchSlug-dryrun.txt"

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input canonical import TSV" `
        -Default $defaultInput

    $reportCsv = Read-ToolkitInput `
        -Prompt "Dry-run report CSV" `
        -Default $defaultReport

    $summaryTxt = Read-ToolkitInput `
        -Prompt "Dry-run summary TXT" `
        -Default $defaultSummary

    Invoke-DryRunReport `
        -InputTsv $inputTsv `
        -ReportCsv $reportCsv

    Invoke-SummaryReport `
        -ReportCsv $reportCsv `
        -SummaryTxt $summaryTxt `
        -BatchSlug $batchSlug

    Write-Host ""
    Write-Host "Validation complete." -ForegroundColor Cyan
    Write-Host "Review the dry-run summary before applying metadata."

    Pause-Toolkit
}

function Start-ApplyImport {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Apply: write approved LCC metadata to Calibre" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This is the only normal workflow step that modifies Calibre metadata." -ForegroundColor Yellow
    Write-Host "Make sure Calibre is closed and the dry-run summary says READY TO APPLY." -ForegroundColor Yellow
    Write-Host ""

    $defaultDryRunReport = ".\reports\lcc-dryrun-$batchSlug.csv"
    $defaultApplyReport = ".\reports\lcc-apply-$batchSlug.csv"

    $dryRunReportCsv = Read-ToolkitInput `
        -Prompt "Dry-run report CSV" `
        -Default $defaultDryRunReport

    $applyReportCsv = Read-ToolkitInput `
        -Prompt "Apply report CSV" `
        -Default $defaultApplyReport

    Write-Host ""
    Write-Host "The apply script will run its own preflight and require APPLY confirmation if updates are pending."
    Write-Host ""

    $continueAnswer = Read-ToolkitInput `
        -Prompt "Continue to apply script? Type YES to continue" `
        -Default "NO"

    if ($continueAnswer -ne "YES") {
        Write-Host "Apply step cancelled." -ForegroundColor Yellow
        Pause-Toolkit
        return
    }

    $applyScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-LccImportApply.ps1"

    Write-Host ""
    Write-Host "Running: Invoke-LccImportApply.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $applyScriptPath `
        -DryRunReportCsv $dryRunReportCsv `
        -ApplyReportCsv $applyReportCsv `
        -Apply

    Pause-Toolkit
}

function Start-VerifyFinalState {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Verify: confirm final state and write summary" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step checks that Calibre now matches the canonical import file." -ForegroundColor DarkGray
    Write-Host "A clean verification should show zero pending field updates." -ForegroundColor DarkGray
    Write-Host ""

    $defaultInput = Get-DefaultImportPath -BatchSlug $batchSlug
    $defaultReport = ".\reports\lcc-verify-$batchSlug.csv"
    $defaultSummary = ".\reports\lcc-summary-$batchSlug-verify.txt"

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input canonical import TSV" `
        -Default $defaultInput

    $reportCsv = Read-ToolkitInput `
        -Prompt "Verify report CSV" `
        -Default $defaultReport

    $summaryTxt = Read-ToolkitInput `
        -Prompt "Verify summary TXT" `
        -Default $defaultSummary

    Invoke-DryRunReport `
        -InputTsv $inputTsv `
        -ReportCsv $reportCsv

    Invoke-SummaryReport `
        -ReportCsv $reportCsv `
        -SummaryTxt $summaryTxt `
        -BatchSlug $batchSlug

    Write-Host ""
    Write-Host "Verification complete." -ForegroundColor Cyan
    Write-Host "Final win condition: VERIFIED CLEAN."

    Pause-Toolkit
}

function Open-ToolkitFolder {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FolderPath
    )

    $fullPath = Resolve-ToolkitPath -Path $FolderPath -ToolkitRoot $script:ToolkitRoot

    if (-not (Test-Path $fullPath)) {
        throw "Folder not found: $fullPath"
    }

    Invoke-Item $fullPath
}

function Open-WorkflowDocumentation {
    $docPath = Resolve-ToolkitPath `
        -Path ".\docs\LCC-Toolkit-Workflow.md" `
        -ToolkitRoot $script:ToolkitRoot

    if (-not (Test-Path $docPath)) {
        throw "Workflow documentation not found: $docPath"
    }

    Invoke-Item $docPath
}

function Start-ShowLatestReports {
    $reportsScriptPath = Get-ToolkitScriptPath -ScriptName "Show-LccLatestReports.ps1"

    Write-Host ""
    Write-Host "Reports: show latest report files" -ForegroundColor Cyan
    Write-Host ""

    & $reportsScriptPath `
        -ReportsFolder ".\reports" `
        -MaxResults 12

    Pause-Toolkit
}

function Show-GitStatus {
    Write-Host ""
    Write-Host "Git status" -ForegroundColor Cyan
    Write-Host "----------"
    git status

    Write-Host ""
    Write-Host "Recent commits" -ForegroundColor Cyan
    Write-Host "--------------"
    git log --oneline --decorate --max-count 8

    Pause-Toolkit
}

$script:ToolkitRoot = Get-ToolkitRoot
$script:CurrentBatchSlug = ""

Push-Location $script:ToolkitRoot

try {
    $configFullPath = Resolve-ToolkitPath -Path $ConfigPath -ToolkitRoot $script:ToolkitRoot

    if (-not (Test-Path $configFullPath)) {
        throw "Config file not found: $configFullPath"
    }

    $config = Get-Content $configFullPath -Raw | ConvertFrom-Json

    do {
        Show-Menu
        $choice = Read-Host "Select an option"



function Start-AuthorTitleExport {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: export source TSV" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads Calibre and creates a source TSV for author/title cleanup review." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "You may use a Calibre search string, an exact Award Programs value, or both." -ForegroundColor DarkGray
    Write-Host "Example search: title:false or author:false" -ForegroundColor DarkGray
    Write-Host "Example award program: AHA - J. Russell Major Prize" -ForegroundColor DarkGray
    Write-Host ""

    $search = Read-ToolkitInput `
        -Prompt "Calibre search string, blank if using exact award program only" `
        -Default ""

    $exactAwardProgram = Read-ToolkitInput `
        -Prompt "Exact Award Programs value, blank to skip" `
        -Default ""

    if ([string]::IsNullOrWhiteSpace($search) -and [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
        throw "Provide either a Calibre search string or an exact Award Programs value."
    }

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output author/title source TSV" `
        -Default ".\input\author-title-cleanup-source-$batchSlug.tsv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $exportScriptPath = Get-ToolkitScriptPath -ScriptName "Export-CalibreBatchForAuthorTitleCleanup.ps1"

    $exportArgs = @{
        OutputTsv = $outputTsv
    }

    if (-not [string]::IsNullOrWhiteSpace($search)) {
        $exportArgs.Search = $search
    }

    if (-not [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
        $exportArgs.ExactAwardProgram = $exactAwardProgram
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $exportArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Running: Export-CalibreBatchForAuthorTitleCleanup.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $exportScriptPath @exportArgs

    Write-Host ""
    Write-Host "Next step:" -ForegroundColor Cyan
    Write-Host "Review the exported TSV, populate proposed title/author fields, then save the import TSV as:"
    Write-Host ".\input\author-title-cleanup-import-$batchSlug.tsv"

    Pause-Toolkit
}

function Start-AuthorTitleDryRun {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: dry run cleanup TSV" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step validates proposed title/author cleanup without modifying Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input author/title import TSV" `
        -Default ".\input\author-title-cleanup-import-$batchSlug.tsv"

    $reportCsv = Read-ToolkitInput `
        -Prompt "Dry-run report CSV" `
        -Default ".\reports\author-title-cleanup-dryrun-$batchSlug.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $dryRunScriptPath = Get-ToolkitScriptPath -ScriptName "Test-AuthorTitleCleanupDryRun.ps1"

    $dryRunArgs = @{
        InputTsv = $inputTsv
        ReportCsv = $reportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $dryRunArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Running: Test-AuthorTitleCleanupDryRun.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $dryRunScriptPath @dryRunArgs

    Pause-Toolkit
}

function Start-AuthorTitleSummary {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: write dry-run summary" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step summarizes an author/title cleanup dry-run CSV." -ForegroundColor DarkGray
    Write-Host ""

    $dryRunCsv = Read-ToolkitInput `
        -Prompt "Dry-run CSV" `
        -Default ".\reports\author-title-cleanup-dryrun-$batchSlug.csv"

    $summaryTxt = Read-ToolkitInput `
        -Prompt "Summary TXT" `
        -Default ".\reports\author-title-cleanup-summary-$batchSlug.txt"

    $summaryScriptPath = Get-ToolkitScriptPath -ScriptName "Write-AuthorTitleCleanupSummary.ps1"

    Write-Host ""
    Write-Host "Running: Write-AuthorTitleCleanupSummary.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $summaryScriptPath `
        -DryRunCsv $dryRunCsv `
        -SummaryTxt $summaryTxt

    Pause-Toolkit
}

function Start-AuthorTitleApply {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: apply cleanup metadata" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This step can modify Calibre title and author metadata." -ForegroundColor Yellow
    Write-Host "Run only after the dry-run report and summary are clean." -ForegroundColor Yellow
    Write-Host ""

    $dryRunCsv = Read-ToolkitInput `
        -Prompt "Dry-run CSV" `
        -Default ".\reports\author-title-cleanup-dryrun-$batchSlug.csv"

    $applyReportCsv = Read-ToolkitInput `
        -Prompt "Apply report CSV" `
        -Default ".\reports\author-title-cleanup-apply-$batchSlug.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $launchAnswer = Read-ToolkitInput `
        -Prompt "Launch real apply script now? Type YES to continue" `
        -Default "NO"

    if ($launchAnswer -ne "YES") {
        Write-Host ""
        Write-Host "Apply not launched." -ForegroundColor Yellow
        Pause-Toolkit
        return
    }

    $applyScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-AuthorTitleCleanupApply.ps1"

    $applyArgs = @{
        DryRunCsv = $dryRunCsv
        ApplyReportCsv = $applyReportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $applyArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Running: Invoke-AuthorTitleCleanupApply.ps1" -ForegroundColor Yellow
    Write-Host ""

    & $applyScriptPath @applyArgs

    Pause-Toolkit
}

function Start-AuthorTitleVerify {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: verify cleanup results" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step verifies current Calibre title/author values against the dry-run report." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $dryRunCsv = Read-ToolkitInput `
        -Prompt "Dry-run CSV" `
        -Default ".\reports\author-title-cleanup-dryrun-$batchSlug.csv"

    $verifyReportCsv = Read-ToolkitInput `
        -Prompt "Verify report CSV" `
        -Default ".\reports\author-title-cleanup-verify-$batchSlug.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $verifyScriptPath = Get-ToolkitScriptPath -ScriptName "Test-AuthorTitleCleanupVerify.ps1"

    $verifyArgs = @{
        DryRunCsv = $dryRunCsv
        VerifyReportCsv = $verifyReportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $verifyArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Running: Test-AuthorTitleCleanupVerify.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $verifyScriptPath @verifyArgs

    Pause-Toolkit
}

function Start-CommentsExport {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Comments: export source TSV" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads Calibre and creates a source TSV for comments generation." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "You may use a Calibre search string, explicit Calibre IDs, or both." -ForegroundColor DarkGray
    Write-Host "Example search: comments:false" -ForegroundColor DarkGray
    Write-Host "Example IDs: 4074,5177,5153" -ForegroundColor DarkGray
    Write-Host ""

    $search = Read-ToolkitInput `
        -Prompt "Calibre search string, blank if using explicit IDs only" `
        -Default ""

    $calibreIds = Read-ToolkitInput `
        -Prompt "Explicit Calibre IDs, comma-separated, blank to skip" `
        -Default ""

    if ([string]::IsNullOrWhiteSpace($search) -and [string]::IsNullOrWhiteSpace($calibreIds)) {
        throw "Provide either a Calibre search string or explicit Calibre IDs."
    }

    $defaultOutput = ".\input\comments-source-$batchSlug.tsv"

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output comments source TSV" `
        -Default $defaultOutput

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $exportScriptPath = Get-ToolkitScriptPath -ScriptName "Export-CalibreBatchForComments.ps1"

    $exportArgs = @{
        OutputTsv = $outputTsv
    }

    if (-not [string]::IsNullOrWhiteSpace($search)) {
        $exportArgs.Search = $search
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
        $exportArgs.CalibreIds = $calibreIds
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $exportArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Running: Export-CalibreBatchForComments.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $exportScriptPath @exportArgs

    Write-Host ""
    Write-Host "Next step:" -ForegroundColor Cyan
    Write-Host "Generate proposed comments, then save the completed import TSV as:"
    Write-Host ".\input\comments-import-$batchSlug.tsv"

    Pause-Toolkit
}

function Start-CommentsDryRun {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Comments: dry run import TSV" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step validates proposed comments without modifying Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input comments import TSV" `
        -Default ".\input\comments-import-$batchSlug.tsv"

    $reportCsv = Read-ToolkitInput `
        -Prompt "Dry-run report CSV" `
        -Default ".\reports\comments-dryrun-$batchSlug.csv"

    $dryRunScriptPath = Get-ToolkitScriptPath -ScriptName "Test-CommentsDryRun.ps1"

    Write-Host ""
    Write-Host "Running: Test-CommentsDryRun.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $dryRunScriptPath `
        -InputTsv $inputTsv `
        -ReportCsv $reportCsv

    Pause-Toolkit
}

function Start-CommentsSummary {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Comments: write dry-run summary" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step summarizes a comments dry-run CSV." -ForegroundColor DarkGray
    Write-Host ""

    $dryRunCsv = Read-ToolkitInput `
        -Prompt "Dry-run CSV" `
        -Default ".\reports\comments-dryrun-$batchSlug.csv"

    $summaryTxt = Read-ToolkitInput `
        -Prompt "Summary TXT" `
        -Default ".\reports\comments-summary-$batchSlug.txt"

    $summaryScriptPath = Get-ToolkitScriptPath -ScriptName "Write-CommentsSummary.ps1"

    Write-Host ""
    Write-Host "Running: Write-CommentsSummary.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $summaryScriptPath `
        -DryRunCsv $dryRunCsv `
        -SummaryTxt $summaryTxt

    Pause-Toolkit
}

function Start-CommentsReviewHtml {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Comments: write HTML review" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step creates a visual HTML review page for proposed comments." -ForegroundColor DarkGray
    Write-Host ""

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input comments import TSV" `
        -Default ".\input\comments-import-$batchSlug.tsv"

    $outputHtml = Read-ToolkitInput `
        -Prompt "Output HTML review file" `
        -Default ".\reports\comments-review-$batchSlug.html"

    $includeExistingAnswer = Read-ToolkitInput `
        -Prompt "Include existing comments in review? YES/NO" `
        -Default "YES"

    $openAnswer = Read-ToolkitInput `
        -Prompt "Open HTML review after writing? YES/NO" `
        -Default "YES"

    $reviewScriptPath = Get-ToolkitScriptPath -ScriptName "Write-CommentsReviewHtml.ps1"

    $reviewArgs = @{
        InputTsv = $inputTsv
        OutputHtml = $outputHtml
    }

    if ($includeExistingAnswer -eq "YES") {
        $reviewArgs.IncludeExistingComments = $true
    }

    if ($openAnswer -eq "YES") {
        $reviewArgs.Open = $true
    }

    Write-Host ""
    Write-Host "Running: Write-CommentsReviewHtml.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $reviewScriptPath @reviewArgs

    Pause-Toolkit
}

function Start-CommentsApply {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Comments: apply comments metadata" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This step can modify the Calibre Comments field." -ForegroundColor Yellow
    Write-Host "Make sure Calibre is closed and the dry-run report has zero blocked rows." -ForegroundColor Yellow
    Write-Host ""

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input comments import TSV" `
        -Default ".\input\comments-import-$batchSlug.tsv"

    $dryRunCsv = Read-ToolkitInput `
        -Prompt "Dry-run CSV" `
        -Default ".\reports\comments-dryrun-$batchSlug.csv"

    $applyReportCsv = Read-ToolkitInput `
        -Prompt "Apply report CSV" `
        -Default ".\reports\comments-apply-$batchSlug.csv"

    $preflightOnlyAnswer = Read-ToolkitInput `
        -Prompt "Preflight only? YES = no write, NO = real apply" `
        -Default "YES"

    $applyScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-CommentsApply.ps1"

    $applyArgs = @{
        InputTsv = $inputTsv
        DryRunCsv = $dryRunCsv
        ApplyReportCsv = $applyReportCsv
    }

    if ($preflightOnlyAnswer -ne "NO") {
        $applyArgs.PreflightOnly = $true
    }

    Write-Host ""
    Write-Host "Running: Invoke-CommentsApply.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $applyScriptPath @applyArgs

    Pause-Toolkit
}

function Start-CommentsVerify {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Comments: verify comments apply report" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step verifies current Calibre comments against an apply report." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $applyReportCsv = Read-ToolkitInput `
        -Prompt "Apply report CSV" `
        -Default ".\reports\comments-apply-$batchSlug.csv"

    $verifyReportCsv = Read-ToolkitInput `
        -Prompt "Verify report CSV" `
        -Default ".\reports\comments-verify-$batchSlug.csv"

    $verifyScriptPath = Get-ToolkitScriptPath -ScriptName "Test-CommentsVerify.ps1"

    Write-Host ""
    Write-Host "Running: Test-CommentsVerify.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $verifyScriptPath `
        -ApplyReportCsv $applyReportCsv `
        -VerifyReportCsv $verifyReportCsv

    Pause-Toolkit
}

        try {
            switch ($choice) {
                "1"  { Start-HealthCheck }
                "2"  { Start-ExportSourceBatch }
                "3"  { Start-PrepareImport }
                "4"  { Start-ValidateImport }
                "5"  { Start-ApplyImport }
                "6"  { Start-VerifyFinalState }
                "7"  { Open-ToolkitFolder -FolderPath ".\input" }
                "8"  { Open-ToolkitFolder -FolderPath ".\reports" }
                "9"  { Open-WorkflowDocumentation }
                "10" { Start-ShowLatestReports }
                "11" { Show-GitStatus }
                "A1" { Start-AuthorTitleExport }
                "A2" { Start-AuthorTitleDryRun }
                "A3" { Start-AuthorTitleSummary }
                "A4" { Start-AuthorTitleApply }
                "A5" { Start-AuthorTitleVerify }
                "C1" { Start-CommentsExport }
                "C2" { Start-CommentsDryRun }
                "C3" { Start-CommentsSummary }
                "C4" { Start-CommentsReviewHtml }
                "C5" { Start-CommentsApply }
                "C6" { Start-CommentsVerify }
                "0"  {
                    Write-Host "Exiting Calibre LCC Toolkit."
                    break
                }
                default {
                    Write-Host "Unknown option: $choice" -ForegroundColor Yellow
                    Pause-Toolkit
                }
            }
        }
        catch {
            Write-Host ""
            Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
            Pause-Toolkit
        }
    } while ($choice -ne "0")
}
finally {
    Pop-Location
}


