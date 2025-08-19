// 配置页面 JavaScript 组件

// 确保API配置可用
const API = window.API;

// 检查依赖是否加载
// console.log('Vue loaded:', typeof Vue !== 'undefined');
// console.log('ElementPlus loaded:', typeof ElementPlus !== 'undefined');
// console.log('Axios loaded:', typeof axios !== 'undefined');

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

// 消息管理器 - 右下角显示
const MessageManager = {
    success(message) {
        ElMessage({
            message: message,
            type: 'success',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    },
    error(message) {
        ElMessage({
            message: message,
            type: 'error',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    },
    warning(message) {
        ElMessage({
            message: message,
            type: 'warning',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    },
    info(message, options = {}) {
        ElMessage({
            message: message,
            type: 'info',
            offset: 20,
            customClass: 'bottom-right-message',
            ...options
        });
    }
};

// 配置应用组件
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
                resolved_group_id: '',
                resolved_target_channel_id: '',
                delay: 0,
                auto_reject_ads: false
            },
            
            // 帮助提示标记
            helpMessageShowing: false,
            
            // 系统设置
            systemConfig: {
                history_message_limit: 50,
                channel_signature: '',
                collection_enabled: true
            },
            
            // 过滤设置 - 系统自动管理
            filterConfig: {}
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
        async loadConfigData() {
            this.loading = true;
            this.loadingMessage = '正在加载配置数据...';
            
            try {
                // 加载频道列表
                await this.loadChannels();
                
                // 加载转发配置
                await this.loadForwardingConfig();
                
                // 加载系统配置
                await this.loadSystemConfig();
                
                // 加载过滤配置
                await this.loadFilterConfig();
                
                MessageManager.success('配置数据加载完成');
            } catch (error) {
                MessageManager.error('加载配置数据失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        async loadChannels() {
            try {
                const response = await axios.get(API.admin.channels);
                if (response.data.success) {
                    this.channels = response.data.channels;
                }
            } catch (error) {
                // console.error('加载频道列表失败:', error);
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
                    // 使用新的配置字段名
                    this.forwardingConfig = {
                        enabled: response.data.auto_forward_enabled || false,
                        target_channel: response.data.target_channel || '',
                        review_group: response.data.review_group || '',
                        delay: response.data.auto_forward_delay || 1800,
                        auto_reject_ads: response.data.auto_reject_ads || false
                    };
                }
            } catch (error) {
                console.error('加载转发配置失败:', error);
                // 使用默认配置
                this.forwardingConfig = {
                    enabled: false,
                    target_channel: '',
                    review_group: '',
                    delay: 1800,
                    auto_reject_ads: false
                };
            }
        },
        
        async loadSystemConfig() {
            try {
                const response = await axios.get(API.config.list);
                if (response.data && response.data.configs) {
                    const configs = response.data.configs;
                    
                    // 从系统配置中提取系统设置
                    this.systemConfig = {
                        history_message_limit: configs['source.history_limit']?.value || 50,
                        channel_signature: configs['target.signature']?.value || '',
                        collection_enabled: configs['collection.enabled']?.value !== undefined ? configs['collection.enabled'].value : true
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
                
                this.loading = true;
                this.loadingMessage = '正在解析频道信息...';
                
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
                // console.error('添加频道错误:', error);
                MessageManager.error('频道添加失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        async removeChannel(channelId) {
            try {
                // console.log('删除频道ID:', channelId);
                
                const response = await axios.delete(API.admin.channels_by_name.replace('{channel_name}', encodeURIComponent(channelId)));
                
                // console.log('删除频道响应:', response.data);
                
                if (response.data.success) {
                    MessageManager.success('频道删除成功');
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道删除失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                // console.error('删除频道错误:', error);
                MessageManager.error('频道删除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resolveChannelIds() {
            try {
                this.loading = true;
                this.loadingMessage = '正在解析频道ID...';
                
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
                this.loading = false;
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
                // console.error('批量添加频道错误:', error);
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
                
                // console.log('切换频道状态:', channel.channel_id || channel.name, '从', channel.status, '到', newStatus);
                
                const response = await axios.put(API.admin.channels_by_name.replace('{channel_name}', encodeURIComponent(channel.name)), {
                    is_active: isActive
                });
                
                // console.log('状态切换响应:', response.data);
                
                if (response.data.success) {
                    MessageManager.success(`频道状态已切换为${newStatus === 'active' ? '活跃' : '停用'}`);
                    await this.loadChannels();
                } else {
                    MessageManager.error('状态切换失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                // console.error('状态切换错误:', error);
                MessageManager.error('状态切换失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        
        async saveForwardingConfig() {
            try {
                // 直接发送原始值到新的API端点
                const response = await axios.post(API.admin.configForwarding, {
                    target_channel: this.forwardingConfig.target_channel.trim(),
                    review_group: this.forwardingConfig.review_group.trim(),
                    auto_forward_enabled: this.forwardingConfig.enabled,
                    auto_forward_delay: this.forwardingConfig.delay,
                    auto_reject_ads: this.forwardingConfig.auto_reject_ads
                });
                
                if (response.data.success) {
                    MessageManager.success('转发配置保存成功，缓存已自动刷新');
                } else {
                    throw new Error(response.data.message || '配置保存失败');
                }
                
            } catch (error) {
                MessageManager.error('转发配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async saveSystemConfig() {
            try {
                // 准备保存的配置数据
                const configData = {
                    'source.history_limit': this.systemConfig.history_message_limit,
                    'target.signature': this.systemConfig.channel_signature,
                    'collection.enabled': this.systemConfig.collection_enabled
                };
                
                // 批量保存配置
                const response = await axios.post(API.admin.configBatch, configData);
                
                if (response.data.success) {
                    MessageManager.success('系统配置保存成功');
                } else {
                    throw new Error(response.data.message || '保存配置失败');
                }
            } catch (error) {
                // console.error('保存系统配置失败:', error);
                MessageManager.error('系统配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resetSystemConfig() {
            this.systemConfig = {
                history_message_limit: 50,
                channel_signature: '',
                collection_enabled: true
            };
            MessageManager.success('系统配置已重置为默认值');
        },
        
        async loadFilterConfig() {
            // 过滤设置由系统自动管理，无需加载
        },
        
        async saveFilterConfig() {
            MessageManager.info('过滤策略由系统自动管理，无需手动保存');
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
        
        // 更新审核群ID
        async updateReviewGroupId() {
            if (this.forwardingConfig.review_group) {
                try {
                    // 使用admin API解析审核群ID
                    const response = await axios.post(API.admin.resolveReviewGroup, {
                        review_group_config: this.forwardingConfig.review_group
                    });
                    if (response.data.success && response.data.resolved_id) {
                        this.forwardingConfig.resolved_group_id = response.data.resolved_id;
                    }
                } catch (error) {
                    // console.error('解析群ID失败:', error);
                    // 静默处理，不影响主流程
                }
            }
        },
        
        // 手动解析目标频道
        async manualResolveTargetChannel() {
            if (!this.forwardingConfig.target_channel) {
                MessageManager.warning('请先输入目标频道');
                return;
            }
            
            try {
                this.loading = true;
                const response = await axios.post(API.admin.resolveChannelId, {
                    channel_name: this.forwardingConfig.target_channel
                });
                
                if (response.data.success) {
                    this.forwardingConfig.resolved_target_channel_id = response.data.resolved_id;
                    MessageManager.success(`目标频道已解析: ${response.data.resolved_id}`);
                    
                    // 重新加载配置
                    await this.loadForwardingConfig();
                } else {
                    MessageManager.error('解析失败: ' + response.data.message);
                }
            } catch (error) {
                // console.error('手动解析目标频道失败:', error);
                MessageManager.error('解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        // 手动解析审核群
        async manualResolveReviewGroup() {
            if (!this.forwardingConfig.review_group) {
                MessageManager.warning('请先输入审核群');
                return;
            }
            
            try {
                this.loading = true;
                const response = await axios.post(API.admin.resolveReviewGroup, {
                    review_group_config: this.forwardingConfig.review_group
                });
                
                if (response.data.success) {
                    this.forwardingConfig.resolved_group_id = response.data.resolved_id;
                    MessageManager.success(`审核群已解析: ${response.data.resolved_id}`);
                    
                    // 重新加载配置
                    await this.loadForwardingConfig();
                } else {
                    MessageManager.error('解析失败: ' + response.data.message);
                }
            } catch (error) {
                // console.error('手动解析审核群失败:', error);
                MessageManager.error('解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        // 批量解析所有频道
        async resolveAllChannels() {
            try {
                this.loading = true;
                this.loadingMessage = '正在解析所有频道ID...';
                
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
                // console.error('批量解析频道失败:', error);
                MessageManager.error('解析失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        // 更新目标频道ID
        async updateTargetChannelId() {
            if (this.forwardingConfig.target_channel) {
                try {
                    // 使用admin API解析频道ID
                    const response = await axios.post(API.admin.resolveChannelId, {
                        channel_name: this.forwardingConfig.target_channel
                    });
                    if (response.data.success && response.data.resolved_id) {
                        this.forwardingConfig.resolved_target_channel_id = response.data.resolved_id;
                        MessageManager.success(`目标频道ID已解析: ${response.data.resolved_id}`);
                    }
                } catch (error) {
                    // console.error('解析目标频道ID失败:', error);
                    // 静默处理，不影响主流程
                }
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
                // console.error('搜索频道失败:', error);
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
                // console.error('添加频道失败:', error);
                MessageManager.error('添加频道失败: ' + (error.response?.data?.detail || error.message));
            }
        }
    }
};

// 等待 DOM 加载完成
document.addEventListener('DOMContentLoaded', function() {
    // console.log('DOM loaded, mounting Vue app...');
    
    // 创建应用实例
    // console.log('Vue version:', Vue.version);
    // console.log('ElementPlus version:', ElementPlus.version);

    try {
        const app = createApp(ConfigApp);
        app.use(ElementPlus);
        
        // 注册导航栏组件
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }

        // 添加错误处理
        app.config.errorHandler = (err, vm, info) => {
            // console.error('Vue Error:', err);
            // console.error('Error Info:', info);
        };

        // 检查目标元素是否存在
        const targetElement = document.getElementById('app');
        if (!targetElement) {
            // console.error('Target element #app not found!');
            return;
        }

        // 挂载应用
        app.mount('#app');
        // console.log('Vue app mounted successfully');
    } catch (error) {
        // console.error('Failed to mount Vue app:', error);
        document.body.innerHTML = '<div style="color: red; padding: 20px;">Vue 应用挂载失败: ' + error.message + '</div>';
    }
}); 