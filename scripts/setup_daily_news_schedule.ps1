param(
    [string]$Time = "05:00",
    [switch]$Status,
    [switch]$Remove
)

$TaskName = "HaizFlow_DailyWorldNews"
$WorkspaceRoot = (Resolve-Path "$PSScriptRoot\..").Path
$PythonExe = Join-Path $WorkspaceRoot ".venv\Scripts\python.exe"
$ScriptPy = Join-Path $WorkspaceRoot "scripts\run_daily_news.py"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python.exe"
}

if ($Status) {
    Write-Host ""
    Write-Host "=== KIỂM TRA TRẠNG THÁI LỊCH CHẠY WINDOWS ===" -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host " Tên tác vụ       : $TaskName" -ForegroundColor Green
        Write-Host " Trạng thái       : $($task.State)"
        Write-Host " Lần chạy gần nhất: $($info.LastRunTime) (Kết quả: $($info.LastTaskResult))"
        Write-Host " Lần chạy tiếp theo: $($info.NextRunTime)"
    } else {
        Write-Host " [CHƯA ĐĂNG KÝ] Tác vụ '$TaskName' chưa được tạo trong Windows Task Scheduler." -ForegroundColor Yellow
    }
    exit 0
}

if ($Remove) {
    Write-Host ""
    Write-Host "=== HỦY BỎ LỊCH CHẠY TỰ ĐỘNG ===" -ForegroundColor Yellow
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host " [ĐÃ HỦY] Đã xóa tác vụ '$TaskName' khỏi Windows Task Scheduler." -ForegroundColor Green
    } else {
        Write-Host " Tác vụ '$TaskName' không tồn tại."
    }
    exit 0
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  HAIZFLOW - THIẾT LẬP LỊCH TỰ ĐỘNG LÀM VIDEO (WINDOWS TASK SCHEDULER) " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " - Thời gian chạy hàng ngày: $Time"
Write-Host " - Thư mục gốc dự án: $WorkspaceRoot"
Write-Host " - Tính năng đánh thức (Wake): BẬT (Tự động thức dậy từ chế độ Sleep)"
Write-Host "======================================================================"

try {
    # 1. Action: Chạy script run_daily_news.py
    $actionArgs = "`"$ScriptPy`" --now --aspect-ratio 16:9 --max-topics 8"
    $action = New-ScheduledTaskAction -Execute $PythonExe -Argument $actionArgs -WorkingDirectory $WorkspaceRoot

    # 2. Trigger: Hàng ngày lúc $Time
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time

    # 3. Settings: Cho phép đánh thức máy tính dậy từ chế độ Sleep
    $taskSettings = @{
        WakeToRun = $true
        AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true
        StartWhenAvailable = $true
        ExecutionTimeLimit = (New-TimeSpan -Hours 2)
    }
    $settings = New-ScheduledTaskSettingsSet @taskSettings

    # 4. Đăng ký tác vụ vào Windows
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Tự động thức dậy mỗi sáng lúc $Time để tạo bản tin thế giới 16:9 Full HD trong HaizFlow" -Force | Out-Null

    Write-Host ""
    Write-Host "[THÀNH CÔNG] Đã đăng ký lịch chạy tự động thành công!" -ForegroundColor Green
    Write-Host " -> Tác vụ sẽ tự động kích hoạt mỗi ngày vào lúc: $Time"
    Write-Host " -> Bạn có thể yên tâm để máy ở chế độ Sleep (Ngủ) và tắt ứng dụng HaizFlow."
    Write-Host " -> Sáng dậy video 16:9 hoàn chỉnh sẽ nằm sẵn trong thư mục runtime/daily_news/"
} catch {
    Write-Host ""
    Write-Host "[LỖI] Không thể đăng ký tác vụ: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Gợi ý: Hãy chạy PowerShell với quyền Administrator (Run as Administrator) để cấp quyền tạo lịch hệ thống." -ForegroundColor Yellow
}
