/**
 * 广告分隔符训练页面
 */

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

createApp({
    data() {
        return {
            // 分隔符模式列表
            separatorPatterns: [
                { regex: '━{10,}', description: '横线分隔符（10个以上）' },
                { regex: '═{10,}', description: '双线分隔符' },
                { regex: '─{10,}', description: '细线分隔符' },
                { regex: '-{20,}', description: '短横线（20个以上）' },
                { regex: '={20,}', description: '等号线' },
                { regex: '\\*{20,}', description: '星号线' }
            ],
            
            // 测试消息
            testMessage: '',
            testResult: null,
            
            // 训练样本
            trainingSamples: [],
            showAddSample: false,
            showViewSample: false,
            currentSample: null,
            
            // 新样本
            newSample: {
                description: '',
                fullContent: '',
                separator: ''
            }
        };
    },
    
    mounted() {
        this.loadPatterns();
        this.loadSamples();
    },
    
    methods: {
        // 加载分隔符模式
        async loadPatterns() {
            try {
                const response = await axios.get(API.training.separatorPatterns);
                if (response.data.patterns) {
                    this.separatorPatterns = response.data.patterns;
                }
            } catch (error) {
            }
        },
        
        // 保存分隔符模式
        async savePatterns() {
            try {
                const response = await axios.post(API.training.separatorPatterns, {
                    patterns: this.separatorPatterns
                });
                
                if (response.data.success) {
                    window.SimpleUI.showMessage('分隔符模式已保存', 'success');
                } else {
                    window.SimpleUI.showMessage('保存失败', 'error');
                }
            } catch (error) {
                window.SimpleUI.showMessage('保存失败: ' + error.message, 'error');
            }
        },
        
        // 添加模式
        addPattern() {
            this.separatorPatterns.push({
                regex: '',
                description: ''
            });
        },
        
        // 删除模式
        removePattern(index) {
            this.separatorPatterns.splice(index, 1);
        },
        
        // 加载默认模式
        loadDefaultPatterns() {
            this.separatorPatterns = [
                { regex: '━{10,}', description: '横线分隔符（10个以上）' },
                { regex: '═{10,}', description: '双线分隔符' },
                { regex: '─{10,}', description: '细线分隔符' },
                { regex: '▬{10,}', description: '粗线分隔符' },
                { regex: '-{20,}', description: '短横线（20个以上）' },
                { regex: '={20,}', description: '等号线' },
                { regex: '\\*{20,}', description: '星号线' },
                { regex: '频道广告赞助商', description: '文字标记' },
                { regex: '\\[广告\\]|\\[推广\\]', description: '方括号标记' }
            ];
            window.SimpleUI.showMessage('已加载默认模式', 'success');
        },
        
        // 测试分隔符检测
        testPatterns() {
            if (!this.testMessage) {
                window.SimpleUI.showMessage('请输入测试消息', 'warning');
                return;
            }
            
            this.testResult = null;
            
            // 遍历所有模式进行测试
            for (const pattern of this.separatorPatterns) {
                if (!pattern.regex) continue;
                
                try {
                    const regex = new RegExp(pattern.regex, 'g');
                    const match = regex.exec(this.testMessage);
                    
                    if (match) {
                        // 找到匹配
                        const position = match.index;
                        const normalContent = this.testMessage.substring(0, position).trim();
                        const adContent = this.testMessage.substring(position).trim();
                        
                        this.testResult = {
                            found: true,
                            matchedPattern: pattern.description || pattern.regex,
                            position: position,
                            normalContent: normalContent,
                            adContent: adContent
                        };
                        break;
                    }
                } catch (e) {
                }
            }
            
            if (!this.testResult) {
                this.testResult = {
                    found: false
                };
            }
        },
        
        // 加载训练样本
        async loadSamples() {
            try {
                const response = await axios.get(API.training.tailFilterSamples);
                this.trainingSamples = response.data.samples || [];
            } catch (error) {
            }
        },
        
        // 添加训练样本
        async addSample() {
            if (!this.newSample.fullContent || !this.newSample.separator) {
                window.SimpleUI.showMessage('请填写完整信息', 'warning');
                return;
            }
            
            try {
                // 分割内容
                const separatorIndex = this.newSample.fullContent.indexOf(this.newSample.separator);
                if (separatorIndex === -1) {
                    window.SimpleUI.showMessage('在内容中未找到指定的分隔符', 'error');
                    return;
                }
                
                const normalPart = this.newSample.fullContent.substring(0, separatorIndex).trim();
                const adPart = this.newSample.fullContent.substring(separatorIndex).trim();
                
                const response = await axios.post(API.training.tailFilterSamples, {
                    description: this.newSample.description,
                    content: this.newSample.fullContent,
                    separator: this.newSample.separator,
                    normalPart: normalPart,
                    tailPart: adPart,  // 改为tailPart
                    adPart: adPart  // 兼容旧字段
                });
                
                if (response.data.success) {
                    window.SimpleUI.showMessage('样本已添加', 'success');
                    this.showAddSample = false;
                    this.newSample = {
                        description: '',
                        fullContent: '',
                        separator: ''
                    };
                    await this.loadSamples();
                } else {
                    window.SimpleUI.showMessage('添加失败', 'error');
                }
            } catch (error) {
                window.SimpleUI.showMessage('添加失败: ' + error.message, 'error');
            }
        },
        
        // 查看样本
        viewSample(sample) {
            // 分割内容
            if (sample.separator) {
                const separatorIndex = sample.content.indexOf(sample.separator);
                if (separatorIndex !== -1) {
                    sample.normalPart = sample.content.substring(0, separatorIndex).trim();
                    sample.adPart = sample.content.substring(separatorIndex).trim();
                }
            }
            
            this.currentSample = sample;
            this.showViewSample = true;
        },
        
        // 删除样本
        async deleteSample(id) {
            try {
                const confirmed = await window.SimpleUI.confirm('确定要删除这个训练样本吗？');
                if (!confirmed) {
                    return;
                }
                
                const response = await axios.delete(API.training.tailFilterSampleById(id));
                
                if (response.data.success) {
                    window.SimpleUI.showMessage('样本已删除', 'success');
                    await this.loadSamples();
                } else {
                    window.SimpleUI.showMessage('删除失败', 'error');
                }
            } catch (error) {
                window.SimpleUI.showMessage('删除失败: ' + error.message, 'error');
            }
        },
        
        // 返回主页
        backToMain() {
            window.location.href = '/';
        }
    }
}).mount('#app');