/* 推广链接训练组件 - 从train.js提取 */

// 确保API配置可用
const API = window.API;

// 检查依赖
if (!window.Vue) {
    console.error('Vue 未加载!');
}

const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            loading: false,
            submitting: false,
            
            // 推广链接训练表单
            promoTrainingForm: {
                full_content: '',
                promo_section: '',
                separator_type: '',
                promo_features: []
            },
            
            // 预览内容
            promoFilteredPreview: ''
        };
    },
    
    methods: {
        // 提交推广链接训练
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
            } catch (error) {
                console.error('提交推广链接训练样本失败:', error);
                this.showMessage(error.response?.data?.detail || '提交失败', 'error');
            } finally {
                this.submitting = false;
            }
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
        
        // 显示消息提示 - 从train.js原样复制
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
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                transition: all 0.3s ease;
                transform: translateX(0);
            `;
            
            // 根据类型设置颜色
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
            
            // 添加到页面
            document.body.appendChild(messageDiv);
            
            // 3秒后移除
            setTimeout(() => {
                messageDiv.style.transform = 'translateX(100%)';
                messageDiv.style.opacity = '0';
                setTimeout(() => {
                    if (messageDiv.parentNode) {
                        messageDiv.parentNode.removeChild(messageDiv);
                    }
                }, 300);
            }, 3000);
        }
    },
    
    mounted() {
        // 组件挂载后的初始化
        console.log('推广链接训练组件已加载');
    }
});

// 注册组件
app.component('nav-bar', NavBar);
app.component('training-nav', TrainingNav);

// 挂载应用 - 确保DOM就绪
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        app.mount('#app');
    });
} else {
    // DOM已准备就绪
    app.mount('#app');
}