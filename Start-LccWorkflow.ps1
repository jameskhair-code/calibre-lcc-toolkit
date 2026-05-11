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
    Write-Host "Calibre LCC Toolkit v0.10.5" -ForegroundColor Cyan
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
    Write-Host "12. LCC: Mark verified MQG complete"
    Write-Host "13. MQG: Show batch status / readiness report"
    Write-Host ""
    Write-Host "Batch Selection Module" -ForegroundColor Cyan
    Write-Host "B1. Batch: Create batch manifest"
    Write-Host ""

    Write-Host "Guided Workflows" -ForegroundColor Cyan
    Write-Host "G1. Guided Author/Title prep"
    Write-Host ""

    Write-Host "Author / Title Cleanup Module" -ForegroundColor Cyan
    Write-Host "A1. Author/Title: Export source TSV"
    Write-Host "A2. Author/Title: Dry run cleanup TSV"
    Write-Host "A3. Author/Title: Write dry-run summary"
    Write-Host "A4. Author/Title: Apply cleanup metadata"
    Write-Host "A5. Author/Title: Verify cleanup results"
    Write-Host "A6. Author/Title: Mark verified MQG complete"
    Write-Host ""
    Write-Host "Comments Module" -ForegroundColor Cyan
    Write-Host "C1. Comments: Export source TSV"
    Write-Host "C2. Comments: Dry run import TSV"
    Write-Host "C3. Comments: Write dry-run summary"
    Write-Host "C4. Comments: Write HTML review"
    Write-Host "C5. Comments: Apply comments metadata"
    Write-Host "C6. Comments: Verify comments apply report"
    Write-Host "C7. Comments: Mark verified MQG complete"
    Write-Host ""

    Write-Host "Identifier Module" -ForegroundColor Cyan
    Write-Host "I1. Identifiers: Export inventory"
    Write-Host "I2. Identifiers: Write diagnostics"
    Write-Host "I3. Identifiers: Generate proposal worksheet"
    Write-Host "I4. Identifiers: Validate proposal worksheet"
    Write-Host ""

    Write-Host "Manual MQG Completion Module" -ForegroundColor Cyan
    Write-Host "W1. Awards: Mark reviewed MQG complete"
    Write-Host "W2. Cover: Mark reviewed MQG complete"
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
    Write-Host "Preferred workflow:" -ForegroundColor DarkGray
    Write-Host "1. Use B1 to create a stable batch manifest." -ForegroundColor DarkGray
    Write-Host "2. Use that manifest here to export the LCC source TSV." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "You may use a batch manifest, Calibre search string, explicit Calibre IDs, exact Award Programs filter, or a combination." -ForegroundColor DarkGray
    Write-Host "If a search and manifest/IDs are both supplied, the manifest/IDs are treated as a local filter/intersection." -ForegroundColor DarkGray
    Write-Host "Example manifest: .\input\batch-$batchSlug.csv" -ForegroundColor DarkGray
    Write-Host "Example search: #award_programs:`"AHA - J. Russell Major Prize`" and #mqg_lcc:false" -ForegroundColor DarkGray
    Write-Host "Example IDs: 5374,5375,5376" -ForegroundColor DarkGray
    Write-Host "Example award program: AHA - J. Russell Major Prize" -ForegroundColor DarkGray
    Write-Host ""

    $batchManifest = Read-ToolkitInput `
        -Prompt "Batch manifest CSV, blank to skip" `
        -Default ".\input\batch-$batchSlug.csv"

    $search = Read-ToolkitInput `
        -Prompt "Calibre search string, blank if using manifest/IDs only" `
        -Default ""

    $calibreIds = Read-ToolkitInput `
        -Prompt "Explicit Calibre IDs, comma-separated, blank to skip" `
        -Default ""

    $exactAwardProgram = Read-ToolkitInput `
        -Prompt "Exact Award Programs filter, blank to skip" `
        -Default ""

    if ([string]::IsNullOrWhiteSpace($batchManifest) -and
        [string]::IsNullOrWhiteSpace($search) -and
        [string]::IsNullOrWhiteSpace($calibreIds) -and
        [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
        throw "Provide a batch manifest, Calibre search string, explicit Calibre IDs, or an exact Award Programs filter."
    }

    $defaultOutput = ".\input\lcc-source-$batchSlug.tsv"

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output source TSV" `
        -Default $defaultOutput

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $exportScriptPath = Get-ToolkitScriptPath -ScriptName "Export-CalibreBatchForLcc.ps1"

    $exportArgs = @{
        OutputTsv = $outputTsv
    }

    if (-not [string]::IsNullOrWhiteSpace($batchManifest)) {
        $exportArgs.BatchManifest = $batchManifest
    }

    if (-not [string]::IsNullOrWhiteSpace($search)) {
        $exportArgs.Search = $search
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
        $exportArgs.CalibreIds = $calibreIds
    }

    if (-not [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
        $exportArgs.ExactAwardProgram = $exactAwardProgram
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $exportArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Running: Export-CalibreBatchForLcc.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $exportScriptPath @exportArgs

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





function Start-GuidedAuthorTitlePrep {
    Write-Host ""
    Write-Host "Guided Author/Title prep" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This guided workflow prepares an Author/Title cleanup batch." -ForegroundColor DarkGray
    Write-Host "It creates or reuses a batch manifest, exports an Author/Title source TSV, writes an MQG status report, and writes an operation summary." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "This workflow is read-only against Calibre. It does not modify Calibre metadata." -ForegroundColor Yellow
    Write-Host ""

    $defaultBatchName = ""
    if (-not [string]::IsNullOrWhiteSpace($script:CurrentBatchSlug)) {
        $defaultBatchName = $script:CurrentBatchSlug
    }

    $batchName = Read-ToolkitInput `
        -Prompt "Batch name, example andrew-carnegie-title-author" `
        -Default $defaultBatchName

    if ([string]::IsNullOrWhiteSpace($batchName)) {
        throw "Batch name is required."
    }

    $batchName = $batchName.Trim()

    if ($batchName -notmatch '^[a-z0-9][a-z0-9-]*$') {
        throw "Batch name must use lowercase letters, numbers, and hyphens only. Example: andrew-carnegie-title-author"
    }

    $script:CurrentBatchSlug = $batchName

    $defaultBatchManifest = ".\input\batch-$batchName.csv"
    $defaultExistingManifest = ""

    if (Test-Path $defaultBatchManifest) {
        $defaultExistingManifest = $defaultBatchManifest
    }

    Write-Host ""
    Write-Host "Batch selection" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Use an existing batch manifest, or provide a Calibre search string / explicit IDs so this workflow can create one." -ForegroundColor DarkGray
    Write-Host ""

    $existingBatchManifest = Read-ToolkitInput `
        -Prompt "Existing batch manifest CSV, blank to create a new one" `
        -Default $defaultExistingManifest

    $search = Read-ToolkitInput `
        -Prompt "Calibre search string, blank if using existing manifest or IDs only" `
        -Default ""

    $calibreIds = Read-ToolkitInput `
        -Prompt "Explicit Calibre IDs, comma-separated, blank to skip" `
        -Default ""

    $exactAwardProgram = Read-ToolkitInput `
        -Prompt "Exact Award Programs filter, blank to skip" `
        -Default ""

    if ([string]::IsNullOrWhiteSpace($existingBatchManifest) -and
        [string]::IsNullOrWhiteSpace($search) -and
        [string]::IsNullOrWhiteSpace($calibreIds)) {
        throw "Provide an existing batch manifest, a Calibre search string, or explicit Calibre IDs."
    }

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $batchManifest = if (-not [string]::IsNullOrWhiteSpace($existingBatchManifest)) {
        $existingBatchManifest
    }
    else {
        $defaultBatchManifest
    }

    $batchSelectionSummaryCsv = ".\reports\batch-$batchName-selection-summary.csv"
    $authorTitleSourceTsv = ".\input\author-title-cleanup-source-$batchName.tsv"
    $mqgStatusReportCsv = ".\reports\mqg-batch-status-$batchName.csv"
    $operationSummaryTxt = ".\reports\operation-summary-author-title-$batchName.txt"
    $authorTitleRulesDocPath = ".\docs\Author-Title-Normalization-Rules.md"
    $authorTitleRulesConfigPath = ".\config\author-title-normalization-rules.json"
    $authorTitleRulesProfileName = ""
    $authorTitleRulesProfileVersion = ""
    $authorTitleRulesProfileStatus = ""
    $authorTitleRulesLoadStatus = "Not loaded"
    $reviewChunksFolder = ".\input\review-chunks"
    $reviewChunkFiles = @()
    $createReviewChunksAnswer = "NO"
    $reviewChunkSize = 0
    $willCreateManifest = [string]::IsNullOrWhiteSpace($existingBatchManifest)

    $plannedOutputs = @(
        $authorTitleSourceTsv,
        $mqgStatusReportCsv,
        $operationSummaryTxt
    )

    if ($willCreateManifest) {
        $plannedOutputs += $batchManifest
        $plannedOutputs += $batchSelectionSummaryCsv
    }

    Write-Host ""
    if (Test-Path $authorTitleRulesConfigPath) {
        try {
            $authorTitleRules = Get-Content -Path $authorTitleRulesConfigPath -Raw | ConvertFrom-Json
            $authorTitleRulesProfileName = [string]$authorTitleRules.ProfileName
            $authorTitleRulesProfileVersion = [string]$authorTitleRules.ProfileVersion
            $authorTitleRulesProfileStatus = [string]$authorTitleRules.Status
            $authorTitleRulesLoadStatus = "Loaded"
        }
        catch {
            $authorTitleRulesLoadStatus = "Error loading rules config: " + $_.Exception.Message
        }
    }
    else {
        $authorTitleRulesLoadStatus = "Rules config not found"
    }

    Write-Host ""
    Write-Host "Loading Author/Title rules profile" -ForegroundColor Cyan
    Write-Host "Rules config: $authorTitleRulesConfigPath" -ForegroundColor DarkGray
    Write-Host "Rules doc:    $authorTitleRulesDocPath" -ForegroundColor DarkGray

    if ($authorTitleRulesLoadStatus -eq "Loaded") {
        Write-Host "Active rules: $authorTitleRulesProfileName $authorTitleRulesProfileVersion ($authorTitleRulesProfileStatus)" -ForegroundColor DarkGray
    }
    else {
        Write-Host "Rules profile status: $authorTitleRulesLoadStatus" -ForegroundColor Yellow
    }
    Write-Host "Plan preview" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This run will:" -ForegroundColor DarkGray

    if ($willCreateManifest) {
        Write-Host "1. Create a new batch manifest from the supplied search/IDs." -ForegroundColor DarkGray
    }
    else {
        Write-Host "1. Reuse the existing batch manifest." -ForegroundColor DarkGray
    }

    Write-Host "2. Preview the selected books." -ForegroundColor DarkGray
    Write-Host "3. Export an Author/Title source TSV." -ForegroundColor DarkGray
    Write-Host "4. Generate an MQG status/readiness report." -ForegroundColor DarkGray
    Write-Host "5. Write an operation summary." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "This run will NOT modify Calibre metadata." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Planned files:" -ForegroundColor DarkGray
    Write-Host "- Batch manifest:          $batchManifest" -ForegroundColor DarkGray
    Write-Host "- Author/Title source TSV: $authorTitleSourceTsv" -ForegroundColor DarkGray
    Write-Host "- MQG status report CSV:   $mqgStatusReportCsv" -ForegroundColor DarkGray
    Write-Host "- Operation summary TXT:   $operationSummaryTxt" -ForegroundColor DarkGray
    Write-Host ""

    $existingOutputs = @(
        foreach ($outputPath in $plannedOutputs) {
            if (-not [string]::IsNullOrWhiteSpace($outputPath) -and (Test-Path $outputPath)) {
                $outputPath
            }
        }
    )

    if ($existingOutputs.Count -gt 0) {
        Write-Host "Existing output files detected:" -ForegroundColor Yellow
        foreach ($existingOutput in $existingOutputs) {
            Write-Host "- $existingOutput" -ForegroundColor Yellow
        }
        Write-Host ""

        $overwriteAnswer = Read-ToolkitInput `
            -Prompt "Overwrite existing local output files? Type YES to overwrite" `
            -Default "NO"

        if ($overwriteAnswer -ne "YES") {
            throw "Guided workflow cancelled because output files already exist."
        }
    }

    $continueAnswer = Read-ToolkitInput `
        -Prompt "Continue with this read-only guided prep? Type YES to continue" `
        -Default "NO"

    if ($continueAnswer -ne "YES") {
        Write-Host "Guided Author/Title prep cancelled." -ForegroundColor Yellow
        Pause-Toolkit
        return
    }

    $manifestScriptPath = Get-ToolkitScriptPath -ScriptName "New-ToolkitBatchManifest.ps1"
    $authorTitleExportScriptPath = Get-ToolkitScriptPath -ScriptName "Export-CalibreBatchForAuthorTitleCleanup.ps1"
    $mqgStatusScriptPath = Get-ToolkitScriptPath -ScriptName "Show-MqgBatchStatus.ps1"

    if ($willCreateManifest) {
        $manifestArgs = @{
            BatchSlug = $batchName
            OutputCsv = $batchManifest
            ReportCsv = $batchSelectionSummaryCsv
            Overwrite = $true
        }

        if (-not [string]::IsNullOrWhiteSpace($search)) {
            $manifestArgs.Search = $search
        }

        if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
            $manifestArgs.CalibreIds = $calibreIds
        }

        if (-not [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
            $manifestArgs.ExactAwardProgram = $exactAwardProgram
        }

        if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
            $manifestArgs.LibraryPath = $libraryPath
        }

        Write-Host ""
        Write-Host "Step 1/4: Creating batch manifest" -ForegroundColor Cyan
        Write-Host ""

        & $manifestScriptPath @manifestArgs
    }
    else {
        if (-not (Test-Path $batchManifest)) {
            throw "Existing batch manifest was not found: $batchManifest"
        }

        Write-Host ""
        Write-Host "Step 1/4: Reusing existing batch manifest" -ForegroundColor Cyan
        Write-Host $batchManifest
    }

    $manifestRows = @(Import-Csv -Path $batchManifest)

    if ($manifestRows.Count -eq 0) {
        throw "Batch manifest contains no rows: $batchManifest"
    }

    Write-Host ""
    Write-Host "Batch preview" -ForegroundColor Cyan
    Write-Host "Books selected: $($manifestRows.Count)"
    Write-Host ""

    $manifestRows |
        Select-Object -First 20 CalibreId,Title,Authors,MqgTitleAuthor,MqgLcc,MqgMetadataComplete |
        Format-Table -AutoSize

    if ($manifestRows.Count -gt 20) {
        Write-Host "Preview limited to first 20 rows. Full batch is in: $batchManifest" -ForegroundColor DarkGray
    }

    Write-Host ""

    if ($manifestRows.Count -ge 101) {
        Write-Host "Large batch detected: $($manifestRows.Count) books." -ForegroundColor Yellow
        Write-Host "Recommended handling: keep the full batch manifest, but review Author/Title rows in smaller chunks." -ForegroundColor Yellow
        Write-Host ""

        $createReviewChunksAnswer = Read-ToolkitInput `
            -Prompt "Create Author/Title review chunk TSV files after export? YES or NO" `
            -Default "YES"

        $createReviewChunksAnswer = $createReviewChunksAnswer.Trim().ToUpperInvariant()

        if ($createReviewChunksAnswer -eq "YES") {
            $chunkSizeInput = Read-ToolkitInput `
                -Prompt "Review chunk size" `
                -Default "50"

            $parsedChunkSize = 0

            if (-not [int]::TryParse($chunkSizeInput, [ref]$parsedChunkSize)) {
                throw "Review chunk size must be a whole number."
            }

            if ($parsedChunkSize -lt 1) {
                throw "Review chunk size must be greater than zero."
            }

            $reviewChunkSize = $parsedChunkSize
        }
    }
    elseif ($manifestRows.Count -ge 26) {
        Write-Host "Medium batch detected: $($manifestRows.Count) books." -ForegroundColor DarkGray
        Write-Host "Read-only prep can continue safely. Consider reviewing the output TSV in smaller passes." -ForegroundColor DarkGray
        Write-Host ""
    }
    $continueAfterPreview = Read-ToolkitInput `
        -Prompt "Continue with Author/Title export and MQG status report? Type YES to continue" `
        -Default "YES"

    if ($continueAfterPreview -ne "YES") {
        Write-Host "Guided Author/Title prep stopped after batch preview." -ForegroundColor Yellow
        Pause-Toolkit
        return
    }

    $authorTitleArgs = @{
        BatchManifest = $batchManifest
        OutputTsv = $authorTitleSourceTsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $authorTitleArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Step 2/4: Exporting Author/Title source TSV" -ForegroundColor Cyan
    Write-Host ""

    & $authorTitleExportScriptPath @authorTitleArgs

    $authorTitleRows = @(Import-Csv -Path $authorTitleSourceTsv -Delimiter "`t")

    if ($createReviewChunksAnswer -eq "YES" -and $reviewChunkSize -gt 0) {
        Write-Host ""
        Write-Host "Creating Author/Title review chunks" -ForegroundColor Cyan
        Write-Host "Chunk size: $reviewChunkSize"
        Write-Host ""

        if (-not (Test-Path $reviewChunksFolder)) {
            New-Item -ItemType Directory -Force -Path $reviewChunksFolder | Out-Null
        }

        Get-ChildItem -Path $reviewChunksFolder -Filter "author-title-$batchName-*.tsv" -ErrorAction SilentlyContinue |
            Remove-Item -Force

        for ($startIndex = 0; $startIndex -lt $authorTitleRows.Count; $startIndex += $reviewChunkSize) {
            $endIndex = [Math]::Min($startIndex + $reviewChunkSize - 1, $authorTitleRows.Count - 1)

            $startRowNumber = $startIndex + 1
            $endRowNumber = $endIndex + 1

            $chunkPath = Join-Path $reviewChunksFolder ("author-title-$batchName-{0:D3}-{1:D3}.tsv" -f $startRowNumber, $endRowNumber)

            $chunkRows = @($authorTitleRows[$startIndex..$endIndex])

            $chunkRows |
                Export-Csv -Path $chunkPath -Delimiter "`t" -NoTypeInformation -Encoding UTF8

            $reviewChunkFiles += $chunkPath
        }

        Write-Host "Review chunk files created: $($reviewChunkFiles.Count)"
    }
    $mqgArgs = @{
        BatchManifest = $batchManifest
        ReportCsv = $mqgStatusReportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $mqgArgs.LibraryPath = $libraryPath
    }

    Write-Host ""
    Write-Host "Step 3/4: Writing MQG status report" -ForegroundColor Cyan
    Write-Host ""

    & $mqgStatusScriptPath @mqgArgs

    $authorTitleRows = @(Import-Csv -Path $authorTitleSourceTsv -Delimiter "`t")
    $mqgRows = @(Import-Csv -Path $mqgStatusReportCsv)

    $rowsBlocked = @($mqgRows | Where-Object { $_.StatusSummary -eq "Blocked" }).Count
    $rowsInProgress = @($mqgRows | Where-Object { $_.StatusSummary -eq "In Progress" }).Count
    $rowsReadyForMqg99 = @($mqgRows | Where-Object { $_.ReadyForMqg99 -eq "Yes" -and $_.MqgMetadataComplete -ne "Yes" }).Count
    $rowsMetadataComplete = @($mqgRows | Where-Object { $_.MqgMetadataComplete -eq "Yes" }).Count

    $rowCountWarning = ""
    if ($manifestRows.Count -ne $authorTitleRows.Count) {
        $rowCountWarning = "Author/Title source row count differs from manifest row count. This usually means the manifest contains duplicate Calibre IDs or unresolved records."
    }
    $summaryLines = @(
        "Guided Author/Title Prep Operation Summary",
        "===========================================",
        "",
        "Batch name: $batchName",
        "Created at: $(Get-Date -Format s)",
        "",
        "Calibre metadata modified: No",
        "Workflow type: Read-only guided prep",
        "",
        "Rules profile",
        "-------------",
        "Rules profile name: $authorTitleRulesProfileName",
        "Rules profile version: $authorTitleRulesProfileVersion",
        "Rules profile status: $authorTitleRulesProfileStatus",
        "Rules load status: $authorTitleRulesLoadStatus",
        "Rules doc: $authorTitleRulesDocPath",
        "Rules config: $authorTitleRulesConfigPath",
        "",
        "Inputs",
        "------",
        "Existing batch manifest: $existingBatchManifest",
        "Calibre search string: $search",
        "Explicit Calibre IDs: $calibreIds",
        "Exact Award Programs filter: $exactAwardProgram",
        "Optional library path: $libraryPath",
        "",
        "Files",
        "-----",
        "Batch manifest: $batchManifest",
        "Batch selection summary: $batchSelectionSummaryCsv",
        "Author/Title source TSV: $authorTitleSourceTsv",
        "MQG status report CSV: $mqgStatusReportCsv",
        "Operation summary TXT: $operationSummaryTxt",
        "",
        "Counts",
        "------",
        "Manifest rows: $($manifestRows.Count)",
        "Author/Title source rows: $($authorTitleRows.Count)",
        "MQG status rows: $($mqgRows.Count)",
        "Rows blocked: $rowsBlocked",
        "Rows in progress: $rowsInProgress",
        "Rows ready for MQG-99: $rowsReadyForMqg99",
        "Rows already metadata complete: $rowsMetadataComplete",
        "Review chunks created: $($reviewChunkFiles.Count)",
        "Review chunk size: $reviewChunkSize",
        "Review chunk folder: $reviewChunksFolder",
        "Row count warning: $rowCountWarning",
        "Recommended next action",
        "-----------------------",
        "Use the Author/Title source TSV as the AI review input, generate proposed changes according to the active rules profile, then run A2 to perform a dry run before any Author/Title metadata is applied.",
        "Only apply changes after reviewing the A2/A3 dry-run output.",
        "",
        "Safety note",
        "-----------",
        "This guided prep did not modify Calibre metadata."
    )

    if ($reviewChunkFiles.Count -gt 0) {
        $summaryLines += @(
            "",
            "Review chunks",
            "-------------"
        )

        foreach ($reviewChunkFile in $reviewChunkFiles) {
            $summaryLines += $reviewChunkFile
        }
    }
    $summaryFolder = Split-Path -Path $operationSummaryTxt -Parent
    if ($summaryFolder -and -not (Test-Path $summaryFolder)) {
        New-Item -ItemType Directory -Force -Path $summaryFolder | Out-Null
    }

    $summaryLines | Set-Content -Path $operationSummaryTxt -Encoding utf8

    Write-Host ""
    Write-Host "Step 4/4: Operation summary written" -ForegroundColor Cyan
    Write-Host $operationSummaryTxt
    Write-Host ""
    Write-Host "Guided Author/Title prep complete." -ForegroundColor Green
    Write-Host ""
    Write-Host "Files used/created/updated:"
    Write-Host "- $batchManifest"
    Write-Host "- $authorTitleSourceTsv"
    Write-Host "- $mqgStatusReportCsv"
    Write-Host "- $operationSummaryTxt"
    if ($reviewChunkFiles.Count -gt 0) {
        Write-Host "- $reviewChunksFolder ($($reviewChunkFiles.Count) review chunk files)"
    }
    Write-Host ""
    Write-Host "Recommended next action:"
    Write-Host "Use the Author/Title source TSV as AI review input, generate proposed changes using the active rules profile, then run A2/A3 for dry-run review."

    Pause-Toolkit
}

function Start-BatchManifest {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Batch: create batch manifest" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads Calibre and creates a stable batch manifest CSV." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Recommended workflow:" -ForegroundColor DarkGray
    Write-Host "1. Build/test the search in Calibre until the visible result set is correct." -ForegroundColor DarkGray
    Write-Host "2. Paste that Calibre search string here." -ForegroundColor DarkGray
    Write-Host "3. Reuse the manifest's CalibreId column for module runs." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "You may use a Calibre search string, explicit Calibre IDs, an ID file, or a combination." -ForegroundColor DarkGray
    Write-Host "If search and IDs are both supplied, IDs are treated as a local filter/intersection." -ForegroundColor DarkGray
    Write-Host ""

    $search = Read-ToolkitInput `
        -Prompt "Calibre search string, blank if using IDs/file only" `
        -Default ""

    $calibreIds = Read-ToolkitInput `
        -Prompt "Explicit Calibre IDs, comma-separated, blank to skip" `
        -Default ""

    $calibreIdFile = Read-ToolkitInput `
        -Prompt "Optional Calibre ID file, blank to skip" `
        -Default ""

    $exactAwardProgram = Read-ToolkitInput `
        -Prompt "Optional exact Award Programs filter, blank to skip" `
        -Default ""

    if ([string]::IsNullOrWhiteSpace($search) -and
        [string]::IsNullOrWhiteSpace($calibreIds) -and
        [string]::IsNullOrWhiteSpace($calibreIdFile)) {
        throw "Provide a Calibre search string, explicit Calibre IDs, or an ID file."
    }

    $outputCsv = Read-ToolkitInput `
        -Prompt "Output batch manifest CSV" `
        -Default ".\input\batch-$batchSlug.csv"

    $reportCsv = Read-ToolkitInput `
        -Prompt "Batch selection summary CSV" `
        -Default ".\reports\batch-$batchSlug-selection-summary.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $overwriteAnswer = Read-ToolkitInput `
        -Prompt "Overwrite existing manifest/report? Type YES to overwrite" `
        -Default "NO"

    $manifestScriptPath = Get-ToolkitScriptPath -ScriptName "New-ToolkitBatchManifest.ps1"

    $manifestArgs = @{
        BatchSlug = $batchSlug
        OutputCsv = $outputCsv
        ReportCsv = $reportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($search)) {
        $manifestArgs.Search = $search
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
        $manifestArgs.CalibreIds = $calibreIds
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreIdFile)) {
        $manifestArgs.CalibreIdFile = $calibreIdFile
    }

    if (-not [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
        $manifestArgs.ExactAwardProgram = $exactAwardProgram
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $manifestArgs.LibraryPath = $libraryPath
    }

    if ($overwriteAnswer -eq "YES") {
        $manifestArgs.Overwrite = $true
    }

    Write-Host ""
    Write-Host "Running: New-ToolkitBatchManifest.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $manifestScriptPath @manifestArgs

    Write-Host ""
    Write-Host "Next step:" -ForegroundColor Cyan
    Write-Host "Use the manifest CSV as the stable record of this batch."
    Write-Host "Current module scripts can use its CalibreId column manually until direct -BatchManifest support is added."

    Pause-Toolkit
}

function Start-LccMqgComplete {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "LCC: mark verified MQG complete" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This step can modify the Calibre custom field #mqg_lcc." -ForegroundColor Yellow
    Write-Host "Only rows from a clean LCC verification report are eligible." -ForegroundColor Yellow
    Write-Host ""

    $verifyReportCsv = Read-ToolkitInput `
        -Prompt "LCC verify report CSV" `
        -Default ".\reports\lcc-verify-$batchSlug.csv"

    $mqgReportCsv = Read-ToolkitInput `
        -Prompt "LCC MQG completion report CSV" `
        -Default ".\reports\lcc-mqg-complete-$batchSlug.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $preflightOnlyAnswer = Read-ToolkitInput `
        -Prompt "Preflight only? YES = no write, NO = mark complete" `
        -Default "YES"

    $mqgScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-LccMqgComplete.ps1"

    $mqgArgs = @{
        VerifyReportCsv = $verifyReportCsv
        MqgReportCsv    = $mqgReportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $mqgArgs.LibraryPath = $libraryPath
    }

    if ($preflightOnlyAnswer -ne "NO") {
        $mqgArgs.PreflightOnly = $true
    }

    Write-Host ""
    Write-Host "Running: Invoke-LccMqgComplete.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $mqgScriptPath @mqgArgs

    Pause-Toolkit
}

function Start-AuthorTitleExport {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: export source TSV" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads Calibre and creates a source TSV for author/title cleanup review." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Preferred workflow:" -ForegroundColor DarkGray
    Write-Host "1. Use B1 to create a stable batch manifest." -ForegroundColor DarkGray
    Write-Host "2. Use that manifest here to export the Author/Title source TSV." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "You may use a batch manifest, Calibre search string, explicit Calibre IDs, exact Award Programs value, or a combination." -ForegroundColor DarkGray
    Write-Host "If a search and manifest/IDs are both supplied, the manifest/IDs are treated as a local filter/intersection." -ForegroundColor DarkGray
    Write-Host "Example manifest: .\input\batch-$batchSlug.csv" -ForegroundColor DarkGray
    Write-Host "Example search: title:false or author:false" -ForegroundColor DarkGray
    Write-Host "Example IDs: 4040,4048,4049" -ForegroundColor DarkGray
    Write-Host "Example award program: AHA - J. Russell Major Prize" -ForegroundColor DarkGray
    Write-Host ""

    $batchManifest = Read-ToolkitInput `
        -Prompt "Batch manifest CSV, blank to skip" `
        -Default ".\input\batch-$batchSlug.csv"

    $search = Read-ToolkitInput `
        -Prompt "Calibre search string, blank if using manifest/IDs only" `
        -Default ""

    $calibreIds = Read-ToolkitInput `
        -Prompt "Explicit Calibre IDs, comma-separated, blank to skip" `
        -Default ""

    $exactAwardProgram = Read-ToolkitInput `
        -Prompt "Exact Award Programs value, blank to skip" `
        -Default ""

    if ([string]::IsNullOrWhiteSpace($batchManifest) -and
        [string]::IsNullOrWhiteSpace($search) -and
        [string]::IsNullOrWhiteSpace($calibreIds) -and
        [string]::IsNullOrWhiteSpace($exactAwardProgram)) {
        throw "Provide a batch manifest, Calibre search string, explicit Calibre IDs, or an exact Award Programs value."
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

    if (-not [string]::IsNullOrWhiteSpace($batchManifest)) {
        $exportArgs.BatchManifest = $batchManifest
    }

    if (-not [string]::IsNullOrWhiteSpace($search)) {
        $exportArgs.Search = $search
    }

    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
        $exportArgs.CalibreIds = $calibreIds
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


function Start-AuthorTitleMqgComplete {
    $batchSlug = Read-BatchSlug

    Write-Host ""
    Write-Host "Author/Title: mark verified MQG complete" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This step can modify the Calibre custom field #mqg_title_author." -ForegroundColor Yellow
    Write-Host "Only rows with VerificationStatus = Verified are eligible." -ForegroundColor Yellow
    Write-Host ""

    $verifyReportCsv = Read-ToolkitInput `
        -Prompt "Verify report CSV" `
        -Default ".\reports\author-title-cleanup-verify-$batchSlug.csv"

    $mqgReportCsv = Read-ToolkitInput `
        -Prompt "MQG completion report CSV" `
        -Default ".\reports\author-title-cleanup-mqg-complete-$batchSlug.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $preflightOnlyAnswer = Read-ToolkitInput `
        -Prompt "Preflight only? YES = no write, NO = mark complete" `
        -Default "YES"

    $mqgScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-AuthorTitleMqgComplete.ps1"

    $mqgArgs = @{
        VerifyReportCsv = $verifyReportCsv
        MqgReportCsv = $mqgReportCsv
    }

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $mqgArgs.LibraryPath = $libraryPath
    }

    if ($preflightOnlyAnswer -ne "NO") {
        $mqgArgs.PreflightOnly = $true
    }

    Write-Host ""
    Write-Host "Running: Invoke-AuthorTitleMqgComplete.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $mqgScriptPath @mqgArgs

    Pause-Toolkit
}

function Start-IdentifierInventoryExport {
    Write-Host ""
    Write-Host "Identifiers: export inventory" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads Calibre and creates a read-only identifier inventory." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output inventory TSV" `
        -Default ".\input\identifier-inventory-source.tsv"

    $coverageSummaryCsv = Read-ToolkitInput `
        -Prompt "Coverage summary CSV" `
        -Default ".\reports\identifier-coverage-summary.csv"

    $identifierTypeCountsCsv = Read-ToolkitInput `
        -Prompt "Identifier type counts CSV" `
        -Default ".\reports\identifier-type-counts.csv"

    $weirdValuesCsv = Read-ToolkitInput `
        -Prompt "Weird values CSV" `
        -Default ".\reports\identifier-weird-values.csv"

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $scriptPath = Get-ToolkitScriptPath -ScriptName "Export-IdentifierInventory.ps1"

    Write-Host ""
    Write-Host "Running: Export-IdentifierInventory.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $scriptPath `
        -OutputTsv $outputTsv `
        -CoverageSummaryCsv $coverageSummaryCsv `
        -IdentifierTypeCountsCsv $identifierTypeCountsCsv `
        -WeirdValuesCsv $weirdValuesCsv `
        -LibraryPath $libraryPath

    Pause-Toolkit
}

function Start-IdentifierInventoryDiagnostics {
    Write-Host ""
    Write-Host "Identifiers: write diagnostics" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads the identifier inventory files and writes focused MQG-02 diagnostic reports." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $inventoryTsv = Read-ToolkitInput `
        -Prompt "Inventory TSV" `
        -Default ".\input\identifier-inventory-source.tsv"

    $identifierTypeCountsCsv = Read-ToolkitInput `
        -Prompt "Identifier type counts CSV" `
        -Default ".\reports\identifier-type-counts.csv"

    $missingCoreCsv = Read-ToolkitInput `
        -Prompt "Missing core report CSV" `
        -Default ".\reports\identifier-missing-core.csv"

    $suspiciousTypesCsv = Read-ToolkitInput `
        -Prompt "Suspicious types report CSV" `
        -Default ".\reports\identifier-suspicious-types.csv"

    $duplicateIsbnCsv = Read-ToolkitInput `
        -Prompt "Duplicate ISBN report CSV" `
        -Default ".\reports\identifier-duplicate-isbn.csv"

    $duplicateGoodreadsCsv = Read-ToolkitInput `
        -Prompt "Duplicate Goodreads report CSV" `
        -Default ".\reports\identifier-duplicate-goodreads.csv"

    $duplicateAmazonCsv = Read-ToolkitInput `
        -Prompt "Duplicate Amazon/ASIN report CSV" `
        -Default ".\reports\identifier-duplicate-amazon.csv"

    $mqg02CandidateSummaryCsv = Read-ToolkitInput `
        -Prompt "MQG-02 candidate summary CSV" `
        -Default ".\reports\identifier-mqg02-candidate-summary.csv"

    $scriptPath = Get-ToolkitScriptPath -ScriptName "Write-IdentifierInventoryDiagnostics.ps1"

    Write-Host ""
    Write-Host "Running: Write-IdentifierInventoryDiagnostics.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $scriptPath `
        -InventoryTsv $inventoryTsv `
        -IdentifierTypeCountsCsv $identifierTypeCountsCsv `
        -MissingCoreCsv $missingCoreCsv `
        -SuspiciousTypesCsv $suspiciousTypesCsv `
        -DuplicateIsbnCsv $duplicateIsbnCsv `
        -DuplicateGoodreadsCsv $duplicateGoodreadsCsv `
        -DuplicateAmazonCsv $duplicateAmazonCsv `
        -Mqg02CandidateSummaryCsv $mqg02CandidateSummaryCsv

    Pause-Toolkit
}
function Start-IdentifierProposalWorksheet {
    Write-Host ""
    Write-Host "Identifiers: generate proposal worksheet" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step reads the MQG-02 candidate diagnostics report and creates a read-only proposal worksheet." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $candidateSummaryCsv = Read-ToolkitInput `
        -Prompt "MQG-02 candidate summary CSV" `
        -Default ".\reports\identifier-mqg02-candidate-summary.csv"

    $proposalTsv = Read-ToolkitInput `
        -Prompt "Proposal worksheet TSV" `
        -Default ".\input\identifier-proposal-worksheet.tsv"

    $proposalSummaryCsv = Read-ToolkitInput `
        -Prompt "Proposal summary CSV" `
        -Default ".\reports\identifier-proposal-summary.csv"

    $scriptPath = Get-ToolkitScriptPath -ScriptName "New-IdentifierProposalWorksheet.ps1"

    Write-Host ""
    Write-Host "Running: New-IdentifierProposalWorksheet.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $scriptPath `
        -CandidateSummaryCsv $candidateSummaryCsv `
        -ProposalTsv $proposalTsv `
        -ProposalSummaryCsv $proposalSummaryCsv

    Pause-Toolkit
}
function Start-IdentifierProposalValidation {
    Write-Host ""
    Write-Host "Identifiers: validate proposal worksheet" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This step validates the identifier proposal worksheet and writes MQG-02 completion preflight reports." -ForegroundColor DarkGray
    Write-Host "It does not modify Calibre metadata." -ForegroundColor DarkGray
    Write-Host ""

    $proposalTsv = Read-ToolkitInput `
        -Prompt "Proposal worksheet TSV" `
        -Default ".\input\identifier-proposal-worksheet.tsv"

    $validationCsv = Read-ToolkitInput `
        -Prompt "Validation report CSV" `
        -Default ".\reports\identifier-proposal-validation.csv"

    $validationSummaryCsv = Read-ToolkitInput `
        -Prompt "Validation summary CSV" `
        -Default ".\reports\identifier-proposal-validation-summary.csv"

    $scriptPath = Get-ToolkitScriptPath -ScriptName "Test-IdentifierProposalWorksheet.ps1"

    Write-Host ""
    Write-Host "Running: Test-IdentifierProposalWorksheet.ps1" -ForegroundColor Cyan
    Write-Host ""

    & $scriptPath `
        -ProposalTsv $proposalTsv `
        -ValidationCsv $validationCsv `
        -ValidationSummaryCsv $validationSummaryCsv

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
                "12" { Start-LccMqgComplete }
                "13" {
                    $batchSlug = Read-BatchSlug

                    Write-Host ""
                    Write-Host "MQG: show batch status / readiness report" -ForegroundColor Yellow
                    Write-Host ""
                    Write-Host "This operation is read-only and does not modify Calibre metadata." -ForegroundColor Yellow
                    Write-Host ""
                    Write-Host "Preferred workflow:" -ForegroundColor DarkGray
                    Write-Host "1. Use B1 to create a stable batch manifest." -ForegroundColor DarkGray
                    Write-Host "2. Use that manifest here to review current MQG readiness." -ForegroundColor DarkGray
                    Write-Host ""
                    Write-Host "You may use a batch manifest, another input CSV with CalibreId, explicit Calibre IDs, or a combination." -ForegroundColor DarkGray
                    Write-Host ""

                    $batchManifest = Read-ToolkitInput `
                        -Prompt "Batch manifest CSV, blank to skip" `
                        -Default ".\input\batch-$batchSlug.csv"

                    $calibreIds = Read-ToolkitInput `
                        -Prompt "Comma-separated Calibre IDs, blank to skip" `
                        -Default ""

                    $inputCsv = Read-ToolkitInput `
                        -Prompt "Optional non-manifest input CSV with CalibreId column, blank to skip" `
                        -Default ""

                    if ([string]::IsNullOrWhiteSpace($batchManifest) -and
                        [string]::IsNullOrWhiteSpace($calibreIds) -and
                        [string]::IsNullOrWhiteSpace($inputCsv)) {
                        throw "Provide a batch manifest, explicit Calibre IDs, or an input CSV with a CalibreId column."
                    }

                    $reportCsv = Read-ToolkitInput `
                        -Prompt "MQG batch status report CSV" `
                        -Default ".\reports\mqg-batch-status-$batchSlug.csv"

                    $libraryPath = Read-ToolkitInput `
                        -Prompt "Optional Calibre library path, blank for default" `
                        -Default ""

                    $statusScriptPath = Get-ToolkitScriptPath -ScriptName "Show-MqgBatchStatus.ps1"

                    $statusArgs = @{
                        ReportCsv = $reportCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($batchManifest)) {
                        $statusArgs.BatchManifest = $batchManifest
                    }

                    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
                        $statusArgs.CalibreIds = $calibreIds
                    }

                    if (-not [string]::IsNullOrWhiteSpace($inputCsv)) {
                        $statusArgs.InputCsv = $inputCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
                        $statusArgs.LibraryPath = $libraryPath
                    }

                    Write-Host ""
                    Write-Host "Running: Show-MqgBatchStatus.ps1" -ForegroundColor Cyan
                    Write-Host ""

                    & $statusScriptPath @statusArgs

                    Pause-Toolkit
                }
                "G1" { Start-GuidedAuthorTitlePrep }
                "B1" { Start-BatchManifest }
                "A1" { Start-AuthorTitleExport }
                "A2" { Start-AuthorTitleDryRun }
                "A3" { Start-AuthorTitleSummary }
                "A4" { Start-AuthorTitleApply }
                "A5" { Start-AuthorTitleVerify }
                "A6" { Start-AuthorTitleMqgComplete }
                "C1" { Start-CommentsExport }
                "C2" { Start-CommentsDryRun }
                "C3" { Start-CommentsSummary }
                "C4" { Start-CommentsReviewHtml }
                "C5" { Start-CommentsApply }
                "C6" { Start-CommentsVerify }
                "C7" {
                    $batchSlug = Read-BatchSlug

                    Write-Host ""
                    Write-Host "Comments: mark verified MQG complete" -ForegroundColor Yellow
                    Write-Host ""
                    Write-Host "This step can modify the Calibre custom field #mqg_description." -ForegroundColor Yellow
                    Write-Host "Only rows from a clean Comments verification report are eligible." -ForegroundColor Yellow
                    Write-Host ""

                    $verifyReportCsv = Read-ToolkitInput `
                        -Prompt "Comments verify report CSV" `
                        -Default ".\reports\comments-verify-$batchSlug.csv"

                    $mqgReportCsv = Read-ToolkitInput `
                        -Prompt "Comments MQG completion report CSV" `
                        -Default ".\reports\comments-mqg-complete-$batchSlug.csv"

                    $libraryPath = Read-ToolkitInput `
                        -Prompt "Optional Calibre library path, blank for default" `
                        -Default ""

                    $preflightOnlyAnswer = Read-ToolkitInput `
                        -Prompt "Preflight only? YES = no write, NO = mark complete" `
                        -Default "YES"

                    $mqgScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-CommentsMqgComplete.ps1"

                    $mqgArgs = @{
                        VerifyReportCsv = $verifyReportCsv
                        MqgReportCsv    = $mqgReportCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
                        $mqgArgs.LibraryPath = $libraryPath
                    }

                    if ($preflightOnlyAnswer -ne "NO") {
                        $mqgArgs.PreflightOnly = $true
                    }

                    Write-Host ""
                    Write-Host "Running: Invoke-CommentsMqgComplete.ps1" -ForegroundColor Cyan
                    Write-Host ""

                    & $mqgScriptPath @mqgArgs

                    Pause-Toolkit
                }
                "I1" { Start-IdentifierInventoryExport }
                "I2" { Start-IdentifierInventoryDiagnostics }
                "I3" { Start-IdentifierProposalWorksheet }
                "I4" { Start-IdentifierProposalValidation }
                "W1" {
                    $batchSlug = Read-BatchSlug

                    Write-Host ""
                    Write-Host "Awards: mark reviewed MQG complete" -ForegroundColor Yellow
                    Write-Host ""
                    Write-Host "This step can modify the Calibre custom field #mqg_awards." -ForegroundColor Yellow
                    Write-Host "Use this only after award metadata has been manually reviewed." -ForegroundColor Yellow
                    Write-Host ""

                    $calibreIds = Read-ToolkitInput `
                        -Prompt "Comma-separated Calibre IDs, blank if using CSV" `
                        -Default ""

                    $inputCsv = Read-ToolkitInput `
                        -Prompt "Optional input CSV with CalibreId column" `
                        -Default ""

                    $mqgReportCsv = Read-ToolkitInput `
                        -Prompt "Awards MQG completion report CSV" `
                        -Default ".\reports\awards-mqg-complete-$batchSlug.csv"

                    $libraryPath = Read-ToolkitInput `
                        -Prompt "Optional Calibre library path, blank for default" `
                        -Default ""

                    $allowNoAwardsAnswer = Read-ToolkitInput `
                        -Prompt "Allow no-awards / not-applicable rows? YES or NO" `
                        -Default "NO"

                    $preflightOnlyAnswer = Read-ToolkitInput `
                        -Prompt "Preflight only? YES = no write, NO = mark complete" `
                        -Default "YES"

                    $mqgScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-AwardsMqgComplete.ps1"

                    $mqgArgs = @{
                        MqgReportCsv = $mqgReportCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
                        $mqgArgs.CalibreIds = $calibreIds
                    }

                    if (-not [string]::IsNullOrWhiteSpace($inputCsv)) {
                        $mqgArgs.InputCsv = $inputCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
                        $mqgArgs.LibraryPath = $libraryPath
                    }

                    if ($allowNoAwardsAnswer -eq "YES") {
                        $mqgArgs.AllowNoAwards = $true
                    }

                    if ($preflightOnlyAnswer -ne "NO") {
                        $mqgArgs.PreflightOnly = $true
                    }

                    Write-Host ""
                    Write-Host "Running: Invoke-AwardsMqgComplete.ps1" -ForegroundColor Cyan
                    Write-Host ""

                    & $mqgScriptPath @mqgArgs

                    Pause-Toolkit
                }
                "W2" {
                    $batchSlug = Read-BatchSlug

                    Write-Host ""
                    Write-Host "Cover: mark reviewed MQG complete" -ForegroundColor Yellow
                    Write-Host ""
                    Write-Host "This step can modify the Calibre custom field #mqg_cover." -ForegroundColor Yellow
                    Write-Host "Use this only after the cover has been manually reviewed." -ForegroundColor Yellow
                    Write-Host ""

                    $calibreIds = Read-ToolkitInput `
                        -Prompt "Comma-separated Calibre IDs, blank if using CSV" `
                        -Default ""

                    $inputCsv = Read-ToolkitInput `
                        -Prompt "Optional input CSV with CalibreId column" `
                        -Default ""

                    $mqgReportCsv = Read-ToolkitInput `
                        -Prompt "Cover MQG completion report CSV" `
                        -Default ".\reports\cover-mqg-complete-$batchSlug.csv"

                    $libraryPath = Read-ToolkitInput `
                        -Prompt "Optional Calibre library path, blank for default" `
                        -Default ""

                    $allowNoCoverAnswer = Read-ToolkitInput `
                        -Prompt "Allow missing/no-cover rows? YES or NO" `
                        -Default "NO"

                    $preflightOnlyAnswer = Read-ToolkitInput `
                        -Prompt "Preflight only? YES = no write, NO = mark complete" `
                        -Default "YES"

                    $mqgScriptPath = Get-ToolkitScriptPath -ScriptName "Invoke-CoverMqgComplete.ps1"

                    $mqgArgs = @{
                        MqgReportCsv = $mqgReportCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($calibreIds)) {
                        $mqgArgs.CalibreIds = $calibreIds
                    }

                    if (-not [string]::IsNullOrWhiteSpace($inputCsv)) {
                        $mqgArgs.InputCsv = $inputCsv
                    }

                    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
                        $mqgArgs.LibraryPath = $libraryPath
                    }

                    if ($allowNoCoverAnswer -eq "YES") {
                        $mqgArgs.AllowNoCover = $true
                    }

                    if ($preflightOnlyAnswer -ne "NO") {
                        $mqgArgs.PreflightOnly = $true
                    }

                    Write-Host ""
                    Write-Host "Running: Invoke-CoverMqgComplete.ps1" -ForegroundColor Cyan
                    Write-Host ""

                    & $mqgScriptPath @mqgArgs

                    Pause-Toolkit
                }
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








































