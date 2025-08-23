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
            // 标签页切换
            activeTab: 'config',
            
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
        
        // 加载分隔符配置 - 从train.js复制
        async loadSeparatorPatterns() {
            try {
                const response = await axios.get(API.training.separatorPatterns);
                if (response.data.success && response.data.patterns) {
                    this.separatorPatterns = response.data.patterns;
                }
            } catch (error) {
                window.SimpleUI.Message.error('加载分隔符配置失败');
            }
        },
        
        // 保存分隔符配置
        async saveSeparatorPatterns() {
            try {
                const response = await axios.post(API.training.separatorPatterns, {
                    patterns: this.separatorPatterns.filter(p => p.regex && p.description)
                });
                
                window.SimpleUI.Message.success('分隔符配置保存成功！');
            } catch (error) {
                console.error('保存分隔符配置失败:', error);
                window.SimpleUI.Message.error(error.response?.data?.detail || '保存失败');
            }
        },
        
        // 消息提示已统一使用 window.SimpleUI.Message
    },
    
    async mounted() {
        // 组件挂载后的初始化
        console.log('分隔符配置组件已加载');
        await this.loadSeparatorPatterns();
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