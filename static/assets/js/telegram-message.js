// Telegram消息结构查看器页面逻辑
const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            messageUrl: '',
            loading: false,
            loadingFilters: false,
            errorMessage: '',
            messageData: null,
            messageInfo: null,
            messageStructures: [],
            expandedStates: [],
            isGroupMessage: false,
            messageContent: '',  // 存储消息内容用于过滤测试
            filterResults: null  // 过滤测试结果
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
        async fetchMessageStructure() {
            // 清空之前的错误消息
            this.errorMessage = '';

            // 检查URL是否为空
            if (!this.messageUrl || !this.messageUrl.trim()) {
                this.errorMessage = '消息URL不能为空';
                // 清空之前的结果
                this.messageData = null;
                this.messageInfo = null;
                this.messageStructures = [];
                return;
            }

            const trimmedUrl = this.messageUrl.trim();

            this.loading = true;
            this.messageData = null;
            this.messageInfo = null;
            this.messageStructures = [];

            try {
                const response = await axios.post(API.telegram.messageStructure, {
                    message_url: trimmedUrl
                });

                // 处理包装的响应格式
                const responseData = response.data.success ? response.data.data : response.data;
                this.messageData = responseData;

                // 使用返回的info信息
                if (responseData.info) {
                    this.messageInfo = responseData.info;
                }

                // 处理返回的数据结构
                if (responseData.structures && Array.isArray(responseData.structures)) {
                    this.messageStructures = responseData.structures;
                    this.isGroupMessage = responseData.info?.is_group_message || this.messageStructures.length > 1;
                    this.expandedStates = new Array(this.messageStructures.length).fill(false);

                    // 提取消息内容用于过滤测试
                    if (this.messageStructures.length > 0) {
                        // 如果是组合消息，合并所有消息内容
                        this.messageContent = this.messageStructures
                            .map(s => s.message || '')
                            .filter(msg => msg)
                            .join('\n\n');
                    }
                } else {
                    // 兼容旧格式
                    this.messageStructures = [responseData];
                    this.isGroupMessage = false;
                    this.expandedStates = [false];

                    // 提取消息内容
                    this.messageContent = responseData.message || '';

                    // 如果没有info，从第一条消息构建
                    if (!this.messageInfo) {
                        this.messageInfo = {
                            message_id: responseData.id,
                            channel_name: responseData.channel_name || '未知频道',
                            channel_id: responseData.peer_id?.channel_id || '未知',
                            date: responseData.date,
                            views: responseData.views,
                            forwards: responseData.forwards
                        };
                    }
                }
            } catch (error) {
                this.errorMessage = error.response?.data?.detail || '获取消息结构失败';
            } finally {
                this.loading = false;
            }
        },

        toggleExpand(index) {
            this.expandedStates[index] = !this.expandedStates[index];
        },

        async copyToClipboard(data) {
            try {
                const jsonString = JSON.stringify(data, null, 2);

                // 尝试使用现代 clipboard API (需要HTTPS或localhost)
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(jsonString);
                    SimpleUI.showMessage('已复制到剪贴板', 'success');
                } else {
                    // 降级方案：使用传统方法
                    const textArea = document.createElement('textarea');
                    textArea.value = jsonString;
                    textArea.style.position = 'fixed';
                    textArea.style.left = '-999999px';
                    textArea.style.top = '-999999px';
                    document.body.appendChild(textArea);
                    textArea.focus();
                    textArea.select();

                    try {
                        const successful = document.execCommand('copy');
                        if (successful) {
                            SimpleUI.showMessage('已复制到剪贴板', 'success');
                        } else {
                            throw new Error('Copy command failed');
                        }
                    } finally {
                        document.body.removeChild(textArea);
                    }
                }
            } catch (error) {
                console.error('复制失败:', error);
                // 提供手动复制的选项
                const modal = document.createElement('div');
                modal.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:white;padding:20px;border:1px solid #ccc;border-radius:5px;z-index:10000;max-width:80%;max-height:80%;overflow:auto;';
                modal.innerHTML = `
                    <h3>请手动复制以下内容：</h3>
                    <textarea style="width:100%;min-width:400px;height:300px;margin:10px 0;" readonly>${JSON.stringify(data, null, 2)}</textarea>
                    <button onclick="this.parentElement.remove()" style="padding:5px 15px;">关闭</button>
                `;
                document.body.appendChild(modal);
                modal.querySelector('textarea').select();
            }
        },

        formatJSON(obj) {
            return JSON.stringify(obj, null, 2);
        },

        formatDate(dateValue) {
            if (!dateValue) return '未知';

            // 处理不同的日期格式
            let date;
            if (typeof dateValue === 'number') {
                // Unix时间戳
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
        },

        // 测试过滤器
        async testFilters() {
            if (!this.messageContent) {
                this.errorMessage = '请先查询消息结构获取内容';
                return;
            }

            this.loadingFilters = true;
            this.filterResults = null;
            this.errorMessage = '';

            try {
                const response = await axios.post(API.telegram.testFilters, {
                    content: this.messageContent
                });

                if (response.data.success) {
                    this.filterResults = response.data.data;
                } else {
                    this.errorMessage = response.data.error || '测试过滤失败';
                }
            } catch (error) {
                this.errorMessage = error.response?.data?.detail || '测试过滤失败';
            } finally {
                this.loadingFilters = false;
            }
        },

        // 关闭过滤结果
        closeFilterResults() {
            this.filterResults = null;
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