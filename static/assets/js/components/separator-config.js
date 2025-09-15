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
            separatorPatterns: [],
            
            // 正则测试数据
            regexTest: {
                content: '',      // 测试内容
                pattern: '',      // 正则表达式
                matches: [],      // 匹配结果
                error: '',        // 错误信息
                highlightedContent: '',  // 高亮显示的内容
                filteredContent: ''  // 过滤后的内容
            }
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
        
        // 测试正则表达式
        async testRegex() {
            // 清空之前的结果
            this.regexTest.matches = [];
            this.regexTest.error = '';
            this.regexTest.highlightedContent = '';
            this.regexTest.filteredContent = '';

            // 如果没有输入内容，直接返回
            if (!this.regexTest.content) {
                return;
            }

            try {
                // 调用后端API进行测试
                const response = await axios.post(API.training.testSeparator, {
                    content: this.regexTest.content,
                    pattern: this.regexTest.pattern || null
                });

                if (response.data.success) {
                    const data = response.data;

                    // 设置匹配结果
                    this.regexTest.matches = data.matches || [];
                    this.regexTest.filteredContent = data.filtered_content || '';

                    // 生成高亮显示（如果有匹配）
                    if (this.regexTest.matches.length > 0) {
                        let highlightedContent = this.regexTest.content;

                        // 从后往前替换，避免索引偏移
                        for (let i = this.regexTest.matches.length - 1; i >= 0; i--) {
                            const match = this.regexTest.matches[i];
                            const before = highlightedContent.substring(0, match.index);
                            const matchText = highlightedContent.substring(match.index, match.index + match.length);
                            const after = highlightedContent.substring(match.index + match.length);

                            const escapedMatch = this.escapeHtml(matchText);

                            highlightedContent = before +
                                '<span style="background: #ffc107; padding: 2px 4px; border-radius: 3px; font-weight: bold;">' +
                                escapedMatch +
                                '</span>' +
                                after;
                        }

                        this.regexTest.highlightedContent = highlightedContent;
                    }

                    // 如果没有指定pattern，显示完整的过滤统计
                    if (!this.regexTest.pattern && data.stats) {
                        console.log('分隔符过滤统计:', data.stats);
                    }
                } else {
                    this.regexTest.error = data.error || '测试失败';
                }
            } catch (error) {
                this.regexTest.error = '测试失败: ' + (error.response?.data?.detail || error.message);
            }
        },
        
        // HTML转义
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },
        
        // 选择预设的正则表达式
        selectPresetPattern(event) {
            const pattern = event.target.value;
            if (pattern) {
                this.regexTest.pattern = pattern;
                this.testRegex();
            }
        }
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