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
            
            // 分隔符模式 - 初始化为空，从服务器加载实际数据
            separatorPatterns: []
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
                    console.log(`成功加载 ${response.data.patterns.length} 条分隔符配置`);
                } else {
                    console.error('API响应格式错误:', response.data);
                    window.SimpleUI.Message.error('分隔符配置格式错误');
                }
            } catch (error) {
                console.error('加载分隔符配置失败:', error);
                window.SimpleUI.Message.error('加载分隔符配置失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 保存分隔符配置
        async saveSeparatorPatterns() {
            try {
                // 过滤出有效的分隔符模式
                const validPatterns = this.separatorPatterns.filter(p => p.regex && p.description);
                
                // 使用PUT方法进行批量更新（完全替换）
                const response = await axios.put(API.training.separatorPatterns, {
                    patterns: validPatterns
                });
                
                if (response.data.success) {
                    // 重新加载数据以确保同步
                    await this.loadSeparatorPatterns();
                    
                    window.SimpleUI.Message.success(
                        response.data.message || `成功保存 ${validPatterns.length} 个分隔符模式！`
                    );
                } else {
                    window.SimpleUI.Message.error(response.data.message || '保存失败');
                }
            } catch (error) {
                console.error('保存分隔符配置失败:', error);
                window.SimpleUI.Message.error('保存失败: ' + (error.response?.data?.detail || error.message));
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