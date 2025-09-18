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
            if (!this.messageUrl.trim()) {
                this.errorMessage = '请输入有效的Telegram消息链接';
                return;
            }

            this.loading = true;
            this.errorMessage = '';
            this.messageData = null;
            this.messageInfo = null;
            this.messageStructures = [];

            try {
                const response = await axios.post(API.telegram.messageStructure, {
                    url: this.messageUrl.trim()
                });

                this.messageData = response.data;

                // 处理返回的数据结构
                if (response.data.structures && Array.isArray(response.data.structures)) {
                    this.messageStructures = response.data.structures;
                    this.isGroupMessage = this.messageStructures.length > 1;
                    this.expandedStates = new Array(this.messageStructures.length).fill(false);

                    // 设置消息基础信息（使用第一条消息的信息）
                    if (this.messageStructures.length > 0) {
                        const firstMessage = this.messageStructures[0];
                        this.messageInfo = {
                            message_id: firstMessage.id,
                            channel_name: response.data.channel_name || '未知频道',
                            channel_id: firstMessage.peer_id?.channel_id || '未知',
                            date: firstMessage.date,
                            views: firstMessage.views,
                            forwards: firstMessage.forwards
                        };
                    }
                } else {
                    // 单条消息或旧格式
                    this.messageStructures = [response.data];
                    this.isGroupMessage = false;
                    this.expandedStates = [false];

                    this.messageInfo = {
                        message_id: response.data.id,
                        channel_name: response.data.channel_name || '未知频道',
                        channel_id: response.data.peer_id?.channel_id || '未知',
                        date: response.data.date,
                        views: response.data.views,
                        forwards: response.data.forwards
                    };
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

        formatDate(timestamp) {
            if (!timestamp) return '未知';
            const date = new Date(timestamp * 1000);
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