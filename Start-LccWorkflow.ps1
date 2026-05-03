<#
.SYNOPSIS
Interactive launcher for the Calibre LCC Toolkit.

.DESCRIPTION
Provides a menu-driven workflow for the Calibre LCC Toolkit.

This launcher does not directly modify Calibre metadata. It calls the underlying
toolkit scripts. Metadata changes only occur through Invoke-LccImportApply.ps1,
which requires the -Apply switch and an explicit APPLY confirmation when updates
are pending.
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

function Pause-Toolkit {
    Write-Host ""
    Read-Host "Press Enter to continue" | Out-Null
}

function Invoke-ToolkitScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptName,

        [string[]]$Arguments = @()
    )

    $scriptPath = Join-Path $script:ToolkitRoot "scripts\$ScriptName"

    if (-not (Test-Path $scriptPath)) {
        throw "Toolkit script not found: $scriptPath"
    }

    Write-Host ""
    Write-Host "Running: $ScriptName" -ForegroundColor Cyan
    Write-Host ""

    & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @Arguments
}

function Get-DefaultImportPath {
    param([string]$BatchName)

    $canonicalPath = ".\input\lcc-import-$BatchName-canonical.tsv"
    $standardPath = ".\input\lcc-import-$BatchName.tsv"

    $canonicalFullPath = Resolve-ToolkitPath -Path $canonicalPath -ToolkitRoot $script:ToolkitRoot

    if (Test-Path $canonicalFullPath) {
        return $canonicalPath
    }

    return $standardPath
}

function Show-Header {
    Clear-Host
    Write-Host "Calibre LCC Toolkit v0.2" -ForegroundColor Cyan
    Write-Host "========================"
    Write-Host ""
    Write-Host "Toolkit root:"
    Write-Host $script:ToolkitRoot
    Write-Host ""
}

function Show-Menu {
    Show-Header

    Write-Host "1. Run toolkit health check"
    Write-Host "2. Export source batch from Calibre"
    Write-Host "3. Canonicalize completed import TSV"
    Write-Host "4. Run dry-run import"
    Write-Host "5. Apply verified import"
    Write-Host "6. Verify final state"
    Write-Host "7. Write batch summary"
    Write-Host "8. Open input folder"
    Write-Host "9. Open reports folder"
    Write-Host "10. Open workflow documentation"
    Write-Host "11. Show Git status"
    Write-Host "0. Exit"
    Write-Host ""
}

function Start-HealthCheck {
    $defaultReport = ".\reports\lcc-toolkit-health.txt"

    $reportTxt = Read-ToolkitInput `
        -Prompt "Health report path" `
        -Default $defaultReport

    Invoke-ToolkitScript `
        -ScriptName "Test-LccToolkitHealth.ps1" `
        -Arguments @(
            "-ReportTxt", $reportTxt
        )

    Pause-Toolkit
}

function Start-ExportSourceBatch {
    $batchName = Read-RequiredInput "Batch name, example herbert-baxter-adams"
    $search = Read-RequiredInput "Calibre search string"

    $defaultOutput = ".\input\lcc-source-$batchName.tsv"

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output source TSV" `
        -Default $defaultOutput

    $libraryPath = Read-ToolkitInput `
        -Prompt "Optional Calibre library path, blank for default" `
        -Default ""

    $args = @(
        "-Search", $search,
        "-OutputTsv", $outputTsv
    )

    if (-not [string]::IsNullOrWhiteSpace($libraryPath)) {
        $args += @("-LibraryPath", $libraryPath)
    }

    Invoke-ToolkitScript `
        -ScriptName "Export-CalibreBatchForLcc.ps1" `
        -Arguments $args

    Pause-Toolkit
}

function Start-CanonicalizeImport {
    $batchName = Read-RequiredInput "Batch name, example herbert-baxter-adams"

    $defaultInput = ".\input\lcc-import-$batchName.tsv"
    $defaultOutput = ".\input\lcc-import-$batchName-canonical.tsv"
    $defaultReport = ".\reports\lcc-canonicalize-$batchName.csv"

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input import TSV" `
        -Default $defaultInput

    $outputTsv = Read-ToolkitInput `
        -Prompt "Output canonical TSV" `
        -Default $defaultOutput

    $reportCsv = Read-ToolkitInput `
        -Prompt "Canonicalization report CSV" `
        -Default $defaultReport

    $overwriteAnswer = Read-ToolkitInput `
        -Prompt "Overwrite existing output/report? Type YES to overwrite" `
        -Default "NO"

    $args = @(
        "-InputTsv", $inputTsv,
        "-OutputTsv", $outputTsv,
        "-ReportCsv", $reportCsv
    )

    if ($overwriteAnswer -eq "YES") {
        $args += "-Overwrite"
    }

    Invoke-ToolkitScript `
        -ScriptName "Convert-LccImportToCanonical.ps1" `
        -Arguments $args

    Pause-Toolkit
}

