// 消息对比显示调试工具
// 用于诊断消息左右栏对比显示问题

window.MessageComparisonDebug = {
    // 启用调试模式
    enableDebug: true,
    
    // 调试日志
    debugLog: [],
    
    // 分析消息数据
    analyzeMessage(message, index) {
        if (!this.enableDebug) return;
        
        const analysis = {
            messageIndex: index,
            messageId: message.id,
            messageType: this.getMessageType(message),
            hasContent: !!message.content,
            hasFilteredContent: !!message.filtered_content,
            contentLength: message.content ? message.content.length : 0,
            filteredContentLength: message.filtered_content ? message.filtered_content.length : 0,
            contentEqual: message.content === message.filtered_content,
            shouldShowComparison: this.shouldShowContentComparison(message),
            hasRemovedHiddenLinks: !!(message.removed_hidden_links && message.removed_hidden_links.length > 0),
            isDuplicate: !!(message.duplicate_info && message.duplicate_original_id),
            status: message.status,
            isAd: message.is_ad,
            filterReason: message.filter_reason
        };
        
        // 详细内容比较
        if (analysis.hasContent && analysis.hasFilteredContent) {
            analysis.contentComparison = {
                originalPreview: message.content.substring(0, 100),
                filteredPreview: message.filtered_content.substring(0, 100),
                lengthDifference: analysis.contentLength - analysis.filteredContentLength,
                hasWhitespaceOnlyChanges: message.content.trim() === message.filtered_content.trim(),
                hasSignificantChanges: Math.abs(analysis.lengthDifference) > 10
            };
        }
        
        this.debugLog.push(analysis);
        
        // 在控制台输出重要信息
        if (analysis.shouldShowComparison) {
            console.group(`🔍 消息 #${message.id} - 应显示对比`);
            console.groupEnd();
        } else if (analysis.hasContent && analysis.hasFilteredContent && !analysis.contentEqual) {
            console.group(`⚠️ 消息 #${message.id} - 有内容差异但未显示对比`);
            console.groupEnd();
        }
        
        return analysis;
    },
    
    // 判断消息类型
    getMessageType(message) {
        if (message.duplicate_info && message.duplicate_original_id) {
            return 'duplicate';
        } else if (message.media_type || (message.is_combined && message.media_group_display)) {
            return 'media';
        } else if (message.content || message.filtered_content) {
            return 'text';
        } else {
            return 'empty';
        }
    },
    
    // 复制自MessageContentRenderer的逻辑
    shouldShowContentComparison(message) {
        const hasContentDifference = (message.content && message.filtered_content && 
                message.content !== message.filtered_content);
        const hasRemovedLinks = (message.removed_hidden_links && message.removed_hidden_links.length > 0);
        
        return hasContentDifference || hasRemovedLinks;
    },
    
    // 分析所有消息
    analyzeAllMessages(messages) {
        this.debugLog = [];
        
        messages.forEach((message, index) => {
            this.analyzeMessage(message, index);
        });
        
        // 统计分析
        const stats = this.getAnalysisStats();
        console.group('📊 消息分析统计');
        console.groupEnd();
        
        // 显示详细报告
        this.showDetailedReport();
        
        return stats;
    },
    
    // 获取分析统计
    getAnalysisStats() {
        const stats = {
            total: this.debugLog.length,
            shouldShowComparison: 0,
            hasContentButNoComparison: 0,
            duplicateMessages: 0,
            mediaOnlyMessages: 0,
            problematicMessages: []
        };
        
        this.debugLog.forEach(analysis => {
            if (analysis.shouldShowComparison) {
                stats.shouldShowComparison++;
            }
            
            if (analysis.hasContent && analysis.hasFilteredContent && 
                !analysis.contentEqual && !analysis.shouldShowComparison) {
                stats.hasContentButNoComparison++;
                stats.problematicMessages.push(analysis);
            }
            
            if (analysis.isDuplicate) {
                stats.duplicateMessages++;
            }
            
            if (analysis.messageType === 'media' && !analysis.hasContent) {
                stats.mediaOnlyMessages++;
            }
        });
        
        return stats;
    },
    
    // 显示详细报告
    showDetailedReport() {
        const problematicMessages = this.debugLog.filter(analysis => 
            analysis.hasContent && analysis.hasFilteredContent && 
            !analysis.contentEqual && !analysis.shouldShowComparison
        );
        
        if (problematicMessages.length > 0) {
            console.group('❗ 问题消息详细报告');
            problematicMessages.forEach(analysis => {
                console.group(`消息 #${analysis.messageId}`);
                if (analysis.contentComparison) {
                }
                console.groupEnd();
            });
            console.groupEnd();
        }
    },
    
    // 实时监控消息渲染
    monitorMessageRendering() {
        // 添加DOM观察器
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1 && node.classList && node.classList.contains('message-item')) {
                            this.checkRenderedMessage(node);
                        }
                    });
                }
            });
        });
        
        // 开始观察
        const messageList = document.querySelector('.message-list');
        if (messageList) {
            observer.observe(messageList, {
                childList: true,
                subtree: true
            });
        }
        
        return observer;
    },
    
    // 检查已渲染的消息
    checkRenderedMessage(messageElement) {
        const messageId = this.extractMessageIdFromElement(messageElement);
        const hasComparison = messageElement.querySelector('.message-content-comparison');
        const hasDuplicateComparison = messageElement.querySelector('.duplicate-comparison-layout');
        
        // 调试信息已清理
    },
    
    // 从DOM元素提取消息ID
    extractMessageIdFromElement(element) {
        const messageIdSpan = element.querySelector('.message-full-id');
        if (messageIdSpan) {
            const match = messageIdSpan.textContent.match(/#(\d+)/);
            return match ? match[1] : 'unknown';
        }
        return 'unknown';
    },
    
    // 导出调试报告
    exportDebugReport() {
        const report = {
            timestamp: new Date().toISOString(),
            debugLog: this.debugLog,
            stats: this.getAnalysisStats(),
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        const blob = new Blob([JSON.stringify(report, null, 2)], {
            type: 'application/json'
        });
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `message-comparison-debug-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        
    },
    
    // 测试特定消息
    testMessage(messageId, messages) {
        const message = messages.find(m => m.id == messageId);
        if (!message) {
            console.error(`消息 #${messageId} 未找到`);
            return;
        }
        
        console.group(`🧪 测试消息 #${messageId}`);
        
        // 测试各种条件
        const tests = {
            hasContent: !!message.content,
            hasFilteredContent: !!message.filtered_content,
            contentsDifferent: message.content !== message.filtered_content,
            hasRemovedLinks: !!(message.removed_hidden_links && message.removed_hidden_links.length > 0),
            shouldShowComparison: this.shouldShowContentComparison(message)
        };
        
        
        // 详细比较
        if (tests.hasContent && tests.hasFilteredContent) {
            
            // 字符级比较
            if (message.content !== message.filtered_content) {
                this.compareStrings(message.content, message.filtered_content);
            }
        }
        
        console.groupEnd();
        return tests;
    },
    
    // 字符串差异比较
    compareStrings(str1, str2) {
        
        // 找出第一个不同的位置
        for (let i = 0; i < Math.min(str1.length, str2.length); i++) {
            if (str1[i] !== str2[i]) {
                break;
            }
        }
        
        // 检查结尾差异
        if (str1.length !== str2.length) {
            const longer = str1.length > str2.length ? str1 : str2;
            const shorter = str1.length > str2.length ? str2 : str1;
        }
    }
};

// 在窗口加载完成后初始化
window.addEventListener('load', () => {
    if (window.MessageComparisonDebug.enableDebug) {
    }
});