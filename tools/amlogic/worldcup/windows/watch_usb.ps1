param([int]$Seconds = 300)
# Read-only Windows PnP event monitor for short-lived Amlogic WorldCup USB devices.
$source = 'CapsulaWorldCupWatcher'
$pattern = 'USB\VID_1B8E&PID_C003'
$started = Get-Date
$log = Join-Path $PSScriptRoot 'usb_events.log'
function Show-Capsula {
    $devices = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like ($pattern + '*') })
    if ($devices.Count -eq 0) {
        Write-Host '  WorldCup has not been enumerated by Windows.'
    }
    foreach ($device in $devices) {
        $present = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -eq $device.InstanceId }).Count -gt 0
        $message = "  WorldCup: Present=$present Status=$($device.Status) Name=$($device.FriendlyName)"
        Write-Host $message
        Add-Content -LiteralPath $log -Value $message -Encoding UTF8
    }
}
Write-Host "USB event watcher ready. Started: $($started.ToString('HH:mm:ss'))"
Write-Host 'Connect/disconnect the speaker; Windows USB/PnP changes will be printed.'
Write-Host "Log: $log"
Show-Capsula
try {
    Register-WmiEvent -Class Win32_DeviceChangeEvent -SourceIdentifier $source -ErrorAction Stop | Out-Null
    while (((Get-Date) - $started).TotalSeconds -lt $Seconds) {
        $event = Wait-Event -SourceIdentifier $source -Timeout 1
        if ($null -ne $event) {
            $kind = switch ([int]$event.SourceEventArgs.NewEvent.EventType) {
                2 { 'device-arrival' }
                3 { 'device-removal' }
                default { 'device-change' }
            }
            $message = "$((Get-Date).ToString('HH:mm:ss.fff')) $kind (Windows PnP notification)"
            Write-Host $message
            Add-Content -LiteralPath $log -Value $message -Encoding UTF8
            Remove-Event -EventIdentifier $event.EventIdentifier -ErrorAction SilentlyContinue
            Show-Capsula
        }
    }
}
finally {
    Unregister-Event -SourceIdentifier $source -ErrorAction SilentlyContinue
    Get-Event -SourceIdentifier $source -ErrorAction SilentlyContinue | Remove-Event -ErrorAction SilentlyContinue
}
Write-Host 'USB watcher stopped.'
