// WebSocket连接管理
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.url = localStorage.getItem('websocketUrl') || 'ws://localhost:8000/chatting?id=test_001';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isManualDisconnect = false;
        this.messageCallbacks = [];
        this.statusCallbacks = [];
    }

    connect() {
        if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
            return;
        }

        this.isManualDisconnect = false;
        this.updateStatus('connecting');
        
        try {
            this.ws = new WebSocket(this.url);
            this.setupEventListeners();
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.updateStatus('disconnected');
            this.scheduleReconnect();
        }
    }

    setupEventListeners() {
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.updateStatus('connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.notifyMessageCallbacks(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket disconnected:', event.code, event.reason);
            this.updateStatus('disconnected');
            
            if (!this.isManualDisconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.scheduleReconnect();
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('disconnected');
        };
    }

    disconnect() {
        this.isManualDisconnect = true;
        if (this.ws) {
            this.ws.close();
        }
    }

    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
            return true;
        }
        return false;
    }

    scheduleReconnect() {
        if (this.isManualDisconnect || this.reconnectAttempts >= this.maxReconnectAttempts) {
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            if (!this.isManualDisconnect) {
                this.connect();
            }
        }, delay);
    }

    updateStatus(status) {
        this.statusCallbacks.forEach(callback => callback(status));
    }

    onMessage(callback) {
        this.messageCallbacks.push(callback);
    }

    onStatusChange(callback) {
        this.statusCallbacks.push(callback);
    }

    notifyMessageCallbacks(data) {
        this.messageCallbacks.forEach(callback => callback(data));
    }

    setUrl(url) {
        this.url = url;
        localStorage.setItem('websocketUrl', url);
    }
}

// 通话展示管理器
class CallDisplayManager {
    constructor() {
        this.calls = [];
        this.currentCallId = null;
        this.isLiveCallActive = false;
        this.liveCallStartTime = null;
        this.liveCallTimer = null;
        this.wsManager = new WebSocketManager();
        this.setupWebSocketCallbacks();
        this.setupEventListeners();
        this.loadSettings();
        this.initializeUI();
    }

    setupWebSocketCallbacks() {
        this.wsManager.onMessage((data) => {
            this.handleWebSocketMessage(data);
        });

        this.wsManager.onStatusChange((status) => {
            this.updateConnectionStatus(status);
            
            if (status === 'connected') {
                this.showActiveCall();
            } else if (status === 'disconnected') {
                this.hideActiveCall();
            }
        });

        // 自动连接
        this.wsManager.connect();
    }

