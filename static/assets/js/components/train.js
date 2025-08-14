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
            
            // 训练模式
            trainingMode: 'tail',  // 'tail', 'ad', 'separator', 'data'
            
            // 保存URL参数用于自动返回
            autoReturnParams: {
                enabled: false,
                messageId: null,
                mode: null
            },
            
            // 频道列表
            channels: [],
            
            // 训练表单（尾部过滤）
            trainingForm: {
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
            
            // 训练数据统计
            trainingDataStats: {
                totalSamples: 0,
                uniqueSamples: 0,
                mediaFiles: 0,
                storageSize: 0
            },
            
            // 训练历史
            trainingHistory: []
        };
    },
    
    async mounted() {
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth('training.view');
        if (!isAuthorized) {
            return;
        }
        
        // 先检查URL参数
        this.checkUrlParams();
        // 然后初始化
        this.init();
        // 加载训练数据统计
        this.loadTrainingDataStats();
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
                } else if (mode === 'data') {
                    this.trainingMode = 'data';
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
            
            // 保存自动返回参数（在清除URL之前）
            if (messageId && mode === 'tail') {
                this.autoReturnParams = {
                    enabled: true,
                    messageId: messageId,
                    mode: mode
                };
                console.log('设置自动返回参数:', this.autoReturnParams);
            }
            
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
                            // 不再需要设置channel_id，系统是频道无关的
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
                    // console.error('获取消息详情失败:', error);
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
                    // 不再需要设置频道ID
                }
                
                // 清除URL参数，避免刷新页面时重复处理
                window.history.replaceState({}, document.title, window.location.pathname);
            } else if (channelId) {
                // 只有频道ID，没有消息ID
                // 不再需要设置频道ID
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
            } else if (this.trainingMode === 'data') {
                // 数据管理模式，加载统计信息
                await this.loadTrainingDataStats();
            } else {
                // 尾部过滤训练 - 不再加载统计和历史数据
                // 只加载频道列表（如果需要）
                // await this.loadChannels();
                // 不需要加载统计和历史
            }
        },
        
        // 训练模式切换
        async onTrainingModeChange(mode) {
            this.trainingMode = mode;
            
            // 如果切换到数据管理模式，自动切换到管理标签页
            if (mode === 'data') {
                this.activeTab = 'manage';
            } else {
                // 其他模式默认显示训练标签页
                this.activeTab = 'train';
            }
            
            await this.init();
        },
        
        // 加载分隔符模式
        async loadSeparatorPatterns() {
            try {
                const response = await axios.get('/api/training/separator-patterns');
                this.separatorPatterns = response.data.patterns || [];
            } catch (error) {
                // console.error('加载分隔符模式失败:', error);
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
                // console.log('广告样本:', response.data);
            } catch (error) {
                // console.error('加载广告样本失败:', error);
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
                // console.error('加载频道失败:', error);
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
                // 只获取统计数据，不获取完整样本列表
                const response = await axios.get('/api/training/tail-filter-statistics');
                
                // 直接使用返回的统计数据
                if (response.data.success) {
                    this.stats = {
                        totalChannels: response.data.total_samples || 0,  // 显示为"总样本数"
                        trainedChannels: response.data.valid_samples || 0,  // 显示为"有效样本"
                        totalSamples: response.data.samples_with_separator || 0,  // 显示为"包含分隔符"
                        todayTraining: response.data.today_added || 0  // 显示为"今日新增"
                    };
                }
            } catch (error) {
                // console.error('加载统计失败:', error);
                // 如果统计端点不存在，降级到不加载
                this.stats = {
                    totalChannels: 0,
                    trainedChannels: 0,
                    totalSamples: 0,
                    todayTraining: 0
                };
            }
        },
        
        async loadHistory() {
            // 如果处于自动返回模式，不加载历史记录
            if (this.autoReturnParams.enabled) {
                console.log('自动返回模式，跳过加载历史记录');
                return;
            }
            
            try {
                // 获取最近的历史记录（限制数量）
                const response = await axios.get('/api/training/tail-filter-history', {
                    params: { limit: 20 }
                });
                
                if (response.data.success) {
                    this.trainingHistory = response.data.history || [];
                }
            } catch (error) {
                // console.error('加载历史失败:', error);
                // 如果历史端点不存在，设置为空
                this.trainingHistory = [];
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
                original_message: '',
                tail_content: '',
                message_id: null
            };
            this.filteredPreview = '';
        },
        
        async submitTraining() {
            // 移除频道选择验证，系统现在是频道无关的
            
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
                // 提取分隔符（尾部内容的第一行作为分隔符）
                const tailLines = this.trainingForm.tail_content.split('\n');
                const separator = tailLines[0] || '';
                
                // 计算正常部分
                const tailIndex = this.trainingForm.original_message.indexOf(this.trainingForm.tail_content);
                const normalPart = tailIndex > -1 
                    ? this.trainingForm.original_message.substring(0, tailIndex).trim()
                    : this.trainingForm.original_message;
                
                // 打印调试信息
                // console.log('提交数据:', {
                //     content: this.trainingForm.original_message,
                //     separator: separator,
                //     normalPart: normalPart,
                //     tailPart: this.trainingForm.tail_content
                // });
                
                // 检查token
                const token = localStorage.getItem('admin_token');
                // console.log('当前Token:', token ? '存在 (' + token.substring(0, 20) + '...)' : '不存在');
                // console.log('Authorization header:', axios.defaults.headers.common['Authorization']);
                
                // 统一提交到tail-filter-samples
                const response = await axios.post('/api/training/tail-filter-samples', {
                    description: '尾部过滤训练样本',
                    content: this.trainingForm.original_message,
                    separator: separator,
                    normalPart: normalPart,
                    tailPart: this.trainingForm.tail_content,
                    message_id: this.trainingForm.message_id  // 传递message_id
                });
                
                if (response.data.success) {
                    // 显示实际的响应消息
                    ElMessage({
                        message: response.data.message || '训练样本已提交并自动应用',
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    
                    // 检查是否需要自动返回主控制台
                    console.log('检查自动返回参数:', this.autoReturnParams);
                    
                    if (this.autoReturnParams.enabled) {
                        console.log('满足自动返回条件，1秒后返回主控制台');
                        // 立即返回，不需要刷新历史记录
                        setTimeout(() => {
                            window.location.href = '/static/index.html?refresh=true';
                        }, 1000);
                        return; // 直接返回，不执行后续操作
                    }
                    
                    // 只有在非自动返回模式下才清空表单
                    this.clearForm();
                    // 不再加载历史和统计数据
                    
                    // 不再需要更新频道训练计数
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
                    message: '提交失败: ' + (error.response?.data?.message || error.response?.data?.detail || error.message),
                    type: 'error',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
            } finally {
                this.submitting = false;
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
                
                // 统一删除tail-filter-samples中的记录
                const response = await axios.delete(`/api/training/tail-filter-samples/${id}`);
                if (response.data.success) {
                    ElMessage({
                        message: '删除成功',
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    // 不再加载历史和统计数据
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
                    // console.error('删除失败:', error);
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
        },

        // 加载训练数据统计
        async loadTrainingDataStats() {
            try {
                const response = await axios.get('/api/training/statistics');
                this.trainingDataStats = response.data;
            } catch (error) {
                // console.error('加载训练数据统计失败:', error);
            }
        },

        // 打开训练数据管理界面
        openTrainingManager(type = null) {
            // console.log('openTrainingManager called with type:', type);
            // 根据类型跳转到不同的独立页面
            let url;
            if (type === 'tail') {
                url = '/static/tail_filter_manager.html';
            } else if (type === 'ad') {
                url = '/static/ad_training_manager.html';
            } else {
                // 默认跳转到广告管理页面
                url = '/static/ad_training_manager.html';
            }
            // console.log('Navigating to:', url);
            // 在当前页面打开，而不是新窗口
            window.location.href = url;
        },

        // 格式化文件大小
        formatSize(bytes) {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
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
        if (window.TrainingNav) {
            app.component('training-nav', window.TrainingNav);
        }
        app.mount('#app');
        // console.log('训练页面初始化成功');
    } catch (error) {
        // console.error('训练页面初始化失败:', error);
    }
});