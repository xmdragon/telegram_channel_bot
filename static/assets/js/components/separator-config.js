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
                
                window.SimpleUI.Message.success('分隔符配置保存成功！');
            } catch (error) {
                console.error('保存分隔符配置失败:', error);
                window.SimpleUI.Message.error(error.response?.data?.detail || '保存失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 消息提示已统一使用 window.SimpleUI.Message
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