const WebSocket = require('ws');
const path = require('path');
let config;
try {
  const cfg = require(path.join(__dirname, 'config'));
  config = cfg.getConfig();
} catch (err) {
  console.warn('Could not load ./config module for websocket example, using defaults:', err && err.message);
  config = {
    backendHost: '192.168.0.201:8000',
    useHttps: false,
    devServerHost: 'localhost:5173',
    exampleServerHost: 'localhost:8080'
  };
}

const [host, port] = (config.exampleServerHost || 'localhost:8080').split(':');

// 创建WebSocket服务器
const wss = new WebSocket.Server({ 
    port: parseInt(port) || 8080,
    host: '0.0.0.0'
});

console.log(`WebSocket服务器启动在 ws://${config.exampleServerHost}`);

// 模拟通话记录数据
const callRecords = [
    {
        id: '1',
        title: 'Customer Support Call #1',
        transcript: {
            user: '你好，我想咨询一下关于产品退换货的问题。我前几天买的商品有质量问题，需要退货。',
            assistant: '您好！很抱歉给您带来不便。我来帮您处理退货事宜。请提供您的订单号码，我来查看具体情况。根据我们的退货政策，质量问题商品可以在7天内免费退货。'
        },
        duration: 185000, // 3分05秒
        createdAt: '2025-01-10T09:30:00.000Z',
        endedAt: '2025-01-10T09:33:05.000Z'
    },
    {
        id: '2',
        title: 'Technical Support Call #2',
        transcript: {
            user: '我的账户登录不了，一直提示密码错误，但我确定密码是正确的。',
            assistant: '我理解您遇到的登录问题。这可能是由于多次错误尝试导致账户被临时锁定。让我来帮您重置密码。请提供您的注册邮箱，我会发送重置链接给您。同时建议您清除浏览器缓存后再尝试登录。'
        },
        duration: 142000, // 2分22秒
        createdAt: '2025-01-10T14:15:00.000Z',
        endedAt: '2025-01-10T14:17:22.000Z'
    },
    {
        id: '3',
        title: 'Sales Inquiry Call #3',
        transcript: {
            user: '我想了解一下你们的企业版服务包含哪些功能，价格是怎样的？',
            assistant: '感谢您对我们企业版服务的关注！企业版包含高级分析功能、优先技术支持、自定义集成选项以及团队协作工具。价格根据用户数量和功能模块有不同的方案。我可以为您安排一次详细的产品演示，您看什么时间方便？'
        },
        duration: 298000, // 4分58秒
        createdAt: '2025-01-09T16:45:00.000Z',
        endedAt: '2025-01-09T16:49:58.000Z'
    },
    {
        id: '4',
        title: 'Billing Question Call #4',
        transcript: {
            user: '我看到本月账单比平时高了很多，想了解一下具体的收费明细。',
            assistant: '我来帮您查看账单详情。看起来您这个月使用了额外的云存储服务，这部分产生了额外费用。我可以为您详细解释每项收费，并帮您优化使用方案以控制成本。另外，我们有一些省钱的套餐方案可以推荐给您。'
        },
        duration: 203000, // 3分23秒
        createdAt: '2025-01-09T11:20:00.000Z',
        endedAt: '2025-01-09T11:23:23.000Z'
    },
    {
        id: '5',
        title: 'Product Feedback Call #5',
        transcript: {
            user: '我使用你们的产品已经三个月了，整体还不错，但有些功能希望能够改进。',
            assistant: '非常感谢您的反馈！用户的意见对我们产品改进非常重要。请详细告诉我您希望改进的功能，我会记录下来并转达给我们的产品团队。同时，如果您有任何使用上的问题，我也很乐意为您解答。'
        },
        duration: 267000, // 4分27秒
        createdAt: '2025-01-08T13:30:00.000Z',
        endedAt: '2025-01-08T13:34:27.000Z'
    }
];

wss.on('connection', (ws, req) => {
    console.log(`新客户端连接: ${req.socket.remoteAddress}`);

    // 发送欢迎消息
    ws.send(JSON.stringify({
        type: 'system',
        message: '已连接到通话记录展示服务器'
    }));

    // 自动发送通话列表
    setTimeout(() => {
        ws.send(JSON.stringify({
            type: 'call_list',
            calls: callRecords
        }));
    }, 500);

    ws.on('message', async (message) => {
        try {
            const data = JSON.parse(message);
            console.log('收到消息:', data);

            if (data.type === 'get_call_list') {
                console.log('请求通话列表');
                
                // 发送通话列表
                ws.send(JSON.stringify({
                    type: 'call_list',
                    calls: callRecords
                }));
                
            } else if (data.type === 'get_call_data') {
                console.log(`请求通话数据: ${data.callId}`);
                
                // 查找指定的通话记录
                const call = callRecords.find(c => c.id === data.callId);
                if (call) {
                    ws.send(JSON.stringify({
                        type: 'call_data',
                        callId: data.callId,
                        call: call
                    }));
                } else {
                    ws.send(JSON.stringify({
                        type: 'error',
                        message: '未找到指定的通话记录'
                    }));
                }
            } else {
                console.log('未知消息类型:', data.type);
                ws.send(JSON.stringify({
                    type: 'error',
                    message: '不支持的消息类型'
                }));
            }
        } catch (error) {
            console.error('处理消息时出错:', error);
            
            // 发送错误消息
            ws.send(JSON.stringify({
                type: 'error',
                message: '服务器处理请求时出错，请稍后重试。'
            }));
        }
    });

    ws.on('close', (code, reason) => {
        console.log(`客户端断开连接: ${code} ${reason}`);
    });

    ws.on('error', (error) => {
        console.error('WebSocket错误:', error);
    });

    // 定期发送心跳包保持连接
    const heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.ping();
        } else {
            clearInterval(heartbeat);
        }
    }, 30000); // 每30秒发送一次心跳
});

wss.on('error', (error) => {
    console.error('WebSocket服务器错误:', error);
});

// 优雅关闭
process.on('SIGINT', () => {
    console.log('\n正在关闭WebSocket服务器...');
    wss.close(() => {
        console.log('WebSocket服务器已关闭');
        process.exit(0);
    });
});

process.on('SIGTERM', () => {
    console.log('\n正在关闭WebSocket服务器...');
    wss.close(() => {
        console.log('WebSocket服务器已关闭');
        process.exit(0);
    });
});
