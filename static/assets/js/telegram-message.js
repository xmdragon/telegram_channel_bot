// 消息分析工具页面逻辑
const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            messageUrl: '',
            loading: false,
            errorMessage: '',
            messageInfo: null,
            messageStructures: [],
            expandedStates: [],
            isGroupMessage: false,
            filterResults: null,
            hasContent: false,
            activeTab: 'structure',  // 默认显示结构标签页
            fullApiResponse: null,  // 保存完整的API响应
            showFullResponse: false  // 控制是否显示完整响应
        };
    },

    computed: {
        showResults() {
            return this.messageStructures.length > 0 || this.errorMessage;
        }
    },

    async mounted() {
        // 初始化权限检查（不阻塞组件加载）
        try {
            await authManager.initPageAuth('training.view');
        } catch (error) {
            console.error('权限检查失败:', error);
            // 继续加载页面，让组件内部处理认证
        }
    },

    methods: {
        async analyzeMessage() {
            // 清空之前的错误消息
            this.errorMessage = '';

            // 检查URL是否为空
            if (!this.messageUrl || !this.messageUrl.trim()) {
                this.errorMessage = '消息URL不能为空';
                // 清空之前的结果
                this.messageInfo = null;
                this.messageStructures = [];
                this.filterResults = null;
                return;
            }

            const trimmedUrl = this.messageUrl.trim();

            this.loading = true;
            this.messageInfo = null;
            this.messageStructures = [];
            this.filterResults = null;
            this.hasContent = false;

            try {
                const response = await axios.post(API.telegram.analyzeMessage, {
                    message_url: trimmedUrl
                });

                // 处理包装的响应格式
                const responseData = response.data.success ? response.data.data : response.data;

                // 保存完整的API响应
                this.fullApiResponse = responseData;

                // 处理消息结构数据
                if (responseData.structure) {
                    const structureData = responseData.structure;

                    // 使用返回的info信息
                    if (structureData.info) {
                        this.messageInfo = structureData.info;
                    }

                    // 处理返回的数据结构
                    if (structureData.structures && Array.isArray(structureData.structures)) {
                        this.messageStructures = structureData.structures;
                        this.isGroupMessage = structureData.info?.is_group_message || this.messageStructures.length > 1;
                        this.expandedStates = new Array(this.messageStructures.length).fill(false);
                    }
                }

                // 处理过滤结果
                if (responseData.filters) {
                    this.filterResults = responseData.filters;
                }

                // 设置是否有内容
                this.hasContent = responseData.has_content || false;

                // 默认显示结构标签页
                this.activeTab = 'structure';

            } catch (error) {
                this.errorMessage = error.response?.data?.detail || '分析消息失败';
            } finally {
                this.loading = false;
            }
        },

        toggleExpand(index) {
            this.expandedStates[index] = !this.expandedStates[index];
        },

        formatJSON(obj) {
            return JSON.stringify(obj, null, 2);
        },

        async copyToClipboard(data) {
            const jsonString = JSON.stringify(data, null, 2);

            try {
                // 优先使用现代API
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(jsonString);
                    SimpleUI.showMessage('已复制到剪贴板', 'success');
                } else {
                    // 降级方案：使用 textarea 和 document.execCommand
                    const textarea = document.createElement('textarea');
                    textarea.value = jsonString;
                    textarea.style.position = 'fixed';
                    textarea.style.left = '-999999px';
                    textarea.style.top = '-999999px';
                    document.body.appendChild(textarea);
                    textarea.focus();
                    textarea.select();

                    try {
                        const successful = document.execCommand('copy');
                        if (successful) {
                            SimpleUI.showMessage('已复制到剪贴板', 'success');
                        } else {
                            SimpleUI.showMessage('复制失败，请手动复制', 'warning');
                        }
                    } catch (err) {
                        SimpleUI.showMessage('复制失败: ' + err.message, 'error');
                    } finally {
                        document.body.removeChild(textarea);
                    }
                }
            } catch (error) {
                console.error('复制失败:', error);
                SimpleUI.showMessage('复制失败，请手动复制', 'error');
            }
        },

        formatDate(dateValue) {
            if (!dateValue) return '未知';

            let date;
            if (typeof dateValue === 'number') {
                // Unix时间戳（秒）
                date = new Date(dateValue * 1000);
            } else if (typeof dateValue === 'string') {
                // ISO 8601格式或其他字符串格式
                date = new Date(dateValue);
            } else {
                return '未知';
            }

            // 检查日期是否有效
            if (isNaN(date.getTime())) {
                return dateValue; // 如果解析失败，返回原始值
            }

            return date.toLocaleString('zh-CN');
        },

        truncateText(text, maxLength) {
            if (!text || text.length <= maxLength) return text;
            return text.substring(0, maxLength) + '...';
        },

        getMediaType(media) {
            if (!media) return '无';
            if (media.photo) return '图片';
            if (media.document) {
                const mimeType = media.document.mime_type;
                if (mimeType?.includes('video')) return '视频';
                if (mimeType?.includes('audio')) return '音频';
                return '文档';
            }
            return '其他媒体';
        }
    }
});

// 注册组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
if (window.TrainingNav) {
    app.component('training-nav', window.TrainingNav);
}

// 挂载应用
app.mount('#app');