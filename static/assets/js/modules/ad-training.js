/**
 * 广告分隔符训练页面
 */

const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

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
                const response = await axios.get('/api/training/separator-patterns');
                if (response.data.patterns) {
                    this.separatorPatterns = response.data.patterns;
                }
            } catch (error) {
                console.error('加载模式失败:', error);
            }
        },
        
        // 保存分隔符模式
        async savePatterns() {
            try {
                const response = await axios.post('/api/training/separator-patterns', {
                    patterns: this.separatorPatterns
                });
                
                if (response.data.success) {
                    ElMessage.success('分隔符模式已保存');
                } else {
                    ElMessage.error('保存失败');
                }
            } catch (error) {
                ElMessage.error('保存失败: ' + error.message);
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
            ElMessage.success('已加载默认模式');
        },
        
        // 测试分隔符检测
        testPatterns() {
            if (!this.testMessage) {
                ElMessage.warning('请输入测试消息');
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
                    console.error('正则表达式错误:', e);
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
                const response = await axios.get('/api/training/tail-filter-samples');
                this.trainingSamples = response.data.samples || [];
            } catch (error) {
                console.error('加载样本失败:', error);
            }
        },
        
        // 添加训练样本
        async addSample() {
            if (!this.newSample.fullContent || !this.newSample.separator) {
                ElMessage.warning('请填写完整信息');
                return;
            }
            
            try {
                // 分割内容
                const separatorIndex = this.newSample.fullContent.indexOf(this.newSample.separator);
                if (separatorIndex === -1) {
                    ElMessage.error('在内容中未找到指定的分隔符');
                    return;
                }
                
                const normalPart = this.newSample.fullContent.substring(0, separatorIndex).trim();
                const adPart = this.newSample.fullContent.substring(separatorIndex).trim();
                
                const response = await axios.post('/api/training/tail-filter-samples', {
                    description: this.newSample.description,
                    content: this.newSample.fullContent,
                    separator: this.newSample.separator,
                    normalPart: normalPart,
                    tailPart: adPart,  // 改为tailPart
                    adPart: adPart  // 兼容旧字段
                });
                
                if (response.data.success) {
                    ElMessage.success('样本已添加');
                    this.showAddSample = false;
                    this.newSample = {
                        description: '',
                        fullContent: '',
                        separator: ''
                    };
                    await this.loadSamples();
                } else {
                    ElMessage.error('添加失败');
                }
            } catch (error) {
                ElMessage.error('添加失败: ' + error.message);
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
                await ElMessageBox.confirm('确定要删除这个训练样本吗？', '确认删除', {
                    confirmButtonText: '删除',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                const response = await axios.delete(`/api/training/tail-filter-samples/${id}`);
                
                if (response.data.success) {
                    ElMessage.success('样本已删除');
                    await this.loadSamples();
                } else {
                    ElMessage.error('删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('删除失败: ' + error.message);
                }
            }
        },
        
        // 返回主页
        backToMain() {
            window.location.href = '/';
        }
    }
}).use(ElementPlus).mount('#app');