function Start-DryRunImport {
    $batchName = Read-RequiredInput "Batch name, example herbert-baxter-adams"

    $defaultInput = Get-DefaultImportPath -BatchName $batchName
    $defaultReport = ".\reports\lcc-dryrun-$batchName.csv"

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input import TSV" `
        -Default $defaultInput

    $reportCsv = Read-ToolkitInput `
        -Prompt "Dry-run report CSV" `
        -Default $defaultReport

    Invoke-ToolkitScript `
        -ScriptName "Test-LccImportDryRun.ps1" `
        -Arguments @(
            "-InputTsv", $inputTsv,
            "-ReportCsv", $reportCsv
        )

    Pause-Toolkit
}

function Start-ApplyImport {
    $batchName = Read-RequiredInput "Batch name, example herbert-baxter-adams"

    $defaultDryRunReport = ".\reports\lcc-dryrun-$batchName.csv"
    $defaultApplyReport = ".\reports\lcc-apply-$batchName.csv"

    $dryRunReportCsv = Read-ToolkitInput `
        -Prompt "Dry-run report CSV" `
        -Default $defaultDryRunReport

    $applyReportCsv = Read-ToolkitInput `
        -Prompt "Apply report CSV" `
        -Default $defaultApplyReport

    Write-Host ""
    Write-Host "The apply script can modify Calibre metadata." -ForegroundColor Yellow
    Write-Host "It will run its own preflight and require APPLY confirmation if updates are pending."
    Write-Host ""

    $continueAnswer = Read-ToolkitInput `
        -Prompt "Continue to apply script? Type YES to continue" `
        -Default "NO"

    if ($continueAnswer -ne "YES") {
        Write-Host "Apply step cancelled." -ForegroundColor Yellow
        Pause-Toolkit
        return
    }

    Invoke-ToolkitScript `
        -ScriptName "Invoke-LccImportApply.ps1" `
        -Arguments @(
            "-DryRunReportCsv", $dryRunReportCsv,
            "-ApplyReportCsv", $applyReportCsv,
            "-Apply"
        )

    Pause-Toolkit
}

function Start-VerifyFinalState {
    $batchName = Read-RequiredInput "Batch name, example herbert-baxter-adams"

    $defaultInput = Get-DefaultImportPath -BatchName $batchName
    $defaultReport = ".\reports\lcc-verify-$batchName.csv"

    $inputTsv = Read-ToolkitInput `
        -Prompt "Input import TSV" `
        -Default $defaultInput

    $reportCsv = Read-ToolkitInput `
        -Prompt "Verify report CSV" `
        -Default $defaultReport

    Invoke-ToolkitScript `
        -ScriptName "Test-LccImportDryRun.ps1" `
        -Arguments @(
            "-InputTsv", $inputTsv,
            "-ReportCsv", $reportCsv
        )

    Pause-Toolkit
}

function Start-WriteBatchSummary {
    $batchName = Read-RequiredInput "Batch name, example herbert-baxter-adams"

    $verifyReport = ".\reports\lcc-verify-$batchName.csv"
    $dryRunReport = ".\reports\lcc-dryrun-$batchName.csv"

    $verifyFullPath = Resolve-ToolkitPath -Path $verifyReport -ToolkitRoot $script:ToolkitRoot

    if (Test-Path $verifyFullPath) {
        $defaultReport = $verifyReport
    }
    else {
        $defaultReport = $dryRunReport
    }

    $defaultSummary = ".\reports\lcc-summary-$batchName.txt"

    $reportCsv = Read-ToolkitInput `
        -Prompt "Report CSV to summarize" `
        -Default $defaultReport

    $summaryTxt = Read-ToolkitInput `
        -Prompt "Summary TXT output" `
        -Default $defaultSummary

    Invoke-ToolkitScript `
        -ScriptName "Write-LccBatchSummary.ps1" `
        -Arguments @(
            "-ReportCsv", $reportCsv,
            "-SummaryTxt", $summaryTxt,
            "-BatchName", $batchName
        )

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

$configFullPath = Resolve-ToolkitPath -Path $ConfigPath -ToolkitRoot $script:ToolkitRoot

if (-not (Test-Path $configFullPath)) {
    throw "Config file not found: $configFullPath"
}

$config = Get-Content $configFullPath -Raw | ConvertFrom-Json

do {
    Show-Menu
    $choice = Read-Host "Select an option"

    try {
        switch ($choice) {
            "1"  { Start-HealthCheck }
            "2"  { Start-ExportSourceBatch }
            "3"  { Start-CanonicalizeImport }
            "4"  { Start-DryRunImport }
            "5"  { Start-ApplyImport }
            "6"  { Start-VerifyFinalState }
            "7"  { Start-WriteBatchSummary }
            "8"  { Open-ToolkitFolder -FolderPath ".\input" }
            "9"  { Open-ToolkitFolder -FolderPath ".\reports" }
            "10" { Open-WorkflowDocumentation }
            "11" { Show-GitStatus }
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