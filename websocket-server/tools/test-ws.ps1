param(
  [string]$TargetHost = 'localhost:18000',
  [string]$Path = 'listening',
  [int]$DurationSec = 8,
  [switch]$Secure,
  [int]$PingIntervalSec = 1,
  [switch]$ShowMessages,
  [switch]$Raw,
  [switch]$FilterNonAscii,
  [switch]$NoColor
)

function _info($m){ if($NoColor){Write-Host "[INFO]  $m";return}; Write-Host '[INFO] ' -NoNewline -ForegroundColor Cyan; Write-Host $m }
function _err($m){ if($NoColor){Write-Host "[ERR ] $m";return}; Write-Host '[ERR ] ' -NoNewline -ForegroundColor Red; Write-Host $m }
function _warn($m){ if($NoColor){Write-Host "[WARN] $m";return}; Write-Host '[WARN] ' -NoNewline -ForegroundColor Yellow; Write-Host $m }

if($Secure){ $scheme='wss' } else { $scheme='ws' }
$Path = $Path.TrimStart('/')
$uriString = ('{0}://{1}/{2}' -f $scheme, $TargetHost.TrimEnd('/'), $Path)
try { $uri = [System.Uri]::new($uriString) } catch { _err "Invalid URI: $uriString"; exit 2 }

_info "Target: $($uri.AbsoluteUri)"
_info "Duration: $DurationSec s  PingInterval: $PingIntervalSec s"

try { Add-Type -AssemblyName System.Net.WebSockets -ErrorAction Stop } catch { _warn 'Assembly System.Net.WebSockets not loaded (ignored)'; }
$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$sw = [System.Diagnostics.Stopwatch]::StartNew()

$messages=0;$pongs=0;$heartbeats=0;$asrPartial=0;$asrUpdate=0;$other=0;$lastPing=Get-Date;$connected=$false;$exitCode=1

try {
  _info 'Connecting...'
  [void]$ws.ConnectAsync($uri,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
  if($ws.State -eq 'Open'){ $connected=$true; _info ("Connected (State={0})" -f $ws.State) } else { _err ("Not Open: {0}" -f $ws.State); exit 2 }
} catch { _err ("Connect failed: {0}" -f $_.Exception.Message); exit 2 }

function Send-Ping {
  if($ws.State -ne 'Open'){ return }
  $ts = (Get-Date).ToUniversalTime().ToString('o')
  $json = '{"type":"ping","ts":"' + $ts + '"}'
  $bytes = [Text.Encoding]::UTF8.GetBytes($json)
  # IMPORTANT: Using static ::new to avoid PowerShell expanding the byte array into multiple ctor args
  $seg = [System.ArraySegment[byte]]::new($bytes)
  try { [void]$ws.SendAsync($seg,[System.Net.WebSockets.WebSocketMessageType]::Text,$true,[Threading.CancellationToken]::None).GetAwaiter().GetResult(); if($ShowMessages){ _info '-> PING' } } catch { _warn ("Ping send error: {0}" -f $_.Exception.Message) }
}

Send-Ping
$buffer = New-Object byte[] 8192
while($sw.Elapsed.TotalSeconds -lt $DurationSec){
  if($ws.State -ne 'Open'){ _warn ("State={0} early end" -f $ws.State); break }
  if(-not $buffer -or $buffer.Length -eq 0){ _err 'Internal buffer missing'; break }
  if((Get-Date) - $lastPing -ge ([TimeSpan]::FromSeconds($PingIntervalSec))){ Send-Ping; $lastPing=Get-Date }
  try {
    $segment = [System.ArraySegment[byte]]::new($buffer)
    # Blocking receive with 1.5s timeout emulation
    $recvTask = $ws.ReceiveAsync($segment,[Threading.CancellationToken]::None)
    for($i=0;$i -lt 15 -and -not $recvTask.IsCompleted;$i++){ Start-Sleep -Milliseconds 100 }
    if(-not $recvTask.IsCompleted){ continue }
    $res = $recvTask.GetAwaiter().GetResult()
    if($res.Count -le 0){ if($res.MessageType -eq 'Close'){ _warn ("Server close {0}" -f $res.CloseStatus); break }; continue }
    $msg = [Text.Encoding]::UTF8.GetString($buffer,0,$res.Count)
    if($FilterNonAscii){
      $msg = -join ($msg.ToCharArray() | ForEach-Object { if([int][char]$_ -lt 128){ $_ } else { '?' } })
    }
    $messages++
    if($Raw){ Write-Host $msg; continue }
    $parsed=$null; try { $parsed = $msg | ConvertFrom-Json -ErrorAction Stop } catch {}
    if($parsed){
      switch($parsed.type){
        'pong' { $pongs++; if($ShowMessages){ _info '<- PONG' } }
        'server_heartbeat' { $heartbeats++; if($ShowMessages){ _info '<- HEARTBEAT' } }
        'asr_partial' { $asrPartial++; if($ShowMessages){ _info ("<- ASR_PARTIAL: {0}" -f $parsed.text) } }
        'asr_update' { $asrUpdate++; if($ShowMessages){ _info ("<- ASR_UPDATE: {0}" -f $parsed.text) } }
        default { $other++; if($ShowMessages){ _info ("<- OTHER type={0}" -f $parsed.type) } }
      }
    } else { $other++; if($ShowMessages){ _warn ("<- NonJSON: {0}" -f $msg) } }
    if($res.EndOfMessage -and $res.MessageType -eq 'Close'){ _warn 'Close frame'; break }
  }
  catch {
    _warn ("Receive loop exception: {0}" -f $_.Exception.Message)
    if($ws.State -ne 'Open'){ break }
  }
}

if($ws.State -eq 'Open'){
  try { [void]$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,'done',[Threading.CancellationToken]::None).GetAwaiter().GetResult(); _info 'Closed gracefully' } catch { _warn ("Close error: {0}" -f $_.Exception.Message) }
}
$sw.Stop()
if($connected -and $messages -gt 0){ $exitCode=0 } elseif($connected -and $messages -eq 0){ $exitCode=3 } else { $exitCode=2 }
Write-Host ''
Write-Host '===== Summary ====='
[pscustomobject]@{
  Uri=$uri.AbsoluteUri;Connected=$connected;Messages=$messages;Pongs=$pongs;Heartbeats=$heartbeats;AsrPartial=$asrPartial;AsrUpdate=$asrUpdate;Other=$other;DurationSec=[int]$sw.Elapsed.TotalSeconds;ExitCode=$exitCode
} | Format-List
exit $exitCode
