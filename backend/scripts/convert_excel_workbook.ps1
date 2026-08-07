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
$wps = $null
$workbook = $null
$converted = $false
$excelFailure = ""

try {
    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $excel.AskToUpdateLinks = $false
        $excel.EnableEvents = $false
        $excel.AutomationSecurity = 3

        try {
            $workbook = $excel.Workbooks.Open(
                $InputPath,
                0,
                $false
            )
        } catch {
            $openFailure = $_.Exception.Message
            if ($openFailure -match "检测到此文件存在一个问题|problem with this file") {
                throw
            }
            # For ordinary corruption errors Excel can sometimes safely repair
            # the file. Office File Validation failures are deliberately not
            # repaired here; they use the WPS-native fallback below instead.
            $xlRepairFile = 1
            $workbook = $excel.Workbooks.Open(
                $InputPath,
                0,
                $false,
                5,
                "",
                "",
                $true,
                2,
                "",
                $false,
                $false,
                0,
                $false,
                $true,
                $xlRepairFile
            )
        }

        if ($Mode -eq "to-xls") {
            if ([string]::IsNullOrEmpty($Password)) {
                $workbook.SaveAs($OutputPath, 56)
            } else {
                $workbook.SaveAs($OutputPath, 56, $Password)
            }
        } else {
            $workbook.SaveAs($OutputPath, 51)
        }
        $converted = $true
    } catch {
        $excelFailure = $_.Exception.Message
    } finally {
        if ($null -ne $workbook) {
            try { $workbook.Close($false) } catch {}
            $workbook = $null
        }
        if ($null -ne $excel) {
            try { $excel.Quit() } catch {}
            $excel = $null
        }
    }

    if (-not $converted) {
        try {
            # WPS-generated BIFF workbooks can contain valid WPS extension
            # records that Office File Validation rejects. Use WPS's native
            # COM server as a fallback while keeping macros forced disabled.
            $wps = New-Object -ComObject Ket.Application
            $wps.Visible = $false
            $wps.DisplayAlerts = $false
            $wps.EnableEvents = $false
            $wps.AutomationSecurity = 3
            $workbook = $wps.Workbooks.Open($InputPath, 0, $false)

            if ($Mode -eq "to-xls") {
                if ([string]::IsNullOrEmpty($Password)) {
                    $workbook.SaveAs($OutputPath, 56)
                } else {
                    $workbook.SaveAs($OutputPath, 56, $Password)
                }
            } else {
                $workbook.SaveAs($OutputPath, 51)
            }
            $converted = $true
        } catch {
            $wpsFailure = $_.Exception.Message
            throw (
                "Microsoft Excel 转换失败：{0}；WPS 表格后备转换也失败：{1}" -f
                $excelFailure,
                $wpsFailure
            )
        } finally {
            if ($null -ne $workbook) {
                try { $workbook.Close($false) } catch {}
                $workbook = $null
            }
            if ($null -ne $wps) {
                try { $wps.Quit() } catch {}
                $wps = $null
            }
        }
    }
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
    if ($null -ne $wps) {
        try { $wps.Quit() } catch {}
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
