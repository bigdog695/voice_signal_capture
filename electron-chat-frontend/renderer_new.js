// WebSocket连接管理
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.url = localStorage.getItem('websocketUrl') || 'ws://localhost:8080';
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

// 通话管理器
class CallManager {
    constructor() {
        this.calls = JSON.parse(localStorage.getItem('calls')) || [];
        this.currentCallId = null;
        this.isInCall = false;
        this.callTimer = null;
        this.callStartTime = null;
        this.isMuted = false;
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
        });

        // 自动连接
        this.wsManager.connect();
    }

    setupEventListeners() {
        // 新建通话
        document.getElementById('newChatBtn').addEventListener('click', () => {
            this.createNewCall();
        });

        // 开始通话
        document.getElementById('startCallBtn').addEventListener('click', () => {
            this.startCall();
        });

        // 结束通话
        document.getElementById('endCallBtn').addEventListener('click', () => {
            this.endCall();
        });

        // 静音/取消静音
        document.getElementById('muteBtn').addEventListener('click', () => {
            this.toggleMute();
        });

        // 清空通话记录
        document.getElementById('clearChatBtn').addEventListener('click', () => {
            this.clearCurrentCall();
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
        
        if (this.calls.length === 0) {
            this.createNewCall();
        } else {
            this.switchToCall(this.calls[0].id);
        }
    }

    createNewCall() {
        const call = {
            id: Date.now().toString(),
            title: 'New Call',
            transcript: { user: '', assistant: '' },
            duration: 0,
            createdAt: new Date().toISOString(),
            endedAt: null
        };

        this.calls.unshift(call);
        this.currentCallId = call.id;
        this.saveCalls();
        this.renderCallHistory();
        this.updateCallTitle();
    }

    switchToCall(callId) {
        this.currentCallId = callId;
        this.renderCallHistory();
        this.updateCallTitle();
    }

    getCurrentCall() {
        return this.calls.find(call => call.id === this.currentCallId);
    }

    handleWebSocketMessage(data) {
        if (data.type === 'voice_transcript') {
            // 处理语音转文字结果
            this.updateTranscript(data.speaker, data.text);
        } else if (data.type === 'call_response') {
            // 处理AI语音回应
            this.updateTranscript('assistant', data.text);
        } else if (data.type === 'error') {
            console.error('Call error:', data.message);
        }
    }

    updateTranscript(speaker, text) {
        const transcriptElement = document.getElementById(speaker === 'user' ? 'userTranscript' : 'assistantTranscript');
        if (transcriptElement) {
            transcriptElement.textContent = text;
            transcriptElement.classList.add('speaking');
            
            // 移除speaking类
            setTimeout(() => {
                transcriptElement.classList.remove('speaking');
            }, 2000);
        }
    }

    // 通话控制方法
    startCall() {
        if (this.isInCall) return;
        
        this.isInCall = true;
        this.callStartTime = Date.now();
        this.isMuted = false;
        
        // 显示通话界面
        document.querySelector('.welcome-message').style.display = 'none';
        document.getElementById('currentCallDisplay').style.display = 'block';
        
        // 更新按钮状态
        document.getElementById('startCallBtn').style.display = 'none';
        document.getElementById('endCallBtn').style.display = 'inline-flex';
        document.getElementById('muteBtn').style.display = 'inline-flex';
        
        // 开始计时器
        this.startCallTimer();
        
        // 模拟开始语音识别
        this.startVoiceRecognition();
        
        // 发送开始通话信号到后端
        this.wsManager.sendMessage({
            type: 'call_start',
            callId: this.currentCallId
        });
        
        console.log('Call started');
    }

    endCall() {
        if (!this.isInCall) return;
        
        this.isInCall = false;
        
        // 停止计时器
        this.stopCallTimer();
        
        // 停止语音识别
        this.stopVoiceRecognition();
        
        // 隐藏通话界面
        document.getElementById('currentCallDisplay').style.display = 'none';
        document.querySelector('.welcome-message').style.display = 'block';
        
        // 更新按钮状态
        document.getElementById('startCallBtn').style.display = 'inline-flex';
        document.getElementById('endCallBtn').style.display = 'none';
        document.getElementById('muteBtn').style.display = 'none';
        
        // 保存通话记录
        this.saveCallToHistory();
        
        // 发送结束通话信号到后端
        this.wsManager.sendMessage({
            type: 'call_end',
            callId: this.currentCallId
        });
        
        console.log('Call ended');
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        const muteBtn = document.getElementById('muteBtn');
        const span = muteBtn.querySelector('span');
        
        if (this.isMuted) {
            muteBtn.classList.add('muted');
            span.textContent = 'Unmute';
        } else {
            muteBtn.classList.remove('muted');
            span.textContent = 'Mute';
        }
        
        console.log(this.isMuted ? 'Microphone muted' : 'Microphone unmuted');
    }

    startCallTimer() {
        this.callTimer = setInterval(() => {
            const elapsed = Date.now() - this.callStartTime;
            const minutes = Math.floor(elapsed / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            
            document.getElementById('callTimer').textContent = 
                `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }, 1000);
    }

    stopCallTimer() {
        if (this.callTimer) {
            clearInterval(this.callTimer);
            this.callTimer = null;
        }
    }

    startVoiceRecognition() {
        // 模拟语音识别 - 在实际应用中，这里会连接到语音识别API
        const userTranscript = document.getElementById('userTranscript');
        const assistantTranscript = document.getElementById('assistantTranscript');
        
        userTranscript.innerHTML = '<span class="transcript-placeholder">Listening...</span>';
        assistantTranscript.innerHTML = '<span class="transcript-placeholder">Ready to respond...</span>';
        
        // 模拟语音输入
        setTimeout(() => {
            userTranscript.innerHTML = 'Hello, can you help me with...';
            userTranscript.classList.add('speaking');
            
            setTimeout(() => {
                userTranscript.classList.remove('speaking');
                assistantTranscript.innerHTML = 'Of course! I\'d be happy to help you with that...';
                assistantTranscript.classList.add('speaking');
                
                setTimeout(() => {
                    assistantTranscript.classList.remove('speaking');
                }, 2000);
            }, 3000);
        }, 2000);
    }

    stopVoiceRecognition() {
        // 停止语音识别
        const userTranscript = document.getElementById('userTranscript');
        const assistantTranscript = document.getElementById('assistantTranscript');
        
        userTranscript.classList.remove('speaking');
        assistantTranscript.classList.remove('speaking');
    }

    saveCallToHistory() {
        const currentCall = this.getCurrentCall();
        if (!currentCall) return;
        
        const callDuration = Date.now() - this.callStartTime;
        const userTranscript = document.getElementById('userTranscript').textContent;
        const assistantTranscript = document.getElementById('assistantTranscript').textContent;
        
        currentCall.duration = callDuration;
        currentCall.transcript = {
            user: userTranscript,
            assistant: assistantTranscript
        };
        currentCall.endedAt = new Date().toISOString();
        
        this.saveCalls();
        this.renderCallHistory();
    }

    renderCallHistory() {
        const container = document.getElementById('chatHistory');
        container.innerHTML = '';

        this.calls.forEach(call => {
            const callElement = document.createElement('div');
            callElement.className = `chat-item ${call.id === this.currentCallId ? 'active' : ''}`;
            
            const duration = call.duration ? this.formatDuration(call.duration) : '00:00';
            const date = new Date(call.createdAt).toLocaleDateString();
            
            callElement.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 2px;">
                    <div style="font-weight: 500;">${call.title}</div>
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
        titleElement.textContent = currentCall ? currentCall.title : 'New Call';
    }

    clearCurrentCall() {
        const currentCall = this.getCurrentCall();
        if (currentCall && confirm('Are you sure you want to clear this call record?')) {
            currentCall.transcript = { user: '', assistant: '' };
            currentCall.title = 'New Call';
            currentCall.duration = 0;
            this.saveCalls();
            this.renderCallHistory();
            this.updateCallTitle();
        }
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

    saveCalls() {
        localStorage.setItem('calls', JSON.stringify(this.calls));
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new CallManager();
});
