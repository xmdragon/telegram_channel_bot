/**
 * 广告关键词管理组件
 * 用于管理权重关键词系统
 */

const KeywordManager = {
    template: `
        <div class="keyword-manager">
            <div class="manager-header">
                <h4>广告关键词管理</h4>
                <div class="threshold-control">
                    <label>检测阈值:</label>
                    <input type="number" v-model.number="threshold" min="0.1" max="20.0" step="0.1" @change="updateThreshold">
                    <span class="threshold-hint">（权重累计≥{{ threshold }}判定为广告）</span>
                </div>
            </div>
            
            <div class="add-keyword-section">
                <input type="text" 
                       v-model="newKeyword" 
                       placeholder="输入新关键词"
                       @keyup.enter="addKeyword"
                       class="keyword-input">
                <input type="number" 
                       v-model.number="newWeight" 
                       class="weight-input"
                       min="0.1" 
                       max="10.0" 
                       step="0.1"
                       placeholder="权重">
                <span class="weight-hint">0.1-10.0</span>
                <button @click="addKeyword" class="btn btn-primary">
                    <i class="fas fa-plus"></i> 添加
                </button>
            </div>
            
            <div class="keywords-container">
                <div class="keyword-stats">
                    <span>共 {{ keywords.length }} 个关键词</span>
                    <button v-if="keywords.length > 0"
                            @click="clearAllKeywords"
                            class="btn btn-danger btn-sm"
                            style="float: right;">
                        <i class="fas fa-trash-alt"></i> 清除全部
                    </button>
                </div>
                
                <div class="keywords-grid">
                    <div v-for="item in keywords" 
                         :key="item.keyword" 
                         class="keyword-tag"
                         :class="getWeightClass(item.weight)">
                        <span class="keyword-text">{{ item.keyword }}</span>
                        <input type="number" 
                               class="weight-selector" 
                               :value="item.weight"
                               @input="updateWeight(item.keyword, $event.target.value)"
                               min="0.1" 
                               max="10.0" 
                               step="0.1">
                        <button class="delete-btn" 
                                @click="deleteKeyword(item.keyword)"
                                title="删除关键词">
                            ×
                        </button>
                    </div>
                </div>
            </div>
            
            <div v-if="loading" class="loading-overlay">
                <div class="spinner"></div>
            </div>
        </div>
    `,
    
    data() {
        return {
            keywords: [],
            threshold: 3,
            newKeyword: '',
            newWeight: 1.0,
            loading: false
        };
    },
    
    mounted() {
        this.loadKeywords();
    },
    
    methods: {
        async loadKeywords() {
            this.loading = true;
            try {
                const response = await axios.get(window.API.training.adKeywords);
                
                if (response.data.success) {
                    this.keywords = response.data.data.keywords || [];
                    this.threshold = response.data.data.threshold || 3;
                } else {
                    window.SimpleUI.Message.error('加载关键词失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                if (error.response) {
                    if (error.response.status === 401) {
                        window.SimpleUI.Message.error('未授权，请先登录');
                    } else {
                        window.SimpleUI.Message.error('加载关键词失败: ' + (error.response.data.detail || error.message));
                    }
                } else {
                    window.SimpleUI.Message.error('网络错误: ' + error.message);
                }
            } finally {
                this.loading = false;
            }
        },
        
        async addKeyword() {
            const keyword = this.newKeyword.trim();
            if (!keyword) {
                window.SimpleUI.Message.warning('请输入关键词');
                return;
            }
            
            // 验证权重值
            const weight = parseFloat(this.newWeight);
            if (isNaN(weight) || weight < 0.1 || weight > 10.0) {
                window.SimpleUI.Message.warning('权重必须在0.1-10.0之间');
                return;
            }
            
            // 检查是否已存在
            if (this.keywords.some(k => k.keyword === keyword)) {
                window.SimpleUI.Message.warning('关键词已存在');
                return;
            }
            
            this.loading = true;
            try {
                const response = await axios.post(window.API.training.addKeyword, {
                    keyword: keyword,
                    weight: parseFloat(this.newWeight)
                });
                
                if (response.data.success) {
                    this.keywords.push({
                        keyword: keyword,
                        weight: parseFloat(this.newWeight)
                    });
                    this.newKeyword = '';
                    this.newWeight = 1.0;
                    window.SimpleUI.Message.success('关键词已添加');
                }
            } catch (error) {
                window.SimpleUI.Message.error('添加失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        async updateWeight(keyword, newWeight) {
            // 验证权重值
            const weight = parseFloat(newWeight);
            if (isNaN(weight) || weight < 0.1 || weight > 10.0) {
                window.SimpleUI.Message.warning('权重必须在0.1-10.0之间');
                return;
            }
            
            this.loading = true;
            try {
                const response = await axios.put(
                    window.API.training.updateKeyword(keyword),
                    { weight: parseFloat(newWeight) }
                );
                
                if (response.data.success) {
                    const item = this.keywords.find(k => k.keyword === keyword);
                    if (item) {
                        item.weight = parseFloat(newWeight);
                    }
                    window.SimpleUI.Message.success('权重已更新');
                }
            } catch (error) {
                window.SimpleUI.Message.error('更新失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        async deleteKeyword(keyword) {
            if (!confirm(`确定删除关键词"${keyword}"吗？`)) {
                return;
            }
            
            this.loading = true;
            try {
                const response = await axios.delete(
                    window.API.training.deleteKeyword(keyword)
                );
                
                if (response.data.success) {
                    const index = this.keywords.findIndex(k => k.keyword === keyword);
                    if (index > -1) {
                        this.keywords.splice(index, 1);
                    }
                    window.SimpleUI.Message.success('关键词已删除');
                }
            } catch (error) {
                window.SimpleUI.Message.error('删除失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        // 获取权重CSS类
        getWeightClass(weight) {
            const w = Math.floor(parseFloat(weight));
            if (w >= 10) return 'weight-10';
            if (w >= 4) return 'weight-high';
            return `weight-${w}`;
        },
        
        async updateThreshold() {
            // 验证阈值
            const threshold = parseFloat(this.threshold);
            if (isNaN(threshold) || threshold < 0.1 || threshold > 20.0) {
                window.SimpleUI.Message.warning('阈值必须在0.1-20.0之间');
                return;
            }

            this.loading = true;
            try {
                const response = await axios.put(
                    window.API.training.updateThreshold,
                    { threshold: this.threshold }
                );

                if (response.data.success) {
                    window.SimpleUI.Message.success('阈值已更新');
                }
            } catch (error) {
                window.SimpleUI.Message.error('更新阈值失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        async clearAllKeywords() {
            if (!confirm('确定要清除所有关键词吗？此操作将删除全部已保存的关键词。')) {
                return;
            }

            this.loading = true;
            try {
                // 批量删除所有关键词
                const deletePromises = this.keywords.map(item =>
                    axios.delete(window.API.training.deleteKeyword(item.keyword))
                );

                await Promise.all(deletePromises);

                // 清空前端列表
                this.keywords = [];
                window.SimpleUI.Message.success('所有关键词已清除');
            } catch (error) {
                window.SimpleUI.Message.error('清除关键词失败: ' + error.message);
                // 刷新列表以同步状态
                await this.loadKeywords();
            } finally {
                this.loading = false;
            }
        }
    }
};

// 导出组件
window.KeywordManager = KeywordManager;