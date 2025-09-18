/**
 * 主页面协调器
 * 
 * 核心理念：
 * 1. 数据结构驱动程序设计 - "Bad programmers worry about the code. Good programmers worry about data structures"
 * 2. 消除边界情况 - 统一的委托模式处理所有操作
 * 3. 简洁执念 - 协调层只负责协调，不做具体实现
 */

// 确保全局依赖可用
let createApp;

// 安全的Loading包装器 - 防止undefined错误
const SafeLoading = {
    show(message) {
        if (window.SimpleUI?.Loading?.show) {
            window.SimpleUI.Loading.show(message);
        } else {
            // 创建临时加载提示
            const tempLoading = document.createElement('div');
            tempLoading.id = 'temp-loading-indicator';
            tempLoading.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:white;padding:20px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.2);z-index:9999';
            tempLoading.textContent = message || '加载中...';
            document.body.appendChild(tempLoading);
        }
    },
    hide() {
        if (window.SimpleUI?.Loading?.hide) {
            window.SimpleUI.Loading.hide();
        } else {
            // 移除临时加载提示
            const tempLoading = document.getElementById('temp-loading-indicator');
            if (tempLoading) {
                tempLoading.remove();
            }
        }
    }
};

// 延迟初始化函数
function initializeGlobals() {
    if (!createApp) {
        if (window.Vue?.createApp) {
            createApp = window.Vue.createApp;
        } else if (typeof Vue !== 'undefined' && Vue.createApp) {
            createApp = Vue.createApp;
        }
    }
    
}

