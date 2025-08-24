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
            // 推广链接训练表单
            promoTrainingForm: {
                promo_content: '',
                separator_type: ''
            },
            
            // 预览内容
            promoFilteredPreview: ''
        };
    },
    
    methods: {
        // 提交推广链接训练
        async submitPromoTraining() {
            if (!this.promoTrainingForm.promo_content.trim()) {
                window.SimpleUI.Message.warning('请填写推广内容');
                return;
            }
            
            try {
                const response = await axios.post(API.training.promoSamples, {
                    promo_content: this.promoTrainingForm.promo_content,
                    separator_type: this.promoTrainingForm.separator_type
                });
                
                window.SimpleUI.Message.success('推广内容样本提交成功！');
                this.clearPromoForm();
            } catch (error) {
                console.error('提交推广内容样本失败:', error);
                window.SimpleUI.Message.error(error.response?.data?.detail || '提交失败');
            }
        },
        
        // 清空推广表单
        clearPromoForm() {
            this.promoTrainingForm = {
                promo_content: '',
                separator_type: ''
            };
            this.promoFilteredPreview = '';
        },
        
        // 预览过滤效果
        async previewPromoFilter() {
            if (!this.promoTrainingForm.promo_content.trim()) {
                window.SimpleUI.Message.warning('请先填写推广内容');
                return;
            }
            
            try {
                const response = await axios.post(API.training.previewPromoFilter, {
                    content: this.promoTrainingForm.promo_content
                });
                
                this.promoFilteredPreview = response.data.data?.filtered_content || '无预览内容';
            } catch (error) {
                console.error('预览过滤效果失败:', error);
                window.SimpleUI.Message.error('预览失败');
            }
        },
        
        // 消息提示已统一使用 window.SimpleUI.Message
        // showMessage 方法已废弃，请使用 window.SimpleUI.Message.success/error/warning/info
        showMessage_deprecated(message, type = 'info') {
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