## WebSocket Diagnostic Tools

### Script: `test-ws.ps1`

PowerShell 客户端脚本，用于验证后端 `/listening` WebSocket 是否正常：

功能:
- 建立连接并发送周期 `ping`
- 统计接收的 `pong`、`server_heartbeat`、`asr_partial`、`asr_update`
- 自定义持续时间、间隔、显示原始消息
- 退出码: 0=收到消息, 3=连接成功无消息, 2=连接失败

#### 快速使用
```powershell
cd websocket-server\tools
./test-ws.ps1 -TargetHost localhost:18000 -ShowMessages
```

#### 参数
| 参数 | 说明 | 默认 |
|------|------|------|
| `-TargetHost` | host:port | `localhost:18000` |
| `-Path` | WebSocket 路径 | `listening` |
| `-DurationSec` | 运行总秒数 | 8 |
| `-PingIntervalSec` | ping 间隔秒 | 1 |
| `-Secure` | 使用 wss | (off) |
| `-ShowMessages` | 打印分类消息 | (off) |
| `-Raw` | 直接输出消息原文 | (off) |
| `-NoColor` | 关闭彩色输出 | (off) |

#### 示例
```powershell
# 基本检查
./test-ws.ps1

# 更长时间并显示内容
./test-ws.ps1 -DurationSec 15 -ShowMessages

# 仅原始输出
./test-ws.ps1 -Raw -DurationSec 5

# 指定不同端口 (真实服务器 8000)
./test-ws.ps1 -TargetHost localhost:8000
```

#### 判定
收到 Heartbeat 或 ASR 消息即说明数据流正常；只有 pong 没有其它消息可能是后端还未广播或广播间隔较长。
