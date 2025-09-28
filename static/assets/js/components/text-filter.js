/**
 * 文本过滤管理组件
 * 用于管理文本过滤关键词系统（支持正则表达式）
 */

const TextFilter = {
    template: `
        <div class="text-filter-manager">
            <div class="manager-header">
                <h4>文本过滤管理</h4>
                <div class="filter-stats">
                    <span>共 {{ filters.length }} 个过滤规则</span>
                </div>
            </div>

            <div class="add-filter-section">
                <input type="text"
                       v-model="newKeyword"
                       placeholder="输入过滤关键词或正则表达式"
                       @keyup.enter="addFilter"
                       class="filter-input">
                <label class="regex-checkbox">
                    <input type="checkbox" v-model="isRegex">
                    <span>正则表达式</span>
                </label>
                <button @click="addFilter" class="btn btn-primary">
                    <i class="fas fa-plus"></i> 添加
                </button>
                <button v-if="filters.length > 0"
                        @click="clearAllFilters"
                        class="btn btn-danger btn-sm">
                    <i class="fas fa-trash-alt"></i> 清除全部
                </button>
            </div>

            <div class="test-section">
                <h5>测试文本过滤</h5>
                <textarea v-model="testText"
                          placeholder="输入测试文本"
                          class="test-input"
                          rows="3"></textarea>
                <button @click="testFilter" class="btn btn-info btn-sm">
                    <i class="fas fa-flask"></i> 测试过滤效果
                </button>
                <div v-if="testResult" class="test-result">
                    <div class="result-item">
                        <strong>原文本：</strong>{{ testResult.original_length }} 字符
                    </div>
                    <div class="result-item">
                        <strong>过滤后：</strong>{{ testResult.filtered_length }} 字符
                    </div>
                    <div class="result-item" v-if="testResult.matched_keywords.length > 0">
                        <strong>匹配的关键词：</strong>
                        <span class="matched-keyword" v-for="keyword in testResult.matched_keywords" :key="keyword">
                            {{ keyword }}
                        </span>
                    </div>
                    <div class="result-item">
                        <strong>过滤后文本：</strong>
                        <div class="filtered-text">{{ testResult.filtered_text || '（空）' }}</div>
                    </div>
                </div>
            </div>

            <div class="filters-container">
                <div class="filters-grid">
                    <div v-for="item in filters"
                         :key="item.keyword"
                         class="filter-tag"
                         :class="{ 'regex-tag': item.is_regex }">
                        <span class="filter-type" v-if="item.is_regex" title="正则表达式">
                            <i class="fas fa-code"></i>
                        </span>
                        <span class="filter-text">{{ item.keyword }}</span>
                        <button class="delete-btn"
                                @click="deleteFilter(item.keyword)"
                                title="删除过滤器">
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
            filters: [],
            newKeyword: '',
            isRegex: false,
            testText: '',
            testResult: null,
            loading: false
        };
    },

    mounted() {
        this.loadFilters();
    },

    methods: {
        async loadFilters() {
            this.loading = true;
            try {
                const response = await axios.get(window.API.training.textFilters);

                if (response.data.success) {
                    this.filters = response.data.data.filters || [];
                } else {
                    window.SimpleUI.Message.error('加载文本过滤器失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                if (error.response) {
                    if (error.response.status === 401) {
                        window.SimpleUI.Message.error('未授权，请先登录');
                    } else {
                        window.SimpleUI.Message.error('加载文本过滤器失败: ' + (error.response.data.detail || error.message));
                    }
                } else {
                    window.SimpleUI.Message.error('网络错误: ' + error.message);
                }
            } finally {
                this.loading = false;
            }
        },

        async addFilter() {
            const keyword = this.newKeyword.trim();
            if (!keyword) {
                window.SimpleUI.Message.warning('请输入过滤关键词');
                return;
            }

            // 如果是正则表达式，验证其有效性
            if (this.isRegex) {
                try {
                    new RegExp(keyword);
                } catch (e) {
                    window.SimpleUI.Message.error('无效的正则表达式: ' + e.message);
                    return;
                }
            }

            // 检查是否已存在
            if (this.filters.some(f => f.keyword === keyword)) {
                window.SimpleUI.Message.warning('过滤器已存在');
                return;
            }

            this.loading = true;
            try {
                const response = await axios.post(window.API.training.textFilters, {
                    keyword: keyword,
                    is_regex: this.isRegex
                });

                if (response.data.success) {
                    this.filters.push({
                        keyword: keyword,
                        is_regex: this.isRegex
                    });
                    this.newKeyword = '';
                    this.isRegex = false;
                    window.SimpleUI.Message.success('过滤器已添加');
                }
            } catch (error) {
                window.SimpleUI.Message.error('添加失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },

        async deleteFilter(keyword) {
            if (!confirm(`确定删除过滤器"${keyword}"吗？`)) {
                return;
            }

            this.loading = true;
            try {
                const response = await axios.delete(
                    window.API.training.deleteTextFilter(keyword)
                );

                if (response.data.success) {
                    this.filters = this.filters.filter(f => f.keyword !== keyword);
                    window.SimpleUI.Message.success('过滤器已删除');
                }
            } catch (error) {
                window.SimpleUI.Message.error('删除失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },

        async clearAllFilters() {
            if (!confirm('确定要清除所有文本过滤器吗？此操作不可恢复！')) {
                return;
            }

            this.loading = true;
            try {
                const response = await axios.delete(window.API.training.clearTextFilters);

                if (response.data.success) {
                    this.filters = [];
                    window.SimpleUI.Message.success('已清除所有过滤器');
                }
            } catch (error) {
                window.SimpleUI.Message.error('清除失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },

        async testFilter() {
            if (!this.testText.trim()) {
                window.SimpleUI.Message.warning('请输入测试文本');
                return;
            }

            this.loading = true;
            try {
                const response = await axios.post(window.API.training.testTextFilter, {
                    text: this.testText
                });

                if (response.data.success) {
                    this.testResult = response.data.data;
                    if (this.testResult.is_filtered) {
                        window.SimpleUI.Message.success(
                            `过滤成功：移除了 ${this.testResult.removed_length} 个字符`
                        );
                    } else {
                        window.SimpleUI.Message.info('文本未被过滤');
                    }
                }
            } catch (error) {
                window.SimpleUI.Message.error('测试失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        }
    }
};

// 导出组件
if (typeof window !== 'undefined') {
    window.TextFilter = TextFilter;
}