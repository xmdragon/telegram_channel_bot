/**
 * 事件处理器模块 - 集中管理所有事件处理逻辑
 * 遵循Linus"好品味"原则：消除复杂的事件分支逻辑
 */

const EventHandlers = {
    // 事件监听器注册表
    listeners: new Map(),
    
    // 注册事件监听器
    register(eventName, handler) {
        if (!this.listeners.has(eventName)) {
            this.listeners.set(eventName, new Set());
        }
        this.listeners.get(eventName).add(handler);
    },
    
    // 注销事件监听器
    unregister(eventName, handler) {
        if (this.listeners.has(eventName)) {
            this.listeners.get(eventName).delete(handler);
        }
    },
    
    // 触发事件
    emit(eventName, ...args) {
        if (this.listeners.has(eventName)) {
            this.listeners.get(eventName).forEach(handler => {
                try {
                    handler(...args);
                } catch (error) {
                    console.error(`事件处理器错误 [${eventName}]:`, error);
                }
            });
        }
    },
    
    // 清理所有监听器
    cleanup() {
        this.listeners.clear();
    },
    
    // 消息列表事件处理
    messageList: {
        // 处理消息加载
        async handleLoad(context, options = {}) {
            const { append = false, showLoading = true } = options;
            
            // 防重复加载保护
            if (context.state._isProcessingAction || window._globalProcessingAction) {
                return;
            }
            
            try {
                if (showLoading) {
                    if (append) {
                        window.StateManager.transitionToLoadingMore(context.state);
                    } else {
                        window.StateManager.transitionToLoading(context.state, '正在加载消息数据...');
                        window.StateManager.resetMessagesState(context.state);
                    }
                }
                
                // 准备请求参数
                const params = {
                    ...context.state.filters,
                    page: context.state.currentPage,
                    size: context.state.pageSize,
                    show_duplicates: context.state.filters._show_duplicates || false
                };
                
                // 处理搜索关键词
                if (context.state.searchKeyword?.trim()) {
                    params.search = context.state.searchKeyword.trim();
                }
                
                // 调用API
                const result = await window.ApiClient.messages.list(params);
                
                if (result.success && result.data?.data?.messages) {
                    const newMessages = result.data.data.messages;
                    
                    // 更新状态
                    window.StateManager.addMessages(context.state, newMessages, append);
                    context.state.hasMore = newMessages.length === context.state.pageSize;
                    
                    // 触发消息加载完成事件
                    EventHandlers.emit('messages:loaded', {
                        messages: newMessages,
                        append,
                        hasMore: context.state.hasMore
                    });
                    
                    // 显示加载反馈
                    if (append && newMessages.length > 0) {
                        window.MessageManager?.success(`收到 ${newMessages.length} 条新消息`);
                    } else if (!append && context.state.filters.source_channel) {
                        const channelInfo = context.channels[context.state.filters.source_channel];
                        const channelName = window.DataUtils?.getChannelDisplayName(channelInfo) || context.state.filters.source_channel;
                        window.MessageManager?.info(`已切换到「${channelName}」，共 ${newMessages.length} 条消息`);
                    }
                    
                } else {
                    window.StateManager.resetMessagesState(context.state);
                    window.MessageManager?.warning('暂无消息数据');
                }
                
            } catch (error) {
                console.error('加载消息失败:', error);
                window.StateManager.resetMessagesState(context.state);
                window.MessageManager?.error('加载消息失败: ' + (error.details?.detail || error.error));
            } finally {
                window.StateManager.transitionToIdle(context.state);
            }
        },
        
        // 处理滚动加载更多
        async handleLoadMore(context) {
            if (context.state.isLoadingMore || !context.state.hasMore) {
                return;
            }
            
            context.state.currentPage++;
            await this.handleLoad(context, { append: true, showLoading: false });
        },
        
        // 处理搜索
        async handleSearch(context, keyword) {
            context.state.searchKeyword = keyword || '';
            window.StateManager.resetPaginationState(context.state);
            await this.handleLoad(context);
        },
        
        // 处理筛选变更
        async handleFilterChange(context, filterKey, filterValue) {
            window.StateManager.updateFilter(context.state, filterKey, filterValue);
            window.StateManager.resetPaginationState(context.state);
            await this.handleLoad(context);
        }
    },
    
    // 消息操作事件处理
    messageOperations: {
        // 处理单个消息审核
        async handleApprove(context, messageId) {
            try {
                window.StateManager.transitionToProcessing(context.state, messageId);
                
                const result = await window.ApiClient.messages.approve(messageId);
                
                if (result.success) {
                    window.MessageManager?.success('消息已发布');
                    
                    // 更新本地状态
                    if (context.state.filters.status === 'pending') {
                        window.StateManager.removeMessage(context.state, messageId);
                    } else {
                        window.StateManager.updateMessageStatus(context.state, messageId, 'approved');
                    }
                    
                    // 触发统计更新
                    EventHandlers.emit('stats:update');
                    
                } else {
                    throw new Error(result.error);
                }
                
            } catch (error) {
                console.error('审核消息失败:', error);
                window.MessageManager?.error('审核失败: ' + error.message);
            } finally {
                window.StateManager.transitionToIdle(context.state, messageId);
            }
        },
        
        // 处理单个消息拒绝
        async handleReject(context, messageId) {
            try {
                window.StateManager.transitionToProcessing(context.state, messageId);
                
                const result = await window.ApiClient.messages.reject(messageId);
                
                if (result.success) {
                    window.MessageManager?.success('消息已拒绝');
                    
                    // 更新本地状态
                    if (context.state.filters.status === 'pending') {
                        window.StateManager.removeMessage(context.state, messageId);
                    } else {
                        window.StateManager.updateMessageStatus(context.state, messageId, 'rejected');
                    }
                    
                    // 触发统计更新
                    EventHandlers.emit('stats:update');
                    
                } else {
                    throw new Error(result.error);
                }
                
            } catch (error) {
                console.error('拒绝消息失败:', error);
                window.MessageManager?.error('拒绝失败: ' + error.message);
            } finally {
                window.StateManager.transitionToIdle(context.state, messageId);
            }
        },
        
        // 处理批量操作
        async handleBatchOperation(context, operation, successMessage) {
            if (context.state.selectedMessages.length === 0) {
                window.MessageManager?.warning('请先选择要操作的消息');
                return;
            }
            
            try {
                // 标记正在处理的消息
                context.state.selectedMessages.forEach(id => {
                    window.StateManager.transitionToProcessing(context.state, id);
                });
                
                const result = await operation(context.state.selectedMessages);
                
                if (result.success) {
                    window.MessageManager?.success(successMessage + ` ${context.state.selectedMessages.length} 条消息`);
                    
                    // 清除选择并刷新
                    window.StateManager.clearSelection(context.state);
                    await EventHandlers.messageList.handleLoad(context);
                    EventHandlers.emit('stats:update');
                    
                } else {
                    throw new Error(result.error);
                }
                
            } catch (error) {
                console.error('批量操作失败:', error);
                window.MessageManager?.error('操作失败: ' + error.message);
            } finally {
                // 清理处理状态
                context.state.selectedMessages.forEach(id => {
                    window.StateManager.transitionToIdle(context.state, id);
                });
            }
        }
    },
    
    // UI交互事件处理
    ui: {
        // 处理消息选择
        handleMessageSelection(context, messageId) {
            window.StateManager.toggleMessageSelection(context.state, messageId);
            EventHandlers.emit('selection:changed', {
                messageId,
                selectedCount: context.state.selectedMessages.length
            });
        },
        
        // 处理全选
        handleSelectAll(context) {
            window.StateManager.selectAllVisible(context.state);
            EventHandlers.emit('selection:changed', {
                selectAll: true,
                selectedCount: context.state.selectedMessages.length
            });
        },
        
        // 处理清除选择
        handleClearSelection(context) {
            window.StateManager.clearSelection(context.state);
            EventHandlers.emit('selection:changed', {
                cleared: true,
                selectedCount: 0
            });
        },
        
        // 处理媒体预览
        handleMediaPreview(context, url) {
            if (window.UIHandlers?.openMediaPreview) {
                window.UIHandlers.openMediaPreview(url);
            } else if (window.DataUtils?.getFileType) {
                const fileType = window.DataUtils.getFileType(url);
                if (fileType === 'video') {
                    // 对于视频文件，显示详情而不是预览
                    context.state.fileDetailsDialog = {
                        visible: true,
                        details: {
                            url: url,
                            fileName: window.UIHandlers?.extractFileName(url) || '视频文件',
                            fileType: 'video'
                        }
                    };
                } else {
                    // 图片等直接预览
                    context.state.mediaPreview = {
                        show: true,
                        url: url
                    };
                }
            }
        },
        
        // 处理对话框关闭
        handleCloseDialog(context, dialogType) {
            switch (dialogType) {
                case 'mediaPreview':
                    context.state.mediaPreview.show = false;
                    context.state.mediaPreview.url = null;
                    break;
                case 'fileDetails':
                    context.state.fileDetailsDialog.visible = false;
                    context.state.fileDetailsDialog.details = null;
                    break;
                case 'edit':
                    context.state.editDialog.visible = false;
                    context.state.editDialog.messageId = null;
                    context.state.editDialog.filteredContent = '';
                    context.state.editDialog.originalMessage = null;
                    break;
            }
        }
    },
    
    // WebSocket事件处理
    websocket: {
        // 处理WebSocket消息
        handleMessage(context, data) {
            try {
                switch (data.type) {
                    case 'new_message':
                        this.handleNewMessage(context, data.data);
                        break;
                    case 'message_updated':
                        this.handleMessageUpdated(context, data.data);
                        break;
                    case 'stats_updated':
                        this.handleStatsUpdated(context, data.data);
                        break;
                    default:
                }
            } catch (error) {
                console.error('处理WebSocket消息失败:', error);
            }
        },
        
        // 处理新消息
        handleNewMessage(context, messageData) {
            // 只有在待审核状态下才显示新消息
            if (context.state.filters.status === 'pending' && messageData.status === 'pending') {
                // 添加到消息列表开头
                context.state.messages.unshift(messageData);
                
                // 限制列表长度
                if (context.state.messages.length > context.state.pageSize * 3) {
                    context.state.messages = context.state.messages.slice(0, context.state.pageSize * 2);
                }
                
                EventHandlers.emit('message:new', messageData);
            }
        },
        
        // 处理消息更新
        handleMessageUpdated(context, messageData) {
            const messageIndex = context.state.messages.findIndex(msg => msg.id === messageData.id);
            if (messageIndex !== -1) {
                // 根据当前筛选器决定是更新还是移除
                if (this.shouldShowMessage(context, messageData)) {
                    context.state.messages[messageIndex] = messageData;
                } else {
                    context.state.messages.splice(messageIndex, 1);
                }
                
                EventHandlers.emit('message:updated', messageData);
            }
        },
        
        // 处理统计更新
        handleStatsUpdated(context, statsData) {
            window.StateManager.updateStats(context.state, statsData);
            EventHandlers.emit('stats:updated', statsData);
        },
        
        // 检查消息是否应该显示
        shouldShowMessage(context, message) {
            const filters = context.state.filters;
            
            if (filters.status && message.status !== filters.status) return false;
            if (filters.is_ad !== null && message.is_ad !== filters.is_ad) return false;
            if (filters.source_channel && message.source_channel_id !== filters.source_channel) return false;
            
            return true;
        }
    },
    
    // 错误处理
    error: {
        // 处理API错误
        handleApiError(error, operation = '操作') {
            console.error(`${operation}失败:`, error);
            
            let message = `${operation}失败`;
            if (error.error) {
                message += ': ' + error.error;
            }
            
            window.MessageManager?.error(message);
            EventHandlers.emit('error:api', { error, operation });
        },
        
        // 处理网络错误
        handleNetworkError(error) {
            console.error('网络错误:', error);
            window.MessageManager?.error('网络连接失败，请检查网络设置');
            EventHandlers.emit('error:network', error);
        },
        
        // 处理权限错误
        handlePermissionError() {
            window.MessageManager?.error('权限不足，请联系管理员');
            EventHandlers.emit('error:permission');
        }
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EventHandlers;
} else {
    window.EventHandlers = EventHandlers;
}