/**
 * AI配置管理组件
 * 管理AI功能的开关、模式选择和缓存管理
 */

const { createApp } = Vue;

const AIConfigApp = createApp({
    data() {
        return {
            loading: false,
            saving: false,
            clearing: false,
            training: false,
            
            // AI状态数据
            aiStatus: {
                ai_enabled: false,
                startup_mode: '',
                modules: {},
                dependencies: {},
                cache_info: {},
                lightweight_available: true,
                recommendations: []
            },
            
            // 全局配置
            globalConfig: {
                ai_mode: 'auto'
            },
            
            // 模块列表
            moduleList: [],
            
            // 配置建议
            recommendations: [],
            
            // UI状态
            statusMessage: '',
            statusType: '',
            loadingMessage: '加载中...'
        }
    },
    
    mounted() {
        this.initPage();
    },
    
    methods: {
        /**
         * 初始化页面
         */
        async initPage() {
            await this.refreshStatus();
        },
        
        /**
         * 刷新AI状态
         */
        async refreshStatus() {
            this.loading = true;
            try {
                const response = await axios.get(window.API.aiConfig.status);
                
                if (response.data.success) {
                    this.aiStatus = response.data.data;
                    this.updateModuleList();
                    this.recommendations = this.aiStatus.recommendations || [];
                    
                    // 根据当前状态推断全局模式
                    this.inferGlobalMode();
                    
                    this.showStatusMessage('状态刷新成功', 'success');
                } else {
                    throw new Error(response.data.message || '获取状态失败');
                }
            } catch (error) {
                console.error('刷新状态失败:', error);
                this.showStatusMessage('刷新状态失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.loading = false;
            }
        },
        
        /**
         * 更新模块列表
         */
        updateModuleList() {
            this.moduleList = Object.entries(this.aiStatus.modules || {}).map(([name, config]) => ({
                name,
                description: config.description,
                enabled: config.enabled,
                mode: config.configured_mode,
                actual_mode: config.actual_mode,
                is_working: config.is_working,
                fallback_to_lightweight: config.fallback_to_lightweight
            }));
        },
        
        /**
         * 推断全局模式
         */
        inferGlobalMode() {
            const modules = Object.values(this.aiStatus.modules || {});
            
            if (modules.every(m => !m.enabled)) {
                this.globalConfig.ai_mode = 'disabled';
            } else {
                // 取最常见的模式
                const modes = modules.filter(m => m.enabled).map(m => m.configured_mode);
                const modeCount = {};
                modes.forEach(mode => {
                    modeCount[mode] = (modeCount[mode] || 0) + 1;
                });
                
                const mostCommonMode = Object.keys(modeCount).reduce((a, b) => 
                    modeCount[a] > modeCount[b] ? a : b, 'auto'
                );
                
                this.globalConfig.ai_mode = mostCommonMode;
            }
        },
        
        /**
         * 更新全局配置
         */
        async updateGlobalConfig() {
            this.saving = true;
            try {
                const response = await axios.post(window.API.aiConfig.globalConfig, this.globalConfig);
                
                if (response.data.success) {
                    this.showStatusMessage('全局配置更新成功', 'success');
                    await this.refreshStatus();
                } else {
                    throw new Error(response.data.message || '更新配置失败');
                }
            } catch (error) {
                console.error('更新全局配置失败:', error);
                this.showStatusMessage('更新全局配置失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.saving = false;
            }
        },
        
        /**
         * 更新模块配置
         */
        async updateModuleConfig(moduleName, enabled, mode) {
            try {
                const config = {
                    module_name: moduleName,
                    enabled: enabled,
                    mode: mode
                };
                
                const response = await axios.post(window.API.aiConfig.moduleConfig, config);
                
                if (response.data.success) {
                    this.showStatusMessage(`模块 ${moduleName} 配置更新成功`, 'success');
                    // 延迟刷新状态，让配置生效
                    setTimeout(() => {
                        this.refreshStatus();
                    }, 500);
                } else {
                    throw new Error(response.data.message || '更新模块配置失败');
                }
            } catch (error) {
                console.error('更新模块配置失败:', error);
                this.showStatusMessage('更新模块配置失败: ' + (error.response?.data?.detail || error.message), 'error');
                // 回滚配置
                await this.refreshStatus();
            }
        },
        
        /**
         * 清理模型缓存
         */
        async clearModelCache() {
            try {
                if (!confirm('清理缓存将删除所有已下载的模型文件，下次使用时需要重新下载。确定要继续吗？')) {
                    return;
                }
                
                this.clearing = true;
                const response = await axios.post(window.API.aiConfig.cacheClear);
                
                if (response.data.success) {
                    const freedMB = response.data.data.freed_mb;
                    this.showStatusMessage(`缓存清理成功，释放空间 ${freedMB} MB`, 'success');
                    await this.refreshStatus();
                } else {
                    throw new Error(response.data.message || '清理缓存失败');
                }
            } catch (error) {
                console.error('清理模型缓存失败:', error);
                this.showStatusMessage('清理模型缓存失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.clearing = false;
            }
        },
        
        /**
         * 训练轻量级模型
         */
        async trainLightweight() {
            try {
                if (!confirm('训练轻量级模型需要足够的训练数据。请确认已收集足够的广告和正常内容样本。')) {
                    return;
                }
                
                this.training = true;
                const response = await axios.post(window.API.aiConfig.lightweightTrain);
                
                if (response.data.success) {
                    this.showStatusMessage('轻量级模型训练成功', 'success');
                    await this.refreshStatus();
                } else {
                    this.showStatusMessage(response.data.message || '训练失败', 'warning');
                }
            } catch (error) {
                console.error('训练轻量级模型失败:', error);
                this.showStatusMessage('训练轻量级模型失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.training = false;
            }
        },
        
        /**
         * 应用推荐配置
         */
        async applyRecommendation(recommendation) {
            try {
                const action = recommendation.action;
                
                if (action.type === 'install') {
                    // 显示安装命令
                    alert(`请在服务器上执行以下命令：\n\n${action.command}`);
                } else if (action.type === 'config') {
                    // 应用配置建议
                    if (action.module) {
                        // 更新单个模块
                        const module = this.moduleList.find(m => m.name === action.module);
                        if (module) {
                            module.mode = action.suggested_mode;
                            await this.updateModuleConfig(action.module, module.enabled, action.suggested_mode);
                        }
                    } else if (action.suggested_mode) {
                        // 更新全局模式
                        this.globalConfig.ai_mode = action.suggested_mode;
                        await this.updateGlobalConfig();
                    }
                }
            } catch (error) {
                console.error('应用推荐配置失败:', error);
                this.showStatusMessage('应用推荐配置失败: ' + error.message, 'error');
            }
        },
        
        /**
         * 获取模式描述
         */
        getModeDescription(mode) {
            const descriptions = {
                'auto': '自动选择最适合的模式，优先使用轻量级高效算法',
                'lightweight': '使用优化算法实现高效文本处理，无外部依赖，启动快速',
                'deep': '已弃用 - 系统已优化为轻量级模式',
                'disabled': '完全禁用功能，仅使用基础规则匹配'
            };
            return descriptions[mode] || '未知模式';
        },
        
        /**
         * 获取实际模式的标签类型
         */
        getActualModeType(mode) {
            const types = {
                'deep': 'success',
                'lightweight': 'warning',
                'rule_based': 'info',
                'disabled': 'danger'
            };
            return types[mode] || 'info';
        },
        
        /**
         * 获取实际模式的Badge类
         */
        getActualModeBadgeClass(mode) {
            const classes = {
                'deep': 'badge-success',
                'lightweight': 'badge-warning',
                'rule_based': 'badge-info',
                'disabled': 'badge-danger'
            };
            return classes[mode] || 'badge-info';
        },
        
        /**
         * 获取警告类
         */
        getAlertClass(type) {
            const classes = {
                'success': 'alert-success',
                'info': 'alert-info',
                'warning': 'alert-warning',
                'error': 'alert-danger'
            };
            return classes[type] || 'alert-info';
        },
        
        /**
         * 获取警告图标
         */
        getAlertIcon(type) {
            const icons = {
                'success': '✅',
                'info': 'ℹ️',
                'warning': '⚠️',
                'error': '❌'
            };
            return icons[type] || 'ℹ️';
        },
        
        /**
         * 显示状态消息
         */
        showStatusMessage(message, type = 'info') {
            this.statusMessage = message;
            this.statusType = type;
            
            // 3秒后自动清除消息
            setTimeout(() => {
                this.statusMessage = '';
                this.statusType = '';
            }, 3000);
        },
        
        /**
         * 返回主页
         */
        goBack() {
            window.location.href = '/static/index.html';
        }
    }
});

// 挂载应用
AIConfigApp.mount('#app');