// 频道管理页面 JavaScript

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

// 消息管理器
const MessageManager = window.SimpleUI ? window.SimpleUI.Message : {
    success: (message) => console.log('SUCCESS:', message),
    error: (message) => console.error('ERROR:', message),
    warning: (message) => console.warn('WARNING:', message),
    info: (message) => console.info('INFO:', message)
};

// 频道管理应用
const ChannelApp = {
    data() {
        return {
            // 频道列表
            channels: [],
            channelSearchFilter: '', // 频道搜索过滤

            // 添加频道相关
            addChannelTab: 'single', // 单个或批量添加
            newChannel: {
                name: '',
                title: ''
            },

            // 批量添加相关
            batchChannel: {
                channels: '',
                loading: false,
                results: null,
                message: '',
                success: false
            },

            // 排序相关
            sortField: 'last_sync_time', // 默认按最后更新时间排序
            sortOrder: 'desc', // 默认降序

            // 批量选择
            selectedChannels: []
        }
    },

    computed: {
        // 过滤后的频道列表
        filteredChannels() {
            if (!this.channelSearchFilter) {
                return this.channels;
            }
            const filter = this.channelSearchFilter.toLowerCase();
            return this.channels.filter(channel => {
                const title = (channel.channel_title || '').toLowerCase();
                const name = (channel.channel_name || '').toLowerCase();
                const id = (channel.channel_id || '').toLowerCase();
                return title.includes(filter) || name.includes(filter) || id.includes(filter);
            });
        },

        // 是否全选
        isAllSelected() {
            return this.sortedChannels.length > 0 &&
                   this.sortedChannels.every(ch => this.selectedChannels.includes(ch.id));
        },

        // 排序后的频道列表
        sortedChannels() {
            const channels = [...this.filteredChannels];
            const field = this.sortField;
            const order = this.sortOrder;

            return channels.sort((a, b) => {
                let aVal = a[field];
                let bVal = b[field];

                // 处理空值
                if (aVal === null || aVal === undefined || aVal === '') {
                    return order === 'asc' ? 1 : -1;
                }
                if (bVal === null || bVal === undefined || bVal === '') {
                    return order === 'asc' ? -1 : 1;
                }

                // 字符串比较
                if (typeof aVal === 'string' && typeof bVal === 'string') {
                    aVal = aVal.toLowerCase();
                    bVal = bVal.toLowerCase();
                }

                // 比较
                if (aVal < bVal) {
                    return order === 'asc' ? -1 : 1;
                }
                if (aVal > bVal) {
                    return order === 'asc' ? 1 : -1;
                }
                return 0;
            });
        }
    },

    methods: {
        // 加载频道列表
        async loadChannels() {
            try {
                const response = await axios.get(API.channels.list);
                if (response.data.success) {
                    this.channels = response.data.channels;
                    this.selectedChannels = [];
                }
            } catch (error) {
                console.error('加载频道列表失败:', error);
                this.channels = [];
                MessageManager.error('加载频道列表失败: ' + (error.response?.data?.detail || error.message));
            }
        },

        // 添加单个频道
        async addChannel() {
            if (!this.newChannel.name) {
                MessageManager.warning('请输入频道名称');
                return;
            }

            try {
                // 处理频道名称，统一格式
                let channelName = this.newChannel.name.trim();
                if (!channelName.startsWith('@')) {
                    channelName = '@' + channelName;
                }

                const response = await axios.post(API.channels.add, {
                    channel_id: "",  // 自动解析
                    channel_name: channelName,
                    channel_title: ""  // 自动解析
                });

                if (response.data.success) {
                    const channel = response.data.channel;
                    MessageManager.success(`频道添加成功: ${channel.channel_title || channel.channel_name}`);
                    this.newChannel = { name: '', title: '' };
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道添加失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                MessageManager.error('频道添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },

        // 批量添加频道
        async batchAddChannels() {
            if (!this.batchChannel.channels.trim()) {
                MessageManager.warning('请输入要添加的频道列表');
                return;
            }

            this.batchChannel.loading = true;
            this.batchChannel.results = null;

            try {
                const response = await axios.post(API.channels.batchAdd, {
                    channels: this.batchChannel.channels
                });

                if (response.data) {
                    this.batchChannel.results = response.data.results;
                    this.batchChannel.message = response.data.message;
                    this.batchChannel.success = response.data.success;

                    if (response.data.success) {
                        // 如果有成功添加的频道，重新加载频道列表
                        if (response.data.results?.added?.length > 0) {
                            await this.loadChannels();

                            // 清空输入框
                            setTimeout(() => {
                                this.batchChannel.channels = '';
                            }, 2000);
                        }
                    } else {
                        MessageManager.error(response.data.message);
                    }
                }
            } catch (error) {
                MessageManager.error('批量添加失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.batchChannel.loading = false;
            }
        },

        // 全选/取消全选
        toggleSelectAll(event) {
            if (event.target.checked) {
                this.selectedChannels = this.sortedChannels.map(ch => ch.id);
            } else {
                this.selectedChannels = [];
            }
        },

        // 批量删除频道
        async batchRemoveChannels() {
            const count = this.selectedChannels.length;
            try {
                const confirmed = await SimpleUI.confirm(
                    `确定要删除选中的 ${count} 个频道吗？`, '批量删除确认'
                );
                if (!confirmed) return;

                let successCount = 0;
                let failCount = 0;
                for (const channelId of [...this.selectedChannels]) {
                    try {
                        const response = await axios.delete(API.channels.delete(channelId));
                        if (response.data.success) successCount++;
                        else failCount++;
                    } catch {
                        failCount++;
                    }
                }

                this.selectedChannels = [];
                await this.loadChannels();

                if (failCount === 0) {
                    MessageManager.success(`成功删除 ${successCount} 个频道`);
                } else {
                    MessageManager.warning(`删除完成：成功 ${successCount}，失败 ${failCount}`);
                }
            } catch (error) {
                if (error !== 'cancel') {
                    MessageManager.error('批量删除失败: ' + error.message);
                }
            }
        },

        // 删除频道
        async removeChannel(channelId) {
            try {
                const confirmed = await SimpleUI.confirm('确定要删除这个频道吗？', '删除确认');
                if (!confirmed) return;

                const response = await axios.delete(API.channels.delete(channelId));

                if (response.data.success) {
                    MessageManager.success('频道删除成功');
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道删除失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                if (error !== 'cancel') {
                    MessageManager.error('频道删除失败: ' + (error.response?.data?.detail || error.message));
                }
            }
        },

        // 解析所有频道ID
        async resolveChannelIds() {
            try {
                const response = await axios.post(API.channels.resolveAll);

                if (response.data.success) {
                    MessageManager.success(`频道ID解析完成：${response.data.message}`);
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道ID解析失败');
                }
            } catch (error) {
                MessageManager.error('频道ID解析失败: ' + (error.response?.data?.detail || error.message));
            }
        },

        // 解析单个频道ID
        async resolveChannelId(channelName) {
            try {
                const response = await axios.post(API.channels.resolve, {
                    channel_input: channelName
                });

                if (response.data.success) {
                    MessageManager.success(`频道 ${channelName} ID解析成功: ${response.data.resolved_id}`);
                    await this.loadChannels();
                } else {
                    MessageManager.error(`频道 ${channelName} ID解析失败: ${response.data.message}`);
                }
            } catch (error) {
                MessageManager.error('频道ID解析失败: ' + (error.response?.data?.detail || error.message));
            }
        },

        // 排序频道列表
        sortChannels(field) {
            if (this.sortField === field) {
                // 如果点击同一个字段，切换排序顺序
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                // 如果点击不同字段，设置新字段并默认降序
                this.sortField = field;
                this.sortOrder = field === 'channel_title' || field === 'channel_name' ? 'asc' : 'desc';
            }
        },

        // 获取排序图标类
        getSortIcon(field) {
            if (this.sortField === field) {
                return this.sortOrder === 'asc' ? 'sort-asc' : 'sort-desc';
            }
            return 'sort-none';
        },

        // 格式化同步时间
        formatSyncTime(time) {
            if (!time) {
                return '从未同步';
            }

            try {
                const date = new Date(time);
                const now = new Date();
                const diff = now - date;

                // 小于1分钟
                if (diff < 60000) {
                    return '刚刚';
                }
                // 小于1小时
                if (diff < 3600000) {
                    const minutes = Math.floor(diff / 60000);
                    return `${minutes}分钟前`;
                }
                // 小于1天
                if (diff < 86400000) {
                    const hours = Math.floor(diff / 3600000);
                    return `${hours}小时前`;
                }
                // 小于7天
                if (diff < 604800000) {
                    const days = Math.floor(diff / 86400000);
                    return `${days}天前`;
                }

                // 超过7天，显示日期
                const month = (date.getMonth() + 1).toString().padStart(2, '0');
                const day = date.getDate().toString().padStart(2, '0');
                const hour = date.getHours().toString().padStart(2, '0');
                const minute = date.getMinutes().toString().padStart(2, '0');
                return `${month}-${day} ${hour}:${minute}`;
            } catch (error) {
                return '时间格式错误';
            }
        }
    },

    async mounted() {
        try {
            // 初始化权限检查
            const isAuthorized = await authManager.initPageAuth();
            if (!isAuthorized) {
                return;
            }

            // 加载频道列表
            await this.loadChannels();
        } catch (error) {
            MessageManager.error('初始化失败: ' + (error.response?.data?.detail || error.message));
        }
    }
};

// 创建Vue应用
document.addEventListener('DOMContentLoaded', () => {
    const app = createApp(ChannelApp);

    // 注册导航栏组件
    if (window.NavBar) {
        app.component('nav-bar', window.NavBar);
    }

    // 挂载应用
    app.mount('#app');
});