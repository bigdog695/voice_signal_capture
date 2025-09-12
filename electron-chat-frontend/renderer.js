// 配置管理类
class ConfigManager {
    constructor() {
        this.defaultHost = 'localhost:8000';
        this.defaultUseHttps = false;
        this.loadConfig();
    }

    loadConfig() {
        this.backendHost = localStorage.getItem('backendHost') || this.defaultHost;
        this.useHttps = localStorage.getItem('useHttps') === 'true' || this.defaultUseHttps;
    }

    saveConfig(host, useHttps) {
        this.backendHost = host;
        this.useHttps = useHttps;
        localStorage.setItem('backendHost', host);
        localStorage.setItem('useHttps', useHttps.toString());
    }

    getProtocols() {
        return {
            http: this.useHttps ? 'https' : 'http',
            ws: this.useHttps ? 'wss' : 'ws'
        };
    }

    getChatUrl(chatId = 'test_001') {
        const protocols = this.getProtocols();
        return `${protocols.ws}://${this.backendHost}/chatting?id=${chatId}`;
    }

    getAsrUrl() {
        const protocols = this.getProtocols();
        return `${protocols.ws}://${this.backendHost}/ws`;
    }

    getListeningUrl() {
        const protocols = this.getProtocols();
        return `${protocols.ws}://${this.backendHost}/listening`;
    }

    getHealthUrl() {
        const protocols = this.getProtocols();
        return `${protocols.http}://${this.backendHost}/health`;
    }

    getApiBaseUrl() {
        const protocols = this.getProtocols();
        return `${protocols.http}://${this.backendHost}`;
    }
}

// WebSocket连接管理
class WebSocketManager {
    constructor(configManager) {
        this.configManager = configManager;
        this.ws = null;
        this.url = this.configManager.getChatUrl();
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

    setUrl(chatId = 'test_001') {
        this.url = this.configManager.getChatUrl(chatId);
    }

    updateConfig() {
        this.url = this.configManager.getChatUrl();
    }
}

// 通话展示管理器
class CallDisplayManager {
    constructor() {
    // 统一日志前缀（便于过滤）
    this.logPrefix = '[RealtimeListening]';
    this._log = (...args) => console.log(this.logPrefix, ...args);
        this.configManager = new ConfigManager();
        this.calls = [];
        this.currentCallId = null;
        this.isLiveCallActive = false;
        this.liveCallStartTime = null;
        this.liveCallTimer = null;
        this.wsManager = new WebSocketManager(this.configManager);
        
        // 本机监听相关
        this.monitorWs = null;
        this.isMonitoring = false;
        
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.asrSocket = null;
        this.audioContext = null;
        this.scriptProcessor = null;
        this.mediaStreamSource = null;
        this.asrMessageId = null;
        this.asrTranscriptQueue = []; // 维护已确认的文本队列
        this.currentInterimText = ''; // 当前临时文本
    // 新增: 结构化增量管理
    this.asrActiveMessageId = null; // 当前活跃句子的 messageId
    this.asrActiveRevision = -1;    // 当前活跃句子的最新 revision
    this.asrMessageMap = new Map(); // messageId -> { text, revision, final }
    // 增量句子拆分状态：segmentId -> { emitted: 已输出完整句子数量 }
    this.segmentSplitState = new Map();
    // 自动滚动控制
    this._autoScrollEnabled = true;

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
            
            // 移除自动显示活跃通话的逻辑
            // 现在需要用户手动点击按钮来连接
        });

