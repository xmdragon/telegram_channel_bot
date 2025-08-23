/* Promo Training - 推广链接训练功能 */

// 全局Vue应用实例
let promoApp;

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    // 初始化Vue应用
    const { createApp } = Vue;
    
    promoApp = createApp({
        components: {
            'training-nav': TrainingNav
        },
        data() {
            return {
                // 加载状态
                loading: false,
                loadingText: '处理中...',
                submitting: false,
                
                // 统计数据
                stats: {
                    totalSamples: 0,
                    uniqueSamples: 0,
                    mediaFiles: 0
                },
                
                // 推广链接训练表单
                promoTrainingForm: {
                    full_content: '',
                    promo_section: '',
                    separator_type: '',
                    promo_features: []
                },
                
                // 预览结果
                promoFilteredPreview: '',
                
                // 消息提示
                message: {
                    text: '',
                    type: 'info'  // info, success, warning, error
                }
            };
        },
        
        async mounted() {
            // 检查认证状态
            if (!(await this.checkAuth())) {
                return;
            }
            
            // 加载初始数据
            await this.loadStats();
            
            // 设置axios拦截器
            if (typeof setupAxiosAuth === 'function') {
                setupAxiosAuth();
            }
        },
        
        methods: {
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
            
            // 预览推广链接过滤效果
            async previewPromoFilter() {
                if (!this.promoTrainingForm.full_content) {
                    this.showMessage('请填写完整消息内容', 'warning');
                    return;
                }
                
                try {
                    const response = await axios.post(API.training.previewPromoFilter, {
                        content: this.promoTrainingForm.full_content
                    });
                    
                    if (response.data.success || response.data.data) {
                        this.promoFilteredPreview = response.data.filtered_content || response.data.data?.filtered_content;
                    } else {
                        this.showMessage('预览失败: ' + response.data.message, 'error');
                    }
                } catch (error) {
                    this.showMessage('预览失败: ' + error.message, 'error');
                }
            },
            
            // 清空推广链接训练表单
            clearPromoForm() {
                this.promoTrainingForm = {
                    full_content: '',
                    promo_section: '',
                    separator_type: '',
                    promo_features: []
                };
                this.promoFilteredPreview = '';
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
            
            // 显示消息
            showMessage(text, type = 'info') {
                this.message = { text, type };
                
                // 3秒后自动隐藏消息
                setTimeout(() => {
                    this.message.text = '';
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
        }
    });
    
    // 挂载Vue应用
    promoApp.mount('#app');
});