    setupEventListeners() {
        // 查看活跃通话按钮
        document.getElementById('viewActiveCallBtn').addEventListener('click', () => {
            this.showLiveCallWindow();
        });

        // 最小化实时通话窗口
        document.getElementById('minimizeLiveCallBtn').addEventListener('click', () => {
            this.hideLiveCallWindow();
        });

        // 刷新通话列表
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshCallList();
        });

        // 设置按钮
        document.getElementById('settingsBtn').addEventListener('click', () => {
            this.openSettings();
        });

        // 设置模态框
        document.getElementById('closeSettingsBtn').addEventListener('click', () => {
            this.closeSettings();
        });

        document.getElementById('cancelSettingsBtn').addEventListener('click', () => {
            this.closeSettings();
        });

        document.getElementById('saveSettingsBtn').addEventListener('click', () => {
            this.saveSettings();
        });

        // 温度滑块
        document.getElementById('temperature').addEventListener('input', (e) => {
            document.getElementById('temperatureValue').textContent = e.target.value;
        });

        // 模态框背景点击关闭
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target.id === 'settingsModal') {
                this.closeSettings();
            }
        });
    }

    initializeUI() {
        this.renderCallHistory();
        this.showNoCallSelected();
        // 从服务器获取通话列表
        this.refreshCallList();
    }

    showActiveCall() {
        this.isLiveCallActive = true;
        this.liveCallStartTime = Date.now();
        
        const activeCallSection = document.getElementById('activeCallSection');
        activeCallSection.style.display = 'block';
        
        // 开始计时器
        this.startLiveCallTimer();
    }

    hideActiveCall() {
        this.isLiveCallActive = false;
        
        const activeCallSection = document.getElementById('activeCallSection');
        activeCallSection.style.display = 'none';
        
        // 停止计时器
        this.stopLiveCallTimer();
        
        // 隐藏实时通话窗口
        this.hideLiveCallWindow();
    }

    startLiveCallTimer() {
        this.liveCallTimer = setInterval(() => {
            if (this.liveCallStartTime) {
                const elapsed = Date.now() - this.liveCallStartTime;
                const minutes = Math.floor(elapsed / 60000);
                const seconds = Math.floor((elapsed % 60000) / 1000);
                
                document.getElementById('activeCallTime').textContent = 
                    `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        }, 1000);
    }

    stopLiveCallTimer() {
        if (this.liveCallTimer) {
            clearInterval(this.liveCallTimer);
            this.liveCallTimer = null;
        }
    }

    showLiveCallWindow() {
        document.getElementById('noCallSelected').style.display = 'none';
        document.getElementById('callDisplay').style.display = 'none';
        document.getElementById('liveCallDisplay').style.display = 'flex';
        document.getElementById('chatTitle').textContent = 'Live Call Session';
    }

    hideLiveCallWindow() {
        document.getElementById('liveCallDisplay').style.display = 'none';
        this.showNoCallSelected();
    }

    showNoCallSelected() {
        document.getElementById('noCallSelected').style.display = 'block';
        document.getElementById('callDisplay').style.display = 'none';
        document.getElementById('chatTitle').textContent = 'Select a Call';
    }

    refreshCallList() {
        // 向服务器请求通话列表
        this.wsManager.sendMessage({
            type: 'get_call_list'
        });
    }

    switchToCall(callId) {
        this.currentCallId = callId;
        this.renderCallHistory();
        this.displayCall(callId);
    }

    displayCall(callId) {
        const call = this.calls.find(c => c.id === callId);
        if (!call) return;

        // 隐藏无选择提示，显示通话内容
        document.getElementById('noCallSelected').style.display = 'none';
        document.getElementById('callDisplay').style.display = 'block';

        // 更新标题
        document.getElementById('chatTitle').textContent = call.title || `Call ${call.id}`;

        // 更新通话信息
        document.getElementById('callDuration').textContent = 
            `Duration: ${this.formatDuration(call.duration || 0)}`;
        document.getElementById('callDate').textContent = 
            `Date: ${new Date(call.createdAt).toLocaleDateString()}`;

        // 更新转录内容
        document.getElementById('userTranscriptContent').textContent = 
            call.transcript?.user || 'No user transcript available';
        document.getElementById('assistantTranscriptContent').textContent = 
            call.transcript?.assistant || 'No assistant transcript available';
    }

    getCurrentCall() {
        return this.calls.find(call => call.id === this.currentCallId);
    }

    handleWebSocketMessage(data) {
        console.log('收到WebSocket消息:', data);
        
        if (data.type === 'connection_established') {
            console.log('WebSocket连接建立:', data.message);
            this.addLiveMessage('system', data.message, data.timestamp);
        } else if (data.type === 'message_history') {
            this.addLiveMessage(data.speaker, data.content, data.timestamp);
        } else if (data.type === 'new_message') {
            // 处理实时消息流 - 支持部分更新
            this.addLiveMessage(data.speaker, data.content, data.timestamp, data.is_partial, data.message_id);
            // 播放提示音或其他通知
            this.notifyNewMessage(data.speaker);
        } else if (data.type === 'conversation_complete') {
            this.addLiveMessage('system', data.message, data.timestamp);
        } else if (data.type === 'chat_ended') {
            this.addLiveMessage('system', data.message, data.timestamp);
        } else if (data.type === 'call_list') {
            // 接收到通话列表
            this.calls = data.calls || [];
            this.renderCallHistory();
        } else if (data.type === 'call_data') {
            // 接收到单个通话数据
            const call = this.calls.find(c => c.id === data.callId);
            if (call) {
                Object.assign(call, data.call);
                if (this.currentCallId === data.callId) {
                    this.displayCall(data.callId);
                }
            }
        } else if (data.type === 'error') {
            console.error('WebSocket错误:', data.message);
            this.addLiveMessage('system', `错误: ${data.message}`, data.timestamp);
        }
    }

    addLiveMessage(speaker, content, timestamp, isPartial = false, messageId = null) {
        const liveMessages = document.getElementById('liveMessages');
        
        // 如果是部分消息且有messageId，先查找是否已存在相同的消息
        let messageElement = null;
        if (messageId) {
            messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        }
        
        // 如果找不到现有消息或没有messageId，创建新消息元素
        if (!messageElement) {
            messageElement = document.createElement('div');
            messageElement.className = `live-message ${speaker}`;
            if (messageId) {
                messageElement.setAttribute('data-message-id', messageId);
            }
            
            const time = new Date(timestamp).toLocaleTimeString();
            
            messageElement.innerHTML = `
                <div class="live-message-content">${content}</div>
                <div class="live-message-time">${time}</div>
            `;
            
            liveMessages.appendChild(messageElement);
        } else {
            // 更新现有消息的内容
            const contentElement = messageElement.querySelector('.live-message-content');
            if (contentElement) {
                contentElement.textContent = content;
                
                // 如果是实时更新，添加打字效果
                if (isPartial) {
                    contentElement.classList.add('typing-effect');
                    setTimeout(() => {
                        contentElement.classList.remove('typing-effect');
                    }, 100);
                }
            }
        }
        
        // 限制消息数量以避免性能问题
        const maxMessages = 100;
        const allMessages = liveMessages.children;
        if (allMessages.length > maxMessages) {
            // 移除最旧的消息
            for (let i = 0; i < allMessages.length - maxMessages; i++) {
                liveMessages.removeChild(allMessages[0]);
            }
        }
        
        // 滚动到底部
        liveMessages.scrollTop = liveMessages.scrollHeight;
    }

    notifyNewMessage(speaker) {
        // 简单的视觉反馈
        const indicator = document.getElementById('liveConnectionIndicator');
        if (indicator) {
            indicator.style.transform = 'scale(1.1)';
            setTimeout(() => {
                indicator.style.transform = 'scale(1)';
            }, 200);
        }
    }

    renderCallHistory() {
        const container = document.getElementById('chatHistory');
        container.innerHTML = '';

        if (this.calls.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: #94a3b8; padding: 20px; font-size: 14px;">No call records available</div>';
            return;
        }

        this.calls.forEach(call => {
            const callElement = document.createElement('div');
            callElement.className = `chat-item ${call.id === this.currentCallId ? 'active' : ''}`;
            
            const duration = call.duration ? this.formatDuration(call.duration) : '00:00';
            const date = new Date(call.createdAt).toLocaleDateString();
            
            callElement.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <div style="font-weight: 500;">${call.title || `Call ${call.id}`}</div>
                    <div style="font-size: 12px; color: #94a3b8;">${date} • ${duration}</div>
                </div>
            `;
            
            callElement.addEventListener('click', () => {
                this.switchToCall(call.id);
            });
            container.appendChild(callElement);
        });
    }

    formatDuration(milliseconds) {
        const minutes = Math.floor(milliseconds / 60000);
        const seconds = Math.floor((milliseconds % 60000) / 1000);
        return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    updateCallTitle() {
        const currentCall = this.getCurrentCall();
        const titleElement = document.getElementById('chatTitle');
        titleElement.textContent = currentCall ? currentCall.title || `Call ${currentCall.id}` : 'Select a Call';
    }

    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connectionStatus');
        const indicator = statusElement.querySelector('.status-indicator');
        const text = statusElement.querySelector('span');

        indicator.className = `status-indicator ${status}`;
        
        switch (status) {
            case 'connected':
                text.textContent = 'Connected';
                break;
            case 'connecting':
                text.textContent = 'Connecting...';
                break;
            case 'disconnected':
                text.textContent = 'Disconnected';
                break;
        }
    }

    openSettings() {
        const modal = document.getElementById('settingsModal');
        
        // 加载当前设置
        document.getElementById('websocketUrl').value = this.wsManager.url;
        document.getElementById('apiModel').value = localStorage.getItem('apiModel') || 'gpt-3.5-turbo';
        document.getElementById('maxTokens').value = localStorage.getItem('maxTokens') || '2000';
        document.getElementById('temperature').value = localStorage.getItem('temperature') || '0.7';
        document.getElementById('temperatureValue').textContent = localStorage.getItem('temperature') || '0.7';
        
        modal.classList.add('show');
    }

    closeSettings() {
        const modal = document.getElementById('settingsModal');
        modal.classList.remove('show');
    }

    saveSettings() {
        const url = document.getElementById('websocketUrl').value;
        const model = document.getElementById('apiModel').value;
        const maxTokens = document.getElementById('maxTokens').value;
        const temperature = document.getElementById('temperature').value;

        // 保存设置
        localStorage.setItem('apiModel', model);
        localStorage.setItem('maxTokens', maxTokens);
        localStorage.setItem('temperature', temperature);

        // 如果WebSocket URL改变了，重新连接
        if (url !== this.wsManager.url) {
            this.wsManager.disconnect();
            this.wsManager.setUrl(url);
            this.wsManager.connect();
        }

        this.closeSettings();
    }

    loadSettings() {
        // 加载保存的设置（已在其他方法中实现）
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new CallDisplayManager();
});
