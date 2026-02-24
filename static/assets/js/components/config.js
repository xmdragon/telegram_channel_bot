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
            activeTab: 'forwarding',
            
            
            
            // 帮助提示标记
            helpMessageShowing: false,
            
            // 统一配置对象 - 使用点分隔键名与后端保持一致
            configs: {
                // 采集设置
                'collection.enabled': true,
                'collection.max_media_size_mb': '200',
                'collection.max_messages_per_batch': '10',
                'source.history_limit': '50',
                'collection.video_only': false,
                'collection.comment_keywords': [],
                'collection.comment_keywords_text': '',

                // 去重检测
                'duplicate_detection.enabled': true,
                'duplicate_detection.content_threshold': '0.86',
                'duplicate_detection.suspected_threshold': '0.82',
                'duplicate_detection.confirmed_threshold': '0.95',
                'duplicate_detection.simhash_threshold': '4',
                'duplicate_detection.media_threshold': '0.90',
                'duplicate_detection.retention_days': '30',
                'duplicate_detection.auto_adjust': true,
                'duplicate_detection.ttl_hours': '24',
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
                'target.auto_forward_delay': '300',
                // 转发设置
                'target.channel_link': '',
                'target.channel_id': '',
                // 系统设置
                'scheduler.data_cleanup_interval_hours': '24',
                'system.log_level': 'WARNING',

                // 性能优化
                'telegram.rate_limit_text_interval': '5',
                'telegram.rate_limit_media_interval': '12',
                'telegram.rate_limit_safety_factor': '1.5',
                'telegram.max_retry_attempts': '3',
                'telegram.flood_wait_buffer_min': '1',
                'telegram.flood_wait_buffer_max': '5',
                'processor.timeout_seconds': '120',
                'processor.send_message_timeout': '120',

                // 消息长度限制
                'telegram.max_message_length': '1000',
                'telegram.max_message_length_vip': '2000',

                // 其他
                'target.signature': ''
            },
            
            // 配置类型映射 - 用于自动类型转换
            configTypes: {
                // 采集设置
                'collection.enabled': 'boolean',
                'collection.max_media_size_mb': 'integer',
                'collection.max_messages_per_batch': 'integer',
                'source.history_limit': 'integer',
                'collection.video_only': 'boolean',
                'collection.comment_keywords': 'json',

                // 去重检测
                'duplicate_detection.enabled': 'boolean',
                'duplicate_detection.content_threshold': 'float',
                'duplicate_detection.suspected_threshold': 'float',
                'duplicate_detection.confirmed_threshold': 'float',
                'duplicate_detection.simhash_threshold': 'integer',
                'duplicate_detection.media_threshold': 'float',
                'duplicate_detection.retention_days': 'integer',
                'duplicate_detection.auto_adjust': 'boolean',
                'duplicate_detection.ttl_hours': 'integer',
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
                'scheduler.data_cleanup_interval_hours': 'integer',
                'system.log_level': 'string',

                // 性能优化
                'telegram.rate_limit_text_interval': 'float',
                'telegram.rate_limit_media_interval': 'float',
                'telegram.rate_limit_safety_factor': 'float',
                'telegram.max_retry_attempts': 'integer',
                'telegram.flood_wait_buffer_min': 'integer',
                'telegram.flood_wait_buffer_max': 'integer',
                'telegram.max_message_length': 'integer',
                'telegram.max_message_length_vip': 'integer',
                'processor.timeout_seconds': 'integer',
                'processor.send_message_timeout': 'integer',

                'target.signature': 'string'
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
        // 暂无计算属性
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

            if (type === 'float') {
                if (value === undefined || value === null) return 0;
                const num = parseFloat(value);
                return isNaN(num) ? 0 : num;
            }

            if (type === 'json') {
                if (value === undefined || value === null) return [];
                if (typeof value === 'string') {
                    try { return JSON.parse(value); } catch (e) { return []; }
                }
                return value;
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
                        // 直接加载所有配置，不限制必须预定义
                        this.configs[key] = this.convertConfigValue(key, value);
                    }
                    // 评论区关键词：JSON数组转换为换行文本
                    const kw = this.configs['collection.comment_keywords'];
                    this.configs['collection.comment_keywords_text'] = Array.isArray(kw) ? kw.join('\n') : '';
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
                    for (const [key, value] of Object.entries(this.configs)) {
                        configData[key] = value;
                    }
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
                // 加载所有配置
                await this.loadConfigs();

            } catch (error) {
                MessageManager.error('加载配置数据失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        

        // 统一保存所有配置
        async saveAllConfigs() {
            try {
                // 特殊处理：转发配置需要使用专门的API来解析频道ID
                if (this.activeTab === 'forwarding') {
                    // 先调用转发配置API获取解析后的频道ID
                    const forwardResponse = await axios.post(API.admin.configForwarding, {
                        target_channel: this.configs['target.channel_link'],
                        target_channel_id: this.configs['target.channel_id'],
                        auto_forward_enabled: this.configs['target.auto_forward_enabled'],
                        auto_forward_delay: Number(this.configs['target.auto_forward_delay']) || 1800,
                        auto_reject_ads: this.configs['target.auto_reject_ads'],
                        require_approval: this.configs['target.require_approval']
                    });

                    if (forwardResponse.data.success && forwardResponse.data.target_channel_id) {
                        this.configs['target.channel_id'] = forwardResponse.data.target_channel_id;
                    }
                }

                // 评论区关键词：换行文本转为JSON数组
                this.configs['collection.comment_keywords'] = (this.configs['collection.comment_keywords_text'] || '')
                    .split('\n').map(s => s.trim()).filter(s => s);

                // 准备所有配置数据，进行类型转换
                const configData = {};
                for (const [key, value] of Object.entries(this.configs)) {
                    if (key === 'collection.comment_keywords_text') continue;
                    configData[key] = this.convertConfigValue(key, value);
                }

                // 调用批量保存API
                const response = await axios.post(API.admin.configBatch, configData);

                if (response.data.success) {
                    MessageManager.success('所有配置已保存成功');
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