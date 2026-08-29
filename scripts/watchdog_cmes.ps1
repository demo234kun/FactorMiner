# cmes collector watchdog: check 3 shards every 5 min, auto-relaunch dead ones (resume-safe).
# Usage: set $env:CEMS_TOKEN first, then run this script.
# Token is NOT stored in this file; shard children inherit env from this process.
param(
    [int]$ShardN = 3,
    [int]$Workers = 2,
    [int]$IntervalSec = 300
)

$env:CEMS_TOKEN = $env:CEMS_TOKEN
if (-not $env:CEMS_TOKEN) {
    Write-Host "WARNING: CEMS_TOKEN empty, shards cannot auth" -ForegroundColor Yellow
}

$logFile = "cmes_watchdog.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

Log "watchdog start (shards=$ShardN workers=$Workers interval=${IntervalSec}s)"

while ($true) {
    Start-Sleep -Seconds $IntervalSec

    # completion check: exit when all shard logs contain DONE
    $doneCount = 0
    for ($i = 0; $i -lt $ShardN; $i++) {
        $log = "cmes_shard$i.log"
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern "\[cmes\] DONE" -Quiet -ErrorAction SilentlyContinue)) {
            $doneCount++
        }
    }
    if ($doneCount -ge $ShardN) {
        Log "all $ShardN shards DONE, watchdog exit"
        break
    }

    for ($i = 0; $i -lt $ShardN; $i++) {
        $log = "cmes_shard$i.log"
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern "\[cmes\] DONE" -Quiet -ErrorAction SilentlyContinue)) {
            continue
        }
        $alive = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*collect_cmes.py*--shard-id $i*" }
        if (-not $alive) {
            Remove-Item $log -ErrorAction SilentlyContinue
            Remove-Item "$log.err" -ErrorAction SilentlyContinue
            Start-Process -FilePath "F:\Python\python.exe" `
                -ArgumentList "-u","scripts/collect_cmes.py","--freq","both",`
                             "--shard-id","$i","--shard-n","$ShardN","--workers","$Workers" `
                -RedirectStandardOutput $log -RedirectStandardError "$log.err" -WindowStyle Hidden
            Log "shard $i relaunched"
        }
    }
}
Log "watchdog exit"
