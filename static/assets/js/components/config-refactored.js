// 重构后的配置页面 JavaScript 组件 - 模块化版本

// 检查依赖是否加载
// console.log('Vue loaded:', typeof Vue !== 'undefined');
// console.log('ElementPlus loaded:', typeof ElementPlus !== 'undefined');
// console.log('Axios loaded:', typeof axios !== 'undefined');

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

// 配置应用组件 - 重构版本
const ConfigApp = {
    data() {
        return {
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            configStatus: '在线',
            activeTab: 'channels',
            
            // 频道管理
            channelSearchFilter: '',
            newChannel: {
                name: '',
                title: ''
            },
            
            // 频道搜索（添加新频道）
            searchForm: {
                query: '',
                results: [],
                loading: false,
                searched: false
            },
            
            // 系统设置
            systemConfig: {
                review_mode: 'manual',
                retention_days: 30,
                max_concurrent: 10,
                log_level: 'info',
                history_message_limit: 50,
                channel_signature: ''
            }
        }
    },
    
    mounted() {
        this.loadConfigData();
    },
    
    computed: {
        // 过滤后的频道列表
        filteredChannels() {
            if (!channelManager.channels) {
                return [];
            }
            return channelManager.filterChannels(channelManager.channels, this.channelSearchFilter);
        },
        
        // 转发配置
        forwardingConfig() {
            return configManager.forwardingConfig;
        }
    },
    
    methods: {
        // ===================
        // 数据加载方法
        // ===================
        async loadConfigData() {
            this.loading = true;
            this.loadingMessage = '正在加载配置数据...';
            
            try {
                // 并行加载数据
                await Promise.all([
                    this.loadChannels(),
                    this.loadConfigs(),
                    this.loadSystemConfig()
                ]);
                
                this.statusMessage = '配置加载成功';
                this.statusType = 'success';
                
            } catch (error) {
                console.error('加载配置数据失败:', error);
                this.statusMessage = `加载失败: ${error.message}`;
                this.statusType = 'error';
            } finally {
                this.loading = false;
                this.loadingMessage = '';
            }
        },

        async loadChannels() {
            try {
                await channelManager.loadChannels();
            } catch (error) {
                throw new Error(`加载频道失败: ${error.message}`);
            }
        },

        async loadConfigs() {
            try {
                await configManager.loadAllConfigs();
            } catch (error) {
                throw new Error(`加载配置失败: ${error.message}`);
            }
        },

        async loadSystemConfig() {
            try {
                // 加载系统配置项
                const configs = configManager.configs;
                this.systemConfig = {
                    review_mode: this._getConfigValue(configs, 'review.mode', 'manual'),
                    retention_days: this._getConfigValue(configs, 'system.retention_days', 30),
                    max_concurrent: this._getConfigValue(configs, 'system.max_concurrent', 10),
                    log_level: this._getConfigValue(configs, 'system.log_level', 'info'),
                    history_message_limit: this._getConfigValue(configs, 'channels.history_message_limit', 50),
                    channel_signature: this._getConfigValue(configs, 'channels.signature', '')
                };
            } catch (error) {
                throw new Error(`加载系统配置失败: ${error.message}`);
            }
        },

        // ===================
        // 频道管理方法
        // ===================
        async searchChannels() {
            if (!this.searchForm.query.trim()) {
                ElMessage.warning('请输入搜索关键词');
                return;
            }
            
            this.searchForm.loading = true;
            
            try {
                this.searchForm.results = await channelManager.searchChannels(this.searchForm.query);
                this.searchForm.searched = true;
                
                if (this.searchForm.results.length === 0) {
                    ElMessage.info('未找到匹配的频道');
                }
            } catch (error) {
                ElMessage.error(`搜索失败: ${error.message}`);
            } finally {
                this.searchForm.loading = false;
            }
        },

        async addChannelFromSearch(channel) {
            try {
                const channelData = {
                    name: channel.name,
                    title: channel.title,
                    channel_id: channel.channel_id
                };
                
                await channelManager.addChannel(channelData);
                ElMessage.success('频道添加成功');
                
                // 清空搜索结果
                this.searchForm.query = '';
                this.searchForm.results = [];
                this.searchForm.searched = false;
                
            } catch (error) {
                ElMessage.error(`添加频道失败: ${error.message}`);
            }
        },

        async addCustomChannel() {
            if (!this.newChannel.name.trim()) {
                ElMessage.warning('请输入频道名称');
                return;
            }
            
            try {
                await channelManager.addChannel({
                    name: this.newChannel.name,
                    title: this.newChannel.title || this.newChannel.name
                });
                
                ElMessage.success('频道添加成功');
                
                // 重置表单
                this.newChannel = {
                    name: '',
                    title: ''
                };
                
            } catch (error) {
                ElMessage.error(`添加频道失败: ${error.message}`);
            }
        },

        async toggleChannelStatus(channel) {
            try {
                const newStatus = channel.status === 'active' ? 'inactive' : 'active';
                await channelManager.updateChannel(channel.id, {
                    is_active: newStatus === 'active'
                });
                
                ElMessage.success(`频道${newStatus === 'active' ? '已启用' : '已停用'}`);
            } catch (error) {
                ElMessage.error(`更新频道状态失败: ${error.message}`);
            }
        },

        async deleteChannel(channel) {
            try {
                await this.$confirm(`确定要删除频道 "${channel.name}" 吗？`, '确认删除', {
                    type: 'warning'
                });
                
                await channelManager.deleteChannel(channel.id);
                ElMessage.success('频道删除成功');
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error(`删除频道失败: ${error.message || error}`);
                }
            }
        },

        // ===================
        // 转发配置方法
        // ===================
        async updateForwardingConfig() {
            try {
                const config = this.forwardingConfig;
                
                // 批量更新配置
                const updates = [
                    configManager.updateConfig('forwarding.enabled', config.enabled),
                    configManager.updateConfig('forwarding.target_channel', config.target_channel),
                    configManager.updateConfig('forwarding.review_group', config.review_group),
                    configManager.updateConfig('forwarding.delay', config.delay),
                    configManager.updateConfig('forwarding.conditions', config.conditions)
                ];
                
                await Promise.all(updates);
                ElMessage.success('转发配置更新成功');
                
            } catch (error) {
                ElMessage.error(`更新转发配置失败: ${error.message}`);
            }
        },

        async resolveTelegramLinks() {
            try {
                const config = this.forwardingConfig;
                
                if (config.target_channel) {
                    const targetResult = await configManager.resolveTelegramLink(config.target_channel);
                    if (targetResult.channel_id) {
                        config.resolved_target_channel_id = targetResult.channel_id;
                        await configManager.updateConfig('forwarding.resolved_target_channel_id', targetResult.channel_id);
                    }
                }
                
                if (config.review_group) {
                    const reviewResult = await configManager.resolveTelegramLink(config.review_group);
                    if (reviewResult.channel_id) {
                        config.resolved_group_id = reviewResult.channel_id;
                        await configManager.updateConfig('forwarding.resolved_group_id', reviewResult.channel_id);
                    }
                }
                
                ElMessage.success('Telegram链接解析成功');
                
            } catch (error) {
                ElMessage.error(`链接解析失败: ${error.message}`);
            }
        },

        async testForwardingConfig() {
            try {
                const result = await configManager.testForwardingConfig();
                ElMessage.success('转发配置测试成功');
            } catch (error) {
                ElMessage.error(`配置测试失败: ${error.message}`);
            }
        },

        // ===================
        // 系统配置方法
        // ===================
        async updateSystemConfig() {
            try {
                const updates = [
                    configManager.updateConfig('review.mode', this.systemConfig.review_mode),
                    configManager.updateConfig('system.retention_days', this.systemConfig.retention_days),
                    configManager.updateConfig('system.max_concurrent', this.systemConfig.max_concurrent),
                    configManager.updateConfig('system.log_level', this.systemConfig.log_level),
                    configManager.updateConfig('channels.history_message_limit', this.systemConfig.history_message_limit),
                    configManager.updateConfig('channels.signature', this.systemConfig.channel_signature)
                ];
                
                await Promise.all(updates);
                ElMessage.success('系统配置更新成功');
                
            } catch (error) {
                ElMessage.error(`更新系统配置失败: ${error.message}`);
            }
        },

        // ===================
        // 辅助方法
        // ===================
        _getConfigValue(configs, key, defaultValue) {
            const config = configs[key];
            return config ? config.value : defaultValue;
        },

        formatChannelDisplay(channel) {
            return channelManager.formatChannelForDisplay(channel);
        },

        showHelpMessage() {
            ElMessage({
                message: '这里显示配置页面的帮助信息',
                type: 'info',
                duration: 3000
            });
        }
    }
};

// 创建并挂载应用
const configApp = createApp(ConfigApp);

// 使用Element Plus
configApp.use(ElementPlus);

// 挂载应用
configApp.mount('#configApp');