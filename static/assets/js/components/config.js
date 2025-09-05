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
            
            // 转发设置
            forwardingConfig: {
                enabled: false,
                target_channel: '',
                review_group: '',
                target_channel_id: '',
                review_group_id: '',
                delay: 0,
                auto_reject_ads: false,
                auto_forward_after_collect: false
            },
            
            // 帮助提示标记
            helpMessageShowing: false,
            
            // 系统设置
            systemConfig: {
                history_message_limit: 50,
                signature: '',
                collection_enabled: true,
                // Telegram API 配置
                'telegram.api_id': '',
                'telegram.api_hash': '',
                // 过滤设置
                filter_enabled: true,
                // 审核设置
                require_approval: true,
                // 转发设置
                auto_forward_enabled: false,
                'target.channel_link': '',
                'target.channel_id': '',
                'review.group_link': '',
                'review.group_id': '',
                'review.auto_forward_delay': 1800,
                // 系统设置
                scheduler_enabled: true,
                data_cleanup_interval_hours: 24
                // 调度和单消息删除默认启用
            },
            
            // 过滤设置 - 系统自动管理
            filterConfig: {},
            
            // 过滤器管理设置 - 修复字段名一致性
            filterSettings: {
                // 内容清理过滤器
                tail_filter: true,        // 尾部过滤器
                footer_promo: true,       // 尾部推广链接过滤器
                markdown: true,           // Markdown格式清理
                promo_vector: true,       // 推广内容向量过滤
                
                // 内容检测过滤器
                duplicate: true,          // 去重检测
                ad_detector: true         // 广告检测
            }
        }
    },
    
    async mounted() {
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth('config.view');
        if (!isAuthorized) {
            return;
        }
        
        this.loadConfigData();
    },
    
    computed: {
        // 过滤后的频道列表
        filteredChannels() {
            if (!this.channelSearchFilter) {
                return this.channels;
            }
            
            const filter = this.channelSearchFilter.toLowerCase();
            return this.channels.filter(channel => {
                const name = (channel.name || '').toLowerCase();
                const title = (channel.title || '').toLowerCase();
                const channelId = (channel.channel_id || '').toLowerCase();
                // 搜索时同时匹配标题、名称和ID
                return name.includes(filter) || title.includes(filter) || channelId.includes(filter);
            });
        }
    },
    
    methods: {
        // 工具函数：解析boolean值
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
        
        async loadConfigData() {
            try {
                // 加载频道列表
                await this.loadChannels();
                
                // 加载转发配置
                await this.loadForwardingConfig();
                
                // 加载系统配置
                await this.loadSystemConfig();
                
                // 加载过滤配置
                await this.loadFilterConfig();
                
                // 加载过滤器管理配置
                await this.loadFilterSettings();
                
            } catch (error) {
                MessageManager.error('加载配置数据失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async loadChannels() {
            try {
                const response = await axios.get(API.admin.channels);
                if (response.data.success) {
                    this.channels = response.data.channels;
                }
            } catch (error) {
                // 使用模拟数据
                this.channels = [
                    { id: 1, name: '测试频道1', title: '测试频道标题1', status: 'active' },
                    { id: 2, name: '测试频道2', title: '测试频道标题2', status: 'inactive' }
                ];
            }
        },
        
        async loadForwardingConfig() {
            try {
                const response = await axios.get(API.admin.config);
                if (response.data) {
                    const configs = response.data;
                    
                    this.forwardingConfig = {
                        enabled: this.parseBooleanValue(configs['target.auto_forward_enabled'], false),
                        target_channel: configs['target.channel_link'] || '',
                        review_group: configs['review.group_link'] || '',
                        delay: parseInt(configs['review.auto_forward_delay']) || 1800,
                        auto_reject_ads: this.parseBooleanValue(configs['review.auto_reject_ads'], false),
                        auto_forward_after_collect: this.parseBooleanValue(configs['review.auto_forward_after_collect'], false),
                        // 加载已解析的ID
                        target_channel_id: configs['target.channel_id'] || '',
                        review_group_id: configs['review.group_id'] || ''
                    };
                    
                }
            } catch (error) {
                console.error('加载转发配置失败:', error);
                // 使用默认配置
                this.forwardingConfig = {
                    enabled: false,
                    target_channel: '',
                    review_group: '',
                    target_channel_id: '',
                    review_group_id: '',
                    delay: 1800,
                    auto_reject_ads: false
                };
            }
        },
        
        async loadSystemConfig() {
            try {
                const response = await axios.get(API.admin.config);
                if (response.data) {
                    const configs = response.data;
                    
                    // 从系统配置中提取系统设置
                    this.systemConfig = {
                        history_message_limit: parseInt(configs['source.history_limit']) || 50,
                        signature: configs['target.signature'] || '',
                        collection_enabled: this.parseBooleanValue(configs['collection.enabled'], true),
                        // Telegram API 配置
                        'telegram.api_id': configs['telegram.api_id'] || '',
                        'telegram.api_hash': configs['telegram.api_hash'] || '',
                        // 过滤设置
                        filter_enabled: this.parseBooleanValue(configs['filter.enabled'], true),
                        // 审核设置
                        require_approval: this.parseBooleanValue(configs['review.require_approval'], true),
                        // 转发设置
                        auto_forward_enabled: this.parseBooleanValue(configs['review.auto_forward_enabled'], false),
                        'target.channel_link': configs['target.channel_link'] || '',
                        'target.channel_id': configs['target.channel_id'] || '',
                        'review.group_link': configs['review.group_link'] || '',
                        'review.group_id': configs['review.group_id'] || '',
                        'review.auto_forward_delay': parseInt(configs['review.auto_forward_delay']) || 1800,
                        // 系统设置
                        scheduler_enabled: this.parseBooleanValue(configs['scheduler.enabled'], true),
                        data_cleanup_interval_hours: parseInt(configs['scheduler.data_cleanup_interval_hours']) || 24
                        // 调度和单消息删除默认启用
                    };
                    
                }
            } catch (error) {
                console.error('加载系统配置失败:', error);
                // 使用默认配置
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
                
                const response = await axios.post(API.admin.channels, {
                    channel_id: "",  // 自动解析
                    channel_name: channelName,
                    channel_title: "",  // 自动解析
                    channel_type: "source"
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
                
                const response = await axios.delete(API.admin.channels_by_name.replace('{channel_name}', encodeURIComponent(channelId)));
                
                
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
                
                const response = await axios.post(API.admin.resolveChannelIds);
                
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
                const response = await axios.post(API.config.channelsBatchAdd, {
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
                const response = await axios.post(API.admin.resolveChannelId, {
                    channel_name: channelName
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
        
        async toggleChannelStatus(channel) {
            try {
                const newStatus = channel.status === 'active' ? 'inactive' : 'active';
                const isActive = newStatus === 'active';
                
                
                const response = await axios.put(API.admin.channels_by_name.replace('{channel_name}', encodeURIComponent(channel.name)), {
                    is_active: isActive
                });
                
                
                if (response.data.success) {
                    MessageManager.success(`频道状态已切换为${newStatus === 'active' ? '活跃' : '停用'}`);
                    await this.loadChannels();
                } else {
                    MessageManager.error('状态切换失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                MessageManager.error('状态切换失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        
        async saveForwardingConfig() {
            try {
                // 使用批量配置保存API
                const configData = {
                    'target.auto_forward_enabled': this.forwardingConfig.enabled,
                    'target.channel_link': this.forwardingConfig.target_channel.trim(),
                    'review.group_link': this.forwardingConfig.review_group.trim(),
                    'review.auto_forward_delay': String(parseInt(this.forwardingConfig.delay)),
                    'review.auto_reject_ads': this.forwardingConfig.auto_reject_ads,
                    'review.auto_forward_after_collect': this.forwardingConfig.auto_forward_after_collect,
                    'target.channel_id': this.forwardingConfig.target_channel_id,
                    'review.group_id': this.forwardingConfig.review_group_id
                };
                
                // 调试日志
                
                const response = await axios.post(API.admin.configBatch, configData);
                
                if (response.data.success) {
                    MessageManager.success('转发配置保存成功');
                    // 保存成功后重新加载配置
                    await this.loadForwardingConfig();
                } else {
                    throw new Error(response.data.message || '配置保存失败');
                }
                
            } catch (error) {
                console.error('保存配置错误:', error);
                MessageManager.error('转发配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async saveSystemConfig() {
            try {
                // 准备保存的配置数据
                const configData = {
                    'source.history_limit': String(parseInt(this.systemConfig.history_message_limit)),
                    'target.signature': this.systemConfig.signature,
                    'collection.enabled': this.systemConfig.collection_enabled,
                    // Telegram API 配置
                    'telegram.api_id': this.systemConfig['telegram.api_id'] || '',
                    'telegram.api_hash': this.systemConfig['telegram.api_hash'] || '',
                    // 过滤设置
                    'filter.enabled': this.systemConfig.filter_enabled,
                    // 审核设置
                    'review.require_approval': this.systemConfig.require_approval,
                    // 转发设置
                    'review.auto_forward_enabled': this.systemConfig.auto_forward_enabled,
                    'target.channel_link': this.systemConfig['target.channel_link'],
                    'target.channel_id': this.systemConfig['target.channel_id'],
                    'review.group_link': this.systemConfig['review.group_link'],
                    'review.group_id': this.systemConfig['review.group_id'],
                    'review.auto_forward_delay': this.systemConfig['review.auto_forward_delay'],
                    // 系统设置
                    'scheduler.enabled': this.systemConfig.scheduler_enabled,
                    'scheduler.data_cleanup_interval_hours': this.systemConfig.data_cleanup_interval_hours
                    // 调度和单消息删除默认启用
                };
                
                // 调试日志
                
                // 批量保存配置
                const response = await axios.post(API.admin.configBatch, configData);
                
                if (response.data.success) {
                    MessageManager.success('系统配置保存成功');
                    // 保存成功后重新加载配置
                    await this.loadSystemConfig();
                } else {
                    throw new Error(response.data.message || '保存配置失败');
                }
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
                'review.group_link': '',
                'review.group_id': '',
                'review.auto_forward_delay': 1800,
                // 系统设置
                scheduler_enabled: true,
                data_cleanup_interval_hours: 24
                // 调度和单消息删除默认启用
            };
            MessageManager.success('系统配置已重置为默认值');
        },
        
        async loadFilterConfig() {
            // 过滤设置由系统自动管理，无需加载
        },
        
        async saveFilterConfig() {
            MessageManager.info('过滤策略由系统自动管理，无需手动保存');
        },
        
        async loadFilterSettings() {
            try {
                const response = await axios.get(API.admin.config);
                if (response.data) {
                    const configs = response.data;
                    
                    // 从系统配置加载过滤器设置 - 修复配置键名映射
                    this.filterSettings = {
                        // 内容清理过滤器
                        tail_filter: this.parseBooleanValue(configs['filter.tail_filter_enabled'], true),
                        footer_promo: this.parseBooleanValue(configs['filter.footer_promo_enabled'], true),
                        markdown: this.parseBooleanValue(configs['filter.markdown_enabled'], true),
                        promo_vector: this.parseBooleanValue(configs['filter.promo_vector_enabled'], true),
                        
                        // 内容检测过滤器
                        duplicate: this.parseBooleanValue(configs['filter.duplicate_enabled'], true),
                        ad_detector: this.parseBooleanValue(configs['filter.ad_detector_enabled'], true)
                    };
                }
            } catch (error) {
                console.error('加载过滤器设置失败:', error);
                // 使用默认设置
            }
        },
        
        async saveFilterSettings() {
            try {
                // 准备保存的配置数据 - 修复配置键名映射
                const configData = {
                    // 内容清理过滤器
                    'filter.tail_filter_enabled': this.filterSettings.tail_filter,
                    'filter.footer_promo_enabled': this.filterSettings.footer_promo,
                    'filter.markdown_enabled': this.filterSettings.markdown,
                    'filter.promo_vector_enabled': this.filterSettings.promo_vector,
                    
                    // 内容检测过滤器
                    'filter.duplicate_enabled': this.filterSettings.duplicate,
                    'filter.ad_detector_enabled': this.filterSettings.ad_detector,
                    
                    // 基础过滤开关（综合判断）
                    'filter.enabled': Boolean(
                        this.filterSettings.duplicate || 
                        this.filterSettings.ad_detector
                    )
                };
                
                console.log('保存过滤器配置:', configData);
                
                // 批量保存配置
                const response = await axios.post(API.admin.configBatch, configData);
                
                if (response.data.success) {
                    MessageManager.success('过滤器配置保存成功');
                    
                    // 保存成功后重新加载配置
                    await this.loadFilterSettings();
                    
                    // 通知系统重新加载过滤器
                    await this.reloadFilters();
                } else {
                    throw new Error(response.data.message || '保存过滤器配置失败');
                }
            } catch (error) {
                console.error('保存过滤器配置失败:', error);
                MessageManager.error('过滤器配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resetFilterSettings() {
            // 重置为默认配置 - 修复字段名一致性
            this.filterSettings = {
                // 内容清理过滤器
                tail_filter: true,
                footer_promo: true,
                markdown: true,
                promo_vector: true,
                
                // 内容检测过滤器
                duplicate: true,
                ad_detector: true
            };
            
            MessageManager.success('过滤器配置已重置为默认值');
        },
        
        async reloadFilters() {
            try {
                // 调用系统API重新加载过滤器配置
                // 注：需要后端实现此API端点
                const response = await axios.post(API.admin.reloadFilters || '/api/admin/reload-filters');
                
                if (response.data && response.data.success) {
                    MessageManager.success('过滤器重新加载成功');
                } else {
                    console.warn('过滤器重新加载API响应异常，但配置可能已生效');
                }
            } catch (error) {
                // 如果API不存在，仍然显示成功消息（配置已保存）
                console.warn('过滤器重新加载API调用失败，但配置已保存:', error);
                MessageManager.info('配置已保存，系统将在下次消息处理时应用新配置');
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
        
        
        // 手动解析目标频道
        async manualResolveTargetChannel() {
            if (!this.forwardingConfig.target_channel) {
                MessageManager.warning('请先输入目标频道');
                return;
            }
            
            try {
                const response = await axios.post(API.admin.resolveChannelId, {
                    channel_name: this.forwardingConfig.target_channel
                });
                
                if (response.data.success) {
                    this.forwardingConfig.target_channel_id = response.data.resolved_id;
                    MessageManager.success(`目标频道已解析: ${response.data.resolved_id}`);
                    
                    // 保存解析结果到系统配置
                    await this.saveForwardingConfig();
                } else {
                    MessageManager.error('解析失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 操作完成
            }
        },
        
        // 手动解析审核群
        async manualResolveReviewGroup() {
            if (!this.forwardingConfig.review_group) {
                MessageManager.warning('请先输入审核群');
                return;
            }
            
            try {
                const response = await axios.post(API.admin.resolveReviewGroup, {
                    review_group_config: this.forwardingConfig.review_group
                });
                
                if (response.data.success) {
                    this.forwardingConfig.review_group_id = response.data.resolved_id;
                    MessageManager.success(`审核群已解析: ${response.data.resolved_id}`);
                    
                    // 保存解析结果到系统配置
                    await this.saveForwardingConfig();
                } else {
                    MessageManager.error('解析失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 操作完成
            }
        },
        
        // 批量解析所有频道
        async resolveAllChannels() {
            try {
                
                const response = await axios.post(API.admin.resolveChannelIds);
                
                if (response.data.success) {
                    MessageManager.success(`频道解析完成: ${response.data.message}`);
                    
                    // 重新加载配置
                    await this.loadChannels();
                    await this.loadForwardingConfig();
                } else {
                    MessageManager.error('解析失败: ' + response.data.message);
                }
            } catch (error) {
                MessageManager.error('解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                // 操作完成
            }
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
        
        // 添加搜索到的频道
        async addSearchedChannel(channel) {
            try {
                // 准备频道数据
                const channelData = {
                    name: channel.id.toString(),
                    title: channel.title,
                    channel_id: channel.id.toString()
                };
                
                const response = await axios.post(API.admin.addChannel, channelData);
                
                if (response.data.success) {
                    MessageManager.success('频道添加成功');
                    // 重新加载频道列表
                    await this.loadChannels();
                    // 清空搜索结果
                    this.searchForm.query = '';
                    this.searchForm.results = [];
                    this.searchForm.searched = false;
                } else {
                    MessageManager.error(response.data.message || '添加失败');
                }
            } catch (error) {
                MessageManager.error('添加频道失败: ' + (error.response?.data?.detail || error.message));
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