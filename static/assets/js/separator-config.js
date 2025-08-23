/* Separator Config - 分隔符配置功能 */

// 全局Vue应用实例
let separatorApp;

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    // 初始化Vue应用
    const { createApp } = Vue;
    
    separatorApp = createApp({
        components: {
            'training-nav': TrainingNav
        },
        data() {
            return {
                // 加载状态
                loading: false,
                loadingText: '处理中...',
                
                // 统计数据
                stats: {
                    totalSamples: 0,
                    accuracy: 0
                },
                
                // 分隔符模式
                separatorPatterns: [
                    { regex: '━{10,}', description: '横线分隔符' },
                    { regex: '═{10,}', description: '双横线分隔符' },
                    { regex: '─{10,}', description: '细横线分隔符' }
                ],
                
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
            await this.loadSeparatorPatterns();
            
            // 设置axios拦截器
            if (typeof setupAxiosAuth === 'function') {
                setupAxiosAuth();
            }
        },
        
        methods: {
            // 添加分隔符模式
            addSeparatorPattern() {
                this.separatorPatterns.push({ regex: '', description: '' });
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
                    const response = await axios.post(API.training.separatorPatterns, {
                        patterns: this.separatorPatterns.filter(p => p.regex.trim())
                    });
                    
                    this.showMessage('分隔符配置保存成功！', 'success');
                } catch (error) {
                    console.error('保存分隔符配置失败:', error);
                    this.showMessage(error.response?.data?.detail || '保存失败', 'error');
                } finally {
                    this.loading = false;
                }
            },
            
            // 加载分隔符模式
            async loadSeparatorPatterns() {
                try {
                    const response = await axios.get(API.training.separatorPatterns);
                    if (response.data.success && response.data.patterns) {
                        this.separatorPatterns = response.data.patterns;
                    }
                } catch (error) {
                    this.showMessage('加载分隔符配置失败', 'error');
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
            
            // 添加预设分隔符模式
            addPresetPattern(regex, description) {
                // 检查是否已存在
                const exists = this.separatorPatterns.some(p => p.regex === regex);
                if (!exists) {
                    this.separatorPatterns.push({ regex, description });
                    this.showMessage(`已添加分隔符模式: ${description}`, 'success');
                } else {
                    this.showMessage('该分隔符模式已存在', 'warning');
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
    separatorApp.mount('#app');
});