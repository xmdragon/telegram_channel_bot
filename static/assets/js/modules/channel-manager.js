/**
 * 频道管理模块
 * 处理频道相关的所有操作
 */
class ChannelManager {
    constructor() {
        this.channels = [];
        this.searchResults = [];
    }

    // 加载频道列表
    async loadChannels(searchFilter = '') {
        const params = searchFilter ? { search: searchFilter } : {};
        const result = await apiClient.get('/admin/channels', { params });
        
        if (result.success) {
            this.channels = result.data.channels || [];
            return this.channels;
        } else {
            throw new Error(result.message);
        }
    }

    // 搜索频道
    async searchChannels(query) {
        const result = await apiClient.get('/admin/search_channels', {
            params: { query }
        });
        
        if (result.success) {
            this.searchResults = result.data.channels || [];
            return this.searchResults;
        } else {
            throw new Error(result.message);
        }
    }

    // 添加频道
    async addChannel(channelData) {
        const result = await apiClient.post('/admin/channels', channelData);
        
        if (result.success) {
            // 重新加载频道列表
            await this.loadChannels();
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 更新频道
    async updateChannel(channelId, updateData) {
        const result = await apiClient.put(`/admin/channels/${channelId}`, updateData);
        
        if (result.success) {
            // 重新加载频道列表
            await this.loadChannels();
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 删除频道
    async deleteChannel(channelId) {
        const result = await apiClient.delete(`/admin/channels/${channelId}`);
        
        if (result.success) {
            // 重新加载频道列表
            await this.loadChannels();
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 过滤频道列表
    filterChannels(channels, filter) {
        if (!filter) return channels;
        
        const filterLower = filter.toLowerCase();
        return channels.filter(channel => {
            const name = (channel.name || '').toLowerCase();
            const title = (channel.title || '').toLowerCase();
            return name.includes(filterLower) || title.includes(filterLower);
        });
    }

    // 格式化频道显示
    formatChannelForDisplay(channel) {
        return {
            ...channel,
            statusText: channel.status === 'active' ? '活跃' : '停用',
            statusClass: channel.status === 'active' ? 'success' : 'danger'
        };
    }
}

// 全局频道管理器实例
window.channelManager = new ChannelManager();