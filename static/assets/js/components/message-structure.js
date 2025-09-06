// Telegram消息结构查看器 JavaScript

const { createApp } = Vue;

const MessageStructureApp = {
    data() {
        return {
            messageUrl: '',
            loading: false,
            showResults: false,
            messageInfo: null,
            messageStructures: [],
            expandedStates: {},
            errorMessage: '',
            isGroupMessage: false
        }
    },
    
    async mounted() {
        // 初始化发布认证检查
        try {
            const isAuthorized = await authManager.initPageAuth('telegram.sender.auth');
            if (!isAuthorized) {
                return; // 认证失败，页面已跳转
            }
        } catch (error) {
            console.error('发布认证失败:', error);
            window.SimpleUI.showMessage('请先完成Telegram发布认证', 'error');
            setTimeout(() => {
                window.location.href = '/static/telegram-auth.html#sender';
            }, 2000);
            return;
        }

        // 检查URL参数中是否有预填消息链接
        const urlParams = new URLSearchParams(window.location.search);
        const prefilledUrl = urlParams.get('url');
        if (prefilledUrl) {
            this.messageUrl = decodeURIComponent(prefilledUrl);
        }
    },
    
    methods: {
        async fetchMessageStructure() {
            if (!this.messageUrl.trim()) {
                window.SimpleUI.showMessage('请输入消息URL', 'warning');
                return;
            }

            this.loading = true;
            this.errorMessage = '';
            this.showResults = false;
            
            try {
                const response = await axios.post(API.telegram.messageStructure, {
                    message_url: this.messageUrl.trim()
                });

                if (response.data.success) {
                    this.processMessageData(response.data.data);
                    this.showResults = true;
                    window.SimpleUI.showMessage('消息结构获取成功', 'success');
                } else {
                    this.errorMessage = response.data.error || '获取消息结构失败';
                }
            } catch (error) {
                console.error('获取消息结构失败:', error);
                this.errorMessage = this.getErrorMessage(error);
            } finally {
                this.loading = false;
            }
        },

        processMessageData(data) {
            // 处理基本信息
            this.messageInfo = data.info || {};
            
            // 处理消息结构
            if (Array.isArray(data.structures)) {
                this.messageStructures = data.structures;
                this.isGroupMessage = data.structures.length > 1;
            } else {
                this.messageStructures = [data.structures || data];
                this.isGroupMessage = false;
            }

            // 初始化展开状态
            this.expandedStates = {};
            this.messageStructures.forEach((_, index) => {
                this.expandedStates[index] = false;
            });
        },

        toggleExpand(index) {
            this.expandedStates[index] = !this.expandedStates[index];
            this.$forceUpdate();
        },

        formatJSON(obj) {
            return JSON.stringify(obj, null, 2);
        },

        formatDate(dateStr) {
            if (!dateStr) return '未知';
            try {
                const date = new Date(dateStr);
                return date.toLocaleString('zh-CN');
            } catch {
                return dateStr;
            }
        },

        truncateText(text, maxLength) {
            if (!text) return '';
            if (text.length <= maxLength) return text;
            return text.substring(0, maxLength) + '...';
        },

        getMediaType(media) {
            if (!media) return '无媒体';
            if (media._) return media._;
            if (media.type) return media.type;
            if (typeof media === 'string') return media;
            return '未知媒体类型';
        },

        async copyToClipboard(data) {
            try {
                let textToCopy;
                if (typeof data === 'object') {
                    textToCopy = JSON.stringify(data, null, 2);
                } else {
                    textToCopy = data;
                }

                await navigator.clipboard.writeText(textToCopy);
                window.SimpleUI.showMessage('已复制到剪贴板', 'success');
            } catch (error) {
                console.error('复制失败:', error);
                window.SimpleUI.showMessage('复制失败', 'error');
            }
        },

        getErrorMessage(error) {
            if (error.response?.data?.error) {
                return error.response.data.error;
            }
            if (error.response?.status === 401) {
                return '认证失败，请检查Telegram发布权限';
            }
            if (error.response?.status === 404) {
                return '消息不存在或无权访问';
            }
            if (error.response?.status === 403) {
                return '没有权限访问此频道';
            }
            return '网络请求失败，请检查连接';
        },

        clearResults() {
            this.showResults = false;
            this.messageInfo = null;
            this.messageStructures = [];
            this.errorMessage = '';
            this.expandedStates = {};
        }
    }
};

// 创建Vue应用实例
const app = createApp(MessageStructureApp);

// 注册全局组件
app.component('nav-bar', NavBar);

// 挂载应用
app.mount('#app');