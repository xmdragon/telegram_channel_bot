// 配置页面 JavaScript 组件

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

// 配置应用组件
const ConfigApp = {
    data() {
        return {
            loading: false,
            loadingMessage: '',
            saving: false,
            reloading: false,
            statusMessage: '',
            statusType: 'success',
            activeTab: 'telegram',
            
            // 配置数据
            allConfigs: {},
            telegramConfigs: {},
            channelConfigs: {},
            accountsConfigs: {},
            filterConfigs: {},
            reviewConfigs: {},
            systemConfigs: {},
            
            // 频道管理
            newChannel: { id: '', name: '', description: '' },
            channelList: [],
            
            // 关键词管理
            newTextKeyword: '',
            newLineKeyword: '',
            textKeywords: [],
            lineKeywords: [],
            
            // 账号管理
            newWhitelistAccount: '',
            newBlacklistAccount: '',
            whitelistAccounts: [],
            blacklistAccounts: [],
            
            // 统计信息
            channelStats: { total: 0, active: 0 },
            keywordStats: { text: 0, line: 0 },
            accountStats: { collected: 0, blacklist: 0, whitelist: 0 }
        }
    },
    
    mounted() {
        this.loadConfigs();
    },
    
    methods: {
        async loadConfigs() {
            this.loading = true;
            this.loadingMessage = '正在加载配置...';
            
            try {
                const response = await axios.get('/api/config/');
                if (response.data.success) {
                    this.allConfigs = response.data.configs;
                    this.categorizeConfigs();
                    await this.updateChannelList();
                    this.updateKeywordLists();
                    this.updateAccountLists();
                    this.updateStats();
                } else {
                    this.showError('加载配置失败');
                }
            } catch (error) {
                this.showError('加载配置失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        categorizeConfigs() {
            this.telegramConfigs = {};
            this.channelConfigs = {};
            this.accountsConfigs = {};
            this.filterConfigs = {};
            this.reviewConfigs = {};
            this.systemConfigs = {};
            
            for (const [key, config] of Object.entries(this.allConfigs)) {
                // 确保配置项有正确的结构
                const configItem = {
                    value: config.value,
                    description: config.description || '',
                    config_type: config.config_type || 'string'
                };
                
                if (key.startsWith('telegram.')) {
                    this.telegramConfigs[key] = configItem;
                } else if (key.startsWith('channels.')) {
                    this.channelConfigs[key] = configItem;
                } else if (key.startsWith('accounts.')) {
                    this.accountsConfigs[key] = configItem;
                } else if (key.startsWith('filter.')) {
                    this.filterConfigs[key] = configItem;
                } else if (key.startsWith('review.')) {
                    this.reviewConfigs[key] = configItem;
                } else if (key.startsWith('system.')) {
                    this.systemConfigs[key] = configItem;
                }
            }
        },
        
        async updateChannelList() {
            try {
                const response = await axios.get('/api/config/channels/');
                if (response.data.success) {
                    this.channelList = response.data.channels.map(channel => ({
                        id: channel.channel_id,
                        name: channel.channel_name,
                        enabled: channel.is_active,
                        description: channel.description
                    }));
                }
            } catch (error) {
                console.error('获取频道列表失败:', error);
                this.channelList = [];
            }
        },
        
        updateKeywordLists() {
            this.textKeywords = this.allConfigs['filter.ad_keywords_text']?.value || [];
            this.lineKeywords = this.allConfigs['filter.ad_keywords_line']?.value || [];
        },
        
        updateAccountLists() {
            this.whitelistAccounts = this.allConfigs['accounts.account_whitelist']?.value || [];
            this.blacklistAccounts = this.allConfigs['accounts.account_blacklist']?.value || [];
        },
        
        updateStats() {
            // 频道统计
            this.channelStats.total = this.channelList.length;
            this.channelStats.active = this.channelList.filter(c => c.enabled).length;
            
            // 关键词统计
            this.keywordStats.text = this.textKeywords.length;
            this.keywordStats.line = this.lineKeywords.length;
            
            // 账号统计
            this.accountStats.collected = this.allConfigs['accounts.collected_accounts']?.value?.length || 0;
            this.accountStats.blacklist = this.blacklistAccounts.length;
            this.accountStats.whitelist = this.whitelistAccounts.length;
        },
        
        // 频道管理
        async addChannel() {
            if (!this.newChannel.id) {
                this.showError('请输入频道ID');
                return;
            }
            
            try {
                const response = await axios.post('/api/config/channels/add', {
                    channel_id: this.newChannel.id,
                    channel_name: this.newChannel.name,
                    description: this.newChannel.description || ''
                });
                
                if (response.data.success) {
                    this.showSuccess('频道添加成功');
                    this.newChannel = { id: '', name: '', description: '' };
                    await this.updateChannelList();
                } else {
                    this.showError('频道添加失败');
                }
            } catch (error) {
                this.showError('频道添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeChannel(channelId) {
            try {
                const response = await axios.delete(`/api/config/channels/${channelId}`);
                
                if (response.data.success) {
                    this.showSuccess('频道移除成功');
                    await this.updateChannelList();
                } else {
                    this.showError('频道移除失败');
                }
            } catch (error) {
                this.showError('频道移除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async updateChannelStatus(channelId, enabled) {
            try {
                const response = await axios.put(`/api/config/channels/${channelId}/status`, {
                    enabled: enabled
                });
                
                if (response.data.success) {
                    this.showSuccess('频道状态更新成功');
                    await this.updateChannelList();
                } else {
                    this.showError('频道状态更新失败');
                }
            } catch (error) {
                this.showError('频道状态更新失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 关键词管理
        async addTextKeyword() {
            if (!this.newTextKeyword) {
                this.showError('请输入关键词');
                return;
            }
            
            try {
                const response = await axios.post('/api/config/keywords/text/add', {
                    keyword: this.newTextKeyword
                });
                
                if (response.data.success) {
                    this.showSuccess('关键词添加成功');
                    this.newTextKeyword = '';
                    await this.loadConfigs();
                } else {
                    this.showError('关键词添加失败');
                }
            } catch (error) {
                this.showError('关键词添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeTextKeyword(keyword) {
            try {
                const response = await axios.delete(`/api/config/keywords/text/${encodeURIComponent(keyword)}`);
                
                if (response.data.success) {
                    this.showSuccess('关键词移除成功');
                    await this.loadConfigs();
                } else {
                    this.showError('关键词移除失败');
                }
            } catch (error) {
                this.showError('关键词移除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async addLineKeyword() {
            if (!this.newLineKeyword) {
                this.showError('请输入关键词');
                return;
            }
            
            try {
                const response = await axios.post('/api/config/keywords/line/add', {
                    keyword: this.newLineKeyword
                });
                
                if (response.data.success) {
                    this.showSuccess('关键词添加成功');
                    this.newLineKeyword = '';
                    await this.loadConfigs();
                } else {
                    this.showError('关键词添加失败');
                }
            } catch (error) {
                this.showError('关键词添加失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeLineKeyword(keyword) {
            try {
                const response = await axios.delete(`/api/config/keywords/line/${encodeURIComponent(keyword)}`);
                
                if (response.data.success) {
                    this.showSuccess('关键词移除成功');
                    await this.loadConfigs();
                } else {
                    this.showError('关键词移除失败');
                }
            } catch (error) {
                this.showError('关键词移除失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 账号管理
        async addToWhitelist() {
            if (!this.newWhitelistAccount) {
                this.showError('请输入账号');
                return;
            }
            
            try {
                const response = await axios.post('/api/config/accounts/whitelist/add', {
                    account: this.newWhitelistAccount
                });
                
                if (response.data.success) {
                    this.showSuccess('账号添加到白名单成功');
                    this.newWhitelistAccount = '';
                    await this.loadConfigs();
                } else {
                    this.showError('添加账号到白名单失败');
                }
            } catch (error) {
                this.showError('添加账号到白名单失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeFromWhitelist(account) {
            try {
                const response = await axios.delete(`/api/config/accounts/whitelist/${encodeURIComponent(account)}`);
                
                if (response.data.success) {
                    this.showSuccess('账号从白名单移除成功');
                    await this.loadConfigs();
                } else {
                    this.showError('从白名单移除账号失败');
                }
            } catch (error) {
                this.showError('从白名单移除账号失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async addToBlacklist() {
            if (!this.newBlacklistAccount) {
                this.showError('请输入账号');
                return;
            }
            
            try {
                const response = await axios.post('/api/config/accounts/blacklist/add', {
                    account: this.newBlacklistAccount
                });
                
                if (response.data.success) {
                    this.showSuccess('账号添加到黑名单成功');
                    this.newBlacklistAccount = '';
                    await this.loadConfigs();
                } else {
                    this.showError('添加账号到黑名单失败');
                }
            } catch (error) {
                this.showError('添加账号到黑名单失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async removeFromBlacklist(account) {
            try {
                const response = await axios.delete(`/api/config/accounts/blacklist/${encodeURIComponent(account)}`);
                
                if (response.data.success) {
                    this.showSuccess('账号从黑名单移除成功');
                    await this.loadConfigs();
                } else {
                    this.showError('从黑名单移除账号失败');
                }
            } catch (error) {
                this.showError('从黑名单移除账号失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        // 配置保存
        async saveTelegramConfigs() {
            await this.saveConfigs(this.telegramConfigs, 'Telegram');
        },
        
        async saveChannelConfigs() {
            await this.saveConfigs(this.channelConfigs, '频道');
        },
        
        async saveAccountsConfigs() {
            await this.saveConfigs(this.accountsConfigs, '账号');
        },
        
        async saveFilterConfigs() {
            await this.saveConfigs(this.filterConfigs, '过滤');
        },
        
        async saveSystemConfigs() {
            await this.saveConfigs(this.systemConfigs, '系统');
        },
        
        async saveConfigs(configs, category) {
            this.saving = true;
            
            try {
                const configItems = Object.entries(configs).map(([key, config]) => ({
                    key: key,
                    value: config.value,
                    description: config.description,
                    config_type: config.config_type
                }));
                
                const response = await axios.post('/api/config/batch-update', configItems);
                
                if (response.data.success) {
                    this.showSuccess(`${category}配置保存成功`);
                    await this.loadConfigs(); // 重新加载配置
                } else {
                    this.showError(`${category}配置保存失败`);
                }
            } catch (error) {
                this.showError(`${category}配置保存失败: ` + (error.response?.data?.detail || error.message));
            } finally {
                this.saving = false;
            }
        },
        
        async resetTelegramConfigs() {
            await this.resetConfigs('telegram', 'Telegram');
        },
        
        async resetChannelConfigs() {
            await this.resetConfigs('channels', '频道');
        },
        
        async resetAccountsConfigs() {
            await this.resetConfigs('accounts', '账号');
        },
        
        async resetFilterConfigs() {
            await this.resetConfigs('filter', '过滤');
        },
        
        async resetConfigs(category, categoryName) {
            try {
                const response = await axios.post(`/api/config/categories/${category}`);
                
                if (response.data.success) {
                    this.showSuccess(`${categoryName}配置重置成功`);
                    await this.loadConfigs(); // 重新加载配置
                } else {
                    this.showError(`${categoryName}配置重置失败`);
                }
            } catch (error) {
                this.showError(`${categoryName}配置重置失败: ` + (error.response?.data?.detail || error.message));
            }
        },
        
        async reloadConfigs() {
            this.reloading = true;
            
            try {
                const response = await axios.post('/api/config/reload');
                
                if (response.data.success) {
                    this.showSuccess('配置重新加载成功');
                    await this.loadConfigs(); // 重新加载配置
                } else {
                    this.showError('配置重新加载失败');
                }
            } catch (error) {
                this.showError('配置重新加载失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.reloading = false;
            }
        },
        
        async resetAllConfigs() {
            try {
                const confirmed = await this.$confirm('确定要重置所有配置为默认值吗？此操作不可撤销。', '确认重置', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                if (confirmed) {
                    const response = await axios.post('/api/config/reset-defaults');
                    
                    if (response.data.success) {
                        this.showSuccess('所有配置重置成功');
                        await this.loadConfigs(); // 重新加载配置
                    } else {
                        this.showError('配置重置失败');
                    }
                }
            } catch (error) {
                if (error !== 'cancel') {
                    this.showError('配置重置失败: ' + (error.response?.data?.detail || error.message));
                }
            }
        },
        
        exportConfigs() {
            const configData = {
                timestamp: new Date().toISOString(),
                configs: this.allConfigs
            };
            
            const dataStr = JSON.stringify(configData, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });
            
            const link = document.createElement('a');
            link.href = URL.createObjectURL(dataBlob);
            link.download = `telegram_config_${new Date().toISOString().split('T')[0]}.json`;
            link.click();
            
            this.showSuccess('配置导出成功');
        },
        
        importConfigs() {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.json';
            
            input.onchange = async (event) => {
                const file = event.target.files[0];
                if (!file) return;
                
                try {
                    const text = await file.text();
                    const configData = JSON.parse(text);
                    
                    if (configData.configs) {
                        // 这里可以实现导入逻辑
                        this.showSuccess('配置导入功能开发中...');
                    } else {
                        this.showError('配置文件格式错误');
                    }
                } catch (error) {
                    this.showError('配置文件读取失败: ' + error.message);
                }
            };
            
            input.click();
        },
        
        handleTabClick(tab) {
            this.activeTab = tab.name;
        },
        
        goToMain() {
            window.location.href = '/';
        },
        
        goToStatus() {
            window.location.href = '/status';
        },
        
        goToAuth() {
            window.location.href = '/auth';
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

// 导出组件
window.ConfigApp = ConfigApp; 