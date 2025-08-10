/**
 * AI训练页面组件
 */
const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const TrainApp = {
    data() {
        return {
            activeTab: 'train',
            loading: false,
            loadingText: '加载中...',
            submitting: false,
            applying: false,
            
            // 训练模式
            trainingMode: 'tail',  // 'tail', 'ad', 'separator'
            
            // 频道列表
            channels: [],
            
            // 训练表单（尾部过滤）
            trainingForm: {
                channel_id: '',
                original_message: '',
                tail_content: '',
                message_id: null  // 添加message_id字段
            },
            
            // 广告训练表单
            adTrainingForm: {
                content: '',
                is_ad: true,
                description: ''
            },
            
            // 分隔符配置
            separatorPatterns: [],
            
            // 预览
            filteredPreview: '',
            
            // 统计信息
            stats: {
                totalChannels: 0,
                trainedChannels: 0,
                totalSamples: 0,
                todayTraining: 0
            },
            
            // 训练历史
            trainingHistory: []
        };
    },
    
    mounted() {
        // 先检查URL参数
        this.checkUrlParams();
        // 然后初始化
        this.init();
    },
    
    methods: {
        // 检查URL参数并自动填充表单
        async checkUrlParams() {
            const params = new URLSearchParams(window.location.search);
            
            // 检查是否有mode参数
            const mode = params.get('mode');
            if (mode) {
                // 设置训练模式
                if (mode === 'ad') {
                    this.trainingMode = 'ad';
                } else if (mode === 'tail') {
                    this.trainingMode = 'tail';
                } else if (mode === 'separator') {
                    this.trainingMode = 'separator';
                }
            }
            
            // 只有当有message_id参数时才处理
            const messageId = params.get('message_id');
            const channelId = params.get('channel_id');
            
            // 如果没有任何参数，直接返回
            if (!messageId && !channelId) {
                return;
            }
            
            // 保存message_id到表单中
            this.trainingForm.message_id = messageId;
            
            // 如果有消息ID，从API获取消息内容
            if (messageId) {
                try {
                    const response = await axios.get(`/api/messages/${messageId}`);
                    if (response.data && response.data.success && response.data.message) {
                        const msg = response.data.message;
                        
                        // 根据模式填充不同的表单
                        if (this.trainingMode === 'ad') {
                            // 广告训练模式
                            this.adTrainingForm.content = msg.content || msg.filtered_content || '';
                            this.adTrainingForm.is_ad = true; // 默认标记为广告
                            
                            // 显示提示信息
                            ElMessage({
                                message: '已自动填充消息内容，请选择是否为广告',
                                type: 'info',
                                offset: 20,
                                customClass: 'bottom-right-message'
                            });
                        } else {
                            // 尾部训练模式
                            this.trainingForm.channel_id = channelId || msg.source_channel;
                            this.trainingForm.original_message = msg.content || msg.filtered_content || '';
                            
                            // 显示提示信息
                            ElMessage({
                                message: '已自动填充消息内容，请标记出需要过滤的尾部内容',
                                type: 'info',
                                offset: 20,
                                customClass: 'bottom-right-message'
                            });
                            
                            // 焦点设置到尾部内容输入框
                            this.$nextTick(() => {
                                const tailInput = document.querySelector('textarea[placeholder*="尾部内容"]');
                                if (tailInput) {
                                    tailInput.focus();
                                }
                            });
                        }
                        
                        // 切换到训练标签页
                        this.activeTab = 'train';
                    }
                } catch (error) {
                    console.error('获取消息详情失败:', error);
                    // 如果是404错误，消息不存在
                    if (error.response && error.response.status === 404) {
                        ElMessage({
                            message: '消息不存在或已被删除',
                            type: 'error',
                            offset: 20,
                            customClass: 'bottom-right-message'
                        });
                    } else {
                        ElMessage({
                            message: '获取消息内容失败，请手动输入',
                            type: 'error',
                            offset: 20,
                            customClass: 'bottom-right-message'
                        });
                    }
                    // 仅设置频道ID
                    if (channelId) this.trainingForm.channel_id = channelId;
                }
                
                // 清除URL参数，避免刷新页面时重复处理
                window.history.replaceState({}, document.title, window.location.pathname);
            } else if (channelId) {
                // 只有频道ID，没有消息ID
                this.trainingForm.channel_id = channelId;
                // 清除URL参数
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        },
        
        async init() {
            // 根据训练模式加载不同的数据
            if (this.trainingMode === 'separator') {
                await this.loadSeparatorPatterns();
            } else if (this.trainingMode === 'ad') {
                await this.loadAdSamples();
            } else {
                // 尾部过滤训练
                await this.loadChannels();
                await this.loadStats();
                await this.loadHistory();
            }
        },
        
        // 训练模式切换
        async onTrainingModeChange(mode) {
            this.trainingMode = mode;
            await this.init();
        },
        
        // 加载分隔符模式
        async loadSeparatorPatterns() {
            try {
                const response = await axios.get('/api/training/separator-patterns');
                this.separatorPatterns = response.data.patterns || [];
            } catch (error) {
                console.error('加载分隔符模式失败:', error);
                this.separatorPatterns = [
                    { regex: '━{10,}', description: '横线分隔符' },
                    { regex: '═{10,}', description: '双线分隔符' },
                    { regex: '─{10,}', description: '细线分隔符' }
                ];
            }
        },
        
        // 保存分隔符模式
        async saveSeparatorPatterns() {
            try {
                const response = await axios.post('/api/training/separator-patterns', {
                    patterns: this.separatorPatterns
                });
                
                if (response.data.success) {
                    ElMessage.success('分隔符模式已保存');
                } else {
                    ElMessage.error('保存失败');
                }
            } catch (error) {
                ElMessage.error('保存失败: ' + error.message);
            }
        },
        
        // 添加分隔符模式
        addSeparatorPattern() {
            this.separatorPatterns.push({ regex: '', description: '' });
        },
        
        // 删除分隔符模式
        removeSeparatorPattern(index) {
            this.separatorPatterns.splice(index, 1);
        },
        
        // 加载广告样本
        async loadAdSamples() {
            try {
                const response = await axios.get('/api/training/ad-samples', {
                    params: { limit: 20 }
                });
                // 处理广告样本数据
                console.log('广告样本:', response.data);
            } catch (error) {
                console.error('加载广告样本失败:', error);
            }
        },
        
        // 提交广告训练
        async submitAdTraining() {
            if (!this.adTrainingForm.content) {
                ElMessage.warning('请输入训练内容');
                return;
            }
            
            this.submitting = true;
            try {
                const response = await axios.post('/api/training/add-ad-sample', {
                    content: this.adTrainingForm.content,
                    is_ad: this.adTrainingForm.is_ad,
                    description: this.adTrainingForm.description
                });
                
                if (response.data.success) {
                    ElMessage.success('广告样本已添加');
                    this.adTrainingForm = {
                        content: '',
                        is_ad: true,
                        description: ''
                    };
                    await this.loadStats();
                } else {
                    ElMessage.error(response.data.message || '添加失败');
                }
            } catch (error) {
                ElMessage.error('提交失败: ' + error.message);
            } finally {
                this.submitting = false;
            }
        },
        
        async loadChannels() {
            try {
                const response = await axios.get('/api/training/channels');
                this.channels = response.data.channels || [];
            } catch (error) {
                console.error('加载频道失败:', error);
                ElMessage({
                    message: '加载频道列表失败',
                    type: 'error',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
            }
        },
        
        async loadStats() {
            try {
                const response = await axios.get('/api/training/stats');
                this.stats = response.data;
            } catch (error) {
                console.error('加载统计失败:', error);
            }
        },
        
        async loadHistory() {
            try {
                const response = await axios.get('/api/training/history');
                this.trainingHistory = response.data.history || [];
            } catch (error) {
                console.error('加载历史失败:', error);
            }
        },
        
        updatePreview() {
            if (this.trainingForm.original_message && this.trainingForm.tail_content) {
                const tailIndex = this.trainingForm.original_message.indexOf(this.trainingForm.tail_content);
                if (tailIndex > -1) {
                    this.filteredPreview = this.trainingForm.original_message.substring(0, tailIndex).trim();
                } else {
                    this.filteredPreview = this.trainingForm.original_message;
                }
            } else {
                this.filteredPreview = '';
            }
        },
        
        clearForm() {
            this.trainingForm = {
                channel_id: '',
                original_message: '',
                tail_content: '',
                message_id: null
            };
            this.filteredPreview = '';
        },
        
        async submitTraining() {
            if (!this.trainingForm.channel_id) {
                ElMessage({
                    message: '请选择频道',
                    type: 'warning',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
                return;
            }
            
            if (!this.trainingForm.original_message || !this.trainingForm.tail_content) {
                ElMessage({
                    message: '请填写完整的训练数据',
                    type: 'warning',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
                return;
            }
            
            this.submitting = true;
            try {
                // 提交训练数据，包括message_id
                const response = await axios.post('/api/training/submit', {
                    channel_id: this.trainingForm.channel_id,
                    original_message: this.trainingForm.original_message,
                    tail_content: this.trainingForm.tail_content,
                    message_id: this.trainingForm.message_id  // 传递message_id
                });
                
                if (response.data.success) {
                    ElMessage({
                        message: '训练样本已提交，消息已更新',
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    this.clearForm();
                    await this.loadHistory();
                    await this.loadStats();
                    
                    // 更新频道的训练计数
                    const channel = this.channels.find(c => c.id === this.trainingForm.channel_id);
                    if (channel) {
                        channel.trained_count = (channel.trained_count || 0) + 1;
                    }
                } else {
                    ElMessage({
                        message: response.data.message || '提交失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } catch (error) {
                ElMessage({
                    message: '提交失败: ' + (error.response?.data?.detail || error.message),
                    type: 'error',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
            } finally {
                this.submitting = false;
            }
        },
        
        async applyTraining() {
            try {
                await ElMessageBox.confirm(
                    '确定要应用所有训练数据吗？这将重新训练AI模型。',
                    '确认操作',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                this.applying = true;
                const response = await axios.post('/api/training/apply');
                if (response.data.success) {
                    ElMessage({
                        message: response.data.message || '训练已应用，AI模型已更新',
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                } else {
                    ElMessage({
                        message: response.data.message || '应用失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage({
                        message: '应用失败: ' + (error.response?.data?.detail || error.message),
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } finally {
                this.applying = false;
            }
        },
        
        async deleteTraining(id) {
            try {
                await ElMessageBox.confirm(
                    '确定要删除这条训练记录吗？',
                    '确认删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                const response = await axios.delete(`/api/training/${id}`);
                if (response.data.success) {
                    ElMessage({
                        message: '删除成功',
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    await this.loadHistory();
                    await this.loadStats();
                } else {
                    ElMessage({
                        message: response.data.message || '删除失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除失败:', error);
                }
            }
        },
        
        formatTime(timeStr) {
            if (!timeStr) return '';
            const date = new Date(timeStr);
            const now = new Date();
            const diff = (now - date) / 1000 / 60; // 分钟
            
            if (diff < 60) return `${Math.floor(diff)}分钟前`;
            if (diff < 1440) return `${Math.floor(diff / 60)}小时前`;
            
            return date.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    }
};

// 导出到全局变量供页面使用
window.TrainApp = TrainApp;

// 等待DOM加载完成后初始化Vue应用
document.addEventListener('DOMContentLoaded', function() {
    try {
        const app = createApp(TrainApp);
        app.use(ElementPlus);
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }
        app.mount('#app');
        console.log('训练页面初始化成功');
    } catch (error) {
        console.error('训练页面初始化失败:', error);
    }
});