        // 不再自动连接，等待用户手动操作
        // this.wsManager.connect();
    }

    setupEventListeners() {
        // 统一按钮：实时通话监听 (/listening)
        document.getElementById('viewCurrentCallBtn').addEventListener('click', () => {
            this._log('Button clicked -> start /listening connection');
            this.connectToLocalMonitor();
        });
        
        // 关闭监听按钮
        document.getElementById('closeMonitorBtn').addEventListener('click', () => {
            this.disconnectLocalMonitor();
        });

    // (已移除活跃通话按钮)

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

        // 测试连接按钮
        document.getElementById('testConnectionBtn').addEventListener('click', () => {
            this.testConnection();
        });

        // 后端地址输入变化时更新预览
        document.getElementById('backendHost').addEventListener('input', () => {
            this.updateEndpointPreview();
        });

        document.getElementById('useHttps').addEventListener('change', () => {
            this.updateEndpointPreview();
        });

        // 模态框背景点击关闭
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target.id === 'settingsModal') {
                this.closeSettings();
            }
        });

        // 录音按钮
        document.getElementById('recordBtn').addEventListener('click', () => {
            this.toggleRecording();
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

    showAsrWindow() {
        document.getElementById('noCallSelected').style.display = 'none';
        document.getElementById('callDisplay').style.display = 'none';
        document.getElementById('liveCallDisplay').style.display = 'none';
        document.getElementById('asrDisplay').style.display = 'flex';
        document.getElementById('chatTitle').textContent = 'Real-time Transcription';
        // 清空转录队列和内容
        this.asrTranscriptQueue = [];
        this.currentInterimText = '';
        document.getElementById('asrContent').innerHTML = '';
    }

    hideAsrWindow() {
        document.getElementById('asrDisplay').style.display = 'none';
        this.showNoCallSelected();
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
        document.getElementById('backendHost').value = this.configManager.backendHost;
        document.getElementById('useHttps').checked = this.configManager.useHttps;
        
        // 更新端点预览
        this.updateEndpointPreview();
        
        modal.classList.add('show');
    }

    closeSettings() {
        const modal = document.getElementById('settingsModal');
        modal.classList.remove('show');
    }

    saveSettings() {
        const host = document.getElementById('backendHost').value.trim();
        const useHttps = document.getElementById('useHttps').checked;

        if (!host) {
            alert('请输入后端服务地址');
            return;
        }

        // 保存配置
        this.configManager.saveConfig(host, useHttps);
        
        // 更新WebSocket管理器
        this.wsManager.updateConfig();
        
        // 如果当前有连接，断开并重新连接
        if (this.wsManager.ws && this.wsManager.ws.readyState === WebSocket.OPEN) {
            this.wsManager.disconnect();
            setTimeout(() => {
                this.wsManager.connect();
            }, 100);
        }
        
        // 如果监听服务正在运行，重新连接
        if (this.isMonitoring) {
            this.disconnectLocalMonitor();
            setTimeout(() => {
                this.connectToLocalMonitor();
            }, 100);
        }

        this.closeSettings();
        alert('设置已保存！');
    }

    updateEndpointPreview() {
        const host = document.getElementById('backendHost').value.trim() || 'localhost:8000';
        const useHttps = document.getElementById('useHttps').checked;
        
        const protocols = {
            http: useHttps ? 'https' : 'http',
            ws: useHttps ? 'wss' : 'ws'
        };

        document.getElementById('chatEndpointPreview').textContent = `${protocols.ws}://${host}/chatting`;
        document.getElementById('asrEndpointPreview').textContent = `${protocols.ws}://${host}/ws`;
        document.getElementById('listeningEndpointPreview').textContent = `${protocols.ws}://${host}/listening`;
        document.getElementById('healthEndpointPreview').textContent = `${protocols.http}://${host}/health`;
    }

    async testConnection() {
        const host = document.getElementById('backendHost').value.trim();
        const useHttps = document.getElementById('useHttps').checked;
        const resultElement = document.getElementById('connectionTestResult');
        
        if (!host) {
            resultElement.textContent = '请先输入后端服务地址';
            resultElement.className = 'connection-status error';
            return;
        }

        resultElement.textContent = '正在测试连接...';
        resultElement.className = 'connection-status testing';

        try {
            const protocol = useHttps ? 'https' : 'http';
            const healthUrl = `${protocol}://${host}/health`;
            
            const response = await fetch(healthUrl, {
                method: 'GET',
                timeout: 5000
            });

            if (response.ok) {
                const data = await response.json();
                resultElement.textContent = `连接成功！服务状态: ${data.status}`;
                resultElement.className = 'connection-status success';
                // 注册白名单
                try {
                    const registerUrl = `${protocol}://${host}/whitelist/register`;
                    const regResp = await fetch(registerUrl);
                    if (regResp.ok) {
                        const regData = await regResp.json();
                        console.log('[Whitelist] added:', regData.added, 'current:', regData.whitelist);
                    }
                } catch (e) {
                    console.warn('Whitelist register failed', e);
                }
            } else {
                resultElement.textContent = `连接失败：HTTP ${response.status}`;
                resultElement.className = 'connection-status error';
            }
        } catch (error) {
            resultElement.textContent = `连接失败：${error.message}`;
            resultElement.className = 'connection-status error';
        }
    }

    loadSettings() {
        // 加载保存的设置（已在其他方法中实现）
    }

    // =================================================================
    // 录音和ASR相关方法
    // =================================================================

    toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            this.startRecording();
        }
    }

    async startRecording() {
        if (this.isRecording) return;

        this.showAsrWindow(); // 确保实时语音识别窗口可见
        console.log('Starting recording...');
        this.isRecording = true;
        this.updateRecordButton(true);
        this.addLiveMessage('system', 'Recording started, connecting to ASR service...', Date.now());
        this.asrMessageId = `asr-message-${Date.now()}`;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.mediaStreamSource = this.audioContext.createMediaStreamSource(stream);
            
            // --- WebSocket 连接 ---
            const asrUrl = this.configManager.getAsrUrl();
            console.log(`Connecting to ASR WebSocket: ${asrUrl}`);
            this.asrSocket = new WebSocket(asrUrl);
            this.setupAsrSocketListeners();

            // --- 音频处理 ---
            const bufferSize = 4096;
            const inputSampleRate = this.audioContext.sampleRate;
            const outputSampleRate = 16000;

            this.scriptProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);
            this.scriptProcessor.onaudioprocess = (e) => {
                if (!this.isRecording || !this.asrSocket || this.asrSocket.readyState !== WebSocket.OPEN) {
                    return;
                }
                const inputData = e.inputBuffer.getChannelData(0);
                const downsampledData = this.downsampleBuffer(inputData, inputSampleRate, outputSampleRate);
                const pcmData = this.floatTo16BitPCM(downsampledData);
                // console.log(`Sending ${pcmData.byteLength} bytes of audio data.`);
                this.asrSocket.send(pcmData);
            };

            this.mediaStreamSource.connect(this.scriptProcessor);
            this.scriptProcessor.connect(this.audioContext.destination);

            // 保存流以备停止
            this.mediaStream = stream;

        } catch (err) {
            console.error('Error starting recording:', err);
            this.addLiveMessage('system', `Error starting recording: ${err.message}`, Date.now());
            this.stopRecording(); // 清理
        }
    }

    stopRecording() {
        if (!this.isRecording) return;

        this.hideAsrWindow(); // 录音结束时隐藏ASR窗口
        console.log('Stopping recording...');
        this.isRecording = false;
        this.updateRecordButton(false);
        this.addLiveMessage('system', 'Recording stopped.', Date.now());

        // 清理转录队列
        this.asrTranscriptQueue = [];
        this.currentInterimText = '';

        // 停止音频流
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }

        // 断开并清理音频节点
        if (this.scriptProcessor) {
            this.scriptProcessor.disconnect();
            this.scriptProcessor = null;
        }
        if (this.mediaStreamSource) {
            this.mediaStreamSource.disconnect();
            this.mediaStreamSource = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        // 关闭ASR WebSocket
        if (this.asrSocket) {
            if (this.asrSocket.readyState === WebSocket.OPEN) {
                // 发送结束信号
                this.asrSocket.send(JSON.stringify({ "is_finished": true }));
            }
            this.asrSocket.close();
            this.asrSocket = null;
        }
    }

    setupAsrSocketListeners() {
        if (!this.asrSocket) return;

        this.asrSocket.onopen = () => {
            console.log('ASR WebSocket connected.');
            this.addLiveMessage('system', 'ASR service connected.', Date.now());
        };

        this.asrSocket.onmessage = (event) => {
            console.log('Received ASR message:', event.data);
            this.handleAsrMessage(event.data);
        };

        this.asrSocket.onclose = (event) => {
            console.log('ASR WebSocket disconnected:', event.code, event.reason);
            if(this.isRecording){ // 如果仍在录音状态，说明是异常关闭
                this.addLiveMessage('system', `ASR service disconnected. Code: ${event.code}, Reason: ${event.reason || 'No reason given'}`, Date.now());
                this.stopRecording(); // 自动停止录音
            }
        };

        this.asrSocket.onerror = (error) => {
            console.error('ASR WebSocket error:', error);
            this.addLiveMessage('system', 'ASR service connection error. Check console for details.', Date.now());
            if(this.isRecording){
               this.stopRecording(); // 自动停止录音
            }
        };
    }

    handleAsrMessage(data) {
        console.log('Handling ASR message data:', data);
        let text = '';
        let isFinal = false;
        let messageId = null;
        let revision = null;
        let isStructured = false;

        try {
            // 首先尝试解析为JSON，这是FunASR的标准格式
            const result = JSON.parse(data);
            if (result.type === 'asr_update' && result.messageId) {
                // 新结构 from backend
                isStructured = true;
                text = result.text || '';
                isFinal = !!result.is_final;
                messageId = result.messageId;
                revision = typeof result.revision === 'number' ? result.revision : 0;
                console.log(`Parsed structured ASR update: id=${messageId} rev=${revision} final=${isFinal} text="${text}"`);
            } else {
                // 旧结构兼容
                text = result.text || '';
                isFinal = result.is_final || false;
                console.log(`Parsed legacy JSON ASR result - text: "${text}", is_final: ${isFinal}`);
            }
        } catch (error) {
            // 如果解析失败，直接将data视为纯文本字符串
            // 这可以兼容没有严格遵循JSON格式的后端实现
            console.warn('Could not parse ASR message as JSON, treating as plain text. Raw data:', data);
            text = data.toString().trim();
            // 当收到纯文本时，我们假定它是一个最终结果
            isFinal = true; 
        }

        if (!text) {
            console.log('ASR message does not contain processable text.');
            return;
        }

        if (!isStructured) {
            // 原始逻辑保持
            console.log(`Updating UI (legacy) with text: "${text}", isFinal: ${isFinal}`);
            this.updateAsrContent(text, isFinal);
            return;
        }

        // 结构化增量处理
        // 如果是新 messageId 且之前有未final的 active，已由后端 finalize，不需处理。
        if (this.asrActiveMessageId === null) {
            this.asrActiveMessageId = messageId;
            this.asrActiveRevision = -1;
        }

        // 如果切换到新的 messageId (说明上一句已经结束)，重置 interim
        if (messageId !== this.asrActiveMessageId) {
            // 安全起见把 active 句子状态标记 final（如果后端没发final也不会重复显示）
            const prev = this.asrMessageMap.get(this.asrActiveMessageId);
            if (prev && !prev.final) {
                prev.final = true;
                if (prev.text && !this.asrTranscriptQueue.includes(prev.text)) {
                    this.asrTranscriptQueue.push(prev.text);
                }
            }
            this.currentInterimText = '';
            this.asrActiveMessageId = messageId;
            this.asrActiveRevision = -1;
        }

        // 检查 revision 乱序
        const existing = this.asrMessageMap.get(messageId);
        if (existing && revision !== null && revision <= existing.revision) {
            console.log(`Discard out-of-order / stale update: rev=${revision} <= ${existing.revision}`);
            return;
        }

        // 更新/创建记录
        const record = {
            text,
            revision: revision ?? ((existing ? existing.revision : 0) + 1),
            final: isFinal
        };
        this.asrMessageMap.set(messageId, record);
        this.asrActiveRevision = record.revision;

        if (isFinal) {
            // 句子完成，加入队列
            if (text.trim()) {
                this.asrTranscriptQueue.push(text.trim());
            }
            if (this.asrActiveMessageId === messageId) {
                this.asrActiveMessageId = null; // 下次新句子会重新赋值
                this.currentInterimText = '';
            }
        } else {
            // 临时更新
            this.currentInterimText = text.trim();
        }

        // 重绘
        const asrContent = document.getElementById('asrContent');
        if (asrContent) {
            const finalText = this.asrTranscriptQueue.join(' ');
            let html = '';
            if (finalText) html += `<span class="final-transcript">${finalText}</span>`;
            if (this.currentInterimText) html += `<span class="interim-transcript">${finalText ? ' ' : ''}${this.currentInterimText}</span>`;
            asrContent.innerHTML = html;
            const wrapper = document.querySelector('.asr-content-wrapper');
            if (wrapper) wrapper.scrollTop = wrapper.scrollHeight;
        }
    }

    updateAsrContent(text, isFinal) {
        const asrContent = document.getElementById('asrContent');
        if (!asrContent) return;

        console.log(`Before update - Queue: [${this.asrTranscriptQueue.join(' | ')}], Interim: "${this.currentInterimText}"`);

        if (isFinal) {
            // 如果是最终结果，将其添加到确认队列中
            if (text.trim()) {
                this.asrTranscriptQueue.push(text.trim());
                console.log('Added final text to queue:', text.trim());
                console.log('Updated queue:', this.asrTranscriptQueue);
            }
            // 清空当前临时文本
            this.currentInterimText = '';
        } else {
            // 如果是临时结果，更新当前临时文本
            this.currentInterimText = text.trim();
            console.log('Updated interim text:', this.currentInterimText);
        }

        // 重新构建显示内容：已确认文本 + 当前临时文本
        const finalText = this.asrTranscriptQueue.join(' ');
        
        // 使用HTML来区分最终文本和临时文本的样式
        let html = '';
        if (finalText) {
            html += `<span class="final-transcript">${finalText}</span>`;
        }
        if (this.currentInterimText) {
            html += `<span class="interim-transcript">${finalText ? ' ' : ''}${this.currentInterimText}</span>`;
        }
        
        asrContent.innerHTML = html;
        
        // 自动滚动到底部
        const asrContentWrapper = document.querySelector('.asr-content-wrapper');
        if (asrContentWrapper) {
            asrContentWrapper.scrollTop = asrContentWrapper.scrollHeight;
        }
        
        console.log(`After update - Final segments: ${this.asrTranscriptQueue.length}, Current interim: "${this.currentInterimText}"`);
        console.log(`Displayed HTML: ${html}`);
    }

    updateRecordButton(isRecording) {
        const recordBtn = document.getElementById('recordBtn');
        if (isRecording) {
            recordBtn.classList.add('recording');
            recordBtn.title = 'Stop Recording';
            recordBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M5 3.5h6A1.5 1.5 0 0 1 12.5 5v6a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 11V5A1.5 1.5 0 0 1 5 3.5z"/>
                </svg>
            `;
        } else {
            recordBtn.classList.remove('recording');
            recordBtn.title = 'Start Recording';
            recordBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 12a4 4 0 0 0 4-4V4a4 4 0 0 0-8 0v4a4 4 0 0 0 4 4zm0 1a5 5 0 0 1-5-5V4a5 5 0 0 1 10 0v4a5 5 0 0 1-5 5z"/>
                    <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5z"/>
                </svg>
            `;
        }
    }

    // --- 音频处理辅助函数 ---
    downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
        if (inputSampleRate === outputSampleRate) {
            return buffer;
        }
        const sampleRateRatio = inputSampleRate / outputSampleRate;
        const newLength = Math.round(buffer.length / sampleRateRatio);
        const result = new Float32Array(newLength);
        let offsetResult = 0;
        let offsetBuffer = 0;
        while (offsetResult < result.length) {
            const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
            let accum = 0, count = 0;
            for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
                accum += buffer[i];
                count++;
            }
            result[offsetResult] = accum / count;
            offsetResult++;
            offsetBuffer = nextOffsetBuffer;
        }
        return result;
    }

    floatTo16BitPCM(input) {
        const output = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        return output.buffer;
    }

    // 废弃 connectToCurrentCall (前端不再主动推流)，保留监听模式
    
    // 连接到本机通话监听
    connectToLocalMonitor() {
        if (this.isMonitoring) {
            this.showLocalMonitorWindow();
            return;
        }
        
        this.showLocalMonitorWindow();
        this.updateMonitorStatus('连接中...');
        
        try {
            const monitorUrl = this.configManager.getListeningUrl();
            this._log('Connecting to backend websocket', monitorUrl);
            this.monitorWs = new WebSocket(monitorUrl);
            this.setupMonitorWebSocket();
        } catch (error) {
            this._log('Connect failed', error);
            alert('连接本机监听失败: ' + error.message);
            this.hideLocalMonitorWindow();
        }
    }
    
    // 设置监听WebSocket事件
    setupMonitorWebSocket() {
        if (!this.monitorWs) return;
        
        this.monitorWs.onopen = () => {
            this._log('WebSocket OPEN');
            this.isMonitoring = true;
            this.updateMonitorStatus('已连接', true);
            // 启动客户端心跳（1s）
            if (this._monitorHeartbeatTimer) clearInterval(this._monitorHeartbeatTimer);
            this._monitorHeartbeatTimer = setInterval(() => {
                try {
                    if (this.monitorWs && this.monitorWs.readyState === WebSocket.OPEN) {
                        this.monitorWs.send(JSON.stringify({ type: 'ping', ts: new Date().toISOString() }));
                        this._log('TX ping');
                    }
                } catch (e) { /* ignore */ }
            }, 1000);
        };
        
        this.monitorWs.onmessage = (event) => {
            try {
                const parsed = JSON.parse(event.data);
                this._log('RX', parsed.type, parsed.text || parsed.message || '');
                this.handleMonitorMessage(parsed);
            } catch (e) {
                // 忽略非JSON（后端现在只发结构化）
            }
        };
        
        this.monitorWs.onclose = (e) => {
            this._log('WebSocket CLOSE', e.code, e.reason);
            this.isMonitoring = false;
            this.updateMonitorStatus('连接断开', false);
            if (this._monitorHeartbeatTimer) {
                clearInterval(this._monitorHeartbeatTimer);
                this._monitorHeartbeatTimer = null;
            }
        };
        
        this.monitorWs.onerror = (error) => {
            this._log('WebSocket ERROR', error);
            this.updateMonitorStatus('连接错误', false);
            if (this._monitorHeartbeatTimer) {
                clearInterval(this._monitorHeartbeatTimer);
                this._monitorHeartbeatTimer = null;
            }
        };
    }
    
    // 处理监听消息
    handleMonitorMessage(data) {
        console.log('=== 处理JSON监听消息 ===');
        console.log('数据类型:', data.type);
        console.log('完整数据:', data);
        // 计算简单端到端延迟（若后端提供 timestamp）
        if (data.timestamp) {
            try {
                const serverMs = new Date(data.timestamp).getTime();
                const diff = Date.now() - serverMs;
                if (diff > 500) {
                    this._log('latency(ms)', diff, 'type', data.type);
                }
            } catch (e) { /* ignore */ }
        }
        
    if (data.type === 'asr_update') {
            const { segmentId, revision, text, is_final, stable_len, source } = data;
            this._log('handle asr_update', segmentId, revision, is_final, text);
            this.updateSegmentBubble({ segmentId, revision, text, is_final, stable_len, source });
        } else if (data.type === 'status') {
            this._log('status', data.message);
        } else if (data.type === 'server_heartbeat') {
            this._log('RX server_heartbeat');
        } else if (data.type === 'pong') {
            this._log('RX pong');
        } else {
            this._log('unknown message type', data.type);
        }
    }
    
    // (legacy listening_text 已移除)

    // 基于 segmentId 的增量气泡更新
    updateSegmentBubble({ segmentId, revision, text, is_final, stable_len, source }) {
        if (!segmentId || typeof text !== 'string') return;
        const monitorDisplay = document.getElementById('localMonitorDisplay');
        if (monitorDisplay && monitorDisplay.style.display === 'none') this.showLocalMonitorWindow();
        let container = document.getElementById('monitorMessages');
        if (!container) {
            const mc = document.getElementById('monitorContent') || monitorDisplay;
            if (!mc) return;
            container = document.createElement('div');
            container.className = 'monitor-messages';
            container.id = 'monitorMessages';
            mc.appendChild(container);
        }
        // 句子切分(包含终止符) 例如: “你好。我很好？”
        const sentenceRegex = /[^。！？!?]*[。！？!?]/g; // 匹配以终止符结束的完整句子
        const completed = [];
        let match;
        while ((match = sentenceRegex.exec(text)) !== null) {
            const s = match[0].trim();
            if (s) completed.push(s);
        }
        const pendingTail = text.slice(sentenceRegex.lastIndex); // 未以终止符结束的部分
        const state = this.segmentSplitState.get(segmentId) || { emitted: 0 };
        // 输出新增完整句子
        for (let i = state.emitted; i < completed.length; i++) {
            const sentence = completed[i];
            const sid = segmentId + '-s' + i; // 每个完整句子独立 final 气泡
            this._emitSentenceBubble({ seg: sid, text: sentence, source, final: true, revision });
        }
        state.emitted = completed.length;
        this.segmentSplitState.set(segmentId, state);
        // 处理未完成部分：只有在非 final 或 final 且确实有尾部时展示
        if (pendingTail) {
            // base segment bubble (可被修订) id = segmentId + '-pending'
            this._emitSentenceBubble({ seg: segmentId + '-pending', text: pendingTail, source, final: !!is_final && !pendingTail.match(/[。！？!?]$/), revision, stable_len, isPartial: !is_final });
        } else {
            // 没有尾部 => 移除旧的 pending bubble（如果存在）
            const oldPending = container.querySelector(`[data-seg="${segmentId}-pending"]`);
            if (oldPending) oldPending.remove();
        }
        // 如果最终且没有 pendingTail 且文本不以标点结束（整段无标点且 final），将整段当作单句
        if (is_final && completed.length === 0 && !pendingTail) {
            this._emitSentenceBubble({ seg: segmentId + '-s0', text, source, final: true, revision });
        }
        // 限制条数 20
    this._trimBubbles(container, 20);
    this._scrollMonitorBottom();
    }

    _emitSentenceBubble({ seg, text, source, final, revision, stable_len, isPartial }) {
        if (!text) return;
        const container = document.getElementById('monitorMessages');
        if (!container) return;
        let node = container.querySelector(`[data-seg="${seg}"]`);
        if (!node) {
            node = document.createElement('div');
            node.className = 'segment-bubble';
            node.setAttribute('data-seg', seg);
            node.setAttribute('data-rev', revision ?? 0);
            const role = source === 'hot-line' ? 'hot-line' : 'citizen';
            node.classList.add(role);
            const timeString = new Date().toLocaleTimeString();
            node.innerHTML = `<div class="bubble-text"></div><div class="bubble-meta"><span class="time">${timeString}</span></div>`;
            container.appendChild(node);
        } else {
            const lastRev = parseInt(node.getAttribute('data-rev')||'-1',10);
            if (revision != null && revision < lastRev) return; // 不回退
            if (revision != null) node.setAttribute('data-rev', revision);
        }
        const textEl = node.querySelector('.bubble-text');
        if (textEl) {
            if (isPartial && typeof stable_len === 'number' && stable_len > 0 && stable_len < text.length) {
                const stable = text.slice(0, stable_len);
                const pend = text.slice(stable_len);
                textEl.innerHTML = `<span class="stable">${stable}</span><span class="pending">${pend}</span>`;
            } else {
                textEl.textContent = text;
            }
        }
        if (final) {
            node.classList.add('final');
            const p = node.querySelector('.pending');
            if (p) p.classList.remove('pending');
        }
    this._scrollMonitorBottom();
    }

    _trimBubbles(container, max) {
        while (container.children.length > max) {
            const removed = container.firstChild;
            container.removeChild(removed);
            console.debug('[BubbleRemovedOverflow]', removed?.getAttribute && removed.getAttribute('data-seg'));
        }
    }

    _scrollMonitorBottom() {
        if (!this._autoScrollEnabled) return;
        const list = document.getElementById('monitorMessages');
        if (!list) return;
        // 寻找真正可滚动容器（父级 monitor-content 有 overflow）
        let target = list;
        if (list.parentElement && list.parentElement.classList.contains('monitor-content')) {
            target = list.parentElement;
        }
        // 使用 requestAnimationFrame 确保 DOM 更新后再滚动
        requestAnimationFrame(()=>{ target.scrollTop = target.scrollHeight; });
    }
    
    // 断开本机监听
    disconnectLocalMonitor() {
        // 将当前流式消息标记为完成
        const monitorMessages = document.getElementById('monitorMessages');
        if (monitorMessages) {
            const streamingElement = monitorMessages.querySelector('.monitor-message.streaming');
            if (streamingElement) {
                streamingElement.classList.remove('streaming');
            }
        }
        
        if (this.monitorWs) {
            this.monitorWs.close();
            this.monitorWs = null;
        }
        this.isMonitoring = false;
        this.hideLocalMonitorWindow();
    }
    
    // 显示本机监听窗口
    showLocalMonitorWindow() {
        document.getElementById('noCallSelected').style.display = 'none';
        document.getElementById('callDisplay').style.display = 'none';
        document.getElementById('liveCallDisplay').style.display = 'none';
        document.getElementById('asrDisplay').style.display = 'none';
        document.getElementById('localMonitorDisplay').style.display = 'flex';
        document.getElementById('chatTitle').textContent = '本机通话监听';
        
        // 清空之前的消息
        document.getElementById('monitorMessages').innerHTML = '';
    }
    
    // 隐藏本机监听窗口
    hideLocalMonitorWindow() {
        document.getElementById('localMonitorDisplay').style.display = 'none';
        this.showNoCallSelected();
    }
    
    // 更新监听连接状态
    updateMonitorStatus(status, isConnected = false) {
        const indicator = document.getElementById('monitorConnectionIndicator');
        if (!indicator) return;
        
        indicator.textContent = status;
        indicator.className = 'connection-indicator';
        
        if (isConnected) {
            indicator.classList.add('connected');
        } else {
            indicator.classList.add('disconnected');
        }
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new CallDisplayManager();
});
