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
        testRegex() {
            // 清空之前的结果
            this.regexTest.matches = [];
            this.regexTest.error = '';
            this.regexTest.highlightedContent = '';
            this.regexTest.filteredContent = '';
            
            // 如果没有输入，直接返回
            if (!this.regexTest.pattern || !this.regexTest.content) {
                return;
            }
            
            try {
                // 固定使用 gi 标志，与后端保持一致
                // g: 全局匹配
                // i: 忽略大小写（对应后端的 re.IGNORECASE）
                const flags = 'gi';
                
                // 创建正则表达式对象
                const regex = new RegExp(this.regexTest.pattern, flags);
                
                // 收集所有匹配
                const matches = [];
                let match;
                
                // 使用exec循环获取所有匹配
                while ((match = regex.exec(this.regexTest.content)) !== null) {
                    matches.push({
                        text: match[0],
                        index: match.index,
                        length: match[0].length
                    });
                    
                    // 防止无限循环（零长度匹配）
                    if (match.index === regex.lastIndex) {
                        regex.lastIndex++;
                    }
                }
                
                this.regexTest.matches = matches;
                
                // 生成高亮显示的内容和过滤后的内容（模拟后端的 pattern.sub）
                if (matches.length > 0) {
                    let highlightedContent = this.regexTest.content;
                    
                    // 生成过滤后的内容（模拟后端的 pattern.sub('', content)）
                    this.regexTest.filteredContent = this.regexTest.content.replace(regex, '');
                    // 清理多余的空行（与后端一致）
                    this.regexTest.filteredContent = this.regexTest.filteredContent.replace(/\n{3,}/g, '\n\n').trim();
                    
                    // 从后往前替换，避免索引偏移
                    for (let i = matches.length - 1; i >= 0; i--) {
                        const match = matches[i];
                        const before = highlightedContent.substring(0, match.index);
                        const matchText = highlightedContent.substring(match.index, match.index + match.length);
                        const after = highlightedContent.substring(match.index + match.length);
                        
                        // 对匹配文本进行HTML转义
                        const escapedMatch = this.escapeHtml(matchText);
                        
                        highlightedContent = before + 
                            '<span style="background: #ffc107; padding: 2px 4px; border-radius: 3px; font-weight: bold;">' + 
                            escapedMatch + 
                            '</span>' + 
                            after;
                    }
                    
                    // 转义其他HTML字符
                    this.regexTest.highlightedContent = highlightedContent;
                }
                
            } catch (error) {
                // 正则表达式语法错误
                this.regexTest.error = '正则表达式语法错误: ' + error.message;
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