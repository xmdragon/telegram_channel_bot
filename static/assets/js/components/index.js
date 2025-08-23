/**
 * 主页面协调器 - Linus式"好品味"重构版本
 * 
 * 核心理念：
 * 1. 数据结构驱动程序设计 - "Bad programmers worry about the code. Good programmers worry about data structures"
 * 2. 消除边界情况 - 统一的委托模式处理所有操作
 * 3. 简洁执念 - 协调层只负责协调，不做具体实现
 */

// 确保全局依赖可用
let createApp, ElMessage;

// 延迟初始化函数
function initializeGlobals() {
    if (!createApp) {
        if (window.Vue?.createApp) {
            createApp = window.Vue.createApp;
        } else if (typeof Vue !== 'undefined' && Vue.createApp) {
            createApp = Vue.createApp;
        }
    }
    if (!ElMessage && window.ElementPlus) ElMessage = window.ElementPlus.ElMessage;
}

// 主应用协调器 - 纯协调层，不包含具体业务逻辑
const MainApp = {
    data() {
        // Linus式"好品味"：确保状态初始化完整且可靠
        const baseState = {
            // 加载状态
            loading: false,
            loadingMessage: '',
            isLoadingMore: false,
            isClearing: false,
            
            // 系统状态
            statusMessage: '',
            statusType: 'success',
            systemStatus: '在线',
            
            // WebSocket状态
            websocket: null,
            websocketConnected: false,
            
            // 数据状态
            messages: [],
            selectedMessages: [],
            searchKeyword: '',
            channelInfo: {},
            previousMessageIds: new Set(),
            
            // 分页状态
            currentPage: 1,
            pageSize: 20,
            hasMore: true,
            
            // 筛选状态 - 确保filters对象完整初始化
            filters: {
                status: 'pending',
                is_ad: null,
                source_channel: '',
                filter_reason: null,
                _show_duplicates: false
            },
            
            
            // 操作状态
            processingMessages: new Set(),
            publishingMessages: new Set(), // 正在发布的消息ID集合
            filteringMessages: new Set(), // 正在过滤的消息ID集合 - Linus风格状态管理
            isBatchPublishing: false, // 批量发布状态
            refetchingMedia: {},
            
            // 对话框状态
            mediaPreview: {
                show: false,
                url: null
            },
            fileDetailsDialog: {
                visible: false,
                details: null
            },
            editDialog: {
                visible: false,
                messageId: null,
                filteredContent: '',
                originalMessage: null
            },
            originalMessageDialog: {
                visible: false,
                messageId: null,
                message: null,
                loading: false,
                error: null
            },
            
            // 虚拟滚动配置
            useVirtualScroll: true,
            virtualScrollThreshold: 100,
            messageItemHeight: 200,
            virtualListHeight: 600,
            
            // 权限控制
            buttonVisibility: {
                edit: true,
                approve: true,
                reject: true,
                markAsAd: true,
                markAsTail: true,
                executeFilter: true,
                refetchMedia: true,
                delete: false
            }
        };
        
        // 如果StateManager可用，验证并使用其初始状态
        if (window.StateManager && typeof window.StateManager.createInitialState === 'function') {
            try {
                const stateManagerState = window.StateManager.createInitialState();
                // 合并状态，确保所有字段都存在
                return { ...baseState, ...stateManagerState };
            } catch (error) {
            }
        }
        
        return baseState;
    },
    
    computed: {
        // Linus式"好品味"：简单直接的频道去重逻辑
        uniqueChannels() {
            if (!this.channelInfo) return {};
            
            const uniqueChannels = {};
            const seenChannels = new Set();
            
            for (const [id, info] of Object.entries(this.channelInfo)) {
                if (!seenChannels.has(id)) {
                    uniqueChannels[id] = info;
                    seenChannels.add(id);
                }
            }
            
            return uniqueChannels;
        },
        
        // Linus式"好品味"：可靠的消息过滤，不依赖外部模块
        filteredMessages() {
            if (!this.messages || !Array.isArray(this.messages)) {
                return [];
            }
            
            if (!this.filters) {
                return this.messages;
            }
            
            return this.messages.filter(message => {
                // 状态筛选
                if (this.filters.status && message.status !== this.filters.status) {
                    return false;
                }
                
                // 广告筛选
                if (this.filters.is_ad !== null && message.is_ad !== this.filters.is_ad) {
                    return false;
                }
                
                // 频道筛选
                if (this.filters.source_channel && 
                    message.source_channel_id !== this.filters.source_channel &&
                    message.source_channel !== this.filters.source_channel) {
                    return false;
                }
                
                // 过滤原因筛选
                if (this.filters.filter_reason && message.filter_reason !== this.filters.filter_reason) {
                    return false;
                }
                
                // 搜索关键词筛选
                if (this.searchKeyword && this.searchKeyword.trim()) {
                    const keyword = this.searchKeyword.trim().toLowerCase();
                    const content = (message.filtered_content || message.content || '').toLowerCase();
                    if (!content.includes(keyword)) {
                        return false;
                    }
                }
                
                return true;
            });
        },
        
        // 简化的全选状态计算
        allSelected() {
            if (!this.filteredMessages || this.filteredMessages.length === 0) return false;
            const selectableIds = this.filteredMessages.map(msg => msg.message_id);
            return selectableIds.length > 0 && 
                   selectableIds.every(id => this.selectedMessages.includes(id));
        }
    },
    
    created() {
        // Linus式"好品味"：确保所有响应式数据正确初始化
        
        // 确保关键对象存在
        if (!this.mediaPreview) {
            this.mediaPreview = { show: false, url: null };
        }
        if (!this.fileDetailsDialog) {
            this.fileDetailsDialog = { visible: false, details: null };
        }
        if (!this.editDialog) {
            this.editDialog = { visible: false, messageId: null, filteredContent: '', originalMessage: null };
        }
        if (!this.refetchingMedia) {
            this.refetchingMedia = {};
        }
        
        // 确保loadMessages方法存在
        if (typeof this.loadMessages !== 'function') {
            console.error('⚠️ loadMessages方法未找到，Vue实例可能不完整');
        } else {
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
            // 频道变化时自动加载消息
            this.loadMessages();
        }
    },
    
    async mounted() {
        try {
            // 🔥 Linus风格：初始化事件委托系统
            if (window.EventDelegate) {
                this.eventDelegate = new window.EventDelegate(this);
            }
            
            // 初始化原消息链接点击事件委托
            this.initOriginalMessageEventDelegate();
            
            
            // 初始化权限检查
            const isAuthorized = await authManager.initPageAuth('messages.view');
            if (!isAuthorized) {
                console.error('❌ 权限验证失败，停止初始化');
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
            const loadResults = await Promise.allSettled([
                this.loadMessages().catch(err => {
                    console.error('❌ 加载消息失败:', err);
                    MessageManager.error('加载消息失败，请刷新页面重试');
                    throw err;
                }),
                // 统计数据由linus-stats组件自动加载
                this.loadChannelInfo().catch(err => {
                    console.error('❌ 加载频道信息失败:', err);
                    throw err;
                })
            ]);
            
            // 检查加载结果
            
            // 在数据加载完成后检查状态
            setTimeout(() => {
            }, 1000);
            
            // 建立WebSocket连接（非关键功能，失败不影响使用）
            try {
                if (window.WebSocketManager) {
                    // 使用模块化的WebSocket管理器
                    window.WebSocketManager.init({
                        onMessage: this.handleWebSocketMessage.bind(this),
                        onStatusChange: (isConnected) => {
                            this.websocketConnected = isConnected;
                            this.systemStatus = isConnected ? '在线' : '离线';
                        },
                        onError: (error) => {
                            this.websocketConnected = false;
                            this.systemStatus = '连接错误';
                        }
                    });
                } else {
                    // 降级到原有方法
                    this.connectWebSocket();
                }
            } catch (err) {
            }
            
            // 定期检查WebSocket连接状态
            this.connectionCheckInterval = setInterval(() => {
                try {
                    if (window.WebSocketManager) {
                        // 检查模块化WebSocket的连接状态
                        if (!window.WebSocketManager.isConnected) {
                            this.websocketConnected = false;
                            this.systemStatus = '离线';
                        }
                    } else {
                        // 降级检查
                        this.checkWebSocketConnection();
                    }
                } catch (err) {
                }
            }, 10000);
            
            // 🔥 Linus原则：删除过于主动的焦点刷新
            // 用户切换窗口不应该触发自动加载，让用户自己控制何时刷新
            
            // 添加滚动监听
            this.setupScrollListener();
        } catch (error) {
            console.error('页面初始化失败:', error);
            MessageManager.error('页面初始化失败，部分功能可能不可用');
        }
    },
    
    beforeUnmount() {
        // 🔥 Linus风格：销毁事件委托系统
        if (this.eventDelegate && typeof this.eventDelegate.destroy === 'function') {
            this.eventDelegate.destroy();
        }
        
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
        // 发布状态检查方法
        isPublishing(messageId) {
            return this.publishingMessages.has(messageId);
        },
        
        // 过滤状态检查方法 - Linus风格：与isPublishing保持一致
        isFiltering(messageId) {
            return this.filteringMessages.has(messageId);
        },
        
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
                            this.setFallbackPermissions('limited');
                        }
                    } catch (error) {
                        // 权限初始化异常 - 使用降级权限
                        console.error('权限检查器执行错误:', error);
                        this.setFallbackPermissions('limited');
                    }
                } else {
                    // 权限检查器不存在，根据用户角色设置基础权限
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
                    const channelInfo = {};
                    
                    // 处理后端返回的频道数据
                    const processChannel = (channel) => {
                        if (!channel || !channel.channel_id) return;
                        
                        // 从channel_name提取username，确保格式正确
                        const channelName = channel.channel_name || '';
                        let username = '';
                        if (channelName) {
                            // 移除@前缀（如果有的话）
                            username = channelName.startsWith('@') ? channelName.substring(1) : channelName;
                        }
                        
                        const channelInfo_item = {
                            id: channel.channel_id,
                            title: channel.channel_title || channel.title || `频道 ${channel.channel_id}`,
                            username: username, // 不包含@前缀
                            type: channel.channel_type || 'source',
                            enabled: channel.is_active !== false && channel.enabled !== false
                        };
                        
                        channelInfo[channel.channel_id] = channelInfo_item;
                        
                    };
                    
                    // 检查是否是数组格式（从get_all_channels返回）
                    if (Array.isArray(response.data.data)) {
                        response.data.data.forEach(processChannel);
                    } 
                    // 兼容对象格式（直接从JSON Store返回）
                    else if (typeof response.data.data === 'object') {
                        Object.values(response.data.data).forEach(processChannel);
                    }
                    
                    this.channelInfo = channelInfo;
                } else {
                }
            } catch (error) {
                console.error('加载频道信息失败:', error);
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
                // 准备请求参数，将_show_duplicates转换为show_duplicates
                const { _show_duplicates, ...apiFilters } = this.filters;
                const params = {
                    ...apiFilters,
                    page: this.currentPage,
                    size: this.pageSize,
                    // 🚀 Linus式优化：传递show_duplicates参数到后端专用查询
                    show_duplicates: _show_duplicates || false
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
                
                // API响应数据结构检查（生产环境已移除调试日志）
                
                if (response.data && response.data.data && response.data.data.messages && Array.isArray(response.data.data.messages)) {
                    const newMessages = response.data.data.messages;
                    
                    // 检查是否还有更多数据
                    this.hasMore = newMessages.length === this.pageSize;
                    
                    // 计算真正的新消息
                    const currentMessageIds = new Set(newMessages.map(msg => msg.message_id));
                    const reallyNewMessages = newMessages.filter(msg => !this.previousMessageIds.has(msg.message_id));
                    
                    // 更新消息列表
                    if (append) {
                        // 追加到现有列表，避免重复
                        const existingIds = new Set(this.messages.map(m => m.message_id));
                        const uniqueNewMessages = newMessages.filter(msg => !existingIds.has(msg.message_id));
                        this.messages = [...this.messages, ...uniqueNewMessages];
                        
                        // 如果没有新的唯一消息，说明已经到底了
                        if (uniqueNewMessages.length === 0) {
                            this.hasMore = false;
                        }
                    } else {
                        // 替换整个列表
                        this.messages = newMessages;
                        
                        // 🔍 调试: 分析消息对比显示问题
                        if (window.MessageComparisonDebug && window.MessageComparisonDebug.enableDebug) {
                            
                            // 分析消息数据
                            setTimeout(() => {
                                window.MessageComparisonDebug.analyzeAllMessages(newMessages);
                            }, 1000);
                        }
                        
                        // 强制Vue重新渲染
                        this.$nextTick(() => {
                        });
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
                        // 重新设置滚动监听器，确保DOM更新后正确绑定
                        setTimeout(() => this.setupScrollListener(), 100);
                    });
                } else {
                    this.messages = [];
                    if (this.previousMessageIds.size === 0) {
                        MessageManager.warning('暂无消息数据');
                    }
                }
            } catch (error) {
                console.error('❌ 加载消息失败:', error);
                console.error('❌ 错误详情:', {
                    message: error.message,
                    status: error.response?.status,
                    statusText: error.response?.statusText,
                    responseData: error.response?.data,
                    config: error.config
                });
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
                return;
            }
            
            // 立即设置加载状态，防止重复触发
            this.isLoadingMore = true;
            
            try {
                this.currentPage++;
                await this.loadMessages(true);
                
                // 检查是否真的还有更多数据
                // 如果当前消息总数小于已加载页数*每页数量，说明没有更多了
                const expectedMessages = this.currentPage * this.pageSize;
                if (this.messages.length < expectedMessages - this.pageSize) {
                    this.hasMore = false;
                }
            } finally {
                // 确保加载状态被重置
                this.isLoadingMore = false;
            }
        },
        
        refreshStats() {
            // 调用Linus统计组件的刷新方法
            if (this.$refs.linusStats) {
                this.$refs.linusStats.loadStats();
            }
        },

        // 获取频道名称
        getChannelName(channel_id) {
            return window.DataUtils ? window.DataUtils.getChannelName(channel_id, this.channelInfo) : channel_id;
        },
        
        // 获取频道显示名称（用于下拉框）
        getChannelDisplayName(channel) {
            return window.DataUtils ? window.DataUtils.getChannelDisplayName(channel) : (channel ? channel.title || channel.name || '未知频道' : '未知频道');
        },
        
        // 处理频道切换事件
        handleChannelChange() {
            if (!this.filters.source_channel) {
                MessageManager.info('已清除频道筛选，显示所有频道的消息');
            }
            
            this.loadMessages();
        },
        
        // 获取状态类型 - 委托给DataUtils
        getStatusType(status) {
            return window.DataUtils ? window.DataUtils.getStatusType(status) : '';
        },
        
        // 获取状态文本 - 委托给DataUtils
        getStatusText(status) {
            return window.DataUtils ? window.DataUtils.getStatusText(status) : status;
        },
        
        // 格式化时间 - 委托给DataUtils
        formatTime(timeStr) {
            return window.DataUtils ? window.DataUtils.formatTime(timeStr) : timeStr;
        },
        
        // 显示原消息详情弹窗
        async showOriginalMessage(messageId) {
            this.originalMessageDialog.visible = true;
            this.originalMessageDialog.messageId = messageId;
            this.originalMessageDialog.loading = true;
            this.originalMessageDialog.error = null;
            this.originalMessageDialog.message = null;
            
            try {
                const response = await axios.get(window.API.messages.getById(messageId));
                this.originalMessageDialog.message = response.data;
                this.originalMessageDialog.loading = false;
            } catch (error) {
                console.error('获取原消息失败:', error);
                this.originalMessageDialog.error = '获取原消息失败: ' + (error.response?.data?.detail || error.message);
                this.originalMessageDialog.loading = false;
            }
        },
        
        // 初始化原消息链接事件委托
        initOriginalMessageEventDelegate() {
            // 使用事件委托在document级别监听点击事件
            document.addEventListener('click', (event) => {
                // 检查是否点击了原消息链接
                if (event.target.classList.contains('duplicate-message-link')) {
                    event.preventDefault();
                    event.stopPropagation();
                    
                    const messageId = event.target.getAttribute('data-message-id');
                    if (messageId) {
                        this.showOriginalMessage(messageId);
                    }
                }
            });
        },
        
        // 获取原消息链接 - 委托给DataUtils
        getOriginalMessageLink(message) {
            return window.DataUtils ? window.DataUtils.getOriginalMessageLink(message) : '#';
        },
        
        // Linus风格统计面板点击 - 没有特殊情况
        handleStatClick(statKey) {
            
            // 数据驱动，直接设置状态
            this.filters.source_channel = '';
            
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
                    this.filters.status = 'pending';  // 只显示待审核的广告消息
                    this.filters.is_ad = true;
                    this.filters.filter_reason = null;
                    this.filters._show_duplicates = false;
                    break;
                case 'duplicates':
                    // 🚀 Linus式优化：不要清空status，使用专门的show_duplicates参数
                    // this.filters.status = '';  // ❌ 删除这行，避免触发get_all_messages
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    // 🔧 设置专用标识，后端将使用专门的重复消息查询
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
        
        // 获取统计标签的显示名称 - 委托给DataUtils
        getStatLabel(statKey) {
            return window.DataUtils ? window.DataUtils.getStatLabel(statKey) : statKey;
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
        
        // 发布消息
        async approveMessage(messageId) {
            // 防止重复点击
            if (this.publishingMessages.has(messageId)) {
                return;
            }
            
            // 标记为正在发布
            this.publishingMessages.add(messageId);
            
            try {
                
                // 保存当前滚动位置
                const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                
                // 临时禁用滚动加载，防止DOM变化触发意外的loadMore
                const wasLoadingMore = this.isLoadingMore;
                this.isLoadingMore = true;
                
                const response = await axios.post(window.API.messages.approveById(messageId));
                if (response.data.success) {
                    MessageManager.success('消息已发布');
                    // 如果当前过滤器是待审核状态，从列表中移除已发布的消息
                    if (this.filters.status === 'pending') {
                        this.messages = this.messages.filter(msg => msg.id !== messageId);
                    } else {
                        // 本地更新消息状态
                        const messageIndex = this.messages.findIndex(msg => msg.id === messageId);
                        if (messageIndex !== -1) {
                            this.messages[messageIndex].status = 'approved';
                        }
                    }
                    this.refreshStats();
                    
                    // 下一帧恢复滚动位置和加载状态
                    this.$nextTick(() => {
                        window.scrollTo(0, scrollPosition);
                        // 延迟恢复加载状态，防止滚动事件立即触发
                        setTimeout(() => {
                            this.isLoadingMore = wasLoadingMore;
                        }, 1000);
                    });
                } else {
                    MessageManager.error('发布失败: ' + response.data.message);
                    // 恢复加载状态
                    setTimeout(() => {
                        this.isLoadingMore = wasLoadingMore;
                    }, 500);
                }
            } catch (error) {
                MessageManager.error('发布失败: ' + (error.response?.data?.detail || error.message));
                // 恢复加载状态
                setTimeout(() => {
                    this.isLoadingMore = false;
                }, 500);
            } finally {
                // 无论成功或失败，都要移除发布状态
                this.publishingMessages.delete(messageId);
            }
        },
        
        // 拒绝消息
        async rejectMessage(messageId) {
            try {
                // 保存当前滚动位置
                const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                
                // 临时禁用滚动加载，防止DOM变化触发意外的loadMore
                const wasLoadingMore = this.isLoadingMore;
                this.isLoadingMore = true;
                
                // 先找到消息对象（在移除之前）
                const message = this.messages.find(msg => msg.id === messageId);
                
                const response = await axios.post(`${window.API.messages.rejectById(messageId)}?reason=手动拒绝&reviewer=Web用户`);
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
                    
                    this.refreshStats();
                    
                    // 下一帧恢复滚动位置和加载状态
                    this.$nextTick(() => {
                        window.scrollTo(0, scrollPosition);
                        // 延迟恢复加载状态，防止滚动事件立即触发
                        setTimeout(() => {
                            this.isLoadingMore = wasLoadingMore;
                        }, 100);
                    });
                    
                    // 如果消息有审核群消息ID，删除审核群中的消息
                    if (message && message.review_message_id) {
                        try {
                            // 调用删除审核群消息的API
                            await axios.delete(window.API.messages.deleteReviewById(messageId));
                        } catch (error) {
                        }
                    }
                } else {
                    MessageManager.error('拒绝失败: ' + response.data.message);
                    // 恢复加载状态
                    this.isLoadingMore = wasLoadingMore;
                }
            } catch (error) {
                MessageManager.error('拒绝失败: ' + (error.response?.data?.detail || error.message));
                // 恢复加载状态
                this.isLoadingMore = false;
            }
        },
        
        // 恢复被拒绝的消息
        async restoreMessage(messageId) {
            try {
                // 保存当前滚动位置
                const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                
                // 临时禁用滚动加载，防止DOM变化触发意外的loadMore
                const wasLoadingMore = this.isLoadingMore;
                this.isLoadingMore = true;
                
                const response = await axios.post(window.API.messages.restoreById(messageId));
                if (response.data.success) {
                    MessageManager.success('消息已恢复到未审核状态');
                    
                    // 如果当前筛选状态是"已拒绝"，从列表中移除消息
                    // 如果筛选状态是"待审核"，则更新消息状态
                    if (this.filters.status === 'rejected') {
                        // 从已拒绝列表中移除消息
                        this.messages = this.messages.filter(msg => msg.id !== messageId);
                    } else if (this.filters.status === 'pending') {
                        // 更新消息状态为待审核
                        const msgIndex = this.messages.findIndex(msg => msg.id === messageId);
                        if (msgIndex !== -1) {
                            this.messages[msgIndex].status = 'pending';
                        }
                    }
                    
                    this.refreshStats();
                    
                    // 下一帧恢复滚动位置和加载状态
                    this.$nextTick(() => {
                        setTimeout(() => {
                            // 恢复滚动位置
                            window.scrollTo(0, scrollPosition);
                            // 恢复加载状态
                            this.isLoadingMore = wasLoadingMore;
                        }, 100);
                    });
                } else {
                    MessageManager.error('恢复失败: ' + response.data.message);
                    // 恢复加载状态
                    this.isLoadingMore = wasLoadingMore;
                }
            } catch (error) {
                MessageManager.error('恢复失败: ' + (error.response?.data?.detail || error.message));
                // 恢复加载状态
                this.isLoadingMore = false;
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
            const messageId = message.id || `${message.source_channel}:${message.message_id}`;
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
        
        // 批量发布
        async batchApprove(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            if (window.MessageManager) {
                const result = await window.MessageManager.batchApprove(this.selectedMessages);
                if (result.success) {
                    MessageManager.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    MessageManager.error('批量发布失败: ' + result.error);
                }
            } else {
                // 降级处理
                if (this.selectedMessages.length === 0) {
                    MessageManager.warning('请先选择要发布的消息');
                    return;
                }
                
                try {
                    const response = await axios.post(window.API.messages.batchApprove, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        MessageManager.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        MessageManager.error('批量发布失败: ' + response.data.message);
                    }
                } catch (error) {
                    MessageManager.error('批量发布失败: ' + (error.response?.data?.detail || error.message));
                }
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
        
        // 获取消息对比状态的CSS类
        getComparisonStatusClass(message) {
            const contentsDifferent = message.content !== message.filtered_content;
            const hasRemovedLinks = !!(message.removed_hidden_links && message.removed_hidden_links.length > 0);
            
            if (contentsDifferent && hasRemovedLinks) {
                return 'status-filtered-and-links';
            } else if (contentsDifferent) {
                return 'status-filtered';
            } else if (hasRemovedLinks) {
                return 'status-links-only';
            } else {
                return 'status-unchanged';
            }
        },
        
        // 获取消息对比状态的图标
        getComparisonStatusIcon(message) {
            const contentsDifferent = message.content !== message.filtered_content;
            const hasRemovedLinks = !!(message.removed_hidden_links && message.removed_hidden_links.length > 0);
            
            if (contentsDifferent && hasRemovedLinks) {
                return '🔄';
            } else if (contentsDifferent) {
                return '🔄';
            } else if (hasRemovedLinks) {
                return '🔗';
            } else {
                return '⚪';
            }
        },
        
        // 获取消息对比状态的文本描述
        getComparisonStatusText(message) {
            const contentsDifferent = message.content !== message.filtered_content;
            const hasRemovedLinks = !!(message.removed_hidden_links && message.removed_hidden_links.length > 0);
            
            if (contentsDifferent && hasRemovedLinks) {
                return '内容已过滤并移除链接';
            } else if (contentsDifferent) {
                return '内容已过滤';
            } else if (hasRemovedLinks) {
                return '仅移除隐藏链接';
            } else {
                return '内容未被过滤';
            }
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
            return window.DataUtils ? window.DataUtils.getMediaTypeIcon(mediaType) : '📎';
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
            
            // 确保fileDetailsDialog存在并且是响应式的
            if (!this.fileDetailsDialog) {
                this.fileDetailsDialog = {
                    visible: false,
                    details: null
                };
            }
            
            // Vue 3响应式更新：直接修改属性
            this.fileDetailsDialog.visible = true;
            this.fileDetailsDialog.details = { ...details };
            
            
            // 强制Vue重新渲染以确保UI更新
            this.$nextTick(() => {
            });
            
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
                    // Vue 3响应式更新：直接修改属性
                    this.fileDetailsDialog.details.size = this.formatFileSize(sizeInBytes);
                }
            } catch (error) {
                if (this.fileDetailsDialog && this.fileDetailsDialog.details) {
                    this.fileDetailsDialog.details.size = '未知';
                }
            }
        },
        
        // 格式化文件大小 - 委托给DataUtils
        formatFileSize(bytes) {
            return window.DataUtils ? window.DataUtils.formatFileSize(bytes) : bytes + ' B';
        },

        // 处理媒体加载错误
        handleMediaError(event, message) {
            
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
                    return;
                }
                
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}${window.API.websocket.main}`;
                
                // 创建新连接前清理旧连接
                if (this.websocket) {
                    this.websocket.close();
                }
                
                this.websocket = new WebSocket(wsUrl);
                
                // 设置超时检测
                const connectionTimeout = setTimeout(() => {
                    if (this.websocket.readyState === WebSocket.CONNECTING) {
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
                        
                        setTimeout(() => {
                            if (!this.websocketConnected && !this._isUnmounting) {
                                this.connectWebSocket();
                            }
                        }, delay);
                    } else {
                        this.systemStatus = '连接断开（已停止重试）';
                    }
                };
                
                this.websocket.onerror = (error) => {
                    clearTimeout(connectionTimeout);
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
                    case 'media_refetched':
                        this.handleMediaRefetched(data.data);
                        break;
                    case 'pong':
                        // 心跳响应，不需要处理
                        break;
                    default:
                }
            } catch (error) {
            }
        },

        // 处理新消息
        handleNewMessage(messageData) {
            //     id: messageData.id,
            //     status: messageData.status,
            //     is_ad: messageData.is_ad,
            //     content_preview: messageData.content ? messageData.content.substring(0, 50) + '...' : '无内容'
            // });
            
            // 检查消息是否已存在
            const existingIndex = this.messages.findIndex(msg => msg.message_id === messageData.message_id);
            
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
                } else {
                }
                
                // 显示通知（无论是否添加到列表）
                const contentPreview = messageData.content ? messageData.content.substring(0, 30) + '...' : '新消息（无文本内容）';
                MessageManager.success(`收到新消息: ${contentPreview}`);
                
                // 刷新统计信息
                this.refreshStats();
                
                // 强制Vue重新渲染媒体元素
                this.$nextTick(() => {
                    // 确保媒体URL被正确加载
                    if (messageData.media_display_url || messageData.media_group_display) {
                    }
                });
            } else {
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
        
        // 处理媒体补抓完成通知
        handleMediaRefetched(data) {
            const messageId = data.message_id;
            
            // 找到并更新消息
            const message = this.messages.find(msg => msg.id === messageId);
            if (message) {
                // 更新媒体信息
                if (data.media_url) {
                    message.media_url = data.media_url;
                    message.media_display_url = data.media_display_url || data.media_url;
                }
                if (data.media_group_display) {
                    message.media_group_display = data.media_group_display;
                }
                
                // 清除加载状态
                delete this.refetchingMedia[messageId];
                
                // 强制更新视图
                this.messages = [...this.messages];
                
                // 显示成功通知
                MessageManager.success(`消息 #${messageId} 的媒体补抓成功！`);
                
            } else {
            }
        },

        // 处理消息状态更新
        handleMessageStatusUpdate(updateData) {
            const messageIndex = this.messages.findIndex(msg => msg.id === updateData.message_id);
            if (messageIndex !== -1) {
                // 如果当前过滤器是待审核，且消息状态变为已发布或已拒绝，从列表中移除
                if (this.filters.status === 'pending' && 
                    (updateData.status === 'approved' || updateData.status === 'rejected')) {
                    this.messages.splice(messageIndex, 1);
                } else {
                    this.messages[messageIndex].status = updateData.status;
                }
            }
        },

        // 检查WebSocket连接状态
        checkWebSocketConnection() {
            if (!this.websocketConnected && (!this.websocket || this.websocket.readyState === WebSocket.CLOSED)) {
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
        
        
        // 编辑消息
        editMessage(messageId) {
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                MessageManager.error('未找到消息');
                return;
            }
            this.editDialog.messageId = message.id;
            this.editDialog.filteredContent = message.filtered_content || '';
            this.editDialog.originalMessage = message;
            this.editDialog.visible = true;
        },
        
        // 保存编辑的消息
        async saveEditedMessage(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 验证必要的数据
            if (!this.editDialog.messageId) {
                MessageManager.error('编辑失败: 消息ID不存在');
                return;
            }
            
            if (!this.editDialog.filteredContent && this.editDialog.filteredContent !== '') {
                MessageManager.error('编辑失败: 内容不能为空');
                return;
            }
            
            // 开始编辑消息（生产环境已移除调试日志）
            
            try {
                // axios拦截器会自动添加认证头，无需手动设置
                const response = await axios.post(window.API.messages.editPublish(this.editDialog.messageId), {
                    filtered_content: this.editDialog.filteredContent
                });
                
                
                if (response.data.success) {
                    MessageManager.success('消息已编辑并保存');
                    this.editDialog.visible = false;
                    
                    // 🚀 性能优化：使用局部更新，避免整个列表重新渲染
                    this.updateSingleMessage(this.editDialog.messageId, {
                        filtered_content: this.editDialog.filteredContent,
                        updated_at: new Date().toISOString()
                    });
                } else {
                    MessageManager.error('编辑失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('编辑请求异常:', error);
                console.error('错误详情:', {
                    status: error.response?.status,
                    statusText: error.response?.statusText,
                    data: error.response?.data
                });
                
                let errorMessage = '编辑失败: ';
                if (error.response?.data?.detail) {
                    errorMessage += error.response.data.detail;
                } else if (error.response?.data?.message) {
                    errorMessage += error.response.data.message;
                } else if (error.message) {
                    errorMessage += error.message;
                } else {
                    errorMessage += '未知错误';
                }
                
                MessageManager.error(errorMessage);
            }
        },
        
        // 🚀 性能优化：单个消息局部更新方法
        updateSingleMessage(messageId, updates) {
            const messageIndex = this.messages.findIndex(msg => msg.id === messageId);
            if (messageIndex !== -1) {
                // Vue 3响应式更新：直接修改属性即可
                Object.keys(updates).forEach(key => {
                    // Vue 3中直接赋值即可触发响应式更新
                    this.messages[messageIndex][key] = updates[key];
                });
            } else {
                // 作为后备方案，只在真正找不到时才重新加载
                this.loadMessages();
            }
        },
        
        // 切换全选
        toggleSelectAll(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            if (this.allSelected) {
                this.selectedMessages = [];
            } else {
                const selectableMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
                this.selectedMessages = selectableMessages.map(msg => msg.id || `${msg.source_channel}:${msg.message_id}`);
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
        
        // 批量发布消息
        async approveMessages(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 防止重复点击
            if (this.isBatchPublishing) {
                return;
            }
            
            // 标记为批量发布中
            this.isBatchPublishing = true;
            
            // 将所有选中的消息标记为正在发布
            this.selectedMessages.forEach(id => this.publishingMessages.add(id));
            
            try {
                if (window.MessageManager) {
                    const result = await window.MessageManager.batchApprove(this.selectedMessages);
                    if (result.success) {
                        MessageManager.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        MessageManager.error('批量发布失败: ' + result.error);
                    }
                } else {
                    // 降级处理
                    if (this.selectedMessages.length === 0) {
                        MessageManager.warning('请先选择要发布的消息');
                        return;
                    }
                    
                    const response = await axios.post(window.API.messages.batchApprove, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        MessageManager.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        MessageManager.error('批量发布失败: ' + response.data.message);
                    }
                }
            } catch (error) {
                MessageManager.error('批量发布失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 恢复发布状态
                this.isBatchPublishing = false;
                this.selectedMessages.forEach(id => this.publishingMessages.delete(id));
            }
        },
        
        // 批量拒绝消息
        async rejectMessages(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            if (window.MessageManager) {
                const result = await window.MessageManager.batchReject(this.selectedMessages);
                if (result.success) {
                    MessageManager.success(`成功拒绝 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    MessageManager.error('批量拒绝失败: ' + result.error);
                }
            } else {
                // 降级处理
                if (this.selectedMessages.length === 0) {
                    MessageManager.warning('请先选择要拒绝的消息');
                    return;
                }
                
                try {
                    const response = await axios.post(window.API.messages.batchReject, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        MessageManager.success(`成功拒绝 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        MessageManager.error('批量拒绝失败: ' + response.data.message);
                    }
                } catch (error) {
                    MessageManager.error('批量拒绝失败: ' + (error.response?.data?.detail || error.message));
                }
            }
        },
        
        // 重新发布消息到目标频道
        async resendMessage(event, message) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 如果message在event中，提取出来
            if (!message && event && event.target && event.target.dataset) {
                message = {
                    id: event.target.dataset.messageId
                };
            }
            try {
                MessageManager.info('正在重新发布消息到目标频道...');
                
                const response = await axios.post(window.API.messages.resendById(message.id));
                
                if (response.data.success) {
                    MessageManager.success('消息已重新发布到目标频道');
                    this.loadMessages(); // 刷新消息列表
                } else {
                    MessageManager.error('重新发布失败: ' + response.data.message);
                }
            } catch (error) {
                const errorMsg = error.response?.data?.detail || error.message || '重新发布失败';
                MessageManager.error('重新发布失败: ' + errorMsg);
                console.error('重新发布消息错误:', error);
            }
        },
        
        // 重置消息状态 - 用于误判恢复
        async resetMessage(event, message) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 如果message在event中，提取出来
            if (!message && event && event.target && event.target.dataset) {
                message = {
                    id: event.target.dataset.messageId,
                    is_ad: event.target.dataset.isAd === 'true'
                };
            }
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
                
                const response = await axios.post(window.API.messages.reset, {
                    source_channel: sourceChannel,
                    message_id: parseInt(messageId),
                    is_ad: message.is_ad
                });
                
                if (response.data.success) {
                    MessageManager.success('消息已重置为待审核状态');
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    MessageManager.error('重置失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('重置失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 批量删除消息
        async deleteMessages(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            if (this.selectedMessages.length === 0) {
                MessageManager.warning('请先选择要删除的消息');
                return;
            }
            
            if (!confirm(`确定要删除 ${this.selectedMessages.length} 条消息吗？`)) {
                return;
            }
            
            if (window.MessageManager) {
                const result = await window.MessageManager.batchDelete(this.selectedMessages);
                if (result.success) {
                    MessageManager.success(`成功删除 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    MessageManager.error('批量删除失败: ' + result.error);
                }
            } else {
                // 降级处理
                try {
                    const response = await axios.post(window.API.messages.batchDelete, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        MessageManager.success(`成功删除 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        MessageManager.error('批量删除失败: ' + response.data.message);
                    }
                } catch (error) {
                    MessageManager.error('批量删除失败: ' + (error.response?.data?.detail || error.message));
                }
            }
        },
        
        // 打开编辑对话框
        openEditDialog(event, message) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 如果message在event中，提取出来
            if (!message && event && event.target && event.target.dataset) {
                message = {
                    id: event.target.dataset.messageId,
                    filtered_content: event.target.dataset.filteredContent || ''
                };
            }
            this.editDialog.messageId = message.id;
            this.editDialog.filteredContent = message.filtered_content || '';
            this.editDialog.originalMessage = message;
            this.editDialog.visible = true;
        },
        
        // 保存编辑
        async saveEdit(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            await this.saveEditedMessage();
        },
        
        // 获取状态标签
        getStatusTag(status) {
            const statusMap = {
                'pending': { text: '待审核', type: 'warning' },
                'approved': { text: '已发布', type: 'success' },
                'rejected': { text: '已拒绝', type: 'danger' },
                'auto_forwarded': { text: '自动转发', type: 'info' }
            };
            return statusMap[status] || { text: status, type: 'default' };
        },

        // 标记/取消标记广告并加入训练样本
        async markAsAd(messageId) {
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                MessageManager.error('未找到消息');
                return;
            }
            
            try {
                // 根据当前状态确定操作类型
                const isCurrentlyAd = message.is_ad;
                const action = isCurrentlyAd ? '取消广告标记' : '标记为广告';
                const confirmMsg = isCurrentlyAd ? 
                    '确定取消此消息的广告标记吗？这将帮助AI减少误判。' : 
                    '确定将此消息标记为广告吗？这将帮助AI更好地识别广告内容。';
                
                if (!confirm(confirmMsg)) {
                    return;
                }
                
                const response = await axios.post(window.API.training.markAdMessage, {
                    message_id: message.id,
                    is_marking_as_ad: !isCurrentlyAd  // 双向操作标识
                });
                
                if (response.data.success) {
                    const hasAutoRejected = response.data.auto_rejected;
                    let successMsg;
                    
                    if (isCurrentlyAd) {
                        // 取消广告标记
                        successMsg = '已取消广告标记，消息状态恢复为未审核';
                    } else {
                        // 标记为广告
                        successMsg = hasAutoRejected ? 
                            '已标记为广告、自动拒绝并加入训练样本' : 
                            '已标记为广告并加入训练样本';
                    }
                    
                    // 显示阈值调整信息（如果有）
                    if (response.data.threshold_adjustment) {
                        successMsg += `\n阈值已自动调整：${response.data.threshold_adjustment}`;
                    }
                    
                    MessageManager.success(successMsg);
                    // 重新加载消息列表以反映状态变化
                    await this.loadMessages();
                    this.refreshStats();
                } else {
                    MessageManager.error(response.data.message || `${action}失败`);
                }
            } catch (error) {
                MessageManager.error('标记失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 标记为"不是广告" - 纠正AI误判
        async markAsNotAd(event, message) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 如果message在event中，提取出来
            if (!message && event && event.target && event.target.dataset) {
                message = {
                    id: event.target.dataset.messageId
                };
            }
            try {
                if (!confirm('确定将此消息标记为"不是广告"吗？这将帮助AI减少误判。')) {
                    return;
                }
                
                const response = await axios.post(window.API.messages.notAd(message.id));
                
                if (response.data.success) {
                    MessageManager.success('已标记为"不是广告"，消息状态已改为待审核');
                    // 重新加载消息以获取最新的过滤内容
                    // 因为后端已应用了尾部过滤和推广链接过滤
                    await this.loadMessages();
                    this.refreshStats();
                } else {
                    MessageManager.error(response.data.message || '操作失败');
                }
            } catch (error) {
                MessageManager.error('操作失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 训练尾部
        trainTail(messageId) {
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                MessageManager.error('未找到消息');
                return;
            }
            // 跳转到训练页面，并传递消息信息用于尾部训练
            // 新增useFiltered参数，指示训练页面优先使用filtered_content
            const params = new URLSearchParams({
                message_id: message.id,
                channel_id: message.source_channel,
                mode: 'tail',
                useFiltered: 'true'  // 指示使用过滤后内容进行尾部训练
            });
            // 使用绝对路径确保正确跳转
            window.location.href = '/static/train.html?' + params.toString();
        },
        
        // 手动执行尾部过滤 - Linus风格：消除重复点击的特殊情况
        async filterTail(messageId) {
            // 防重复点击保护 - 没有if分支，直接返回
            if (this.filteringMessages.has(messageId)) {
                return;
            }
            
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                MessageManager.error('未找到消息');
                return;
            }
            
            // 标记正在过滤
            this.filteringMessages.add(messageId);
            
            try {
                // 🚀 Linus风格：依赖axios拦截器自动处理认证（消除特殊情况）
                const response = await axios.post(
                    window.API.messages.filterTail(message.id),
                    {} // 让拦截器自动添加认证头，避免手动覆盖
                );
                
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
            } finally {
                // 确保总是清理状态
                this.filteringMessages.delete(messageId);
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
            if (window.DataUtils) {
                window.DataUtils.handleImageError(message, event);
            } else {
                // 降级处理
                if (message && !message._mediaLoadFailed) {
                    message._mediaLoadFailed = true;
                }
                if (event) event.preventDefault();
            }
        },
        
        // Linus式媒体补抓 - 防重复点击，WebSocket通知
        async refetchMedia(messageId) {
            // Linus式防重复点击
            if (this.refetchingMedia[messageId]) {
                MessageManager.warning('正在补抓中，请稍候...');
                return;
            }
            
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                MessageManager.error('未找到消息');
                return;
            }
            
            try {
                // 立即设置状态，防止重复点击
                this.refetchingMedia[message.id] = true;
                
                // 直接执行（Linus风格：减少用户交互）
                const response = await axios.post(window.API.messages.refetchMedia(message.id));
                
                if (response.data.success) {
                    MessageManager.success('正在补抓媒体文件...');
                    // 不再轮询，等待WebSocket通知
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
        
        // 检查消息是否正在补抓中（供子组件使用）
        isRefetching(messageId) {
            return !!this.refetchingMedia[messageId];
        },

        // 轮询补抓任务状态
        async pollRefetchTaskStatus(taskId, message, maxAttempts = 30) {
            let attempts = 0;
            
            const poll = async () => {
                try {
                    attempts++;
                    
                    const response = await axios.get(window.API.messages.refetchTask(taskId));
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
        smartSelectAll(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            const pendingMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
            if (pendingMessages.length === this.selectedMessages.length) {
                this.selectedMessages = [];
            } else {
                this.selectedMessages = pendingMessages.map(msg => msg.id || `${msg.source_channel}:${msg.message_id}`);
            }
        },
        
        // 反选
        invertSelection(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            const pendingMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
            const currentSelected = new Set(this.selectedMessages);
            this.selectedMessages = pendingMessages
                .filter(msg => !currentSelected.has(msg.message_id))
                .map(msg => msg.message_id);
        },
        
        // 清空选择
        clearSelection(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            this.selectedMessages = [];
        },
        
        // 处理快速选择模式变化
        handleQuickSelectModeChange(enabled) {
            // 可以在这里处理快速选择模式的状态变化
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
            
            this.selectedMessages = targetMessages.map(msg => msg.id || `${msg.source_channel}:${msg.message_id}`);
            MessageManager.success(`已选择 ${targetMessages.length} 条消息`);
        },
        
        // 处理批量操作完成
        handleBatchOperationComplete(result) {
            // 刷新数据
            this.loadMessages();
            this.refreshStats();
        },
        
        // 处理进度更新
        handleProgressUpdate(progress) {
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
                
                // 修复滚动百分比计算
                const maxScrollTop = Math.max(0, documentHeight - windowHeight);
                if (maxScrollTop <= 0) {
                    // 页面内容不足一屏，不需要滚动加载
                    scrollPercentage = 0;
                } else {
                    // 正常计算滚动百分比，确保不会超过100%
                    scrollPercentage = Math.min(100, (scrollTop / maxScrollTop) * 100);
                }
                
                // 只有当页面确实可以滚动且滚动到95%以上才加载更多
                const canScroll = maxScrollTop > 50; // 至少要有50px的滚动空间
                const nearBottom = scrollPercentage > 95;
                
                // 只在真正接近底部且页面可滚动时加载
                if (canScroll && nearBottom && !this.isLoadingMore && this.hasMore) {
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
    if (typeof createApp === 'undefined' && !window.Vue?.createApp) missingDeps.push('Vue');
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
        };
        
        app.use(ElementPlus);
        
        // 注册导航栏组件（可选）
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        } else {
        }

        // 注册Linus统计组件
        if (window.LinusStatsComponent) {
            app.component('linus-stats', window.LinusStatsComponent);
        } else {
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