/* 分隔符配置组件 - 从train.js提取 */

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
            loadingText: '处理中...',
            
            // 分隔符模式 - 从train.js复制的默认模式
            separatorPatterns: [
                { regex: '━{10,}', description: '横线分隔符' },
                { regex: '═{10,}', description: '双线分隔符' },
                { regex: '─{10,}', description: '细线分隔符' },
                { regex: '\\*{10,}', description: '星号分隔符' },
                { regex: '-{10,}', description: '短横线分隔符' }
            ]
        };
    },
    
    methods: {
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
        console.log('分隔符配置组件已加载');
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