// 配置页面 JavaScript 组件

// 检查依赖是否加载
console.log('Vue loaded:', typeof Vue !== 'undefined');
console.log('ElementPlus loaded:', typeof ElementPlus !== 'undefined');
console.log('Axios loaded:', typeof axios !== 'undefined');

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

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
            
            // 过滤规则
            filterRules: [],
            newRule: {
                name: '',
                pattern: '',
                action: 'block'
            },
            
            // 转发设置
            forwardingConfig: {
                enabled: false,
                target_channel: '',
                review_group: '',
                resolved_group_id: '',
                resolved_target_channel_id: '',
                delay: 0,
                conditions: ['approved']
            },
            
            // 帮助提示标记
            helpMessageShowing: false,
            
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
            if (!this.channelSearchFilter) {
                return this.channels;
            }
            
            const filter = this.channelSearchFilter.toLowerCase();
            return this.channels.filter(channel => {
                const name = (channel.name || '').toLowerCase();
                const title = (channel.title || '').toLowerCase();
                return name.includes(filter) || title.includes(filter);
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
                
                // 加载过滤规则
                await this.loadFilterRules();
                
                // 加载转发配置
                await this.loadForwardingConfig();
                
                // 加载系统配置
                await this.loadSystemConfig();
                
                MessageManager.success('配置数据加载完成');
            } catch (error) {
                MessageManager.error('加载配置数据失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        async loadChannels() {
            try {
                const response = await axios.get('/api/admin/channels');
                if (response.data.success) {
                    this.channels = response.data.channels;
                }
            } catch (error) {
                console.error('加载频道列表失败:', error);
                // 使用模拟数据
                this.channels = [
                    { id: 1, name: '测试频道1', title: '测试频道标题1', status: 'active' },
                    { id: 2, name: '测试频道2', title: '测试频道标题2', status: 'inactive' }
                ];
            }
        },
        
        async loadFilterRules() {
            try {
                const response = await axios.get('/api/admin/filter-rules');
                if (response.data.success) {
                    this.filterRules = response.data.rules;
                }
            } catch (error) {
                console.error('加载过滤规则失败:', error);
                // 使用模拟数据
                this.filterRules = [
                    { id: 1, name: '广告关键词', pattern: '.*(广告|推广|优惠).*', action: 'mark_ad' },
                    { id: 2, name: '垃圾信息', pattern: '.*(垃圾|spam).*', action: 'block' }
                ];
            }
        },
        
        async loadForwardingConfig() {
            try {
                const response = await axios.get('/api/admin/config');
                if (response.data) {
                    // 处理目标频道名称显示格式
                    let targetChannel = response.data.target_channel_id || '';
                    if (targetChannel && !targetChannel.startsWith('@') && !targetChannel.startsWith('-')) {
                        targetChannel = '@' + targetChannel;
                    }
                    
                    // 处理审核群名称显示格式
                    let reviewGroup = response.data.review_group_id || '';
                    const cachedGroupId = response.data.review_group_id_cached || '';
                    const cachedTargetChannelId = response.data.target_channel_id_cached || '';
                    
                    // 如果有缓存的ID，显示格式为 "原配置 (ID: 缓存ID)"
                    if (reviewGroup && cachedGroupId && reviewGroup !== cachedGroupId) {
                        reviewGroup = `${reviewGroup} (ID: ${cachedGroupId})`;
                    } else if (reviewGroup && !reviewGroup.startsWith('@') && !reviewGroup.startsWith('-') && !reviewGroup.includes('t.me')) {
                        reviewGroup = '@' + reviewGroup;
                    }
                    
                    // 从系统配置中提取转发相关设置
                    this.forwardingConfig = {
                        enabled: response.data.auto_forward_delay > 0,
                        target_channel: targetChannel,
                        review_group: response.data.review_group_id || '',
                        resolved_group_id: cachedGroupId || '',
                        resolved_target_channel_id: cachedTargetChannelId || '',
                        delay: response.data.auto_forward_delay || 0,
                        conditions: ['approved']
                    };
                }
            } catch (error) {
                // 静默处理错误，使用默认配置
                console.log('使用默认转发配置');
            }
        },
        
        async loadSystemConfig() {
            try {
                const response = await axios.get('/api/admin/config');
                if (response.data) {
                    // 从系统配置中提取系统设置
                    this.systemConfig = {
                        review_mode: 'manual', // 默认手动审核
                        retention_days: 30,
                        max_concurrent: 10,
                        log_level: 'info',
                        history_message_limit: response.data.history_message_limit || 50,
                        channel_signature: response.data.channel_signature || ''
                    };
                }
            } catch (error) {
                // 静默处理错误，使用默认配置
                console.log('使用默认系统配置');
            }
        },
        
        async addChannel() {
            if (!this.newChannel.name || !this.newChannel.title) {
                MessageManager.warning('请填写完整的频道信息');
                return;
            }
            
            try {
                // 处理频道名称，统一格式
                let channelName = this.newChannel.name.trim();
                if (!channelName.startsWith('@')) {
                    channelName = '@' + channelName;
                }
                
                console.log('添加频道请求数据:', {
                    channel_id: channelName,
                    channel_name: channelName,
                    channel_title: this.newChannel.title,
                    channel_type: "source"
                });
                
                const response = await axios.post('/api/admin/channels', {
                    channel_id: "",  // 初始为空，后续通过Telethon获取真实ID
                    channel_name: channelName,
                    channel_title: this.newChannel.title,
                    channel_type: "source"
                });
                
                console.log('添加频道响应:', response.data);
                
                if (response.data.success) {
                    MessageManager.success('频道添加成功');
                    this.newChannel = { name: '', title: '' };
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道添加失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('添加频道错误:', error);
                MessageManager.error('频道添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeChannel(channelId) {
            try {
                console.log('删除频道ID:', channelId);
                
                const response = await axios.delete(`/api/admin/channels/${encodeURIComponent(channelId)}`);
                
                console.log('删除频道响应:', response.data);
                
                if (response.data.success) {
                    MessageManager.success('频道删除成功');
                    await this.loadChannels();
                } else {
                    MessageManager.error('频道删除失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('删除频道错误:', error);
                MessageManager.error('频道删除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resolveChannelIds() {
            try {
                this.loading = true;
                this.loadingMessage = '正在解析频道ID...';
                
                const response = await axios.post('/api/admin/resolve-channel-ids');
                
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
        
        async resolveChannelId(channelName) {
            try {
                const response = await axios.post('/api/admin/resolve-channel-id', {
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
                
                console.log('切换频道状态:', channel.channel_id || channel.name, '从', channel.status, '到', newStatus);
                
                const response = await axios.put(`/api/admin/channels/${encodeURIComponent(channel.name)}`, {
                    is_active: isActive
                });
                
                console.log('状态切换响应:', response.data);
                
                if (response.data.success) {
                    MessageManager.success(`频道状态已切换为${newStatus === 'active' ? '活跃' : '停用'}`);
                    await this.loadChannels();
                } else {
                    MessageManager.error('状态切换失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('状态切换错误:', error);
                MessageManager.error('状态切换失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async addRule() {
            if (!this.newRule.name || !this.newRule.pattern) {
                MessageManager.warning('请填写完整的规则信息');
                return;
            }
            
            try {
                const response = await axios.post('/api/admin/filter-rules', {
                    name: this.newRule.name,
                    pattern: this.newRule.pattern,
                    action: this.newRule.action
                });
                
                if (response.data.success) {
                    MessageManager.success('规则添加成功');
                    this.newRule = { name: '', pattern: '', action: 'block' };
                    await this.loadFilterRules();
                } else {
                    MessageManager.error('规则添加失败');
                }
            } catch (error) {
                MessageManager.error('规则添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeRule(ruleId) {
            try {
                const response = await axios.delete(`/api/admin/filter-rules/${ruleId}`);
                if (response.data.success) {
                    MessageManager.success('规则删除成功');
                    await this.loadFilterRules();
                } else {
                    MessageManager.error('规则删除失败');
                }
            } catch (error) {
                MessageManager.error('规则删除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async saveForwardingConfig() {
            try {
                // 处理目标频道名称，统一格式
                let targetChannel = this.forwardingConfig.target_channel.trim();
                if (targetChannel && !targetChannel.startsWith('@') && !targetChannel.startsWith('-') && !targetChannel.includes('t.me')) {
                    targetChannel = '@' + targetChannel;
                }
                
                // 处理审核群名称，智能格式化
                let reviewGroup = this.forwardingConfig.review_group.trim();
                // 如果是HTTP/HTTPS链接，保持原样
                if (reviewGroup && (reviewGroup.startsWith('http://') || reviewGroup.startsWith('https://'))) {
                    // 保持链接格式不变
                } else if (reviewGroup && reviewGroup.includes('t.me') && !reviewGroup.startsWith('http')) {
                    // 如果包含t.me但不是完整链接，添加https://前缀
                    reviewGroup = 'https://' + reviewGroup;
                } else if (reviewGroup && !reviewGroup.startsWith('@') && !reviewGroup.startsWith('-') && !reviewGroup.includes('t.me')) {
                    // 如果不是链接且不是ID，添加@符号
                    reviewGroup = '@' + reviewGroup;
                }
                
                console.log('保存转发配置:', {
                    enabled: this.forwardingConfig.enabled,
                    target_channel: targetChannel,
                    review_group: reviewGroup,
                    delay: this.forwardingConfig.delay,
                    conditions: this.forwardingConfig.conditions
                });
                
                // 使用批量更新API
                const configData = {
                    'channels.target_channel_id': targetChannel,
                    'channels.review_group_id': reviewGroup,
                    'review.auto_forward_delay': this.forwardingConfig.delay
                };
                
                // 批量保存配置
                const response = await axios.post('/api/admin/config/batch', configData);
                
                if (!response.data.success) {
                    throw new Error(response.data.message || '批量保存配置失败');
                }
                
                // 如果配置了审核群链接，尝试解析并缓存ID
                if (reviewGroup && (reviewGroup.includes('t.me/+') || reviewGroup.includes('t.me/joinchat/'))) {
                    try {
                        const resolveResponse = await axios.post('/api/admin/resolve-review-group', {
                            review_group_config: reviewGroup
                        });
                        
                        if (resolveResponse.data.success) {
                            console.log('审核群链接解析成功:', resolveResponse.data);
                            MessageManager.success(`转发配置保存成功，审核群ID已解析为: ${resolveResponse.data.resolved_id}`);
                        } else {
                            MessageManager.warning('转发配置保存成功，但审核群链接解析失败，请检查链接或机器人权限');
                        }
                    } catch (error) {
                        console.warn('解析审核群链接失败:', error);
                        MessageManager.warning('转发配置保存成功，但审核群链接解析失败');
                    }
                } else {
                    MessageManager.success('转发配置保存成功');
                }
                
                // 更新配置对象
                this.forwardingConfig.target_channel = targetChannel;
                this.forwardingConfig.review_group = reviewGroup;
                
            } catch (error) {
                console.error('保存转发配置失败:', error);
                MessageManager.error('转发配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async saveSystemConfig() {
            try {
                // 准备保存的配置数据
                const configData = {
                    'channels.history_message_limit': this.systemConfig.history_message_limit,
                    'channels.signature': this.systemConfig.channel_signature
                };
                
                // 批量保存配置
                const response = await axios.post('/api/admin/config/batch', configData);
                
                if (response.data.success) {
                    MessageManager.success('系统配置保存成功');
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
                review_mode: 'manual',
                retention_days: 30,
                max_concurrent: 10,
                log_level: 'info',
                history_message_limit: 50,
                channel_signature: ''
            };
            MessageManager.success('系统配置已重置为默认值');
        },
        
        
        showReviewGroupHelp() {
            // 如果已经有提示在显示，不再弹出新的
            if (this.helpMessageShowing) {
                return;
            }
            
            this.helpMessageShowing = true;
            const messageInstance = ElMessage({
                message: `
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
                `,
                dangerouslyUseHTMLString: true,
                type: 'info',
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
                    const response = await axios.get('/api/config/resolve-group-id', {
                        params: { group_link: this.forwardingConfig.review_group }
                    });
                    if (response.data.success && response.data.group_id) {
                        this.forwardingConfig.resolved_group_id = response.data.group_id;
                    }
                } catch (error) {
                    console.error('解析群ID失败:', error);
                }
            }
        },
        
        // 更新目标频道ID
        async updateTargetChannelId() {
            if (this.forwardingConfig.target_channel) {
                try {
                    const response = await axios.post('/api/config/resolve-target-channel', {
                        target_channel: this.forwardingConfig.target_channel
                    });
                    if (response.data.success && response.data.resolved_id) {
                        this.forwardingConfig.resolved_target_channel_id = response.data.resolved_id;
                        MessageManager.success(`目标频道ID已解析: ${response.data.resolved_id}`);
                    }
                } catch (error) {
                    console.error('解析目标频道ID失败:', error);
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
                const response = await axios.get('/api/admin/search-channels', {
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
                console.error('搜索频道失败:', error);
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
                    name: channel.username || channel.id.toString(),
                    title: channel.title,
                    channel_id: channel.id.toString()
                };
                
                const response = await axios.post('/api/admin/add-channel', channelData);
                
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
                console.error('添加频道失败:', error);
                MessageManager.error('添加频道失败: ' + (error.response?.data?.detail || error.message));
            }
        }
    }
};

// 等待 DOM 加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, mounting Vue app...');
    
    // 创建应用实例
    console.log('Vue version:', Vue.version);
    console.log('ElementPlus version:', ElementPlus.version);

    try {
        const app = createApp(ConfigApp);
        app.use(ElementPlus);
        
        // 注册导航栏组件
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }

        // 添加错误处理
        app.config.errorHandler = (err, vm, info) => {
            console.error('Vue Error:', err);
            console.error('Error Info:', info);
        };

        // 检查目标元素是否存在
        const targetElement = document.getElementById('app');
        if (!targetElement) {
            console.error('Target element #app not found!');
            return;
        }

        // 挂载应用
        app.mount('#app');
        console.log('Vue app mounted successfully');
    } catch (error) {
        console.error('Failed to mount Vue app:', error);
        document.body.innerHTML = '<div style="color: red; padding: 20px;">Vue 应用挂载失败: ' + error.message + '</div>';
    }
}); 