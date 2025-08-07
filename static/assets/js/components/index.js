// 主页面 JavaScript 组件

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

// 主应用组件
const MainApp = {
    data() {
        return {
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            systemStatus: '在线',
            messages: [],
            websocket: null,
            websocketConnected: false,
            selectedMessages: [],
            channelInfo: {},
            mediaPreview: {
                show: false,
                url: null
            },
            stats: {
                total: { value: 0, label: '总消息' },
                pending: { value: 0, label: '待审核' },
                approved: { value: 0, label: '已批准' },
                rejected: { value: 0, label: '已拒绝' },
                ads: { value: 0, label: '广告消息' },
                channels: { value: 0, label: '监听频道' }
            },
            filters: {
                status: 'pending',
                is_ad: null
            },
            previousMessageIds: new Set(),  // 存储之前加载的消息ID
            editDialog: {
                visible: false,
                messageId: null,
                content: '',
                originalMessage: null
            }
        }
    },
    
    created() {
        // 确保所有响应式数据正确初始化
        if (!this.mediaPreview) {
            this.mediaPreview = { show: false, url: null };
        }
    },
    
    mounted() {
        this.loadMessages();
        this.loadStats();
        this.loadChannelInfo();
        
        // 建立WebSocket连接
        this.connectWebSocket();
        
        // 定期检查WebSocket连接状态
        this.connectionCheckInterval = setInterval(() => {
            this.checkWebSocketConnection();
        }, 10000);
        
        // 页面获得焦点时立即刷新
        window.addEventListener('focus', () => {
            this.loadMessages();
            this.loadStats();
        });
    },
    
    beforeUnmount() {
        // 清理定时器
        if (this.connectionCheckInterval) {
            clearInterval(this.connectionCheckInterval);
        }
        
        // 关闭WebSocket连接
        if (this.websocket) {
            this.websocket.close();
        }
    },
    
    methods: {
        async loadChannelInfo() {
            try {
                const response = await axios.get('/api/messages/channel-info');
                if (response.data.success) {
                    this.channelInfo = response.data.data;
                }
            } catch (error) {
                console.error('加载频道信息失败:', error);
            }
        },
        
        async loadMessages() {
            this.loading = true;
            this.loadingMessage = '正在加载消息数据...';
            
            try {
                const response = await axios.get('/api/messages/', {
                    params: this.filters
                });
                
                console.log('API响应:', response.data);
                
                if (response.data && response.data.messages && Array.isArray(response.data.messages)) {
                    const newMessages = response.data.messages;
                    
                    // 计算真正的新消息
                    const currentMessageIds = new Set(newMessages.map(msg => msg.id));
                    const reallyNewMessages = newMessages.filter(msg => !this.previousMessageIds.has(msg.id));
                    
                    // 更新消息列表
                    this.messages = newMessages;
                    
                    // 只有当有真正的新消息时才显示提示
                    if (reallyNewMessages.length > 0) {
                        console.log('发现', reallyNewMessages.length, '条新消息');
                        MessageManager.success(`收到 ${reallyNewMessages.length} 条新消息`);
                    } else {
                        console.log('消息已是最新，共', this.messages.length, '条');
                    }
                    
                    // 更新已知消息ID集合
                    this.previousMessageIds = currentMessageIds;
                    
                    // 强制Vue下一帧重新渲染，确保媒体URL被正确加载
                    this.$nextTick(() => {
                        console.log('消息列表已更新，触发媒体重新加载');
                    });
                } else {
                    this.messages = [];
                    console.warn('API返回格式异常:', response.data);
                    if (this.previousMessageIds.size === 0) {
                        MessageManager.warning('暂无消息数据');
                    }
                }
            } catch (error) {
                console.error('加载消息失败:', error);
                this.messages = [];
                MessageManager.error('加载消息失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        async loadStats() {
            try {
                const response = await axios.get('/api/messages/stats/overview');
                if (response.data) {
                    const stats = response.data;
                    this.stats.total.value = stats.total || 0;
                    this.stats.pending.value = stats.pending || 0;
                    this.stats.approved.value = stats.approved || 0;
                    this.stats.rejected.value = stats.rejected || 0;
                    this.stats.ads.value = stats.ads || 0;
                    this.stats.channels.value = stats.channels || 0;
                }
            } catch (error) {
                console.error('加载统计信息失败:', error);
            }
        },

        // 获取频道名称
        getChannelName(channel_id) {
            if (this.channelInfo[channel_id]) {
                return this.channelInfo[channel_id].title || this.channelInfo[channel_id].name || channel_id;
            }
            return channel_id;
        },
        
        // 获取状态类型
        getStatusType(status) {
            const statusMap = {
                'pending': '',
                'approved': 'success',
                'rejected': 'danger',
                'auto_forwarded': 'info'
            };
            return statusMap[status] || '';
        },
        
        // 获取状态文本
        getStatusText(status) {
            const statusMap = {
                'pending': '待审核',
                'approved': '已批准',
                'rejected': '已拒绝',
                'auto_forwarded': '自动转发'
            };
            return statusMap[status] || status;
        },
        
        // 格式化时间
        formatTime(timeStr) {
            if (!timeStr) return '';
            try {
                const date = new Date(timeStr);
                const now = new Date();
                const diffInSeconds = Math.floor((now - date) / 1000);
                
                if (diffInSeconds < 60) return `${diffInSeconds}秒前`;
                if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}分钟前`;
                if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}小时前`;
                
                // 超过一天显示具体时间
                return date.toLocaleString('zh-CN', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (error) {
                return timeStr;
            }
        },
        
        // 统计面板点击事件
        handleStatClick(statKey) {
            switch(statKey) {
                case 'pending':
                    this.filters.status = 'pending';
                    break;
                case 'approved':
                    this.filters.status = 'approved';
                    break;
                case 'rejected':
                    this.filters.status = 'rejected';
                    break;
                case 'ads':
                    this.filters.is_ad = true;
                    break;
                default:
                    this.filters.status = '';
                    this.filters.is_ad = null;
            }
            this.loadMessages();
        },
        
        // 批准消息
        async approveMessage(messageId) {
            try {
                const response = await axios.post(`/api/messages/${messageId}/approve`);
                if (response.data.success) {
                    MessageManager.success('消息已批准');
                    // 如果当前过滤器是待审核状态，从列表中移除已批准的消息
                    if (this.filters.status === 'pending') {
                        this.messages = this.messages.filter(msg => msg.id !== messageId);
                    } else {
                        // 本地更新消息状态
                        const messageIndex = this.messages.findIndex(msg => msg.id === messageId);
                        if (messageIndex !== -1) {
                            this.messages[messageIndex].status = 'approved';
                        }
                    }
                    this.loadStats();
                } else {
                    MessageManager.error('批准失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('批准失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 拒绝消息
        async rejectMessage(messageId) {
            try {
                const response = await axios.post(`/api/messages/${messageId}/reject?reviewer=Web用户`);
                if (response.data.success) {
                    MessageManager.success('消息已拒绝');
                    // 从列表中移除消息
                    this.messages = this.messages.filter(msg => msg.id !== messageId);
                    this.loadStats();
                    
                    // 如果消息有审核群消息ID，删除审核群中的消息
                    const message = this.messages.find(msg => msg.id === messageId);
                    if (message && message.review_message_id) {
                        try {
                            // 调用删除审核群消息的API
                            await axios.delete(`/api/messages/${messageId}/review-message`);
                        } catch (error) {
                            console.error('删除审核群消息失败:', error);
                        }
                    }
                } else {
                    MessageManager.error('拒绝失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('拒绝失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 批量批准
        async batchApprove() {
            if (this.selectedMessages.length === 0) {
                MessageManager.warning('请先选择要批准的消息');
                return;
            }
            
            try {
                const response = await axios.post('/api/messages/batch/approve', {
                    message_ids: this.selectedMessages
                });
                if (response.data.success) {
                    MessageManager.success(`成功批准 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.loadStats();
                } else {
                    MessageManager.error('批量批准失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('批量批准失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 切换消息选择
        toggleMessageSelection(messageId) {
            const index = this.selectedMessages.indexOf(messageId);
            if (index > -1) {
                this.selectedMessages.splice(index, 1);
            } else {
                this.selectedMessages.push(messageId);
            }
        },
        
        // 检查消息是否被选中
        isMessageSelected(messageId) {
            return this.selectedMessages.includes(messageId);
        },
        
        // 预览媒体
        previewMedia(url) {
            this.mediaPreview.url = url;
            this.mediaPreview.show = true;
        },
        
        // 关闭媒体预览
        closeMediaPreview() {
            this.mediaPreview.show = false;
            this.mediaPreview.url = null;
        },

        // 格式化消息内容
        formatMessageContent(message) {
            return message.filtered_content || message.content || '';
        },

        // 检查是否为组合消息
        isCombinedMessage(message) {
            return message.is_combined && message.media_group_display && Array.isArray(message.media_group_display);
        },

        // 获取媒体类型图标
        getMediaTypeIcon(mediaType) {
            const iconMap = {
                'photo': '🖼️',
                'video': '🎥',
                'document': '📄',
                'animation': '🎬',
                'audio': '🎧'
            };
            return iconMap[mediaType] || '📎';
        },

        // 媒体预览（支持组合消息）
        openMediaPreview(url) {
            this.mediaPreview.url = url;
            this.mediaPreview.show = true;
        },

        // 处理媒体加载错误
        handleMediaError(event, message) {
            console.error('媒体加载失败:', message.id, event.target.src);
            event.target.style.display = 'none';
        },

        // 获取媒体组数据属性
        getMediaGroupCount(message) {
            if (!this.isCombinedMessage(message)) return 1;
            return Math.min(message.media_group_display.length, 9);
        },

        // WebSocket连接管理
        connectWebSocket() {
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/api/ws/messages`;
                
                this.websocket = new WebSocket(wsUrl);
                
                this.websocket.onopen = () => {
                    console.log('WebSocket连接已建立');
                    this.websocketConnected = true;
                    this.systemStatus = '在线';
                    
                    // 发送心跳
                    this.startHeartbeat();
                };
                
                this.websocket.onmessage = (event) => {
                    this.handleWebSocketMessage(event);
                };
                
                this.websocket.onclose = () => {
                    console.log('WebSocket连接已关闭');
                    this.websocketConnected = false;
                    this.systemStatus = '离线';
                    
                    // 尝试重连
                    setTimeout(() => {
                        if (!this.websocketConnected) {
                            this.connectWebSocket();
                        }
                    }, 5000);
                };
                
                this.websocket.onerror = (error) => {
                    console.error('WebSocket错误:', error);
                    this.websocketConnected = false;
                    this.systemStatus = '连接错误';
                };
                
            } catch (error) {
                console.error('建立WebSocket连接失败:', error);
                this.websocketConnected = false;
                this.systemStatus = '连接失败';
            }
        },

        // 处理WebSocket消息
        handleWebSocketMessage(event) {
            try {
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch (parseError) {
                    console.warn('收到非JSON格式的WebSocket消息:', event.data);
                    return;
                }
                
                switch (data.type) {
                    case 'new_message':
                        this.handleNewMessage(data.data);
                        break;
                    case 'stats_update':
                        this.handleStatsUpdate(data.data);
                        break;
                    case 'message_status_update':
                        this.handleMessageStatusUpdate(data.data);
                        break;
                    case 'pong':
                        // 心跳响应，不需要处理
                        break;
                    default:
                        console.log('未知WebSocket消息类型:', data.type);
                }
            } catch (error) {
                console.error('处理WebSocket消息失败:', error);
            }
        },

        // 处理新消息
        handleNewMessage(messageData) {
            // 检查消息是否已存在
            const existingIndex = this.messages.findIndex(msg => msg.id === messageData.id);
            
            if (existingIndex === -1) {
                // 新消息，添加到列表顶部
                this.messages.unshift(messageData);
                console.log('收到新消息:', messageData.content.substring(0, 50) + '...');
                
                // 显示通知
                MessageManager.success(`收到新消息: ${messageData.content.substring(0, 30)}...`);
                
                // 刷新统计信息
                this.loadStats();
                
                // 强制Vue重新渲染媒体元素
                this.$nextTick(() => {
                    // 确保媒体URL被正确加载
                    if (messageData.media_display_url || messageData.media_group_display) {
                        console.log('新消息包含媒体，触发重新渲染');
                    }
                });
            }
        },

        // 处理统计更新
        handleStatsUpdate(statsData) {
            this.stats.total.value = statsData.total || 0;
            this.stats.pending.value = statsData.pending || 0;
            this.stats.approved.value = statsData.approved || 0;
            this.stats.rejected.value = statsData.rejected || 0;
            this.stats.ads.value = statsData.ads || 0;
            this.stats.channels.value = statsData.channels || 0;
        },

        // 处理消息状态更新
        handleMessageStatusUpdate(updateData) {
            const messageIndex = this.messages.findIndex(msg => msg.id === updateData.message_id);
            if (messageIndex !== -1) {
                // 如果当前过滤器是待审核，且消息状态变为已批准或已拒绝，从列表中移除
                if (this.filters.status === 'pending' && 
                    (updateData.status === 'approved' || updateData.status === 'rejected')) {
                    this.messages.splice(messageIndex, 1);
                    console.log(`消息 ${updateData.message_id} 已从列表中移除（状态: ${updateData.status}）`);
                } else {
                    this.messages[messageIndex].status = updateData.status;
                    console.log(`消息 ${updateData.message_id} 状态更新为: ${updateData.status}`);
                }
            }
        },

        // 检查WebSocket连接状态
        checkWebSocketConnection() {
            if (!this.websocketConnected && (!this.websocket || this.websocket.readyState === WebSocket.CLOSED)) {
                console.log('WebSocket断开，尝试重连...');
                this.connectWebSocket();
            }
        },

        // 启动心跳
        startHeartbeat() {
            this.heartbeatInterval = setInterval(() => {
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    this.websocket.send('ping');
                }
            }, 30000); // 30秒心跳
        },
        
        // 发布消息到目标频道
        async publishMessage(messageId) {
            try {
                const response = await axios.post(`/api/messages/${messageId}/publish`);
                if (response.data.success) {
                    MessageManager.success('消息已发布到目标频道');
                    // 从列表中移除消息（消息已发布）
                    this.messages = this.messages.filter(msg => msg.id !== messageId);
                    this.loadStats();
                } else {
                    MessageManager.error('发布失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('发布失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 编辑消息
        editMessage(message) {
            this.editDialog.messageId = message.id;
            this.editDialog.content = message.filtered_content || message.content;
            this.editDialog.originalMessage = message;
            this.editDialog.visible = true;
        },
        
        // 保存编辑的消息
        async saveEditedMessage() {
            try {
                const response = await axios.post(`/api/messages/${this.editDialog.messageId}/edit-publish`, {
                    content: this.editDialog.content
                });
                if (response.data.success) {
                    MessageManager.success('消息已编辑');
                    this.editDialog.visible = false;
                    // 更新本地消息内容
                    const messageIndex = this.messages.findIndex(msg => msg.id === this.editDialog.messageId);
                    if (messageIndex !== -1) {
                        this.messages[messageIndex].filtered_content = this.editDialog.content;
                    }
                } else {
                    MessageManager.error('编辑失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('编辑失败: ' + (error.response?.data?.detail || error.message));
            }
        }
    }
};

// 将组件导出供HTML中使用
window.MainApp = MainApp;

// 等待 DOM 加载完成后初始化Vue应用
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, mounting Vue app...');
    try {
        const app = createApp(MainApp);
        app.use(ElementPlus);
        // 注册导航栏组件
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }
        app.mount('#app');
        console.log('Vue app mounted successfully');
    } catch (error) {
        console.error('Failed to mount Vue app:', error);
    }
});