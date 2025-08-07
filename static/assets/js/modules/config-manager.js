/**
 * 配置管理模块
 * 处理系统配置的加载、更新和验证
 */
class ConfigManager {
    constructor() {
        this.configs = {};
        this.forwardingConfig = {
            enabled: false,
            target_channel: '',
            review_group: '',
            resolved_group_id: '',
            resolved_target_channel_id: '',
            delay: 0,
            conditions: ['approved']
        };
    }

    // 加载所有配置
    async loadAllConfigs() {
        const result = await apiClient.get('/config/');
        
        if (result.success) {
            this.configs = result.data.configs || {};
            this._extractForwardingConfig();
            return this.configs;
        } else {
            throw new Error(result.message);
        }
    }

    // 获取单个配置
    async getConfig(key) {
        const result = await apiClient.get(`/config/${key}`);
        
        if (result.success) {
            return result.data.value;
        } else {
            throw new Error(result.message);
        }
    }

    // 更新配置
    async updateConfig(key, value, description = '') {
        const result = await apiClient.put(`/config/${key}`, {
            value: value,
            description: description
        });
        
        if (result.success) {
            // 更新本地配置缓存
            if (this.configs[key]) {
                this.configs[key].value = value;
                this.configs[key].description = description;
            }
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 创建新配置
    async createConfig(key, value, description = '', configType = 'string') {
        const result = await apiClient.post('/config/', {
            key: key,
            value: value,
            description: description,
            config_type: configType
        });
        
        if (result.success) {
            // 重新加载配置
            await this.loadAllConfigs();
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 解析Telegram链接
    async resolveTelegramLink(link) {
        const result = await apiClient.post('/config/resolve_telegram_link', {
            link: link
        });
        
        if (result.success) {
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 测试转发配置
    async testForwardingConfig() {
        const result = await apiClient.post('/config/test_forwarding');
        
        if (result.success) {
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 从配置中提取转发配置
    _extractForwardingConfig() {
        this.forwardingConfig = {
            enabled: this._getConfigValue('forwarding.enabled', false),
            target_channel: this._getConfigValue('forwarding.target_channel', ''),
            review_group: this._getConfigValue('forwarding.review_group', ''),
            resolved_group_id: this._getConfigValue('forwarding.resolved_group_id', ''),
            resolved_target_channel_id: this._getConfigValue('forwarding.resolved_target_channel_id', ''),
            delay: this._getConfigValue('forwarding.delay', 0),
            conditions: this._getConfigValue('forwarding.conditions', ['approved'])
        };
    }

    // 获取配置值的辅助方法
    _getConfigValue(key, defaultValue = null) {
        const config = this.configs[key];
        return config ? config.value : defaultValue;
    }

    // 验证必要配置
    validateConfigs() {
        const requiredConfigs = [
            'telegram.api_id',
            'telegram.api_hash',
            'telegram.session'
        ];
        
        const missing = [];
        for (const key of requiredConfigs) {
            if (!this._getConfigValue(key)) {
                missing.push(key);
            }
        }
        
        return {
            valid: missing.length === 0,
            missing: missing
        };
    }

    // 格式化配置用于显示
    formatConfigForDisplay(key, config) {
        const sensitiveKeys = ['telegram.session', 'telegram.api_hash'];
        const isSensitive = sensitiveKeys.some(sensitiveKey => key.includes(sensitiveKey));
        
        return {
            key: key,
            value: isSensitive ? '***' : config.value,
            actualValue: config.value,
            description: config.description || '',
            type: config.config_type || 'string',
            isSensitive: isSensitive
        };
    }
}

// 全局配置管理器实例
window.configManager = new ConfigManager();