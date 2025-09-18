// Telegram消息结构查看器页面逻辑
const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            messageUrl: '',
            loading: false,
            errorMessage: '',
            messageData: null,
            messageInfo: null,
            messageStructures: [],
            expandedStates: [],
            isGroupMessage: false
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
                } else {
                    // 兼容旧格式
                    this.messageStructures = [responseData];
                    this.isGroupMessage = false;
                    this.expandedStates = [false];

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
                await navigator.clipboard.writeText(jsonString);
                SimpleUI.showMessage('已复制到剪贴板', 'success');
            } catch (error) {
                console.error('复制失败:', error);
                SimpleUI.showMessage('复制失败，请手动选择复制', 'error');
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