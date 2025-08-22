/**
 * AI训练页面组件
 */

// 确保API配置可用
const API = window.API;

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
                message_id: null,  // 添加message_id字段
                contentType: '',   // 内容类型说明（原始内容/过滤后内容）
                mediaGroupInfo: '' // 媒体组信息（隐藏字段）
            },
            
            // 广告训练表单
            adTrainingForm: {
                content: '',
                is_ad: true,
                description: ''
            },
            
            // 推广链接训练表单
            promoTrainingForm: {
                full_content: '',
                promo_section: '',
                separator_type: '',
                promo_features: []
            },
            
            // 分隔符配置
            separatorPatterns: [],
            
            // 预览
            filteredPreview: '',
            promoFilteredPreview: '',
            
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
        await this.checkUrlParams();
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
                } else if (mode === 'promo') {
                    this.trainingMode = 'promo';
                } else if (mode === 'separator') {
                    this.trainingMode = 'separator';
                } else if (mode === 'data') {
                    this.trainingMode = 'data';
                }
            }
            
            // 只有当有message_id参数时才处理
            const messageId = params.get('message_id');
            const channelId = params.get('channel_id');
            const useFiltered = params.get('useFiltered') === 'true';  // 是否使用过滤后内容
            
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
            }
            
            // 如果有消息ID，从API获取消息内容
            if (messageId) {
                try {
                    const response = await axios.get(API.messages.getById(messageId), {
                        headers: authManager.getAuthHeaders()
                    });
                    
                    if (response.data && response.data.data) {
                        const msg = response.data.data;
                        
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
                            // 根据useFiltered参数决定使用原始内容还是过滤后内容
                            let contentToUse;
                            let messageType;
                            
                            if (useFiltered && msg.filtered_content) {
                                contentToUse = msg.filtered_content;
                                messageType = '过滤后的内容';
                                this.trainingForm.contentType = 'filtered';
                            } else {
                                contentToUse = msg.content || msg.filtered_content || '';
                                messageType = '原始内容';
                                this.trainingForm.contentType = 'original';
                            }
                            
                            // 过滤媒体组信息并保存到隐藏字段
                            const mediaGroupPattern = /\[📎 媒体组:.*?\]/g;
                            const mediaGroupInfo = contentToUse.match(mediaGroupPattern) || [];
                            this.trainingForm.mediaGroupInfo = mediaGroupInfo.join(' ');
                            
                            // 显示时去除媒体组信息
                            const displayContent = contentToUse.replace(mediaGroupPattern, '').trim();
                            
                            this.trainingForm.original_message = displayContent;
                            
                            // 显示提示信息，说明当前使用的内容类型
                            ElMessage({
                                message: `已自动填充${messageType}，请标记出需要过滤的尾部内容`,
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
                        
                        // 成功处理后清除URL参数，避免刷新页面时重复处理
                        window.history.replaceState({}, document.title, window.location.pathname);
                    }
                } catch (error) {
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
                    // 出错时不清除URL参数，允许用户重试
                }
            } else if (channelId) {
                // 只有频道ID，没有消息ID时清除参数
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
                // 尾部过滤训练模式
                await this.loadStats();  // 加载统计信息
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
            const response = await axios.get(API.training.separatorPatterns);
            this.separatorPatterns = response.data.patterns || [];
        },
        
        // 保存分隔符模式
        async saveSeparatorPatterns() {
            try {
                const response = await axios.post(API.training.separatorPatterns, {
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
                const response = await axios.get(API.training.tailAdSamples);
                // 处理广告样本数据
            } catch (error) {
                // 静默处理加载失败
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
                const response = await axios.post(API.training.tailAdSamples, {
                    content: this.adTrainingForm.content,
                    description: this.adTrainingForm.description,
                    separator: '',  // 广告样本暂时不需要分隔符
                    normalPart: this.adTrainingForm.is_ad ? '' : this.adTrainingForm.content,
                    adPart: this.adTrainingForm.is_ad ? this.adTrainingForm.content : ''
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
        
        // 推广链接训练相关方法
        async submitPromoTraining() {
            if (!this.promoTrainingForm.full_content) {
                ElMessage.warning('请输入完整消息内容');
                return;
            }
            
            if (!this.promoTrainingForm.promo_section) {
                ElMessage.warning('请输入推广链接部分');
                return;
            }
            
            if (this.promoTrainingForm.promo_features.length === 0) {
                ElMessage.warning('请选择至少一个推广特征');
                return;
            }
            
            this.submitting = true;
            try {
                const response = await axios.post(API.training.promoSamples, {
                    full_content: this.promoTrainingForm.full_content,
                    promo_section: this.promoTrainingForm.promo_section,
                    separator_type: this.promoTrainingForm.separator_type,
                    promo_features: this.promoTrainingForm.promo_features
                });
                
                if (response.data.success) {
                    ElMessage.success('推广链接训练样本已添加');
                    this.clearPromoForm();
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
        
        clearPromoForm() {
            this.promoTrainingForm = {
                full_content: '',
                promo_section: '',
                separator_type: '',
                promo_features: []
            };
            this.promoFilteredPreview = '';
        },
        
        async previewPromoFilter() {
            if (!this.promoTrainingForm.full_content) {
                ElMessage.warning('请先输入完整消息内容');
                return;
            }
            
            try {
                const response = await axios.post(API.training.previewPromoFilter, {
                    content: this.promoTrainingForm.full_content,
                    separator_type: this.promoTrainingForm.separator_type
                });
                
                if (response.data.success) {
                    this.promoFilteredPreview = response.data.filtered_content;
                } else {
                    ElMessage.error('预览失败: ' + response.data.message);
                }
            } catch (error) {
                ElMessage.error('预览失败: ' + error.message);
            }
        },
        
        async loadChannels() {
            try {
                const response = await axios.get(API.training.channels);
                this.channels = response.data.channels || [];
            } catch (error) {
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
                const response = await axios.get(API.training.tailFilterStatistics);
                
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
                return;
            }
            
            try {
                // 获取最近的历史记录（限制数量）
                const response = await axios.get(API.training.tailFilterHistory, {
                    params: { limit: 20 }
                });
                
                if (response.data.success) {
                    this.trainingHistory = response.data.history || [];
                }
            } catch (error) {
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
                message_id: null,
                contentType: '',
                mediaGroupInfo: ''
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
                
                // 数据处理结果（调试模式下显示）
                if (window.DEBUG) {
                    console.log('📊 数据处理结果:', {
                        separator: separator.substring(0, 20) + '...',
                        normalPartLength: normalPart.length,
                        tailIndex: tailIndex,
                        tailLinesCount: tailLines.length
                    });
                }
                
                // 打印调试信息
                //     content: this.trainingForm.original_message,
                //     separator: separator,
                //     normalPart: normalPart,
                //     tailPart: this.trainingForm.tail_content
                // });
                
                // 检查token
                const token = localStorage.getItem('admin_token');
                
                // 统一提交到tail-filter-samples
                // 在保存时将媒体组信息附加到内容后面
                const fullContent = this.trainingForm.original_message + 
                    (this.trainingForm.mediaGroupInfo ? ' ' + this.trainingForm.mediaGroupInfo : '');
                    
                const postData = {
                    description: '尾部过滤训练样本',
                    content: fullContent,
                    separator: separator,
                    normalPart: normalPart,
                    tailPart: this.trainingForm.tail_content,
                    message_id: this.trainingForm.message_id  // 传递message_id
                };
                
                // 发送API请求（调试模式下显示）
                if (window.DEBUG) {
                    console.log('📡 发送API请求:', {
                        url: API.training.tailFilterSamples,
                        method: 'POST',
                        dataKeys: Object.keys(postData),
                        contentLength: postData.content.length,
                        tailPartLength: postData.tailPart.length
                    });
                }
                
                const response = await axios.post(API.training.tailFilterSamples, postData);
                
                // 收到API响应（调试模式下显示）
                if (window.DEBUG) {
                    console.log('📥 收到API响应:', {
                        status: response.status,
                        success: response.data.success,
                        message: response.data.message,
                        id: response.data.id
                    });
                }
                
                if (response.data.success) {
                    // 显示实际的响应消息
                    ElMessage({
                        message: response.data.message || '训练样本已提交并自动应用',
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    
                    // 检查是否需要自动返回主控制台
                    
                    if (this.autoReturnParams.enabled) {
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
                console.error('❌ 提交训练数据失败:', error);
                console.error('错误详情:', {
                    message: error.message,
                    status: error.response?.status,
                    statusText: error.response?.statusText,
                    responseData: error.response?.data
                });
                
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
                const response = await axios.delete(API.training.tailFilterSampleById(id));
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
                }
            }
        },
        
        formatTime(timeStr) {
            if (!timeStr) return '';
            try {
                // 🕐 修复时区bug：明确处理UTC时间
                const utcTimeStr = timeStr.endsWith('Z') ? timeStr : timeStr + 'Z';
                const date = new Date(utcTimeStr);
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
            } catch (error) {
                return timeStr;
            }
        },

        // 加载训练数据统计
        async loadTrainingDataStats() {
            try {
                const response = await axios.get(API.training.stats);
                // 适配API返回的数据结构
                this.trainingDataStats = {
                    totalSamples: response.data.totalSamples || 0,
                    uniqueSamples: response.data.totalChannels || 0,
                    mediaFiles: 0,  // 暂时不统计媒体文件
                    storageSize: 0  // 暂时不统计存储空间
                };
            } catch (error) {
                this.trainingDataStats = {
                    totalSamples: 0,
                    uniqueSamples: 0,
                    mediaFiles: 0,
                    storageSize: 0
                };
            }
        },

        // 打开训练数据管理界面
        openTrainingManager(type = null) {
            // 根据类型跳转到不同的独立页面
            let url;
            if (type === 'tail') {
                url = '/static/tail-filter-manager.html';
            } else if (type === 'ad') {
                url = '/static/ad-training-manager.html';
            } else {
                // 默认跳转到广告管理页面
                url = '/static/ad-training-manager.html';
            }
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
    } catch (error) {
    }
});