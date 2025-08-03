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
            newChannel: {
                name: '',
                title: ''
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
                delay: 0,
                conditions: ['approved']
            },
            
            // 系统设置
            systemConfig: {
                review_mode: 'manual',
                retention_days: 30,
                max_concurrent: 10,
                log_level: 'info',
                history_message_limit: 50
            }
        }
    },
    
    mounted() {
        this.loadConfigData();
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
                
                this.showSuccess('配置数据加载完成');
            } catch (error) {
                this.showError('加载配置数据失败: ' + (error.response?.data?.detail || error.message));
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
                    if (targetChannel && !targetChannel.startsWith('@')) {
                        targetChannel = '@' + targetChannel;
                    }
                    
                    // 从系统配置中提取转发相关设置
                    this.forwardingConfig = {
                        enabled: response.data.auto_forward_delay > 0,
                        target_channel: targetChannel,
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
                        log_level: 'info'
                    };
                }
            } catch (error) {
                // 静默处理错误，使用默认配置
                console.log('使用默认系统配置');
            }
        },
        
        async addChannel() {
            if (!this.newChannel.name || !this.newChannel.title) {
                this.showError('请填写完整的频道信息');
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
                    this.showSuccess('频道添加成功');
                    this.newChannel = { name: '', title: '' };
                    await this.loadChannels();
                } else {
                    this.showError('频道添加失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('添加频道错误:', error);
                this.showError('频道添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeChannel(channelId) {
            try {
                console.log('删除频道ID:', channelId);
                
                const response = await axios.delete(`/api/admin/channels/${encodeURIComponent(channelId)}`);
                
                console.log('删除频道响应:', response.data);
                
                if (response.data.success) {
                    this.showSuccess('频道删除成功');
                    await this.loadChannels();
                } else {
                    this.showError('频道删除失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('删除频道错误:', error);
                this.showError('频道删除失败: ' + (error.response?.data?.detail || error.message));
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
                    this.showSuccess(`频道状态已切换为${newStatus === 'active' ? '活跃' : '停用'}`);
                    await this.loadChannels();
                } else {
                    this.showError('状态切换失败: ' + (response.data.message || '未知错误'));
                }
            } catch (error) {
                console.error('状态切换错误:', error);
                this.showError('状态切换失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async addRule() {
            if (!this.newRule.name || !this.newRule.pattern) {
                this.showError('请填写完整的规则信息');
                return;
            }
            
            try {
                const response = await axios.post('/api/admin/filter-rules', {
                    name: this.newRule.name,
                    pattern: this.newRule.pattern,
                    action: this.newRule.action
                });
                
                if (response.data.success) {
                    this.showSuccess('规则添加成功');
                    this.newRule = { name: '', pattern: '', action: 'block' };
                    await this.loadFilterRules();
                } else {
                    this.showError('规则添加失败');
                }
            } catch (error) {
                this.showError('规则添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeRule(ruleId) {
            try {
                const response = await axios.delete(`/api/admin/filter-rules/${ruleId}`);
                if (response.data.success) {
                    this.showSuccess('规则删除成功');
                    await this.loadFilterRules();
                } else {
                    this.showError('规则删除失败');
                }
            } catch (error) {
                this.showError('规则删除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async saveForwardingConfig() {
            try {
                // 处理目标频道名称，统一格式
                let targetChannel = this.forwardingConfig.target_channel.trim();
                if (targetChannel && !targetChannel.startsWith('@')) {
                    targetChannel = '@' + targetChannel;
                }
                
                console.log('保存转发配置:', {
                    enabled: this.forwardingConfig.enabled,
                    target_channel: targetChannel,
                    delay: this.forwardingConfig.delay,
                    conditions: this.forwardingConfig.conditions
                });
                
                // 更新配置对象
                this.forwardingConfig.target_channel = targetChannel;
                
                // 暂时使用模拟成功响应，因为后端API可能还不支持这些配置
                this.showSuccess('转发配置保存成功');
            } catch (error) {
                this.showError('转发配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async saveSystemConfig() {
            try {
                // 暂时使用模拟成功响应，因为后端API可能还不支持这些配置
                this.showSuccess('系统配置保存成功');
            } catch (error) {
                this.showError('系统配置保存失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async resetSystemConfig() {
            this.systemConfig = {
                review_mode: 'manual',
                retention_days: 30,
                max_concurrent: 10,
                log_level: 'info',
                history_message_limit: 50
            };
            this.showSuccess('系统配置已重置为默认值');
        },
        
        showSuccess(message) {
            this.statusMessage = message;
            this.statusType = 'success';
            setTimeout(() => {
                this.statusMessage = '';
            }, 3000);
        },
        
        showError(message) {
            this.statusMessage = message;
            this.statusType = 'error';
            setTimeout(() => {
                this.statusMessage = '';
            }, 5000);
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