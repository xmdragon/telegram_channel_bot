// 重构后的主页面 JavaScript 组件 - 模块化版本

// 检查依赖是否加载
// console.log('Vue loaded:', typeof Vue !== 'undefined');
// console.log('ElementPlus loaded:', typeof ElementPlus !== 'undefined');
// console.log('Axios loaded:', typeof axios !== 'undefined');

const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

// 主页面应用组件 - 重构版本
const IndexApp = {
    data() {
        return {
            loading: false,
            
            // WebSocket连接
            ws: null,
            wsStatus: 'disconnected',
            
            // 消息过滤器
            filters: {
                status: 'all',
                search: '',
                channel: 'all',
                isAd: 'all'
            },
            
            // 分页
            currentPage: 1,
            pageSize: 20,
            
            // 选择状态
            selectAll: false,
            
            // 编辑对话框
            editDialog: {
                visible: false,
                message: null,
                content: ''
            },
            
            // 批量操作
            batchAction: {
                loading: false,
                reason: ''
            },
            
            // 统计信息
            stats: {
                total: 0,
                pending: 0,
                approved: 0,
                rejected: 0
            }
        }
    },
    
    mounted() {
        this.initializeApp();
    },
    
    beforeUnmount() {
        this.disconnectWebSocket();
    },
    
    computed: {
        // 获取消息列表
        messages() {
            return messageManager.messages || [];
        },
        
        // 过滤后的消息
        filteredMessages() {
            return messageManager.filterMessages(this.messages, this.filters);
        },
        
        // 分页信息
        pagination() {
            return messageManager.pagination;
        },
        
        // 选中的消息数量
        selectedCount() {
            return messageManager.getSelectedCount();
        },
        
        // 是否有选中的消息
        hasSelected() {
            return this.selectedCount > 0;
        },
        
        // WebSocket状态文本
        wsStatusText() {
            const statusMap = {
                'connected': '已连接',
                'disconnected': '已断开',
                'connecting': '连接中',
                'error': '连接错误'
            };
            return statusMap[this.wsStatus] || this.wsStatus;
        }
    },
    
    methods: {
        // ===================
        // 初始化方法
        // ===================
        async initializeApp() {
            this.loading = true;
            
            try {
                // 并行加载数据
                await Promise.all([
                    this.loadMessages(),
                    this.loadStats()
                ]);
                
                // 连接WebSocket
                this.connectWebSocket();
                
            } catch (error) {
                console.error('初始化失败:', error);
                ElMessage.error(`初始化失败: ${error.message}`);
            } finally {
                this.loading = false;
            }
        },

        async loadMessages(page = 1, pageSize = 20) {
            try {
                await messageManager.loadMessages(page, pageSize, this.filters);
                this.currentPage = page;
            } catch (error) {
                throw new Error(`加载消息失败: ${error.message}`);
            }
        },

        async loadStats() {
            try {
                this.stats = await messageManager.getMessageStats();
            } catch (error) {
                console.warn('加载统计信息失败:', error);
                // 统计信息不是必需的，不抛出错误
            }
        },

        // ===================
        // WebSocket方法
        // ===================
        connectWebSocket() {
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/messages`;
                
                this.ws = new WebSocket(wsUrl);
                this.wsStatus = 'connecting';
                
                this.ws.onopen = () => {
                    this.wsStatus = 'connected';
//                     console.log('WebSocket连接已建立');
                };
                
                this.ws.onmessage = (event) => {
                    this.handleWebSocketMessage(JSON.parse(event.data));
                };
                
                this.ws.onclose = () => {
                    this.wsStatus = 'disconnected';
//                     console.log('WebSocket连接已关闭');
                    
                    // 5秒后尝试重连
                    setTimeout(() => {
                        if (this.wsStatus === 'disconnected') {
                            this.connectWebSocket();
                        }
                    }, 5000);
                };
                
                this.ws.onerror = (error) => {
                    this.wsStatus = 'error';
                    console.error('WebSocket错误:', error);
                };
                
            } catch (error) {
                console.error('WebSocket连接失败:', error);
                this.wsStatus = 'error';
            }
        },

        disconnectWebSocket() {
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }
        },

        handleWebSocketMessage(data) {
            if (data.type === 'new_message') {
                // 新消息到达，刷新列表
                this.loadMessages(this.currentPage, this.pageSize);
                this.loadStats();
                
                // 显示通知
                ElMessage.info('收到新消息');
            }
        },

        // ===================
        // 消息操作方法
        // ===================
        async approveMessage(message) {
            try {
                await messageManager.reviewMessage(message.id, 'approve');
                ElMessage.success('消息已通过审核');
                await this.loadStats();
            } catch (error) {
                ElMessage.error(`审核失败: ${error.message}`);
            }
        },

        async rejectMessage(message) {
            try {
                await messageManager.reviewMessage(message.id, 'reject');
                ElMessage.success('消息已拒绝');
                await this.loadStats();
            } catch (error) {
                ElMessage.error(`操作失败: ${error.message}`);
            }
        },

        showEditDialog(message) {
            this.editDialog = {
                visible: true,
                message: message,
                content: message.filtered_content || message.content || ''
            };
        },

        async saveEditedMessage() {
            try {
                await messageManager.editMessage(this.editDialog.message.id, this.editDialog.content);
                ElMessage.success('消息编辑成功');
                this.editDialog.visible = false;
            } catch (error) {
                ElMessage.error(`编辑失败: ${error.message}`);
            }
        },

        // ===================
        // 批量操作方法
        // ===================
        toggleMessageSelection(message) {
            messageManager.toggleMessageSelection(message.id);
        },

        toggleSelectAll() {
            messageManager.toggleSelectAll(this.selectAll);
        },

        async batchApprove() {
            if (!this.hasSelected) {
                ElMessage.warning('请先选择消息');
                return;
            }
            
            try {
                await ElMessageBox.confirm(
                    `确定要批量通过 ${this.selectedCount} 条消息吗？`,
                    '批量审核',
                    { type: 'info' }
                );
                
                this.batchAction.loading = true;
                
                await messageManager.batchReviewMessages(
                    messageManager.selectedMessages,
                    'approve',
                    this.batchAction.reason
                );
                
                ElMessage.success(`已批量通过 ${this.selectedCount} 条消息`);
                
                await this.loadStats();
                this.batchAction.reason = '';
                
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error(`批量操作失败: ${error.message || error}`);
                }
            } finally {
                this.batchAction.loading = false;
            }
        },

        async batchReject() {
            if (!this.hasSelected) {
                ElMessage.warning('请先选择消息');
                return;
            }
            
            try {
                await ElMessageBox.confirm(
                    `确定要批量拒绝 ${this.selectedCount} 条消息吗？`,
                    '批量审核',
                    { type: 'warning' }
                );
                
                this.batchAction.loading = true;
                
                await messageManager.batchReviewMessages(
                    messageManager.selectedMessages,
                    'reject',
                    this.batchAction.reason
                );
                
                ElMessage.success(`已批量拒绝 ${this.selectedCount} 条消息`);
                
                await this.loadStats();
                this.batchAction.reason = '';
                
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error(`批量操作失败: ${error.message || error}`);
                }
            } finally {
                this.batchAction.loading = false;
            }
        },

        // ===================
        // 过滤和分页方法
        // ===================
        async applyFilters() {
            this.currentPage = 1;
            await this.loadMessages(1, this.pageSize);
        },

        async resetFilters() {
            this.filters = {
                status: 'all',
                search: '',
                channel: 'all',
                isAd: 'all'
            };
            await this.applyFilters();
        },

        async handlePageChange(page) {
            await this.loadMessages(page, this.pageSize);
        },

        async handlePageSizeChange(size) {
            this.pageSize = size;
            await this.loadMessages(1, size);
        },

        // ===================
        // 辅助方法
        // ===================
        formatMessageDisplay(message) {
            return messageManager.formatMessageForDisplay(message);
        },

        isMessageSelected(message) {
            return messageManager.isMessageSelected(message.id);
        },

        getMediaPreview(message) {
            if (!message.media_url) return null;
            
            if (message.media_type === 'photo') {
                return message.media_url.replace('./temp_media/', '/media/');
            }
            
            return null;
        },

        truncateContent(content, maxLength = 100) {
            if (!content) return '';
            return content.length > maxLength ? content.substring(0, maxLength) + '...' : content;
        }
    }
};

// 创建并挂载应用
const indexApp = createApp(IndexApp);

// 使用Element Plus
indexApp.use(ElementPlus);

// 挂载应用
indexApp.mount('#indexApp');