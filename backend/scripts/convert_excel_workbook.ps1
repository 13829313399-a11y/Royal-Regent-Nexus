param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("to-xlsx", "to-xls")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$excel = $null
$workbook = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $excel.EnableEvents = $false
    $excel.AutomationSecurity = 3

    $workbook = $excel.Workbooks.Open(
        $InputPath,
        0,
        $false
    )

    if ($Mode -eq "to-xls") {
        if ([string]::IsNullOrEmpty($Password)) {
            $workbook.SaveAs($OutputPath, 56)
        } else {
            $workbook.SaveAs($OutputPath, 56, $Password)
        }
    } else {
        $workbook.SaveAs($OutputPath, 51)
    }

    $workbook.Close($false)
    $workbook = $null
    $excel.Quit()
    $excel = $null
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($null -ne $workbook) {
        try { $workbook.Close($false) } catch {}
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch {}
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
