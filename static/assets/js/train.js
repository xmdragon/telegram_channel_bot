/* Train.js - 原生JavaScript训练管理功能 */

// 全局Vue应用实例
let trainApp;

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    // 初始化Vue应用
    const { createApp } = Vue;
    
    trainApp = createApp({
        data() {
            return {
                // 训练模式
                trainingMode: 'tail',
                
                // 活动标签页
                activeTab: 'train',
                
                // 加载状态
                loading: false,
                loadingText: '处理中...',
                submitting: false,
                
                // 统计数据
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
                
                // 尾部训练表单
                trainingForm: {
                    original_message: '',
                    tail_content: '',
                    contentType: null
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
                
                // 分隔符模式
                separatorPatterns: [
                    { regex: '━{10,}', description: '横线分隔符' },
                    { regex: '═{10,}', description: '双线分隔符' },
                    { regex: '─{10,}', description: '细线分隔符' },
                    { regex: '\\*{10,}', description: '星号分隔符' },
                    { regex: '-{10,}', description: '短横线分隔符' }
                ],
                
                // 预览内容
                filteredPreview: '',
                promoFilteredPreview: ''
            }
        },
        
        methods: {
            // 设置训练模式
            setTrainingMode(mode) {
                this.trainingMode = mode;
                if (mode !== 'data') {
                    this.activeTab = 'train';
                }
            },
            
            // 更新预览
            updatePreview() {
                if (this.trainingForm.original_message && this.trainingForm.tail_content) {
                    const original = this.trainingForm.original_message;
                    const tail = this.trainingForm.tail_content;
                    this.filteredPreview = original.replace(tail, '').trim();
                } else {
                    this.filteredPreview = '';
                }
            },
            
            // 预览推广过滤效果
            previewPromoFilter() {
                if (this.promoTrainingForm.full_content && this.promoTrainingForm.promo_section) {
                    const full = this.promoTrainingForm.full_content;
                    const promo = this.promoTrainingForm.promo_section;
                    this.promoFilteredPreview = full.replace(promo, '').trim();
                } else {
                    this.promoFilteredPreview = '';
                }
            },
            
            // 提交尾部训练样本
            async submitTraining() {
                if (!this.trainingForm.original_message || !this.trainingForm.tail_content) {
                    this.showMessage('请填写完整的训练内容', 'warning');
                    return;
                }
                
                this.submitting = true;
                try {
                    const response = await axios.post(API.training.tailSamples, {
                        original_message: this.trainingForm.original_message,
                        tail_content: this.trainingForm.tail_content
                    });
                    
                    this.showMessage('训练样本提交成功！', 'success');
                    this.clearForm();
                    this.loadStats();
                } catch (error) {
                    console.error('提交训练样本失败:', error);
                    this.showMessage(error.response?.data?.detail || '提交失败', 'error');
                } finally {
                    this.submitting = false;
                }
            },
            
            // 提交广告训练样本
            async submitAdTraining() {
                if (!this.adTrainingForm.content) {
                    this.showMessage('请填写训练内容', 'warning');
                    return;
                }
                
                this.submitting = true;
                try {
                    const response = await axios.post(API.training.adSamples, {
                        content: this.adTrainingForm.content,
                        is_ad: this.adTrainingForm.is_ad,
                        description: this.adTrainingForm.description
                    });
                    
                    this.showMessage('广告训练样本提交成功！', 'success');
                    this.adTrainingForm = { content: '', is_ad: true, description: '' };
                    this.loadStats();
                } catch (error) {
                    console.error('提交广告训练样本失败:', error);
                    this.showMessage(error.response?.data?.detail || '提交失败', 'error');
                } finally {
                    this.submitting = false;
                }
            },
            
            // 提交推广链接训练样本
            async submitPromoTraining() {
                if (!this.promoTrainingForm.full_content || !this.promoTrainingForm.promo_section) {
                    this.showMessage('请填写完整的推广链接训练内容', 'warning');
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
                    
                    this.showMessage('推广链接训练样本提交成功！', 'success');
                    this.clearPromoForm();
                    this.loadStats();
                } catch (error) {
                    console.error('提交推广链接训练样本失败:', error);
                    this.showMessage(error.response?.data?.detail || '提交失败', 'error');
                } finally {
                    this.submitting = false;
                }
            },
            
            // 清空表单
            clearForm() {
                this.trainingForm = {
                    original_message: '',
                    tail_content: '',
                    contentType: null
                };
                this.filteredPreview = '';
            },
            
            // 清空推广表单
            clearPromoForm() {
                this.promoTrainingForm = {
                    full_content: '',
                    promo_section: '',
                    separator_type: '',
                    promo_features: []
                };
                this.promoFilteredPreview = '';
            },
            
            // 添加分隔符模式
            addSeparatorPattern() {
                this.separatorPatterns.push({
                    regex: '',
                    description: ''
                });
            },
            
            // 删除分隔符模式
            removeSeparatorPattern(index) {
                this.separatorPatterns.splice(index, 1);
            },
            
            // 保存分隔符配置
            async saveSeparatorPatterns() {
                this.loading = true;
                this.loadingText = '保存配置中...';
                
                try {
                    const response = await axios.post(API.config.separatorPatterns, {
                        patterns: this.separatorPatterns.filter(p => p.regex && p.description)
                    });
                    
                    this.showMessage('分隔符配置保存成功！', 'success');
                } catch (error) {
                    console.error('保存分隔符配置失败:', error);
                    this.showMessage(error.response?.data?.detail || '保存失败', 'error');
                } finally {
                    this.loading = false;
                }
            },
            
            // 加载统计数据
            async loadStats() {
                try {
                    const response = await axios.get(API.training.stats);
                    this.stats = response.data;
                } catch (error) {
                    console.error('加载统计数据失败:', error);
                }
            },
            
            // 加载训练数据统计
            async loadTrainingDataStats() {
                try {
                    const response = await axios.get(API.training.dataStats);
                    this.trainingDataStats = response.data;
                } catch (error) {
                    console.error('加载训练数据统计失败:', error);
                }
            },
            
            // 打开训练管理器
            openTrainingManager(type) {
                // 根据类型跳转到相应的管理页面
                if (type === 'tail') {
                    window.location.href = '/static/tail-filter-manager.html';
                } else if (type === 'ad') {
                    window.location.href = '/static/ad-training-manager.html';
                }
            },
            
            // 格式化文件大小
            formatSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            },
            
            // 显示消息提示
            showMessage(message, type = 'info') {
                // 创建消息提示元素
                const messageDiv = document.createElement('div');
                messageDiv.className = `message-toast message-${type}`;
                messageDiv.textContent = message;
                
                // 添加样式
                messageDiv.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    padding: 12px 20px;
                    border-radius: 6px;
                    color: white;
                    font-weight: 500;
                    z-index: 10000;
                    animation: slideIn 0.3s ease;
                    max-width: 300px;
                    word-wrap: break-word;
                `;
                
                // 根据类型设置背景色
                switch (type) {
                    case 'success':
                        messageDiv.style.backgroundColor = '#67c23a';
                        break;
                    case 'warning':
                        messageDiv.style.backgroundColor = '#e6a23c';
                        break;
                    case 'error':
                        messageDiv.style.backgroundColor = '#f56c6c';
                        break;
                    default:
                        messageDiv.style.backgroundColor = '#409eff';
                }
                
                document.body.appendChild(messageDiv);
                
                // 3秒后自动移除
                setTimeout(() => {
                    messageDiv.style.animation = 'slideOut 0.3s ease';
                    setTimeout(() => {
                        if (messageDiv.parentNode) {
                            messageDiv.parentNode.removeChild(messageDiv);
                        }
                    }, 300);
                }, 3000);
            },
            
            // 检查认证状态
            async checkAuth() {
                try {
                    const token = localStorage.getItem('authToken');
                    if (!token) {
                        window.location.href = '/static/login.html';
                        return false;
                    }
                    
                    // 验证token有效性
                    const response = await axios.get(API.admin.profile);
                    return true;
                } catch (error) {
                    if (error.response && error.response.status === 401) {
                        localStorage.removeItem('authToken');
                        window.location.href = '/static/login.html';
                    }
                    return false;
                }
            }
        },
        
        async mounted() {
            // 检查认证状态
            const isAuthenticated = await this.checkAuth();
            if (!isAuthenticated) {
                return;
            }
            
            // 加载初始数据
            await this.loadStats();
            await this.loadTrainingDataStats();
            
            // 设置axios拦截器
            if (typeof setupAxiosAuth === 'function') {
                setupAxiosAuth();
            }
        }
    });
    
    // 挂载应用
    trainApp.mount('#app');
});

// 添加CSS动画
const style = document.createElement('style');
style.textContent = `
@keyframes slideIn {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

@keyframes slideOut {
    from {
        transform: translateX(0);
        opacity: 1;
    }
    to {
        transform: translateX(100%);
        opacity: 0;
    }
}

.message-toast {
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
`;
document.head.appendChild(style);