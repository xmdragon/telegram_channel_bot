/**
 * AI配置管理组件
 * 管理AI功能的开关、模式选择和缓存管理
 */

const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

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
            recommendations: []
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
                    
                    ElMessage.success('状态刷新成功');
                } else {
                    throw new Error(response.data.message || '获取状态失败');
                }
            } catch (error) {
                console.error('刷新状态失败:', error);
                ElMessage.error('刷新状态失败: ' + (error.response?.data?.detail || error.message));
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
                    ElMessage.success('全局配置更新成功');
                    await this.refreshStatus();
                } else {
                    throw new Error(response.data.message || '更新配置失败');
                }
            } catch (error) {
                console.error('更新全局配置失败:', error);
                ElMessage.error('更新全局配置失败: ' + (error.response?.data?.detail || error.message));
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
                    ElMessage.success(`模块 ${moduleName} 配置更新成功`);
                    // 延迟刷新状态，让配置生效
                    setTimeout(() => {
                        this.refreshStatus();
                    }, 500);
                } else {
                    throw new Error(response.data.message || '更新模块配置失败');
                }
            } catch (error) {
                console.error('更新模块配置失败:', error);
                ElMessage.error('更新模块配置失败: ' + (error.response?.data?.detail || error.message));
                // 回滚配置
                await this.refreshStatus();
            }
        },
        
        /**
         * 清理模型缓存
         */
        async clearModelCache() {
            try {
                await ElMessageBox.confirm(
                    '清理缓存将删除所有已下载的模型文件，下次使用时需要重新下载。确定要继续吗？',
                    '确认清理缓存',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                this.clearing = true;
                const response = await axios.post(window.API.aiConfig.cacheClear);
                
                if (response.data.success) {
                    const freedMB = response.data.data.freed_mb;
                    ElMessage.success(`缓存清理成功，释放空间 ${freedMB} MB`);
                    await this.refreshStatus();
                } else {
                    throw new Error(response.data.message || '清理缓存失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('清理模型缓存失败:', error);
                    ElMessage.error('清理模型缓存失败: ' + (error.response?.data?.detail || error.message));
                }
            } finally {
                this.clearing = false;
            }
        },
        
        /**
         * 训练轻量级模型
         */
        async trainLightweight() {
            try {
                await ElMessageBox.confirm(
                    '训练轻量级模型需要足够的训练数据。请确认已收集足够的广告和正常内容样本。',
                    '确认训练模型',
                    {
                        confirmButtonText: '开始训练',
                        cancelButtonText: '取消',
                        type: 'info'
                    }
                );
                
                this.training = true;
                const response = await axios.post(window.API.aiConfig.lightweightTrain);
                
                if (response.data.success) {
                    ElMessage.success('轻量级模型训练成功');
                    await this.refreshStatus();
                } else {
                    ElMessage.warning(response.data.message || '训练失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('训练轻量级模型失败:', error);
                    ElMessage.error('训练轻量级模型失败: ' + (error.response?.data?.detail || error.message));
                }
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
                    await ElMessageBox.alert(
                        `请在服务器上执行以下命令：\n\n${action.command}`,
                        '安装依赖',
                        {
                            confirmButtonText: '知道了'
                        }
                    );
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
                ElMessage.error('应用推荐配置失败: ' + error.message);
            }
        },
        
        /**
         * 获取模式描述
         */
        getModeDescription(mode) {
            const descriptions = {
                'auto': '自动选择最适合的模式，如果有sentence_transformers则使用深度学习，否则使用轻量级模式',
                'lightweight': '使用TF-IDF+SVD实现的轻量级语义分析，无需额外依赖，启动快速',
                'deep': '使用sentence_transformers深度学习模型，准确率最高但需要额外依赖',
                'disabled': '完全禁用AI功能，仅使用规则匹配'
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
         * 返回主页
         */
        goBack() {
            window.location.href = '/static/index.html';
        }
    }
});

// 使用Element Plus
AIConfigApp.use(ElementPlus);

// 挂载应用
AIConfigApp.mount('#app');