// 主页面 JavaScript 组件

// 确保API配置可用，延迟解析避免加载时错误
let createApp, ElMessage;

// 延迟初始化函数
function initializeGlobals() {
    if (!createApp && window.Vue) createApp = window.Vue.createApp;
    if (!ElMessage && window.ElementPlus) ElMessage = window.ElementPlus.ElMessage;
}

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
            searchKeyword: '',  // 搜索关键词
            channelInfo: {},
            
            // 虚拟列表配置
            useVirtualScroll: true,
            virtualScrollThreshold: 100,
            messageItemHeight: 200,
            virtualListHeight: 600,
            
            // 状态管理
            processingMessages: new Set(),
            mediaPreview: {
                show: false,
                url: null
            },
            fileDetailsDialog: {
                visible: false,
                details: null
            },
            stats: {
                total: { value: 0, label: '总消息' },
                pending: { value: 0, label: '待审核' },
                approved: { value: 0, label: '已批准' },
                rejected: { value: 0, label: '已拒绝' },
                ads: { value: 0, label: '广告消息' },
                duplicates: { value: 0, label: '重复消息' },
                chats: { value: 0, label: '聊天消息' }
            },
            filters: {
                status: 'pending',
                is_ad: null,
                source_channel: '',  // 频道筛选，使用空字符串匹配HTML默认值
                filter_reason: null,    // 过滤原因筛选
                _show_duplicates: false  // 🔧 新增：重复消息对比显示标识
            },
            currentPage: 1,
            pageSize: 20,
            hasMore: true,
            isLoadingMore: false,
            isClearing: false,  // 专门的清空状态，确保DOM立即更新
            previousMessageIds: new Set(),  // 存储之前加载的消息ID
            editDialog: {
                visible: false,
                messageId: null,
                content: '',
                originalMessage: null
            },
            refetchingMedia: {}, // 记录正在补抓的消息ID
            // 权限控制
            buttonVisibility: {
                edit: true,
                approve: true,
                reject: true,
                markAsAd: true,
                markAsTail: true,
                executeFilter: true,
                refetchMedia: true
            }
        }
    },
    
    computed: {
        // 去重的频道列表（只显示监听频道）
        uniqueChannels() {
            if (!this.channelInfo) return {};
            
            const uniqueChannels = {};
            const seenChannels = new Set();
            
            // 遍历所有频道，去重并过滤
            for (const [key, channelData] of Object.entries(this.channelInfo)) {
                // 只处理source类型的频道（监听频道）
                if (channelData.type !== 'source') {
                    continue;
                }
                
                // 使用ID作为唯一标识
                const channelId = channelData.id;
                if (seenChannels.has(channelId)) {
                    continue;
                }
                
                seenChannels.add(channelId);
                uniqueChannels[channelId] = channelData;
            }
            
            return uniqueChannels;
        },
        
        // 过滤后的消息列表
        filteredMessages() {
            if (!this.messages || !Array.isArray(this.messages)) {
                return [];
            }
            
            // 🔧 特殊处理：重复消息模式下只显示有重复信息的消息
            if (this.filters._show_duplicates) {
                const duplicateMessages = this.messages.filter(msg => {
                    const hasDuplicateId = !!(msg.duplicate_original_id);
                    const hasDuplicateInfo = !!(msg.duplicate_info);
                    const hasFilterReason = !!(msg.filter_reason && msg.filter_reason.toLowerCase().includes('duplicate'));
                    const hasRejectReason = !!(msg.reject_reason && (
                        msg.reject_reason.includes('重复') || 
                        msg.reject_reason.toLowerCase().includes('duplicate')
                    ));
                    
                    const isDuplicate = hasDuplicateId || hasDuplicateInfo || hasFilterReason || hasRejectReason;
                    
                    if (isDuplicate) {
                        console.log(`找到重复消息: ${msg.source_channel}:${msg.message_id}`, {
                            hasDuplicateId,
                            hasDuplicateInfo,
                            hasFilterReason,
                            hasRejectReason,
                            filter_reason: msg.filter_reason,
                            reject_reason: msg.reject_reason,
                            duplicate_original_id: msg.duplicate_original_id
                        });
                    }
                    
                    return isDuplicate;
                });
                
                console.log(`重复消息模式：从${this.messages.length}条消息中筛选出${duplicateMessages.length}条重复消息`);
                return [...duplicateMessages];
            }
            
            // 确保返回新的数组引用，避免Vue缓存问题
            return [...this.messages];
        },
        
        // 是否全选
        allSelected() {
            if (!this.filteredMessages || this.filteredMessages.length === 0) {
                return false;
            }
            const selectableMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
            return selectableMessages.length > 0 && 
                   selectableMessages.every(msg => this.selectedMessages.includes(msg.id));
        }
    },
    
    created() {
        // 确保所有响应式数据正确初始化
        if (!this.mediaPreview) {
            this.mediaPreview = { show: false, url: null };
        }
    },
    
    watch: {
        'filters.status': function(newVal, oldVal) {
            // 如果状态筛选器被清空（变为null），自动设置为'pending'
            if (newVal === null) {
                this.filters.status = 'pending';
            }
        },
        'filters.source_channel': function(newVal, oldVal) {
            console.log(`频道选择变化：${oldVal} -> ${newVal}`);
            // 频道变化时自动加载消息
            this.loadMessages();
        }
    },
    
    async mounted() {
        try {
            // 初始化权限检查
            const isAuthorized = await authManager.initPageAuth('messages.view');
            if (!isAuthorized) {
                return;
            }
            
            // 初始化权限按钮可见性
            await this.initializePermissions();
            
            // 初始化状态管理器
            if (window.messageStateManager) {
                window.messageStateManager.subscribe(this.handleStateUpdates);
            }
            
            // 检查是否需要刷新（从训练页面返回）
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('refresh') === 'true') {
                // 清除refresh参数，避免重复刷新
                window.history.replaceState({}, document.title, window.location.pathname);
                // 强制刷新数据
                this.messages = [];
            }
            
            // 并行加载初始数据
            await Promise.all([
                this.loadMessages().catch(err => {
                    console.error('加载消息失败:', err);
                    MessageManager.error('加载消息失败，请刷新页面重试');
                }),
                this.loadStats().catch(err => {
                    console.error('加载统计失败:', err);
                }),
                this.loadChannelInfo().catch(err => {
                    console.error('加载频道信息失败:', err);
                })
            ]);
            
            // 建立WebSocket连接（非关键功能，失败不影响使用）
            try {
                this.connectWebSocket();
            } catch (err) {
                console.warn('WebSocket连接失败，实时更新功能将不可用:', err);
            }
            
            // 定期检查WebSocket连接状态
            this.connectionCheckInterval = setInterval(() => {
                try {
                    this.checkWebSocketConnection();
                } catch (err) {
                    console.warn('WebSocket连接检查失败:', err);
                }
            }, 10000);
            
            // 页面获得焦点时立即刷新
            window.addEventListener('focus', () => {
                this.loadMessages().catch(err => {
                    console.error('焦点刷新失败:', err);
                });
                this.loadStats().catch(err => {
                    console.error('统计刷新失败:', err);
                });
            });
            
            // 添加滚动监听
            this.setupScrollListener();
        } catch (error) {
            console.error('页面初始化失败:', error);
            MessageManager.error('页面初始化失败，部分功能可能不可用');
        }
    },
    
    beforeUnmount() {
        // 标记组件正在卸载，避免重连
        this._isUnmounting = true;
        
        // 清理定时器
        if (this.connectionCheckInterval) {
            clearInterval(this.connectionCheckInterval);
            this.connectionCheckInterval = null;
        }
        
        // 清理心跳定时器
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
        
        // 关闭WebSocket连接
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        
        // 移除事件监听器
        if (this.scrollHandler) {
            window.removeEventListener('scroll', this.scrollHandler);
            const container = document.querySelector('.message-list');
            if (container) {
                container.removeEventListener('scroll', this.scrollHandler);
            }
        }
    },
    
    methods: {
        // 初始化权限
        async initializePermissions() {
            try {
                // 获取当前用户信息
                const response = await axios.get(window.API.adminAuth.current);
                const adminInfo = response.data;
                
                // 检查权限检查器是否存在
                if (window.permissionChecker && typeof window.permissionChecker.initialize === 'function') {
                    try {
                        const initialized = await window.permissionChecker.initialize(adminInfo);
                        if (initialized) {
                            // 更新按钮可见性
                            this.buttonVisibility = window.permissionChecker.getButtonVisibility();
                        } else {
                            // 初始化失败，使用降级权限
                            console.warn('权限检查器初始化失败，使用降级权限');
                            this.setFallbackPermissions('limited');
                        }
                    } catch (error) {
                        // 权限初始化异常 - 使用降级权限
                        console.error('权限检查器执行错误:', error);
                        this.setFallbackPermissions('limited');
                    }
                } else {
                    // 权限检查器不存在，根据用户角色设置基础权限
                    console.warn('权限检查器未加载，使用基础权限');
                    if (adminInfo && adminInfo.role) {
                        // 根据角色设置权限
                        if (adminInfo.role === 'super_admin') {
                            this.setFallbackPermissions('full');
                        } else if (adminInfo.role === 'admin') {
                            this.setFallbackPermissions('admin');
                        } else {
                            this.setFallbackPermissions('view');
                        }
                    } else {
                        // 默认只读权限
                        this.setFallbackPermissions('view');
                    }
                }
            } catch (error) {
                // 获取用户信息失败 - 使用最小权限
                console.error('获取用户信息失败:', error);
                this.setFallbackPermissions('minimal');
            }
        },
        
        // 设置降级权限
        setFallbackPermissions(level) {
            switch(level) {
                case 'full':
                    // 完整权限
                    this.buttonVisibility = {
                        edit: true,
                        approve: true,
                        reject: true,
                        markAsAd: true,
                        markAsTail: true,
                        executeFilter: true,
                        refetchMedia: true,
                        delete: true
                    };
                    break;
                case 'admin':
                    // 管理员权限
                    this.buttonVisibility = {
                        edit: true,
                        approve: true,
                        reject: true,
                        markAsAd: true,
                        markAsTail: false,
                        executeFilter: true,
                        refetchMedia: true,
                        delete: false
                    };
                    break;
                case 'limited':
                    // 有限权限
                    this.buttonVisibility = {
                        edit: true,
                        approve: true,
                        reject: true,
                        markAsAd: false,
                        markAsTail: false,
                        executeFilter: false,
                        refetchMedia: false,
                        delete: false
                    };
                    break;
                case 'view':
                    // 只读权限
                    this.buttonVisibility = {
                        edit: false,
                        approve: false,
                        reject: false,
                        markAsAd: false,
                        markAsTail: false,
                        executeFilter: false,
                        refetchMedia: true,
                        delete: false
                    };
                    break;
                case 'minimal':
                default:
                    // 最小权限
                    this.buttonVisibility = {
                        edit: false,
                        approve: false,
                        reject: false,
                        markAsAd: false,
                        markAsTail: false,
                        executeFilter: false,
                        refetchMedia: false,
                        delete: false
                    };
                    break;
            }
        },
        
        async loadChannelInfo() {
            try {
                const response = await axios.get(window.API.messages.channelInfo);
                if (response.data.success) {
                    this.channelInfo = response.data.data;
                }
            } catch (error) {
                // console.error('加载频道信息失败:', error);
            }
        },
        
        
        async loadMessages(append = false) {
            if (append) {
                this.isLoadingMore = true;
            } else {
                // 立即清空消息数据和设置加载状态
                this.messages = [];  
                this.selectedMessages = [];  
                this.previousMessageIds = new Set();  
                this.currentPage = 1;
                this.hasMore = true;  // 重置hasMore状态
                this.loading = true;
                this.loadingMessage = '正在加载消息数据...';
            }
            
            try {
                // 准备请求参数（过滤掉前端专用参数）
                const { _show_duplicates, ...apiFilters } = this.filters;
                const params = {
                    ...apiFilters,
                    page: this.currentPage,
                    // 🔧 重复消息模式下增加页面大小，确保获取足够多的消息进行筛选
                    size: _show_duplicates ? Math.max(this.pageSize * 3, 50) : this.pageSize
                };
                
                // 只有当status为null或undefined时才使用默认值，空字符串应该被保留
                if (this.filters.status === null || this.filters.status === undefined) {
                    params.status = 'pending';
                }
                
                // 过滤掉空字符串的source_channel参数
                if (!params.source_channel || params.source_channel.trim() === '') {
                    delete params.source_channel;
                }
                
                // 添加搜索关键词参数
                if (this.searchKeyword && this.searchKeyword.trim()) {
                    params.search = this.searchKeyword.trim();
                }
                
                const response = await axios.get(window.API.messages.list, {
                    params: params
                });
                
                if (response.data && response.data.messages && Array.isArray(response.data.messages)) {
                    const newMessages = response.data.messages;
                    
                    // 检查是否还有更多数据
                    this.hasMore = newMessages.length === this.pageSize;
                    
                    // 计算真正的新消息
                    const currentMessageIds = new Set(newMessages.map(msg => msg.id));
                    const reallyNewMessages = newMessages.filter(msg => !this.previousMessageIds.has(msg.id));
                    
                    // 更新消息列表
                    if (append) {
                        // 追加到现有列表，避免重复
                        const existingIds = new Set(this.messages.map(m => m.id));
                        const uniqueNewMessages = newMessages.filter(msg => !existingIds.has(msg.id));
                        this.messages = [...this.messages, ...uniqueNewMessages];
                        
                        // 如果没有新的唯一消息，说明已经到底了
                        if (uniqueNewMessages.length === 0) {
                            this.hasMore = false;
                        }
                    } else {
                        // 替换整个列表
                        this.messages = newMessages;
                    }
                    
                    // 只有在追加模式且有真正新消息时才显示提示
                    if (append && reallyNewMessages.length > 0) {
                        MessageManager.success(`收到 ${reallyNewMessages.length} 条新消息`);
                    } else if (!append && this.filters.source_channel) {
                        // 频道切换时显示提示
                        const channelInfo = this.uniqueChannels[this.filters.source_channel];
                        const channelName = this.getChannelDisplayName(channelInfo);
                        MessageManager.info(`已切换到「${channelName}」，共 ${newMessages.length} 条消息`);
                    }
                    
                    // 更新已知消息ID集合
                    this.previousMessageIds = currentMessageIds;
                    
                    // 强制Vue下一帧重新渲染，确保媒体URL被正确加载
                    this.$nextTick(() => {
                        // console.log('消息列表已更新，触发媒体重新加载');
                        // 重新设置滚动监听器，确保DOM更新后正确绑定
                        setTimeout(() => this.setupScrollListener(), 100);
                    });
                } else {
                    this.messages = [];
                    // console.warn('API返回格式异常:', response.data);
                    if (this.previousMessageIds.size === 0) {
                        MessageManager.warning('暂无消息数据');
                    }
                }
            } catch (error) {
                // console.error('加载消息失败:', error);
                this.messages = [];
                MessageManager.error('加载消息失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 根据模式正确清理状态
                if (append) {
                    this.isLoadingMore = false;
                } else {
                    this.loading = false;
                }
            }
        },
        
        // 加载更多消息
        async loadMore() {
            // 双重检查，防止重复加载
            if (this.isLoadingMore || !this.hasMore) {
                // console.log('跳过加载更多:', { isLoadingMore: this.isLoadingMore, hasMore: this.hasMore });
                return;
            }
            
            // 立即设置加载状态，防止重复触发
            this.isLoadingMore = true;
            
            try {
                // console.log('容器滚动触发加载更多');
                // console.log(`加载更多消息，当前页: ${this.currentPage} -> ${this.currentPage + 1}`);
                this.currentPage++;
                await this.loadMessages(true);
                
                // 检查是否真的还有更多数据
                // 如果当前消息总数小于已加载页数*每页数量，说明没有更多了
                const expectedMessages = this.currentPage * this.pageSize;
                if (this.messages.length < expectedMessages - this.pageSize) {
                    this.hasMore = false;
                    // console.log('已加载所有消息，总数:', this.messages.length);
                }
            } finally {
                // 确保加载状态被重置
                this.isLoadingMore = false;
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
                    this.stats.duplicates.value = stats.duplicates || 0;
                    this.stats.chats.value = stats.chats || 0;
                }
            } catch (error) {
                // console.error('加载统计信息失败:', error);
            }
        },

        // 获取频道名称
        getChannelName(channel_id) {
            if (this.channelInfo[channel_id]) {
                return this.channelInfo[channel_id].title || this.channelInfo[channel_id].name || channel_id;
            }
            return channel_id;
        },
        
        // 获取频道显示名称（用于下拉框）
        getChannelDisplayName(channel) {
            if (!channel) return '未知频道';
            
            // 优先使用title，其次name
            let displayName = channel.title || channel.name || '未知频道';
            
            // 添加[@用户名]标识
            const username = channel.username;
            if (username) {
                // 确保username以@开头
                const formattedUsername = username.startsWith('@') ? username : '@' + username;
                displayName += ` [${formattedUsername}]`;
            }
            
            // 如果名称太长，截取前50个字符（增加长度以容纳用户名）
            if (displayName.length > 50) {
                return displayName.substring(0, 50) + '...';
            }
            
            return displayName;
        },
        
        // 处理频道切换事件
        handleChannelChange() {
            if (!this.filters.source_channel) {
                MessageManager.info('已清除频道筛选，显示所有频道的消息');
            }
            
            this.loadMessages();
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
        
        // 获取原消息链接
        getOriginalMessageLink(message) {
            if (!message.message_id) {
                return '#';
            }
            
            // 优先使用后端提供的link_prefix
            if (message.source_channel_link_prefix) {
                return `${message.source_channel_link_prefix}/${message.message_id}`;
            }
            
            // 兼容旧逻辑：如果没有link_prefix，尝试自己构建
            if (!message.source_channel) {
                return '#';
            }
            
            let channelId = message.source_channel;
            
            // 如果是数字ID（如 -1001234567890），需要特殊处理
            if (channelId.startsWith('-100')) {
                // 私有频道使用 c/ 格式
                const id = channelId.substring(4);  // 移除 -100 前缀
                return `https://t.me/c/${id}/${message.message_id}`;
            } else {
                // 其他情况尝试作为私有频道处理
                const id = channelId.replace('-', '');
                return `https://t.me/c/${id}/${message.message_id}`;
            }
        },
        
        // 统计面板点击事件
        handleStatClick(statKey) {
            // 点击标签页时，清除频道选择并设置对应的筛选条件
            this.filters.source_channel = '';  // 清除频道选择
            
            switch(statKey) {
                case 'pending':
                    this.filters.status = 'pending';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    this.filters._show_duplicates = false;
                    break;
                case 'approved':
                    this.filters.status = 'approved';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    this.filters._show_duplicates = false;
                    break;
                case 'rejected':
                    this.filters.status = 'rejected';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    this.filters._show_duplicates = false;
                    break;
                case 'ads':
                    this.filters.status = '';
                    this.filters.is_ad = true;
                    this.filters.filter_reason = null;
                    this.filters._show_duplicates = false;
                    break;
                case 'duplicates':
                    this.filters.status = '';  // 不限制状态，因为重复消息可能有不同状态
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;  // 不通过filter_reason筛选
                    // 🔧 新增：设置特殊标识来显示重复消息对比
                    this.filters._show_duplicates = true;
                    break;
                case 'chats':
                    this.filters.status = 'rejected';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = 'chat_content_filter';
                    break;
                default:
                    // 总消息：清除所有筛选条件
                    this.filters.status = '';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
            }
            
            MessageManager.info(`已切换到「${this.getStatLabel(statKey)}」并清除频道筛选`);
            this.loadMessages();
        },
        
        // 获取统计标签的显示名称
        getStatLabel(statKey) {
            const labelMap = {
                'total': '总消息',
                'pending': '待审核',
                'approved': '已批准', 
                'rejected': '已拒绝',
                'ads': '广告消息',
                'duplicates': '重复消息',
                'chats': '聊天消息'
            };
            return labelMap[statKey] || '总消息';
        },
        
        // 点击频道名称筛选该频道的消息
        filterByChannel(channelId, channelTitle) {
            // 设置频道筛选
            this.filters.source_channel = channelId;
            // 重置其他筛选条件以便只显示该频道的消息
            this.filters.status = '';
            this.filters.is_ad = null;
            // 重新加载消息
            this.currentPage = 1;
            this.hasMore = true;
            this.loadMessages();
            // 显示筛选提示
            MessageManager.info(`正在显示频道「${channelTitle || channelId}」的消息`);
        },
        
        // 清除频道筛选
        clearChannelFilter() {
            this.filters.source_channel = '';
            this.filters.status = 'pending';  // 恢复默认筛选
            this.currentPage = 1;
            this.hasMore = true;
            this.loadMessages();
            MessageManager.info('已清除频道筛选');
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
                // 先找到消息对象（在移除之前）
                const message = this.messages.find(msg => msg.id === messageId);
                
                const response = await axios.post(`/api/messages/${messageId}/reject?reviewer=Web用户`);
                if (response.data.success) {
                    MessageManager.success('消息已拒绝');
                    
                    // 如果当前筛选状态不是"已拒绝"，才从列表中移除消息
                    // 如果筛选状态是"已拒绝"，则更新消息状态而不是移除
                    if (this.filters.status === 'rejected') {
                        // 更新消息状态
                        const msgIndex = this.messages.findIndex(msg => msg.id === messageId);
                        if (msgIndex !== -1) {
                            this.messages[msgIndex].status = 'rejected';
                        }
                    } else {
                        // 从列表中移除消息
                        this.messages = this.messages.filter(msg => msg.id !== messageId);
                    }
                    
                    this.loadStats();
                    
                    // 如果消息有审核群消息ID，删除审核群中的消息
                    if (message && message.review_message_id) {
                        try {
                            // 调用删除审核群消息的API
                            await axios.delete(`/api/messages/${messageId}/review-message`);
                        } catch (error) {
                            // console.error('删除审核群消息失败:', error);
                        }
                    }
                } else {
                    MessageManager.error('拒绝失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('拒绝失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 搜索消息
        searchMessages() {
            // 直接加载消息，不设置最小长度限制
            // 允许空搜索和单字符搜索
            this.loadMessages();
        },
        
        // 切换消息选择状态
        toggleMessageSelection(message) {
            const index = this.selectedMessages.indexOf(message.id);
            if (index > -1) {
                this.selectedMessages.splice(index, 1);
            } else {
                this.selectedMessages.push(message.id);
            }
        },
        
        // 检查消息是否被选中
        isMessageSelected(messageId) {
            return this.selectedMessages.includes(messageId);
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
            // 如果是视频文件，显示文件详情而不是直接预览
            if (url && (url.includes('.mp4') || url.includes('.MP4') || url.includes('.avi') || url.includes('.mov'))) {
                this.showFileDetails(url);
            } else {
                this.mediaPreview.url = url;
                this.mediaPreview.show = true;
            }
        },
        
        // 显示文件详情
        showFileDetails(url) {
            if (!url) return;
            
            // 从URL中提取文件信息
            const fileName = url.split('/').pop();
            const fileExt = fileName.split('.').pop().toLowerCase();
            
            // 简化文件名显示
            const simplifiedName = this.simplifyFileName(fileName);
            
            // 创建文件详情对话框
            const fileDetails = {
                fileName: simplifiedName,
                originalFileName: fileName, 
                path: url,
                type: this.getFileType(fileExt),
                size: '计算中...',
                hash: fileName.includes('_') ? fileName.split('_').slice(-1)[0].split('.')[0] : '',
                createTime: this.extractCreateTime(fileName),
                tags: this.extractTags(fileName)
            };
            
            // 显示文件详情对话框
            this.showFileDetailsDialog(fileDetails);
        },
        
        // 简化文件名
        simplifyFileName(fileName) {
            if (!fileName) return '';
            
            // 匹配格式: XXXX_YYYYMMDD_HHMMSS_hash.ext
            const pattern = /^(\d+)_(\d{8})_(\d{6})_([a-f0-9]+)\.(\w+)$/i;
            const match = fileName.match(pattern);
            
            if (match) {
                const [, id, date, time, , ext] = match;
                // 返回简化的格式: ID_日期_时间.扩展名
                return `${id}_${date}_${time}.${ext.toUpperCase()}`;
            }
            
            // 如果文件名过长，截断显示
            if (fileName.length > 30) {
                const ext = fileName.split('.').pop();
                return fileName.substring(0, 20) + '...' + '.' + ext;
            }
            
            return fileName;
        },
        
        // 提取创建时间
        extractCreateTime(fileName) {
            const pattern = /_(\d{8})_(\d{6})_/;
            const match = fileName.match(pattern);
            if (match) {
                const [, date, time] = match;
                const year = date.substring(0, 4);
                const month = date.substring(4, 6);
                const day = date.substring(6, 8);
                const hour = time.substring(0, 2);
                const minute = time.substring(2, 4);
                const second = time.substring(4, 6);
                return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
            }
            return '';
        },
        
        // 提取标签
        extractTags(fileName) {
            const tags = [];
            // 从文件名中提取频道ID等信息
            const idMatch = fileName.match(/^(\d+)_/);
            if (idMatch) {
                tags.push('#' + idMatch[1]);
            }
            return tags;
        },
        
        // 获取文件类型
        getFileType(ext) {
            const typeMap = {
                'mp4': 'video',
                'avi': 'video',
                'mov': 'video',
                'mkv': 'video',
                'jpg': 'photo',
                'jpeg': 'photo',
                'png': 'photo',
                'gif': 'photo',
                'pdf': 'document',
                'doc': 'document',
                'docx': 'document'
            };
            return typeMap[ext.toLowerCase()] || 'file';
        },
        
        // 显示文件详情对话框
        showFileDetailsDialog(details) {
            // 创建或更新文件详情对话框数据
            if (!this.fileDetailsDialog) {
                this.fileDetailsDialog = {
                    visible: false,
                    details: null
                };
            }
            
            // 确保响应式更新 - 重新赋值整个对象
            this.fileDetailsDialog = {
                visible: true,
                details: { ...details }
            };
            
            // 异步获取文件大小
            this.getFileSize(details.path);
        },
        
        // 获取文件大小
        async getFileSize(url) {
            try {
                const response = await fetch(url, { method: 'HEAD' });
                const size = response.headers.get('content-length');
                if (size && this.fileDetailsDialog && this.fileDetailsDialog.details) {
                    const sizeInBytes = parseInt(size);
                    this.fileDetailsDialog.details.size = this.formatFileSize(sizeInBytes);
                }
            } catch (error) {
                // console.error('获取文件大小失败:', error);
                if (this.fileDetailsDialog && this.fileDetailsDialog.details) {
                    this.fileDetailsDialog.details.size = '未知';
                }
            }
        },
        
        // 格式化文件大小
        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        // 处理媒体加载错误
        handleMediaError(event, message) {
            // console.error('媒体加载失败:', message.id, event.target.src);
            
            // 创建错误占位符
            const placeholder = document.createElement('div');
            placeholder.className = 'media-error-placeholder';
            placeholder.innerHTML = `
                <div class="error-icon">📷</div>
                <div class="error-text">图片加载失败</div>
            `;
            
            // 替换失败的图片
            const parent = event.target.parentNode;
            if (parent) {
                parent.replaceChild(placeholder, event.target);
            } else {
                event.target.style.display = 'none';
            }
        },

        // 获取媒体组数据属性
        getMediaGroupCount(message) {
            if (!this.isCombinedMessage(message)) return 1;
            return Math.min(message.media_group_display.length, 9);
        },

        // WebSocket连接管理
        connectWebSocket() {
            try {
                // 如果已经在连接中，避免重复连接
                if (this.websocket && this.websocket.readyState === WebSocket.CONNECTING) {
                    console.log('WebSocket正在连接中，跳过重复连接');
                    return;
                }
                
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/api/ws/messages`;
                
                // 创建新连接前清理旧连接
                if (this.websocket) {
                    this.websocket.close();
                }
                
                this.websocket = new WebSocket(wsUrl);
                
                // 设置超时检测
                const connectionTimeout = setTimeout(() => {
                    if (this.websocket.readyState === WebSocket.CONNECTING) {
                        console.warn('WebSocket连接超时，关闭连接');
                        this.websocket.close();
                    }
                }, 10000); // 10秒超时
                
                this.websocket.onopen = () => {
                    clearTimeout(connectionTimeout);
                    this.websocketConnected = true;
                    this.systemStatus = '在线';
                    this.reconnectAttempts = 0; // 重置重连次数
                    
                    // 发送心跳
                    this.startHeartbeat();
                };
                
                this.websocket.onmessage = (event) => {
                    try {
                        this.handleWebSocketMessage(event);
                    } catch (err) {
                        console.error('处理WebSocket消息失败:', err);
                    }
                };
                
                this.websocket.onclose = (event) => {
                    clearTimeout(connectionTimeout);
                    this.websocketConnected = false;
                    this.systemStatus = '离线';
                    
                    // 停止心跳
                    if (this.heartbeatInterval) {
                        clearInterval(this.heartbeatInterval);
                        this.heartbeatInterval = null;
                    }
                    
                    // 实现指数退避重连策略
                    if (!this.reconnectAttempts) this.reconnectAttempts = 0;
                    this.reconnectAttempts++;
                    
                    if (this.reconnectAttempts <= 10) { // 最多重试10次
                        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 30000); // 最大延迟30秒
                        console.log(`WebSocket将在${delay/1000}秒后尝试第${this.reconnectAttempts}次重连`);
                        
                        setTimeout(() => {
                            if (!this.websocketConnected && !this._isUnmounting) {
                                this.connectWebSocket();
                            }
                        }, delay);
                    } else {
                        console.warn('WebSocket重连次数已达上限，停止重连');
                        this.systemStatus = '连接断开（已停止重试）';
                    }
                };
                
                this.websocket.onerror = (error) => {
                    clearTimeout(connectionTimeout);
                    console.warn('WebSocket连接错误，将尝试重连');
                    this.websocketConnected = false;
                    this.systemStatus = '连接错误';
                };
                
            } catch (error) {
                console.error('建立WebSocket连接失败:', error);
                this.websocketConnected = false;
                this.systemStatus = '连接失败';
                
                // 5秒后重试
                setTimeout(() => {
                    if (!this.websocketConnected && !this._isUnmounting) {
                        this.connectWebSocket();
                    }
                }, 5000);
            }
        },

        // 处理WebSocket消息
        handleWebSocketMessage(event) {
            try {
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch (parseError) {
                    // console.warn('收到非JSON格式的WebSocket消息:', event.data);
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
                        // console.log('未知WebSocket消息类型:', data.type);
                }
            } catch (error) {
                // console.error('处理WebSocket消息失败:', error);
            }
        },

        // 处理新消息
        handleNewMessage(messageData) {
            // console.log('📨 收到WebSocket新消息:', {
            //     id: messageData.id,
            //     status: messageData.status,
            //     is_ad: messageData.is_ad,
            //     content_preview: messageData.content ? messageData.content.substring(0, 50) + '...' : '无内容'
            // });
            
            // 检查消息是否已存在
            const existingIndex = this.messages.findIndex(msg => msg.id === messageData.id);
            
            if (existingIndex === -1) {
                // 检查新消息是否符合当前筛选条件
                let shouldAddMessage = true;
                let filterReason = null;
                
                // 检查状态筛选
                if (this.filters.status && messageData.status !== this.filters.status) {
                    shouldAddMessage = false;
                    filterReason = `状态不匹配: 期望${this.filters.status}, 实际${messageData.status}`;
                }
                
                // 检查广告筛选
                if (this.filters.is_ad !== null && messageData.is_ad !== this.filters.is_ad) {
                    shouldAddMessage = false;
                    filterReason = `广告状态不匹配: 期望${this.filters.is_ad}, 实际${messageData.is_ad}`;
                }
                
                // 检查搜索关键词
                if (this.searchKeyword && this.searchKeyword.trim()) {
                    const keyword = this.searchKeyword.trim().toLowerCase();
                    const content = (messageData.filtered_content || messageData.content || '').toLowerCase();
                    if (!content.includes(keyword)) {
                        shouldAddMessage = false;
                        filterReason = `内容不包含关键词: ${keyword}`;
                    }
                }
                
                if (shouldAddMessage) {
                    // 新消息，添加到列表顶部
                    this.messages.unshift(messageData);
                    // console.log('✅ 新消息已添加到列表, 当前列表长度:', this.messages.length);
                } else {
                    // console.log('⚠️ 新消息未添加到列表, 原因:', filterReason);
                }
                
                // 显示通知（无论是否添加到列表）
                const contentPreview = messageData.content ? messageData.content.substring(0, 30) + '...' : '新消息（无文本内容）';
                MessageManager.success(`收到新消息: ${contentPreview}`);
                
                // 刷新统计信息
                this.loadStats();
                
                // 强制Vue重新渲染媒体元素
                this.$nextTick(() => {
                    // 确保媒体URL被正确加载
                    if (messageData.media_display_url || messageData.media_group_display) {
                        // console.log('🎨 新消息包含媒体，触发重新渲染');
                    }
                });
            } else {
                // console.log('⚠️ 消息已存在，跳过添加');
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
                    // console.log(`消息 ${updateData.message_id} 已从列表中移除（状态: ${updateData.status}）`);
                } else {
                    this.messages[messageIndex].status = updateData.status;
                    // console.log(`消息 ${updateData.message_id} 状态更新为: ${updateData.status}`);
                }
            }
        },

        // 检查WebSocket连接状态
        checkWebSocketConnection() {
            if (!this.websocketConnected && (!this.websocket || this.websocket.readyState === WebSocket.CLOSED)) {
                // console.log('WebSocket断开，尝试重连...');
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
            this.editDialog.content = message.filtered_content || '';
            this.editDialog.originalMessage = message;
            this.editDialog.visible = true;
        },
        
        // 保存编辑的消息
        async saveEditedMessage() {
            try {
                // axios拦截器会自动添加认证头，无需手动设置
                const response = await axios.post(`/api/messages/${this.editDialog.messageId}/edit-publish`, {
                    content: this.editDialog.content
                });
                if (response.data.success) {
                    MessageManager.success('消息已编辑并保存');
                    this.editDialog.visible = false;
                    // 更新本地消息内容
                    const messageIndex = this.messages.findIndex(msg => msg.id === this.editDialog.messageId);
                    if (messageIndex !== -1) {
                        // 只更新filtered_content字段
                        this.messages[messageIndex].filtered_content = response.data.content || this.editDialog.content;
                        // Vue 3中直接修改即可触发响应式更新
                        // 如果需要强制刷新，可以重新赋值整个数组
                        this.messages = [...this.messages];
                    }
                } else {
                    MessageManager.error('编辑失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('编辑失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 切换全选
        toggleSelectAll() {
            if (this.allSelected) {
                this.selectedMessages = [];
            } else {
                const selectableMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
                this.selectedMessages = selectableMessages.map(msg => msg.id);
            }
        },
        
        // 检查消息是否被选中
        isSelected(messageId) {
            return this.selectedMessages.includes(messageId);
        },
        
        // 切换消息选择
        toggleMessage(messageId) {
            const index = this.selectedMessages.indexOf(messageId);
            if (index > -1) {
                this.selectedMessages.splice(index, 1);
            } else {
                this.selectedMessages.push(messageId);
            }
        },
        
        // 批量批准消息
        async approveMessages() {
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
        
        // 批量拒绝消息
        async rejectMessages() {
            if (this.selectedMessages.length === 0) {
                MessageManager.warning('请先选择要拒绝的消息');
                return;
            }
            
            try {
                const response = await axios.post('/api/messages/batch/reject', {
                    message_ids: this.selectedMessages
                });
                if (response.data.success) {
                    MessageManager.success(`成功拒绝 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.loadStats();
                } else {
                    MessageManager.error('批量拒绝失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('批量拒绝失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 重置消息状态 - 用于误判恢复
        async resetMessage(message) {
            try {
                // 解析消息ID
                const idParts = message.id.split(':');
                if (idParts.length !== 2) {
                    MessageManager.error('消息ID格式错误');
                    return;
                }
                
                const [sourceChannel, messageId] = idParts;
                
                // 确认操作
                const confirmText = message.is_ad 
                    ? '确定要重置此广告消息吗？这将从训练样本中移除并重置为待审核状态。'
                    : '确定要重置此消息为待审核状态吗？';
                    
                if (!confirm(confirmText)) {
                    return;
                }
                
                const response = await axios.post('/api/messages/reset', {
                    source_channel: sourceChannel,
                    message_id: parseInt(messageId),
                    is_ad: message.is_ad
                });
                
                if (response.data.success) {
                    MessageManager.success('消息已重置为待审核状态');
                    this.loadMessages();
                    this.loadStats();
                } else {
                    MessageManager.error('重置失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('重置失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 批量删除消息
        async deleteMessages() {
            if (this.selectedMessages.length === 0) {
                MessageManager.warning('请先选择要删除的消息');
                return;
            }
            
            if (!confirm(`确定要删除 ${this.selectedMessages.length} 条消息吗？`)) {
                return;
            }
            
            try {
                const response = await axios.post('/api/messages/batch/delete', {
                    message_ids: this.selectedMessages
                });
                if (response.data.success) {
                    MessageManager.success(`成功删除 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.loadStats();
                } else {
                    MessageManager.error('批量删除失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('批量删除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 打开编辑对话框
        openEditDialog(message) {
            this.editDialog.messageId = message.id;
            this.editDialog.content = message.filtered_content || '';
            this.editDialog.originalMessage = message;
            this.editDialog.visible = true;
        },
        
        // 保存编辑
        async saveEdit() {
            await this.saveEditedMessage();
        },
        
        // 获取状态标签
        getStatusTag(status) {
            const statusMap = {
                'pending': { text: '待审核', type: 'warning' },
                'approved': { text: '已批准', type: 'success' },
                'rejected': { text: '已拒绝', type: 'danger' },
                'auto_forwarded': { text: '自动转发', type: 'info' }
            };
            return statusMap[status] || { text: status, type: 'default' };
        },

        // 标记为广告并加入训练样本
        async markAsAd(message) {
            try {
                if (!confirm('确定将此消息标记为广告吗？这将帮助AI更好地识别广告内容。')) {
                    return;
                }
                
                const response = await axios.post('/api/training-db/mark-ad-message', {
                    message_id: message.id
                });
                
                if (response.data.success) {
                    const hasAutoRejected = response.data.auto_rejected;
                    const successMsg = hasAutoRejected ? 
                        '已标记为广告、自动拒绝并加入训练样本' : 
                        '已标记为广告并加入训练样本';
                    MessageManager.success(successMsg);
                    // 重新加载消息列表以反映状态变化
                    await this.loadMessages();
                    await this.loadStats();
                } else {
                    MessageManager.error(response.data.message || '标记失败');
                }
            } catch (error) {
                // console.error('标记广告失败:', error);
                MessageManager.error('标记失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 标记为"不是广告" - 纠正AI误判
        async markAsNotAd(message) {
            try {
                if (!confirm('确定将此消息标记为"不是广告"吗？这将帮助AI减少误判。')) {
                    return;
                }
                
                const response = await axios.post(`/api/messages/${message.id}/not-ad`);
                
                if (response.data.success) {
                    MessageManager.success('已标记为"不是广告"，消息状态已改为待审核');
                    // 重新加载消息以获取最新的过滤内容
                    // 因为后端已应用了尾部过滤和推广链接过滤
                    await this.loadMessages();
                    await this.loadStats();
                } else {
                    MessageManager.error(response.data.message || '操作失败');
                }
            } catch (error) {
                MessageManager.error('操作失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 训练尾部
        trainTail(message) {
            // 跳转到训练页面，并传递消息信息用于尾部训练
            const params = new URLSearchParams({
                message_id: message.id,
                channel_id: message.source_channel,
                mode: 'tail'
            });
            // 使用绝对路径确保正确跳转
            window.location.href = '/static/train.html?' + params.toString();
        },
        
        // 手动执行尾部过滤
        async filterTail(message) {
            try {
                const response = await axios.post(`/api/messages/${message.id}/filter-tail`);
                
                if (response.data.success) {
                    if (response.data.removed_length && response.data.removed_length > 0) {
                        MessageManager.success(`尾部过滤成功，移除了 ${response.data.removed_length} 个字符`);
                        // 更新消息的过滤后内容
                        const index = this.messages.findIndex(m => m.id === message.id);
                        if (index !== -1) {
                            this.messages[index].filtered_content = response.data.filtered_content;
                        }
                    } else {
                        MessageManager.info('未检测到需要过滤的尾部内容');
                    }
                } else {
                    MessageManager.warning(response.data.message || '过滤失败');
                }
            } catch (error) {
                console.error('尾部过滤失败:', error);
                MessageManager.error('尾部过滤失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 检查媒体文件是否存在
        mediaExists(message) {
            // 对于组合消息，检查媒体组
            if (message.is_combined && message.media_group_display) {
                // 检查是否有任何媒体实际显示
                return message.media_group_display.some(media => 
                    media.display_url && media.display_url.trim() !== '' && !media._loadFailed
                );
            }
            
            // 对于单个媒体
            // 1. 如果没有 media_display_url，文件肯定不存在
            if (!message.media_display_url || message.media_display_url.trim() === '') {
                return false;
            }
            
            // 2. 如果已标记加载失败，文件不存在
            if (message._mediaLoadFailed) {
                return false;
            }
            
            // 3. 默认认为文件存在（将通过onerror事件动态更新）
            return true;
        },
        
        // 处理图片加载错误
        handleImageError(message, event) {
            // 静默处理，不输出日志避免控制台噪音
            // console.log(`图片加载失败: 消息 #${message.id}`);
            
            // 标记媒体为不存在，触发补抓按钮显示
            if (!message._mediaLoadFailed) {
                message._mediaLoadFailed = true;
            }
            
            // 阻止错误冒泡到控制台
            if (event) {
                event.preventDefault();
            }
        },
        
        // 补抓媒体文件
        async refetchMedia(message) {
            try {
                // 设置加载状态
                this.refetchingMedia[message.id] = true;
                
                // 确认操作
                if (!confirm(`确定要重新下载消息 #${message.id} 的媒体文件吗？`)) {
                    delete this.refetchingMedia[message.id];
                    return;
                }
                
                // 提交补抓任务
                const response = await axios.post(`/api/messages/${message.id}/refetch-media`);
                
                if (response.data.success) {
                    const taskId = response.data.task_id;
                    MessageManager.success('媒体补抓任务已提交，正在处理中...');
                    
                    // 轮询任务状态
                    await this.pollRefetchTaskStatus(taskId, message);
                } else {
                    MessageManager.error(response.data.message || '补抓失败');
                    delete this.refetchingMedia[message.id];
                }
            } catch (error) {
                console.error('补抓媒体失败:', error);
                MessageManager.error('补抓失败: ' + (error.response?.data?.detail || error.message));
                delete this.refetchingMedia[message.id];
            }
        },

        // 轮询补抓任务状态
        async pollRefetchTaskStatus(taskId, message, maxAttempts = 30) {
            let attempts = 0;
            
            const poll = async () => {
                try {
                    attempts++;
                    
                    const response = await axios.get(`/api/refetch-task/${taskId}`);
                    const taskData = response.data.data;
                    
                    if (taskData.status === 'completed') {
                        // 任务完成，更新媒体URL
                        if (taskData.result && taskData.result.media_url) {
                            message.media_url = taskData.result.media_url;
                            
                            // 重新生成显示URL
                            const fileName = taskData.result.media_url.split('/').pop();
                            message.display_url = `/media/${fileName}`;
                            
                            // 触发视图更新
                            this.messages = [...this.messages];
                            
                            MessageManager.success('媒体补抓成功');
                        } else {
                            MessageManager.warning('任务完成但未获取到媒体文件');
                        }
                        
                        delete this.refetchingMedia[message.id];
                        return;
                        
                    } else if (taskData.status === 'failed') {
                        // 任务失败
                        const errorMsg = taskData.error_message || '未知错误';
                        MessageManager.error(`媒体补抓失败: ${errorMsg}`);
                        delete this.refetchingMedia[message.id];
                        return;
                        
                    } else if (taskData.status === 'processing' || taskData.status === 'pending') {
                        // 任务仍在处理中，继续轮询
                        if (attempts < maxAttempts) {
                            setTimeout(poll, 2000); // 2秒后再次检查
                        } else {
                            MessageManager.warning('任务处理超时，请稍后手动检查结果');
                            delete this.refetchingMedia[message.id];
                        }
                    }
                    
                } catch (error) {
                    console.error('检查任务状态失败:', error);
                    if (attempts < maxAttempts) {
                        setTimeout(poll, 2000);
                    } else {
                        MessageManager.error('无法获取任务状态');
                        delete this.refetchingMedia[message.id];
                    }
                }
            };
            
            // 开始轮询
            setTimeout(poll, 1000); // 1秒后开始第一次检查
        },
        
        // 处理状态更新
        handleStateUpdates(updates) {
            // 处理批量状态更新
            if (updates.update && updates.update.length > 0) {
                updates.update.forEach(update => {
                    const index = this.messages.findIndex(m => m.id === update.messageId);
                    if (index !== -1) {
                        // 更新消息状态
                        this.messages[index] = { ...this.messages[index], ...update.changes };
                    }
                });
            }
        },
        
        // 智能全选
        smartSelectAll() {
            const pendingMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
            if (pendingMessages.length === this.selectedMessages.length) {
                this.selectedMessages = [];
            } else {
                this.selectedMessages = pendingMessages.map(msg => msg.id);
            }
        },
        
        // 反选
        invertSelection() {
            const pendingMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
            const currentSelected = new Set(this.selectedMessages);
            this.selectedMessages = pendingMessages
                .filter(msg => !currentSelected.has(msg.id))
                .map(msg => msg.id);
        },
        
        // 清空选择
        clearSelection() {
            this.selectedMessages = [];
        },
        
        // 处理快速选择模式变化
        handleQuickSelectModeChange(enabled) {
            // 可以在这里处理快速选择模式的状态变化
            console.log('快速选择模式:', enabled);
        },
        
        // 按条件快速选择
        handleQuickSelectByCondition(condition) {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            let targetMessages = [];
            
            switch(condition) {
                case 'today':
                    targetMessages = this.filteredMessages.filter(msg => {
                        const msgDate = new Date(msg.created_at);
                        msgDate.setHours(0, 0, 0, 0);
                        return msgDate.getTime() === today.getTime() && msg.status === 'pending';
                    });
                    break;
                case 'ads':
                    targetMessages = this.filteredMessages.filter(msg => 
                        msg.is_ad && msg.status === 'pending'
                    );
                    break;
                case 'no-media':
                    targetMessages = this.filteredMessages.filter(msg => 
                        !msg.media_type && msg.status === 'pending'
                    );
                    break;
                case 'long-text':
                    targetMessages = this.filteredMessages.filter(msg => {
                        const content = msg.filtered_content || msg.content || '';
                        return content.length > 200 && msg.status === 'pending';
                    });
                    break;
            }
            
            this.selectedMessages = targetMessages.map(msg => msg.id);
            MessageManager.success(`已选择 ${targetMessages.length} 条消息`);
        },
        
        // 处理批量操作完成
        handleBatchOperationComplete(result) {
            console.log('批量操作完成:', result);
            // 刷新数据
            this.loadMessages();
            this.loadStats();
        },
        
        // 处理进度更新
        handleProgressUpdate(progress) {
            console.log('进度更新:', progress);
            // 可以在这里显示全局进度条
        },
        
        // 设置滚动监听
        setupScrollListener() {
            // 移除之前的所有滚动监听
            if (this.scrollHandler) {
                window.removeEventListener('scroll', this.scrollHandler);
                const oldContainer = document.querySelector('.message-list');
                if (oldContainer) {
                    oldContainer.removeEventListener('scroll', this.scrollHandler);
                }
            }
            
            // 记录上次触发加载的时间戳
            let lastLoadTime = 0;
            const minLoadInterval = 2000; // 最少间隔2秒才能再次加载
            
            // 创建新的滚动处理函数
            this.scrollHandler = () => {
                // 如果正在加载或没有更多数据，直接返回
                if (this.isLoadingMore || !this.hasMore) {
                    return;
                }
                
                // 检查距离上次加载的时间间隔
                const now = Date.now();
                if (now - lastLoadTime < minLoadInterval) {
                    return;
                }
                
                let scrollPercentage = 0;
                let isNearBottom = false;
                let scrollInfo = {};
                
                // 由于页面使用body滚动，直接检查窗口滚动
                // 不再尝试容器滚动，因为.message-list是grid布局没有自己的滚动
                const windowHeight = window.innerHeight;
                const documentHeight = document.documentElement.scrollHeight;
                const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                
                scrollInfo = {
                    type: '页面滚动',
                    scrollTop,
                    documentHeight,
                    windowHeight,
                    remaining: documentHeight - (scrollTop + windowHeight)
                };
                
                // 计算滚动百分比
                if (documentHeight > windowHeight) {
                    scrollPercentage = (scrollTop + windowHeight) / documentHeight * 100;
                }
                
                // 降低阈值：滚动到90%以上才认为接近底部
                if (scrollPercentage > 90) {
                    isNearBottom = true;
                }
                
                
                // 只在真正接近底部时加载
                if (isNearBottom && !this.isLoadingMore && this.hasMore) {
                    lastLoadTime = now;
                    this.loadMore();
                }
            };
            
            // 只使用窗口滚动监听，因为页面使用body滚动模式
            window.addEventListener('scroll', this.scrollHandler, { passive: true });
        }
    }
};

// 将组件导出供HTML中使用
window.MainApp = MainApp;

// 初始化Vue应用的函数
function initializeVueApp() {
    
    // 首先初始化全局变量
    initializeGlobals();
    
    // 检查必要的依赖
    const missingDeps = [];
    if (typeof Vue === 'undefined') missingDeps.push('Vue');
    if (typeof ElementPlus === 'undefined') missingDeps.push('ElementPlus');
    if (typeof axios === 'undefined') missingDeps.push('axios');
    
    if (missingDeps.length > 0) {
        console.error('缺少必要的依赖:', missingDeps.join(', '));
        const appEl = document.getElementById('app');
        if (appEl) {
            appEl.innerHTML = `
                <div style="padding: 20px; color: #e74c3c; font-family: monospace;">
                    <h2>⚠️ 页面加载失败</h2>
                    <p>缺少必要的依赖库: ${missingDeps.join(', ')}</p>
                    <p>请检查网络连接并刷新页面重试。</p>
                    <button onclick="location.reload()" style="padding: 10px 20px; margin-top: 10px; cursor: pointer;">刷新页面</button>
                </div>
            `;
        }
        return;
    }
    
    try {
        const app = createApp(MainApp);
        
        // 配置全局错误处理
        app.config.errorHandler = (err, instance, info) => {
            console.error('Vue错误:', err, info);
            // 不中断应用运行，只记录错误
            if (window.MessageManager) {
                MessageManager.error('操作失败，请重试');
            }
        };
        
        // 配置全局警告处理
        app.config.warnHandler = (msg, instance, trace) => {
            console.warn('Vue警告:', msg);
        };
        
        app.use(ElementPlus);
        
        // 注册导航栏组件（可选）
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        } else {
            console.warn('导航栏组件未加载，使用降级UI');
        }
        
        // 注册全局错误边界组件
        app.component('error-boundary', {
            template: `
                <div v-if="hasError" style="padding: 20px; background: #fff3cd; color: #856404; border: 1px solid #ffeeba; border-radius: 4px;">
                    <h3>组件加载错误</h3>
                    <p>{{ errorMessage }}</p>
                    <button @click="retry" style="padding: 5px 15px; margin-top: 10px;">重试</button>
                </div>
                <slot v-else></slot>
            `,
            data() {
                return {
                    hasError: false,
                    errorMessage: ''
                };
            },
            errorCaptured(err, instance, info) {
                this.hasError = true;
                this.errorMessage = err.message || '未知错误';
                console.error('组件错误:', err, info);
                return false; // 阻止错误继续传播
            },
            methods: {
                retry() {
                    this.hasError = false;
                    this.errorMessage = '';
                    this.$forceUpdate();
                }
            }
        });
        
        // 注册新组件
        if (window.VirtualList) {
            app.component('virtual-list', window.VirtualList);
        }
        
        if (window.BatchOperationPanel) {
            app.component('batch-operation-panel', window.BatchOperationPanel);
        }
        
        if (window.MessageContentRenderer) {
            app.component('message-content-renderer', window.MessageContentRenderer);
        }
        
        app.mount('#app');
    } catch (error) {
        console.error('Failed to mount Vue app:', error);
        // 提供更友好的错误界面
        const appEl = document.getElementById('app');
        if (appEl) {
            appEl.innerHTML = `
                <div style="padding: 20px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; max-width: 600px; margin: 50px auto; font-family: system-ui, -apple-system, sans-serif;">
                    <h2 style="color: #dc3545; margin-bottom: 15px;">⚠️ 页面加载失败</h2>
                    <div style="background: #fff; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
                        <strong>错误信息：</strong>
                        <code style="display: block; margin-top: 10px; padding: 10px; background: #f4f4f4; border-radius: 4px; overflow-x: auto;">${error.message}</code>
                    </div>
                    <div style="color: #6c757d; margin-bottom: 15px;">
                        <p>可能的解决方案：</p>
                        <ul style="margin-left: 20px;">
                            <li>清除浏览器缓存并刷新页面</li>
                            <li>检查网络连接是否正常</li>
                            <li>使用其他浏览器访问</li>
                            <li>联系系统管理员</li>
                        </ul>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button onclick="location.reload()" style="padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer;">刷新页面</button>
                        <button onclick="window.location.href='/static/status.html'" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">系统状态</button>
                    </div>
                </div>
            `;
        }
    }
}

// 更可靠的初始化方式：检查DOM状态
if (document.readyState === 'loading') {
    // DOM还在加载，等待DOMContentLoaded事件
    document.addEventListener('DOMContentLoaded', initializeVueApp);
} else {
    // DOM已经加载完成（interactive或complete状态），直接初始化
    // 使用setTimeout确保所有脚本都已执行完毕
    setTimeout(initializeVueApp, 0);
}