// 主应用协调器 - 纯协调层，不包含具体业务逻辑
const MainApp = {
    data() {
        // "好品味"：确保状态初始化完整且可靠
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
                filter_reason: null
            },
            
            
            // 操作状态
            processingMessages: new Set(),
            publishingMessages: new Set(), // 正在发布的消息ID集合
            filteringMessages: new Set(), // 正在过滤的消息ID集合
            isBatchPublishing: false, // 批量发布状态
            componentRefreshKey: 0, // 用于强制组件重新渲染
            
            // 对话框状态现在由DialogStateManager管理
            // 这里只保留一个标记用于触发Vue更新
            dialogUpdateTrigger: 0,
            
            // 虚拟滚动配置
            useVirtualScroll: true,
            virtualScrollThreshold: 100,
            messageItemHeight: 200,
            virtualListHeight: 600,

            // 批量操作按钮可见性控制
            buttonVisibility: {
                approve: true,
                reject: true,
                delete: true
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
        // 弹窗状态代理 - 从独立的DialogStateManager获取
        editDialog() {
            this.dialogUpdateTrigger; // 依赖触发器以响应更新
            const state = window.DialogStateManager.getState('editDialog');
            console.log(`[Vue Computed] editDialog accessed, visible: ${state.visible}, trigger: ${this.dialogUpdateTrigger}`);
            // 返回新对象确保Vue检测到变化
            return { ...state };
        },
        originalMessageDialog() {
            this.dialogUpdateTrigger;
            const state = window.DialogStateManager.getState('originalMessageDialog');
            // 返回新对象确保Vue检测到变化
            return { ...state };
        },
        fileDetailsDialog() {
            this.dialogUpdateTrigger;
            const state = window.DialogStateManager.getState('fileDetailsDialog');
            // 返回新对象确保Vue检测到变化
            return { ...state };
        },
        mediaPreview() {
            this.dialogUpdateTrigger;
            const state = window.DialogStateManager.getState('mediaPreview');
            // 返回新对象确保Vue检测到变化
            return { ...state };
        },

        // "好品味"：简单直接的频道去重逻辑
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
        
        // "好品味"：可靠的消息过滤，不依赖外部模块
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
                
                // 广告筛选 - 使用统一的匹配函数修复字符串"False"问题
                if (!MessageUtils.matchesAdFilter(message, this.filters.is_ad)) {
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
        // "好品味"：确保所有响应式数据正确初始化

        // 注册DialogStateManager监听器以触发Vue更新
        window.DialogStateManager.addListener((dialogName, state) => {
            console.log(`[Vue] Dialog state changed: ${dialogName}, trigger: ${this.dialogUpdateTrigger}`);
            this.dialogUpdateTrigger++;
            console.log(`[Vue] New trigger value: ${this.dialogUpdateTrigger}`);
        });
        
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
            // 如果有弹窗打开，不自动刷新
            if (!window.DialogStateManager.hasOpenDialog()) {
                // 频道变化时自动加载消息
                this.loadMessages();
            }
        }
    },
    
    async mounted() {
        try {
            // 🔥 初始化事件委托系统
            if (window.EventDelegate) {
                this.eventDelegate = new window.EventDelegate(this);
            }
            
            // 初始化原消息链接点击事件委托
            this.initOriginalMessageEventDelegate();
            
            
            // 初始化权限检查
            const isAuthorized = await authManager.initPageAuth();
            if (!isAuthorized) {
                console.error('❌ 权限验证失败，停止初始化');
                return;
            }
            
            
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
                    window.SimpleUI.Message.error('加载消息失败，请刷新页面重试');
                    return { error: err }; // 返回错误对象，不抛出异常，让WebSocket能正常初始化
                }),
                // 统计数据由stats组件自动加载
                this.loadChannelInfo().catch(err => {
                    console.error('❌ 加载频道信息失败:', err);
                    return { error: err }; // 返回错误对象，不抛出异常，让WebSocket能正常初始化
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
                            console.error('WebSocket连接错误:', error);
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
            
            // 🔥 删除过于主动的焦点刷新
            // 用户切换窗口不应该触发自动加载，让用户自己控制何时刷新
            
            // 添加滚动监听
            this.setupScrollListener();
        } catch (error) {
            console.error('页面初始化失败:', error);
            window.SimpleUI.Message.error('页面初始化失败，部分功能可能不可用');
        }
    },
    
    beforeUnmount() {
        // 🔥 销毁事件委托系统
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
        // 工具函数：确保消息ID包含-100前缀 - 消除特殊情况
        ensureChannelIdPrefix(messageId) {
            if (!messageId || !messageId.includes(':')) {
                return messageId;
            }
            
            // 如果ID已经包含-100前缀，直接返回
            if (messageId.startsWith('-100')) {
                return messageId;
            }
            
            // 分解ID并添加-100前缀
            const [channelPart, messagePart] = messageId.split(':');
            return `-100${channelPart}:${messagePart}`;
        },
        
        // 发布状态检查方法
        isPublishing(messageId) {
            return this.publishingMessages.has(messageId);
        },
        
        // 过滤状态检查方法 - 与isPublishing保持一致
        isFiltering(messageId) {
            return this.filteringMessages.has(messageId);
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
                            enabled: true
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
                // 准备请求参数
                const params = {
                    ...this.filters,
                    page: this.currentPage,
                    page_size: this.pageSize
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
                    
                    // 计算真正的新消息 - 使用完整ID避免冲突
                    const getFullId = (msg) => msg.id || `${msg.source_channel}:${msg.message_id}`;
                    const currentMessageIds = new Set(newMessages.map(msg => getFullId(msg)));
                    const reallyNewMessages = newMessages.filter(msg => !this.previousMessageIds.has(getFullId(msg)));
                    
                    // 更新消息列表
                    if (append) {
                        // 追加到现有列表，避免重复 - 使用完整ID
                        const existingIds = new Set(this.messages.map(m => getFullId(m)));
                        const uniqueNewMessages = newMessages.filter(msg => !existingIds.has(getFullId(msg)));
                        this.messages = [...this.messages, ...uniqueNewMessages];
                        
                        // 如果没有新的唯一消息，说明已经到底了
                        if (uniqueNewMessages.length === 0) {
                            this.hasMore = false;
                        }
                    } else {
                        // 替换整个列表
                        this.messages = newMessages;
                        
                        
                        // 强制Vue重新渲染
                        this.$nextTick(() => {
                        });
                    }
                    
                    // 只有在追加模式且有真正新消息时才显示提示
                    if (append && reallyNewMessages.length > 0) {
                        window.SimpleUI.Message.success(`收到 ${reallyNewMessages.length} 条新消息`);
                    } else if (!append && this.filters.source_channel) {
                        // 频道切换时显示提示
                        const channelInfo = this.uniqueChannels[this.filters.source_channel];
                        const channelName = this.getChannelDisplayName(channelInfo);
                        window.SimpleUI.Message.info(`已切换到「${channelName}」，共 ${newMessages.length} 条消息`);
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
                        window.SimpleUI.Message.warning('暂无消息数据');
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
                window.SimpleUI.Message.error('加载消息失败: ' + (error.response?.data?.detail || error.message));
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
            // 调用统计组件的刷新方法
            if (this.$refs.messageStats) {
                this.$refs.messageStats.refreshStats();
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
                window.SimpleUI.Message.info('已清除频道筛选，显示所有频道的消息');
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
            window.DialogStateManager.show('originalMessageDialog', {
                messageId: messageId,
                loading: true,
                error: null,
                message: null
            });

            try {
                const response = await axios.get(window.API.messages.getById(encodeURIComponent(messageId)));
                window.DialogStateManager.setState('originalMessageDialog', {
                    message: response.data,
                    loading: false
                });
            } catch (error) {
                console.error('获取原消息失败:', error);
                window.DialogStateManager.setState('originalMessageDialog', {
                    error: '获取原消息失败: ' + (error.response?.data?.detail || error.message),
                    loading: false
                });
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
                
                // 检查是否点击了带有data-action的按钮
                const action = event.target.getAttribute('data-action');
                if (action === 'restoreMessage') {
                    event.preventDefault();
                    event.stopPropagation();

                    const messageId = event.target.getAttribute('data-message-id');
                    if (messageId) {
                        this.restoreMessage(messageId);
                    }
                } else if (action === 'markAsNotAd') {
                    event.preventDefault();
                    event.stopPropagation();

                    const messageId = event.target.getAttribute('data-message-id');
                    if (messageId) {
                        // 找到对应的消息对象
                        const message = this.messages.find(msg =>
                            `${msg.source_channel}:${msg.message_id}` === messageId);
                        if (message) {
                            this.markAsNotAd(event, message);
                        }
                    }
                } else if (action === 'deleteMessage') {
                    event.preventDefault();
                    event.stopPropagation();

                    const messageId = event.target.getAttribute('data-message-id');
                    if (messageId) {
                        this.deleteSingleMessage(messageId);
                    }
                }
            });
        },
        
        // 获取原消息链接 - 委托给DataUtils
        getOriginalMessageLink(message) {
            return window.DataUtils ? window.DataUtils.getOriginalMessageLink(message) : '#';
        },
        
        // 统计面板点击 - 没有特殊情况
        handleStatClick(statKey) {
            
            // 数据驱动，直接设置状态
            this.filters.source_channel = '';
            
            switch(statKey) {
                case 'pending':
                    this.filters.status = 'pending';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    break;
                case 'approved':
                    this.filters.status = 'approved';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    break;
                case 'rejected':
                    this.filters.status = 'rejected';
                    this.filters.is_ad = null;
                    this.filters.filter_reason = null;
                    break;
                default:
                    // 未知状态：不做任何操作
                    break;
            }
            
            window.SimpleUI.Message.info(`已切换到「${this.getStatLabel(statKey)}」并清除频道筛选`);
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
            window.SimpleUI.Message.info(`正在显示频道「${channelTitle || channelId}」的消息`);
        },
        
        // 清除频道筛选
        clearChannelFilter() {
            this.filters.source_channel = '';
            this.filters.status = 'pending';  // 恢复默认筛选
            this.currentPage = 1;
            this.hasMore = true;
            this.loadMessages();
            window.SimpleUI.Message.info('已清除频道筛选');
        },
        
        // 发布消息
        async approveMessage(event, messageId) {
            // 处理参数兼容性
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
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
                
                const response = await axios.post(window.API.messages.publishDirect(messageId));
                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已发布');
                    
                    // 如果当前过滤器是待审核状态，从列表中移除已发布的消息
                    if (this.filters.status === 'pending') {
                        // 修复ID格式不匹配问题：移除-100前缀进行比较
                        const normalizedMessageId = messageId.startsWith('-100') ? messageId.substring(4) : messageId;
                        
                        this.messages = this.messages.filter(msg => {
                            const msgId = String(msg.id);
                            const normalizedMsgId = msgId.startsWith('-100') ? msgId.substring(4) : msgId;
                            return normalizedMsgId !== normalizedMessageId;
                        });
                        
                        // 强制Vue更新
                        this.$forceUpdate();
                    } else {
                        // 本地更新消息状态
                        const normalizedMessageId = messageId.startsWith('-100') ? messageId.substring(4) : messageId;
                        const messageIndex = this.messages.findIndex(msg => {
                            const msgId = String(msg.id);
                            const normalizedMsgId = msgId.startsWith('-100') ? msgId.substring(4) : msgId;
                            return normalizedMsgId === normalizedMessageId;
                        });
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
                    window.SimpleUI.Message.error('发布失败: ' + response.data.message);
                    // 恢复加载状态
                    setTimeout(() => {
                        this.isLoadingMore = wasLoadingMore;
                    }, 500);
                }
            } catch (error) {
                window.SimpleUI.Message.error('发布失败: ' + (error.response?.data?.detail || error.message));
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
        async rejectMessage(event, messageId) {
            // 处理参数兼容性
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
            try {
                // 保存当前滚动位置
                const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                
                // 临时禁用滚动加载，防止DOM变化触发意外的loadMore
                const wasLoadingMore = this.isLoadingMore;
                this.isLoadingMore = true;
                
                // 标准化消息ID格式（移除-100前缀）
                const normalizedMessageId = messageId.startsWith('-100') ? messageId.substring(4) : messageId;
                
                // 先找到消息对象（在移除之前）- 使用标准化的ID查找
                const message = this.messages.find(msg => {
                    const msgId = String(msg.id);
                    const normalizedMsgId = msgId.startsWith('-100') ? msgId.substring(4) : msgId;
                    return normalizedMsgId === normalizedMessageId;
                });
                
                const response = await axios.post(`${window.API.messages.rejectById(messageId)}?reason=手动拒绝&reviewer=Web用户`);
                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已拒绝');
                    
                    // 如果当前筛选状态不是"已拒绝"，才从列表中移除消息
                    // 如果筛选状态是"已拒绝"，则更新消息状态而不是移除
                    if (this.filters.status === 'rejected') {
                        // 更新消息状态 - 使用标准化的ID查找
                        const msgIndex = this.messages.findIndex(msg => {
                            const msgId = String(msg.id);
                            const normalizedMsgId = msgId.startsWith('-100') ? msgId.substring(4) : msgId;
                            return normalizedMsgId === normalizedMessageId;
                        });
                        if (msgIndex !== -1) {
                            this.messages[msgIndex].status = 'rejected';
                        }
                    } else {
                        // 从列表中移除消息 - 使用标准化的ID比较
                        this.messages = this.messages.filter(msg => {
                            const msgId = String(msg.id);
                            const normalizedMsgId = msgId.startsWith('-100') ? msgId.substring(4) : msgId;
                            return normalizedMsgId !== normalizedMessageId;
                        });
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
                    window.SimpleUI.Message.error('拒绝失败: ' + response.data.message);
                    // 恢复加载状态
                    this.isLoadingMore = wasLoadingMore;
                }
            } catch (error) {
                window.SimpleUI.Message.error('拒绝失败: ' + (error.response?.data?.detail || error.message));
                // 恢复加载状态
                this.isLoadingMore = false;
            }
        },
        
        // 恢复被拒绝的消息
        async restoreMessage(event, messageId) {
            // 处理参数兼容性
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
            // 添加确认对话框
            if (!confirm('确定要恢复此消息为待审核状态吗？\n\n这将仅修改消息状态，不会影响训练数据。')) {
                return;
            }
            
            try {
                // 保存当前滚动位置
                const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                
                // 临时禁用滚动加载，防止DOM变化触发意外的loadMore
                const wasLoadingMore = this.isLoadingMore;
                this.isLoadingMore = true;
                
                const response = await axios.post(window.API.messages.restoreById(messageId));
                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已恢复到未审核状态');
                    
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
                    window.SimpleUI.Message.error('恢复失败: ' + response.data.message);
                    // 恢复加载状态
                    this.isLoadingMore = wasLoadingMore;
                }
            } catch (error) {
                window.SimpleUI.Message.error('恢复失败: ' + (error.response?.data?.detail || error.message));
                // 恢复加载状态
                this.isLoadingMore = false;
            }
        },

        // 删除单个消息
        async deleteSingleMessage(messageId) {
            // 添加确认对话框
            if (!confirm('确定要删除此消息吗？\n\n⚠️ 此操作将删除消息及其所有相关媒体文件，且不可恢复！')) {
                return;
            }

            try {
                // 保存当前滚动位置
                const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;

                // 临时禁用滚动加载
                const wasLoadingMore = this.isLoadingMore;
                this.isLoadingMore = true;

                const response = await axios.delete(window.API.messages.deleteById(messageId));
                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已删除');

                    // 从列表中移除该消息
                    const index = this.messages.findIndex(m =>
                        `${m.source_channel}:${m.message_id}` === messageId
                    );
                    if (index !== -1) {
                        this.messages.splice(index, 1);
                    }

                    // 刷新统计
                    this.refreshStats();

                    // 恢复滚动位置
                    this.$nextTick(() => {
                        window.scrollTo(0, scrollPosition);
                        // 恢复滚动加载状态
                        this.isLoadingMore = wasLoadingMore;
                    });
                } else {
                    window.SimpleUI.Message.error('删除失败: ' + response.data.message);
                }
            } catch (error) {
                console.error('删除消息失败:', error);
                window.SimpleUI.Message.error('删除失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 确保恢复滚动加载状态
                this.isLoadingMore = false;
            }
        },

        // 搜索消息
        searchMessages() {
            // 直接加载消息，不设置最小长度限制
            // 允许空搜索和单字符搜索
            this.loadMessages();
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
                    window.SimpleUI.Message.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    window.SimpleUI.Message.error('批量发布失败: ' + result.error);
                }
            } else {
                // 降级处理
                if (this.selectedMessages.length === 0) {
                    window.SimpleUI.Message.warning('请先选择要发布的消息');
                    return;
                }
                
                try {
                    const response = await axios.post(window.API.messages.batchApprove, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        window.SimpleUI.Message.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        window.SimpleUI.Message.error('批量发布失败: ' + response.data.message);
                    }
                } catch (error) {
                    window.SimpleUI.Message.error('批量发布失败: ' + (error.response?.data?.detail || error.message));
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
            window.DialogStateManager.show('mediaPreview', { url });
        },

        // 关闭媒体预览
        closeMediaPreview() {
            window.DialogStateManager.hide('mediaPreview');
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
            if (window.UIHandlers?.openMediaPreview) {
                window.UIHandlers.openMediaPreview(url);
            } else {
                window.DialogStateManager.show('mediaPreview', { url });
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
            
            // 使用DialogStateManager管理弹窗状态
            window.DialogStateManager.show('fileDetailsDialog', {
                details: { ...details }
            });
            
            
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
                if (size) {
                    const sizeInBytes = parseInt(size);
                    const currentDetails = window.DialogStateManager.getState('fileDetailsDialog').details;
                    window.DialogStateManager.setState('fileDetailsDialog', {
                        details: { ...currentDetails, size: this.formatFileSize(sizeInBytes) }
                    });
                }
            } catch (error) {
                const currentDetails = window.DialogStateManager.getState('fileDetailsDialog').details;
                window.DialogStateManager.setState('fileDetailsDialog', {
                    details: { ...currentDetails, size: '未知' }
                });
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
                
                // 创建新连接前清理旧连接
                if (this.websocket) {
                    this.websocket.close();
                }
                
                // 使用统一的WebSocket工厂，消除重复代码
                this.websocket = WebSocketFactory.create('main');
                
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

        // 处理WebSocket消息 - 兼容两种格式
        handleWebSocketMessage(eventOrData) {
            try {
                let data;
                
                // ：消除特殊情况，智能检测参数类型
                if (eventOrData && typeof eventOrData.data === 'string') {
                    // WebSocket原生event格式：{data: "json字符串"}
                    try {
                        data = JSON.parse(eventOrData.data);
                    } catch (parseError) {
                        console.error('WebSocket消息JSON解析失败:', parseError, eventOrData.data);
                        return;
                    }
                } else if (eventOrData && typeof eventOrData === 'object') {
                    // WebSocketManager传递的已解析对象格式
                    data = eventOrData;
                } else {
                    console.error('未知的WebSocket消息格式:', eventOrData);
                    return;
                }
                
                switch (data.type) {
                    case 'new_message':
                        this.handleNewMessage(data.data);
                        break;
                    case 'message_status_update':
                        this.handleMessageStatusUpdate(data.data);
                        break;
                    case 'forward_success':
                        this.handleForwardSuccess(data.data);
                        break;
                    case 'forward_retry':
                        this.handleForwardRetry(data.data);
                        break;
                    case 'forward_final_failure':
                        this.handleForwardFinalFailure(data.data);
                        break;
                    case 'pong':
                        // 心跳响应
                        break;
                    default:
                }
            } catch (error) {
                console.error('处理WebSocket消息时出错:', error, event.data);
            }
        },

        // 处理新消息
        handleNewMessage(messageData) {
            //     id: messageData.id,
            //     status: messageData.status,
            //     is_ad: messageData.is_ad,
            //     content_preview: messageData.content ? messageData.content.substring(0, 50) + '...' : '无内容'
            // });

            // 使用完整ID判断消息是否已存在，避免不同频道消息ID冲突
            const getFullId = (msg) => msg.id || `${msg.source_channel}:${msg.message_id}`;
            const existingIndex = this.messages.findIndex(msg => getFullId(msg) === getFullId(messageData));
            
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
                window.SimpleUI.Message.success(`收到新消息: ${contentPreview}`);
                
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

        // 处理转发成功
        handleForwardSuccess(data) {
            const messageIndex = this.messages.findIndex(msg => 
                msg.id === data.message_id || msg.message_id === data.message_id
            );
            if (messageIndex !== -1) {
                // 更新消息状态为已发布
                this.messages[messageIndex].status = 'approved';
                // 显示成功通知
                window.SimpleUI.Message.success(`消息 ${data.message_id} 已成功发布到目标频道`);
            }
        },

        // 处理转发重试
        handleForwardRetry(data) {
            // 显示重试通知
            window.SimpleUI.Message.warning(`消息 ${data.message_id} 发布失败，正在重试 (${data.retry_count}/3)`);
        },

        // 处理转发最终失败
        handleForwardFinalFailure(data) {
            const messageIndex = this.messages.findIndex(msg => 
                msg.id === data.message_id || msg.message_id === data.message_id
            );
            if (messageIndex !== -1) {
                // 更新消息状态回到待审核
                this.messages[messageIndex].status = 'pending';
                // 显示失败通知
                window.SimpleUI.Message.error(`消息 ${data.message_id} 发布失败，已退回待审核状态。错误：${data.error || '未知错误'}`);
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
                    this.websocket.send(JSON.stringify({type: 'ping'}));
                }
            }, 20000); // 20秒心跳，确保在服务器30秒超时前发送
        },
        
        
        // 编辑消息
        editMessage(messageId) {
            console.log('editMessage called with:', messageId);
            console.log('Available messages:', this.messages.map(msg => ({
                id: msg.id,
                message_id: msg.message_id,
                source_channel: msg.source_channel,
                computed: msg.id || `${msg.source_channel}:${msg.message_id}`
            })));

            const message = this.messages.find(msg => {
                // 规范化消息ID以确保匹配
                let msgId = msg.id;
                if (!msgId && msg.source_channel && msg.message_id) {
                    // 如果频道ID不包含-100前缀且是纯数字，添加前缀
                    let normalizedChannelId = msg.source_channel;
                    if (!msg.source_channel.startsWith('-100') && /^\d+$/.test(msg.source_channel)) {
                        normalizedChannelId = `-100${msg.source_channel}`;
                    }
                    msgId = `${normalizedChannelId}:${msg.message_id}`;
                }
                return msgId === messageId;
            });
            if (!message) {
                window.SimpleUI.Message.error(`未找到消息: ${messageId}`);
                return;
            }
            const realMessageId = message.id || `${message.source_channel}:${message.message_id}`;
            window.DialogStateManager.show('editDialog', {
                messageId: realMessageId,
                filteredContent: message.filtered_content || '',
                originalMessage: message
            });
        },
        
        // 保存编辑的消息
        async saveEditedMessage(event) {
            // 强制阻止事件传播
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            // 从DialogStateManager获取当前编辑状态
            const editState = window.DialogStateManager.getState('editDialog');

            // 验证必要的数据
            if (!editState.messageId) {
                window.SimpleUI.Message.error('编辑失败: 消息ID不存在');
                return;
            }

            if (!editState.filteredContent && editState.filteredContent !== '') {
                window.SimpleUI.Message.error('编辑失败: 内容不能为空');
                return;
            }
            
            // 开始编辑消息（生产环境已移除调试日志）
            
            try {
                // axios拦截器会自动添加认证头，无需手动设置
                const response = await axios.post(window.API.messages.editPublish(this.ensureChannelIdPrefix(editState.messageId)), {
                    filtered_content: editState.filteredContent
                });


                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已编辑并保存');
                    window.DialogStateManager.hide('editDialog');

                    // 🚀 性能优化：使用局部更新，避免整个列表重新渲染
                    this.updateSingleMessage(editState.messageId, {
                        filtered_content: editState.filteredContent,
                        updated_at: new Date().toISOString()
                    });
                } else {
                    window.SimpleUI.Message.error('编辑失败: ' + (response.data.message || '未知错误'));
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
                
                window.SimpleUI.Message.error(errorMessage);
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
                        window.SimpleUI.Message.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        window.SimpleUI.Message.error('批量发布失败: ' + result.error);
                    }
                } else {
                    // 降级处理
                    if (this.selectedMessages.length === 0) {
                        window.SimpleUI.Message.warning('请先选择要发布的消息');
                        return;
                    }
                    
                    const response = await axios.post(window.API.messages.batchApprove, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        window.SimpleUI.Message.success(`成功发布 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        window.SimpleUI.Message.error('批量发布失败: ' + response.data.message);
                    }
                }
            } catch (error) {
                window.SimpleUI.Message.error('批量发布失败: ' + (error.response?.data?.detail || error.message));
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
                    window.SimpleUI.Message.success(`成功拒绝 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    window.SimpleUI.Message.error('批量拒绝失败: ' + result.error);
                }
            } else {
                // 降级处理
                if (this.selectedMessages.length === 0) {
                    window.SimpleUI.Message.warning('请先选择要拒绝的消息');
                    return;
                }
                
                try {
                    const response = await axios.post(window.API.messages.batchReject, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        window.SimpleUI.Message.success(`成功拒绝 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        window.SimpleUI.Message.error('批量拒绝失败: ' + response.data.message);
                    }
                } catch (error) {
                    window.SimpleUI.Message.error('批量拒绝失败: ' + (error.response?.data?.detail || error.message));
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
                window.SimpleUI.Message.info('正在重新发布消息到目标频道...');
                
                const response = await axios.post(window.API.messages.resendById(this.ensureChannelIdPrefix(message.id)));
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已重新发布到目标频道');
                    this.loadMessages(); // 刷新消息列表
                } else {
                    window.SimpleUI.Message.error('重新发布失败: ' + response.data.message);
                }
            } catch (error) {
                const errorMsg = error.response?.data?.detail || error.message || '重新发布失败';
                window.SimpleUI.Message.error('重新发布失败: ' + errorMsg);
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
                    window.SimpleUI.Message.error('消息ID格式错误');
                    return;
                }
                
                const [sourceChannel, messageId] = idParts;
                
                // 确认操作 - 使用统一的广告判断函数
                const confirmText = MessageUtils.isMessageAd(message) 
                    ? '确定要重置此广告消息吗？这将从训练样本中移除并重置为待审核状态。'
                    : '确定要重置此消息为待审核状态吗？';
                    
                if (!confirm(confirmText)) {
                    return;
                }
                
                const response = await axios.post(window.API.messages.reset, {
                    source_channel: sourceChannel,
                    message_id: parseInt(messageId),
                    is_ad: MessageUtils.getRawAdValue(message)
                });
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('消息已重置为待审核状态');
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    window.SimpleUI.Message.error('重置失败: ' + response.data.message);
                }
            } catch (error) {
                window.SimpleUI.Message.error('重置失败: ' + (error.response?.data?.detail || error.message));
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
                window.SimpleUI.Message.warning('请先选择要删除的消息');
                return;
            }
            
            if (!confirm(`确定要删除 ${this.selectedMessages.length} 条消息吗？`)) {
                return;
            }
            
            if (window.MessageManager) {
                const result = await window.MessageManager.batchDelete(this.selectedMessages);
                if (result.success) {
                    window.SimpleUI.Message.success(`成功删除 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    window.SimpleUI.Message.error('批量删除失败: ' + result.error);
                }
            } else {
                // 降级处理
                try {
                    const response = await axios.post(window.API.messages.batchDelete, {
                        message_ids: this.selectedMessages
                    });
                    if (response.data.success) {
                        window.SimpleUI.Message.success(`成功删除 ${this.selectedMessages.length} 条消息`);
                        this.selectedMessages = [];
                        this.loadMessages();
                        this.refreshStats();
                    } else {
                        window.SimpleUI.Message.error('批量删除失败: ' + response.data.message);
                    }
                } catch (error) {
                    window.SimpleUI.Message.error('批量删除失赅: ' + (error.response?.data?.detail || error.message));
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
            window.DialogStateManager.show('editDialog', {
                messageId: message.id,
                filteredContent: message.filtered_content || '',
                originalMessage: message
            });
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

        // 标记为广告 - 手动添加关键词
        async markAsAd(event, messageId) {
            // 处理参数兼容性
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
            // 直接使用messageId查找消息（已包含-100前缀）
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                window.SimpleUI.Message.error('未找到消息');
                return;
            }

            // 直接显示手动添加关键词的对话框
            this.showAdMarkingDialog(message, []);
        },
        
        // 显示广告标记弹窗
        showAdMarkingDialog(message, extractedKeywords) {
            // 创建弹窗HTML
            const dialogHtml = `
                <div class="ad-marking-dialog">
                    <div class="message-preview">
                        <h4>消息内容</h4>
                        <div class="message-content">${this.escapeHtml(message.content || message.filtered_content || '')}</div>
                    </div>
                    
                    <div class="keywords-section">
                        <h4>添加广告关键词</h4>
                        <div class="keywords-list" id="keywords-list">
                            <p class="no-keywords">请手动添加广告关键词</p>
                        </div>

                        <div class="add-keyword-section" style="margin-top:15px;padding-top:15px;border-top:1px solid #e4e7ed">
                            <div style="display:flex;align-items:center;gap:10px">
                                <input type="text"
                                       id="new-keyword-input"
                                       placeholder="输入广告关键词"
                                       style="flex:1;padding:8px;border:1px solid #dcdfe6;border-radius:4px">
                                <input type="number"
                                       id="new-keyword-weight"
                                       value="1.0"
                                       min="1.0"
                                       max="10.0"
                                       step="0.1"
                                       placeholder="权重"
                                       style="width:80px;padding:8px;border:1px solid #dcdfe6;border-radius:4px">
                                <button onclick="app.addKeywordToList()"
                                        class="btn-add"
                                        style="padding:8px 16px;background:#67c23a;color:white;border:none;border-radius:4px;cursor:pointer">添加</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // 创建自定义对话框
            const dialog = document.createElement('div');
            dialog.className = 'simple-dialog-overlay';
            dialog.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
            
            const dialogBox = document.createElement('div');
            dialogBox.className = 'simple-dialog-box';
            dialogBox.style.cssText = 'background:white;border-radius:8px;max-width:600px;width:90%;max-height:80vh;overflow:auto;box-shadow:0 4px 20px rgba(0,0,0,0.2)';
            
            dialogBox.innerHTML = `
                <div style="padding:20px;border-bottom:1px solid #e4e7ed">
                    <h3 style="margin:0;font-size:18px">标记为广告</h3>
                </div>
                <div style="padding:20px">
                    ${dialogHtml}
                </div>
                <div style="padding:20px;border-top:1px solid #e4e7ed;text-align:right">
                    <button id="dialog-cancel" style="margin-right:10px;padding:8px 20px;border:1px solid #dcdfe6;background:white;border-radius:4px;cursor:pointer">取消</button>
                    <button id="dialog-confirm" style="padding:8px 20px;background:#409eff;color:white;border:none;border-radius:4px;cursor:pointer">确认标记</button>
                </div>
            `;
            
            dialog.appendChild(dialogBox);
            document.body.appendChild(dialog);
            
            // 绑定事件
            document.getElementById('dialog-cancel').onclick = () => {
                document.body.removeChild(dialog);
            };
            
            document.getElementById('dialog-confirm').onclick = async () => {
                // 先收集关键词（在移除对话框之前）
                const keywords = {};
                const keywordItems = dialog.querySelectorAll('.keyword-item');

                keywordItems.forEach(item => {
                    const keywordText = item.querySelector('.keyword-text').value.trim();
                    const weight = parseFloat(item.querySelector('.keyword-weight').value) || 1.0;
                    // 只添加非空的关键词
                    if (keywordText) {
                        keywords[keywordText] = weight;
                    }
                });

                // 然后移除对话框
                document.body.removeChild(dialog);

                // 最后提交（传入收集的关键词）
                await this.submitAdMarking(message.id, keywords);
            };
            
            // 点击遮罩关闭
            dialog.onclick = (e) => {
                if (e.target === dialog) {
                    document.body.removeChild(dialog);
                }
            };
        },
        
        // 添加关键词到列表
        addKeywordToList() {
            const input = document.getElementById('new-keyword-input');
            const weight = document.getElementById('new-keyword-weight').value;
            const keyword = input.value.trim();
            
            if (!keyword) {
                window.SimpleUI.Message.warning('请输入关键词');
                return;
            }
            
            // 检查是否已存在
            const existingItems = document.querySelectorAll('.keyword-item .keyword-text');
            for (let item of existingItems) {
                if (item.value === keyword) {
                    window.SimpleUI.Message.warning('关键词已存在');
                    return;
                }
            }
            
            // 添加到列表
            const keywordsList = document.getElementById('keywords-list');
            const noKeywordsMsg = keywordsList.querySelector('.no-keywords');
            if (noKeywordsMsg) {
                noKeywordsMsg.remove();
            }
            
            // 生成唯一ID
            const itemId = 'keyword-manual-' + Date.now();
            
            const newItem = document.createElement('div');
            newItem.className = 'keyword-item';
            newItem.setAttribute('data-keyword-id', itemId);
            newItem.style.cssText = 'display:flex;align-items:center;margin-bottom:8px;padding:8px;background:#f5f7fa;border-radius:4px';
            newItem.innerHTML = `
                <input type="text" 
                       class="keyword-text" 
                       value="${this.escapeHtml(keyword)}"
                       style="flex:1;margin-right:10px;padding:6px;border:1px solid #dcdfe6;border-radius:4px;background:white">
                <input type="number" 
                       class="keyword-weight" 
                       value="${parseFloat(weight) || 1.0}"
                       min="1.0"
                       max="10.0"
                       step="0.1"
                       style="width:60px;padding:6px;border:1px solid #dcdfe6;border-radius:4px;margin-right:10px">
                <button onclick="app.removeKeywordFromList('${itemId}')" 
                        style="background:#f56c6c;color:white;border:none;border-radius:4px;padding:6px 10px;cursor:pointer;font-size:14px"
                        onmouseover="this.style.background='#f78989'"
                        onmouseout="this.style.background='#f56c6c'">×</button>
            `;
            keywordsList.appendChild(newItem);
            
            // 清空输入
            input.value = '';
            document.getElementById('new-keyword-weight').value = '1.0';
            window.SimpleUI.Message.success('已添加关键词');
        },
        
        // 从列表中删除关键词
        removeKeywordFromList(itemId) {
            const item = document.querySelector(`[data-keyword-id="${itemId}"]`);
            if (item) {
                item.remove();
                
                // 检查是否还有关键词
                const keywordsList = document.getElementById('keywords-list');
                const remainingItems = keywordsList.querySelectorAll('.keyword-item');
                if (remainingItems.length === 0) {
                    keywordsList.innerHTML = '<p class="no-keywords">未识别到新的广告关键词</p>';
                }
            }
        },
        
        // 提交广告标记
        async submitAdMarking(messageId, preCollectedKeywords = null) {
            try {
                // 使用传入的关键词，或者从DOM中收集（向后兼容）
                let keywords = preCollectedKeywords;

                if (!keywords) {
                    // 如果没有传入关键词，尝试从DOM收集（向后兼容）
                    keywords = {};
                    const keywordItems = document.querySelectorAll('.keyword-item');

                    keywordItems.forEach(item => {
                        const keywordText = item.querySelector('.keyword-text').value.trim();
                        const weight = parseFloat(item.querySelector('.keyword-weight').value) || 1.0;
                        // 只添加非空的关键词
                        if (keywordText) {
                            keywords[keywordText] = weight;
                        }
                    });
                }
                
                // 发送请求
                window.SimpleUI.Loading.show('正在保存...');
                const response = await axios.post(
                    window.API.messages.markAsAd(this.ensureChannelIdPrefix(messageId)),
                    { keywords }
                );
                window.SimpleUI.Loading.hide();
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('已标记为广告并保存关键词');
                    // 重新加载消息列表
                    this.loadMessages();
                    this.refreshStats();
                } else {
                    window.SimpleUI.Message.error(response.data.message || '标记失败');
                }
            } catch (error) {
                window.SimpleUI.Loading.hide();
                window.SimpleUI.Message.error('操作失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // HTML转义辅助函数
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },
        
        // 标记为"不是广告" - 纠正AI误判
        async markAsNotAd(event, messageId) {
            // 处理参数兼容性
            let message = null;

            // 如果第一个参数是字符串，说明是旧的调用方式
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
            // 如果第二个参数是对象，说明是message对象
            else if (typeof messageId === 'object' && messageId !== null) {
                message = messageId;
                messageId = message.id;
            }

            // 强制阻止事件传播
            if (event && event.preventDefault) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }

            // 如果没有message对象，从消息列表查找
            if (!message && messageId) {
                message = this.messages.find(msg => msg.id === messageId);
                if (!message) {
                    message = { id: messageId };
                }
            }
            try {
                if (!confirm('确定要将此广告标记为"不是广告"吗？\n\n这将执行以下操作：\n• 降低相关关键词的权重\n• 取消广告标记\n• 恢复为待审核状态\n\n这有助于提高AI广告识别的准确性。')) {
                    return;
                }
                
                const response = await axios.post(window.API.messages.notAd(this.ensureChannelIdPrefix(message.id)));
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('已标记为"不是广告"，消息状态已改为待审核');
                    // 重新加载消息以获取最新的过滤内容
                    // 因为后端已应用了尾部过滤和推广链接过滤
                    await this.loadMessages();
                    this.refreshStats();
                } else {
                    window.SimpleUI.Message.error(response.data.message || '操作失败');
                }
            } catch (error) {
                window.SimpleUI.Message.error('操作失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 训练尾部
        trainTail(event, messageId) {
            // 处理参数兼容性
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
            // 直接使用messageId查找消息（已包含-100前缀）
            const message = this.messages.find(msg => msg.id === messageId);

            if (!message) {
                window.SimpleUI.Message.error('未找到消息');
                return;
            }
            const processedId = this.ensureChannelIdPrefix(message.id);
            
            // 只传递message_id，让训练页面自己获取消息详情
            const params = new URLSearchParams({
                message_id: processedId
            });
            // 使用新的独立尾部过滤训练页面
            window.location.href = API.pages.tailFilterTraining + '?' + params.toString();
        },
        
        // 手动执行内容过滤 - 消除重复点击的特殊情况
        async filterContent(event, messageId) {
            // 处理参数兼容性
            if (typeof event === 'string') {
                messageId = event;
                event = null;
            }
            // 防重复点击保护 - 没有if分支，直接返回
            if (this.filteringMessages.has(messageId)) {
                return;
            }
            
            const message = this.messages.find(msg => msg.id === messageId);
            if (!message) {
                window.SimpleUI.Message.error('未找到消息');
                return;
            }
            
            // 标记正在过滤
            this.filteringMessages.add(messageId);
            
            try {
                // 🚀 依赖axios拦截器自动处理认证（消除特殊情况）
                const response = await axios.post(
                    window.API.messages.filterContent(this.ensureChannelIdPrefix(message.id)),
                    {} // 让拦截器自动添加认证头，避免手动覆盖
                );
                
                
                if (response.data.success) {
                    if (response.data.has_tail && response.data.removed_length > 0) {
                        window.SimpleUI.Message.success(`内容过滤成功，移除了 ${response.data.removed_length} 个字符`);
                        // 更新消息的过滤后内容
                        const index = this.messages.findIndex(m => m.id === message.id);
                        if (index !== -1) {
                            this.messages[index].filtered_content = response.data.filtered_content;
                        }
                    } else {
                        // 修复：显示后端返回的具体消息
                        window.SimpleUI.Message.info(response.data.message || '内容无需过滤');
                    }
                } else {
                    window.SimpleUI.Message.warning(response.data.message || '过滤失败');
                }
            } catch (error) {
                console.error('尾部过滤失败:', error);
                window.SimpleUI.Message.error('尾部过滤失败: ' + (error.response?.data?.detail || error.message));
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
            window.SimpleUI.Message.success(`已选择 ${targetMessages.length} 条消息`);
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
                window.SimpleUI.Message.error('操作失败，请重试');
            }
        };
        
        // 配置全局警告处理
        app.config.warnHandler = (msg, instance, trace) => {
        };
        
        
        // 注册导航栏组件（可选）
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        } else {
        }

        // 注册统计组件
        if (window.MessageStatsComponent) {
            app.component('message-stats', window.MessageStatsComponent);
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
        
        if (window.TelegramAlbum) {
            app.component('telegram-album', window.TelegramAlbum);
        }
        
        const vmInstance = app.mount('#app');
        // 暴露到全局，让内联事件处理器可以访问
        window.app = vmInstance;
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