// 配置页面 JavaScript 组件

// 确保API配置可用
const API = window.API;

// 检查依赖是否加载

const { createApp } = Vue;

// 消息管理器 - 使用SimpleUI消息系统
const MessageManager = window.SimpleUI ? window.SimpleUI.Message : {
    success: (message) => console.log('SUCCESS:', message),
    error: (message) => console.error('ERROR:', message),
    warning: (message) => console.warn('WARNING:', message),
    info: (message) => console.info('INFO:', message)
};

// 配置应用组件
const ConfigApp = {
    data() {
        return {
            statusMessage: '',
            statusType: 'success',
            configStatus: '在线',
            activeTab: 'channels',
            
            // 频道管理
            channels: [],
            channelSearchFilter: '', // 频道列表搜索过滤
            addChannelTab: 'single', // 添加频道的标签页
            newChannel: {
                name: '',
                title: ''
            },
            batchChannel: {
                channels: '',
                loading: false,
                results: null,
                message: '',
                success: false
            },
            
            // 频道搜索（添加新频道）
            searchForm: {
                query: '',
                results: [],
                loading: false,
                searched: false
            },
            
            
            // 帮助提示标记
            helpMessageShowing: false,
            
            // 统一配置对象 - 使用点分隔键名与后端保持一致
            configs: {
                // 系统设置
                'source.history_limit': '50',
                'target.signature': '',
                'collection.enabled': true,
                'collection.max_media_size_mb': '200',
                // Telegram API 配置
                'telegram.api_id': '',
                'telegram.api_hash': '',
                // 过滤设置
                'filter.enabled': true,
                'filter.tail_filter': true,
                'filter.separator': true,
                'filter.markdown': true,
                'filter.ad_detector': false,
                // 审核设置
                'target.require_approval': true,
                'target.auto_reject_ads': false,
                'target.auto_forward_enabled': false,
                'target.auto_forward_delay': '1800',
                // 转发设置
                'target.channel_link': '',
                'target.channel_id': '',
                // 系统设置
                'scheduler.enabled': true,
                'scheduler.data_cleanup_interval_hours': '24'
            },
            
            // 配置类型映射 - 用于自动类型转换
            configTypes: {
                'source.history_limit': 'integer',
                'target.signature': 'string',
                'collection.enabled': 'boolean',
                'collection.max_media_size_mb': 'integer',
                'telegram.api_id': 'string',
                'telegram.api_hash': 'string',
                'filter.enabled': 'boolean',
                'filter.tail_filter': 'boolean',
                'filter.separator': 'boolean',
                'filter.markdown': 'boolean',
                'filter.ad_detector': 'boolean',
                'target.require_approval': 'boolean',
                'target.auto_reject_ads': 'boolean',
                'target.auto_forward_enabled': 'boolean',
                'target.auto_forward_delay': 'integer',
                'target.channel_link': 'string',
                'target.channel_id': 'string',
                'scheduler.enabled': 'boolean',
                'scheduler.data_cleanup_interval_hours': 'integer'
            }
        }
    },
    
    async mounted() {
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth();
        if (!isAuthorized) {
            return;
        }
        
        // 加载配置数据
        await this.loadConfigData();
        
        // 强制更新视图以确保数据显示
        this.$nextTick(() => {
            this.$forceUpdate();
        });
    },
    
    computed: {
        // 过滤后的频道列表
        filteredChannels() {
            if (!this.channelSearchFilter) {
                return this.channels;
            }
            
            const filter = this.channelSearchFilter.toLowerCase();
            return this.channels.filter(channel => {
                const name = (channel.channel_name || '').toLowerCase();
                const title = (channel.channel_title || '').toLowerCase();
                const channelId = (channel.channel_id || '').toLowerCase();
                // 搜索时同时匹配标题、名称和ID
                return name.includes(filter) || title.includes(filter) || channelId.includes(filter);
            });
        }
    },
    
    methods: {
        // 统一配置类型转换函数
        convertConfigValue(key, value) {
            const type = this.configTypes[key] || 'string';
            
            if (type === 'boolean') {
                if (value === undefined || value === null) return false;
                if (typeof value === 'boolean') return value;
                if (typeof value === 'string') {
                    return value.toLowerCase() === 'true';
                }
                return Boolean(value);
            }
            
            if (type === 'integer') {
                if (value === undefined || value === null) return 0;
                const num = parseInt(value);
                return isNaN(num) ? 0 : num;
            }
            
            // string类型或默认
            return value === undefined || value === null ? '' : String(value);
        },
        
        // 工具函数：解析boolean值 (保持向后兼容)
        parseBooleanValue(value, defaultValue = false) {
            if (value === undefined || value === null) {
                return defaultValue;
            }
            if (typeof value === 'boolean') {
                return value;
            }
            if (typeof value === 'string') {
                // 修复：正确处理字符串形式的布尔值
                const lowerValue = value.toLowerCase();
                if (lowerValue === 'false' || lowerValue === '0' || lowerValue === '') {
                    return false;
                }
                if (lowerValue === 'true' || lowerValue === '1') {
                    return true;
                }
                // 其他非空字符串视为true
                return value !== '';
            }
            return Boolean(value);
        },

        // 时间格式化方法
        formatLastSyncTime(lastSyncTime) {
            if (window.TimeUtils) {
                return window.TimeUtils.formatTimeAgo(lastSyncTime);
            }
            // 降级处理
            return lastSyncTime ? '有同步记录' : '未同步';
        },

        getLastSyncClass(lastSyncTime) {
            if (window.TimeUtils) {
                return window.TimeUtils.getTimeAgoClass(lastSyncTime);
            }
            // 降级处理
            return lastSyncTime ? 'recent' : 'never-synced';
        },

        // 统一配置加载方法
        async loadConfigs() {
            try {
                const response = await axios.get(API.admin.config);
                if (response.data) {
                    const serverConfigs = response.data;
                    
                    // 使用类型转换加载所有配置
                    for (const [key, value] of Object.entries(serverConfigs)) {
                        if (this.configs.hasOwnProperty(key)) {
                            this.configs[key] = this.convertConfigValue(key, value);
                        }
                    }
                }
            } catch (error) {
                console.error('加载配置失败:', error);
                MessageManager.error('加载配置失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 统一配置保存方法 - 支持单个或批量保存
        async saveConfigs(keys = null) {
            try {
                let configData = {};
                
                if (keys === null) {
                    // 保存所有配置
                    configData = { ...this.configs };
                } else if (Array.isArray(keys)) {
                    // 保存指定的多个配置
                    keys.forEach(key => {
                        if (this.configs.hasOwnProperty(key)) {
                            configData[key] = this.configs[key];
                        }
                    });
                } else if (typeof keys === 'string') {
                    // 保存单个配置
                    if (this.configs.hasOwnProperty(keys)) {
                        configData[keys] = this.configs[keys];
                    }
                } else {
                    throw new Error('keys参数类型错误');
                }
                
                // 确保数值类型正确转换
                for (const [key, value] of Object.entries(configData)) {
                    const type = this.configTypes[key];
                    if (type === 'integer' && typeof value === 'string') {
                        configData[key] = String(parseInt(value) || 0);
                    } else if (type === 'string' && typeof value !== 'string') {
                        configData[key] = String(value);
                    }
                }
                
                const response = await axios.post(API.admin.configBatch, configData);
                
                if (response.data.success) {
                    MessageManager.success('配置保存成功');
                    // 重新加载配置以确保同步
                    await this.loadConfigs();
                } else {
                    throw new Error(response.data.message || '配置保存失败');
                }
                
            } catch (error) {
                console.error('保存配置失败:', error);
                MessageManager.error('配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async loadConfigData() {
            try {
                // 加载频道列表
                await this.loadChannels();
                
                // 加载所有配置
                await this.loadConfigs();
                
            } catch (error) {
                MessageManager.error('加载配置数据失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async loadChannels() {
            try {
                const response = await axios.get(API.channels.list);
                if (response.data.success) {
                    this.channels = response.data.channels;
                }
            } catch (error) {
                console.error('加载频道列表失败:', error);
                this.channels = [];
            }
        },
        
        
        
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
        
        async removeChannel(channelId) {
            try {
                
                const response = await axios.delete(API.channels.delete(channelId));
                
                
                if (response.data.success) {
                    MessageManager.success('频道删除成功');
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道删除失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                MessageManager.error('频道删除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resolveChannelIds() {
            try {

                const response = await axios.post(API.channels.resolveAll);
                
                if (response.data.success) {
                    MessageManager.success(`频道ID解析完成：${response.data.message}`);
                    await this.loadChannels(); // 重新加载频道列表
                } else {
                    MessageManager.error('频道ID解析失败');
                }
            } catch (error) {
                MessageManager.error('频道ID解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 操作完成
            }
        },
        
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
                MessageManager.error('批量添加频道失败: ' + (error.response?.data?.detail || error.message));
                this.batchChannel.results = null;
            } finally {
                this.batchChannel.loading = false;
            }
        },
        
        async resolveChannelId(channelName) {
            try {
                const response = await axios.post(API.channels.resolve, {
                    channel_input: channelName
                });
                
                if (response.data.success) {
                    MessageManager.success(`频道 ${channelName} ID解析成功: ${response.data.resolved_id}`);
                    await this.loadChannels(); // 重新加载频道列表
                } else {
                    MessageManager.error(`频道 ${channelName} ID解析失败: ${response.data.message}`);
                }
            } catch (error) {
                MessageManager.error('频道ID解析失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        
        
        // 保存转发配置 - 使用统一方法
        async saveForwardingConfig() {
            try {
                // 调用专门的转发配置API，会自动解析频道/群组ID
                const response = await axios.post(API.admin.configForwarding, {
                    target_channel: this.configs['target.channel_link'],
                    target_channel_id: this.configs['target.channel_id'],  // 传递前端的ID值
                    auto_forward_enabled: this.configs['target.auto_forward_enabled'],
                    auto_forward_delay: Number(this.configs['target.auto_forward_delay']) || 1800,
                    auto_reject_ads: this.configs['target.auto_reject_ads'],
                    require_approval: this.configs['target.require_approval']
                });

                if (response.data.success) {
                    // 更新显示的ID值
                    if (response.data.target_channel_id) {
                        this.configs['target.channel_id'] = response.data.target_channel_id;
                    }

                    MessageManager.success(response.data.message || '转发配置保存成功');
                } else {
                    throw new Error(response.data.message || '转发配置保存失败');
                }

            } catch (error) {
                console.error('保存配置错误:', error);
                MessageManager.error('转发配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 保存系统配置 - 使用统一方法
        async saveSystemConfig() {
            try {
                // 保存所有系统相关配置
                const systemKeys = [
                    'source.history_limit',
                    'target.signature',
                    'collection.enabled',
                    'collection.max_media_size_mb',
                    'telegram.api_id',
                    'telegram.api_hash',
                    'filter.enabled',
                    'target.require_approval',
                    'scheduler.enabled',
                    'scheduler.data_cleanup_interval_hours'
                ];
                
                await this.saveConfigs(systemKeys);
                
            } catch (error) {
                console.error('保存系统配置失败:', error);
                MessageManager.error('系统配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resetSystemConfig() {
            this.systemConfig = {
                history_message_limit: 50,
                signature: '',
                collection_enabled: true,
                // 过滤设置
                filter_enabled: true,
                // 审核设置
                require_approval: true,
                // 转发设置
                auto_forward_enabled: false,
                'target.channel_link': '',
                'target.channel_id': '',
                'target.auto_forward_delay': 1800,
                // 系统设置
                scheduler_enabled: true,
                data_cleanup_interval_hours: 24
                // 调度和单消息删除默认启用
            };
            MessageManager.success('系统配置已重置为默认值');
        },
        
        
        
        // 保存过滤器配置 - 使用统一方法
        async saveFilterSettings() {
            try {
                // 保存所有过滤器相关配置
                const filterKeys = [
                    'filter.enabled',
                    'filter.tail_filter',
                    'filter.separator',
                    'filter.markdown',
                    'filter.ad_detector'
                ];
                
                await this.saveConfigs(filterKeys);

                // 直接显示成功消息，配置已保存并会自动生效
                MessageManager.success('过滤器配置已保存，将在下次处理消息时生效');
                
            } catch (error) {
                console.error('保存过滤器配置失败:', error);
                MessageManager.error('过滤器配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resetFilterSettings() {
            // 重置过滤器配置到默认值
            this.configs['filter.enabled'] = true;
            this.configs['filter.tail_filter'] = true;
            this.configs['filter.separator'] = true;
            this.configs['filter.markdown'] = true;
            this.configs['filter.ad_detector'] = false;
            
            MessageManager.success('过滤器配置已重置为默认值');
},
        
        showReviewGroupHelp() {
            // 如果已经有提示在显示，不再弹出新的
            if (this.helpMessageShowing) {
                return;
            }
            
            this.helpMessageShowing = true;
            MessageManager.info(`
                <div style="text-align: left; line-height: 1.6;">
                    <strong>审核群设置帮助：</strong><br>
                    1. <strong>群链接：</strong> https://t.me/+Z_jrvX6YLLwxOTE1 (推荐)<br>
                    2. <strong>群ID格式：</strong> -1001234567890 (以-100开头的负数)<br>
                    3. <strong>群用户名：</strong> @review_group 或 review_group<br>
                    4. <strong>获取群ID方法：</strong><br>
                    &nbsp;&nbsp;• 转发群内任意消息给 @userinfobot<br>
                    &nbsp;&nbsp;• 邀请 @RawDataBot 到群内查看<br>
                    &nbsp;&nbsp;• 使用 @chatIDrobot 获取<br>
                    5. <strong>智能解析：</strong> 输入群链接后系统会自动解析并缓存真实ID<br>
                    6. <strong>注意：</strong> 机器人必须是群管理员才能发送消息
                </div>
                `, {
                dangerouslyUseHTMLString: true,
                duration: 12000,
                showClose: true,
                onClose: () => {
                    this.helpMessageShowing = false;
                }
            });
            
            // 12秒后自动重置标记
            setTimeout(() => {
                this.helpMessageShowing = false;
            }, 12000);
        },
        
        
        // 搜索频道
        async searchChannels() {
            if (!this.searchForm.query) {
                MessageManager.warning('请输入搜索关键词');
                return;
            }
            
            this.searchForm.loading = true;
            this.searchForm.searched = false;
            
            try {
                const response = await axios.get(API.admin.searchChannels, {
                    params: { query: this.searchForm.query }
                });
                
                if (response.data.success) {
                    this.searchForm.results = response.data.channels || [];
                    this.searchForm.searched = true;
                    
                    if (this.searchForm.results.length === 0) {
                        MessageManager.info('没有找到相关频道');
                    } else {
                        MessageManager.success(`找到 ${this.searchForm.results.length} 个频道`);
                    }
                } else {
                    MessageManager.error(response.data.message || '搜索失败');
                }
            } catch (error) {
                MessageManager.error('搜索频道失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.searchForm.loading = false;
            }
        },
        
        
        // Telegram API 配置验证
        validateApiId() {
            const apiId = this.systemConfig['telegram.api_id'];
            if (apiId && !/^\d+$/.test(apiId)) {
                MessageManager.warning('API ID 应该是纯数字');
                return false;
            }
            return true;
        },
        
        validateApiHash() {
            const apiHash = this.systemConfig['telegram.api_hash'];
            if (apiHash && apiHash.length !== 32) {
                MessageManager.warning('API Hash 应该是32位字符串');
                return false;
            }
            return true;
        }
    }
};

// 等待 DOM 加载完成
document.addEventListener('DOMContentLoaded', function() {
    
    // 创建应用实例

    try {
        const app = createApp(ConfigApp);
        
        // 注册导航栏组件
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }

        // 添加错误处理
        app.config.errorHandler = (err, vm, info) => {
        };

        // 检查目标元素是否存在
        const targetElement = document.getElementById('app');
        if (!targetElement) {
            return;
        }

        // 挂载应用
        app.mount('#app');
    } catch (error) {
        document.body.innerHTML = '<div style="color: red; padding: 20px;">Vue 应用挂载失败: ' + error.message + '</div>';
    }
}); 