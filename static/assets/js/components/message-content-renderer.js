// 消息内容渲染器组件 - 优化的消息显示组件

const MessageContentRenderer = {
    name: 'MessageContentRenderer',
    props: {
        message: {
            type: Object,
            required: true
        },
        channelInfo: {
            type: Object,
            default: () => ({})
        }
    },
    
    emits: [
        'toggle-select',
        'is-selected', 
        'open-media-preview',
        'filter-by-channel',
        'get-channel-display-name',
        'format-time',
        'handle-image-error',
        'get-media-type-icon',
        'approve-message',
        'reject-message',
        'edit-message',
        'mark-as-ad',
        'train-tail',
        'filter-content'
    ],
    
    data() {
        return {
            mediaLoadError: false,
            // 控制右栏显示内容
            showingDuplicate: false,     // 是否显示母本消息
            duplicateMessage: null,      // 母本消息的完整数据
            duplicateLoading: false      // 加载状态
        };
    },
    
    computed: {
        // 检查是否被选中
        isSelected() {
            // 通过父组件的isSelected方法来判断
            if (this.$parent && this.$parent.isSelected) {
                return this.$parent.isSelected(this.messageId);
            }
            return false;
        },

        // 格式化的消息内容
        formattedContent() {
            return this.message.filtered_content || '';
        },
        
        // 高亮命中关键词的过滤后内容
        highlightedFilteredContent() {
            let content = this.message.filtered_content || '';

            // 🎯 优先从新字段ad_keywords_detail获取关键词信息
            let keywordsToHighlight = [];

            if (this.message.ad_keywords_detail && this.message.ad_keywords_detail.matched_keywords) {
                // 新格式：使用ad_keywords_detail
                keywordsToHighlight = this.message.ad_keywords_detail.matched_keywords;
            } else if (this.message.hit_keywords && this.message.hit_keywords.length > 0) {
                // 旧格式：使用hit_keywords
                keywordsToHighlight = this.message.hit_keywords;
            }

            // 转义HTML特殊字符
            content = this.escapeHtml(content);

            // 如果消息已发布，处理目标消息链接（让它可点击）
            if (this.isApprovedStatus(this.message.status)) {
                content = this.makeTargetLinkClickable(content);
            }

            if (!content || keywordsToHighlight.length === 0) {
                return content;
            }

            // 按关键词长度从长到短排序，避免短关键词先匹配
            const sortedKeywords = [...keywordsToHighlight].sort((a, b) =>
                b.keyword.length - a.keyword.length
            );

            // 高亮每个关键词
            for (const item of sortedKeywords) {
                const keyword = item.keyword;
                const weight = item.weight || 1.0;

                // 根据权重选择不同的高亮样式
                let highlightClass = 'ad-keyword-highlight';
                if (weight >= 5.0) {
                    highlightClass += ' high-weight';     // 红色背景
                } else if (weight >= 2.0) {
                    highlightClass += ' medium-weight';   // 橙色背景
                } else {
                    highlightClass += ' low-weight';      // 黄色背景
                }

                // 使用正则替换，确保大小写不敏感
                const regex = new RegExp(this.escapeRegExp(keyword), 'gi');
                content = content.replace(regex, match =>
                    `<span class="${highlightClass}" title="权重: ${weight}">${match}</span>`
                );
            }

            return content;
        },
        
        // 高亮命中关键词的原始内容
        highlightedOriginalContent() {
            let content = this.message.content || '';

            // 如果没有内容，返回空字符串
            if (!content) return '';

            // 总是先转义HTML特殊字符（安全性）
            content = this.escapeHtml(content);

            // 🎯 优先从新字段ad_keywords_detail获取关键词信息
            let keywordsToHighlight = [];

            if (this.message.ad_keywords_detail && this.message.ad_keywords_detail.matched_keywords) {
                // 新格式：使用ad_keywords_detail
                keywordsToHighlight = this.message.ad_keywords_detail.matched_keywords;
            } else if (this.message.hit_keywords && this.message.hit_keywords.length > 0) {
                // 旧格式：使用hit_keywords
                keywordsToHighlight = this.message.hit_keywords;
            }

            // 如果没有关键词，返回转义后的内容
            if (!keywordsToHighlight || keywordsToHighlight.length === 0) {
                return content;
            }

            // 按关键词长度从长到短排序
            const sortedKeywords = [...keywordsToHighlight].sort((a, b) =>
                b.keyword.length - a.keyword.length
            );

            // 高亮每个关键词
            for (const item of sortedKeywords) {
                const keyword = item.keyword;
                const weight = item.weight || 1.0;

                // 根据权重选择不同的高亮样式
                let highlightClass = 'ad-keyword-highlight';
                if (weight >= 5.0) {
                    highlightClass += ' high-weight';     // 红色背景
                } else if (weight >= 2.0) {
                    highlightClass += ' medium-weight';   // 橙色背景
                } else {
                    highlightClass += ' low-weight';      // 黄色背景
                }

                // 使用正则替换（忽略positions字段，直接匹配）
                const regex = new RegExp(this.escapeRegExp(keyword), 'gi');
                content = content.replace(regex, match =>
                    `<span class="${highlightClass}" title="权重: ${weight}">${match}</span>`
                );
            }

            return content;
        },
        
        // 🆕 媒体组信息显示
        mediaGroupInfoDisplay() {
            if (!this.message.media_group_info) return null;
            return this.message.media_group_info.display_text || '';
        },
        
        
        // 是否应该显示左右栏对比（总是显示双栏对比）
        shouldShowContentComparison() {
            return true; // 始终显示双栏对比，简化逻辑
        },
        
        // 内容是否真正被过滤
        isContentActuallyFiltered() {
            const contentsDifferent = this.message.content !== this.message.filtered_content;
            const hasRemovedLinks = !!(this.message.removed_hidden_links && this.message.removed_hidden_links.length > 0);
            return contentsDifferent || hasRemovedLinks;
        },
        
        // 过滤状态描述
        filterStatus() {
            if (!this.shouldShowContentComparison) {
                return { type: 'none', text: '无对比数据', icon: '⚪' };
            }
            
            const contentsDifferent = this.message.content !== this.message.filtered_content;
            const hasRemovedLinks = !!(this.message.removed_hidden_links && this.message.removed_hidden_links.length > 0);
            
            if (contentsDifferent && hasRemovedLinks) {
                return { type: 'filtered-and-links', text: '内容已过滤并移除链接', icon: '🔄' };
            } else if (contentsDifferent) {
                return { type: 'filtered', text: '内容已过滤', icon: '🔄' };
            } else if (hasRemovedLinks) {
                return { type: 'links-only', text: '仅移除隐藏链接', icon: '🔗' };
            } else {
                return { type: 'unchanged', text: '内容未被过滤', icon: '⚪' };
            }
        },
        
        // 消息状态标签
        statusTag() {
            const statusMap = {
                'pending': { text: '待审核', type: 'warning' },
                'approved': { text: '已发布', type: 'success' },
                'rejected': { text: '已拒绝', type: 'danger' },
                'auto_forwarded': { text: '自动转发', type: 'info' }
            };
            return statusMap[this.message.status] || { text: this.message.status, type: 'default' };
        },
        
        // 确保消息ID包含-100前缀的格式化ID
        
        // 是否为组合消息
        isCombinedMessage() {
            return this.message.is_combined && 
                   this.message.media_group_display && 
                   Array.isArray(this.message.media_group_display);
        },
        
        // Telegram风格媒体网格类
        telegramMediaGridClass() {
            if (!this.isCombinedMessage) return '';
            
            const count = this.message.media_group_display.length;
            if (count >= 10) return 'count-10plus';
            return `count-${count}`;
        },
        
        // 显示的媒体项（最多显示9个，第9个显示剩余数量）
        displayMediaItems() {
            if (!this.isCombinedMessage) return [];
            
            const items = this.message.media_group_display;
            const maxDisplay = 9;
            
            if (items.length <= maxDisplay) {
                return items.map((item, index) => ({
                    ...item,
                    index: index + 1,
                    isLast: false
                }));
            }
            
            // 如果超过9个，显示前8个和第9个带计数
            const displayItems = items.slice(0, maxDisplay - 1).map((item, index) => ({
                ...item,
                index: index + 1,
                isLast: false
            }));
            
            displayItems.push({
                ...items[maxDisplay - 1],
                index: maxDisplay,
                isLast: true,
                remainingCount: items.length - maxDisplay
            });
            
            return displayItems;
        },
        
        // 准备媒体项数据用于新的TelegramAlbum组件 - 支持单个媒体和组合媒体
        preparedAlbumMediaItems() {
            if (this.isCombinedMessage) {
                // 组合媒体消息
                return this.message.media_group_display.map((media, index) => ({
                    ...media,
                    // 确保有默认尺寸
                    width: media.width || 640,
                    height: media.height || 640,
                    // 统一URL字段
                    url: media.url || media.display_url,
                    display_url: media.url || media.display_url
                }));
            } else if (this.message.media_type && this.message.media_display_url) {
                // 单个媒体消息 - 包装成数组格式供TelegramAlbum使用
                return [{
                    media_type: this.message.media_type,
                    width: this.message.media_width || 640,
                    height: this.message.media_height || 640,
                    url: this.message.media_display_url,
                    display_url: this.message.media_display_url,
                    // 添加缩略图URL（如果是视频）
                    thumbnail_url: this.message.thumbnail_url,
                    thumbnail_display_url: this.message.thumbnail_display_url
                }];
            }
            
            return [];
        },
        
        // 检查是否有媒体可以显示（包括单个媒体和组合媒体）
        hasMediaToShow() {
            return this.preparedAlbumMediaItems.length > 0;
        },

        // 准备母本消息的媒体数据用于TelegramAlbum组件
        preparedDuplicateAlbumMediaItems() {
            if (!this.duplicateMessage) return [];

            // 处理组合媒体
            if (this.duplicateMessage.media_group_display && this.duplicateMessage.media_group_display.length > 0) {
                return this.duplicateMessage.media_group_display.map((media, index) => ({
                    ...media,
                    width: media.width || 640,
                    height: media.height || 640,
                    url: media.url || media.display_url,
                    display_url: media.url || media.display_url
                }));
            }
            // 处理单个媒体
            else if (this.duplicateMessage.media_type && this.duplicateMessage.media_display_url) {
                return [{
                    media_type: this.duplicateMessage.media_type,
                    width: this.duplicateMessage.media_width || 640,
                    height: this.duplicateMessage.media_height || 640,
                    url: this.duplicateMessage.media_display_url,
                    display_url: this.duplicateMessage.media_display_url,
                    thumbnail_url: this.duplicateMessage.thumbnail_url,
                    thumbnail_display_url: this.duplicateMessage.thumbnail_display_url
                }];
            }

            return [];
        },

        // 获取正确的消息ID - 解决ID字段不一致问题
        messageId() {
            // 如果有id字段，直接使用
            if (this.message.id) {
                return this.message.id;
            }

            // 如果没有id字段，从source_channel和message_id组合生成
            // 并确保频道ID包含正确的-100前缀
            const channelId = this.message.source_channel;
            const msgId = this.message.message_id;

            if (!channelId || !msgId) {
                return null;
            }

            // 如果频道ID不包含-100前缀且是纯数字，添加前缀
            let normalizedChannelId = channelId;
            if (!channelId.startsWith('-100') && /^\d+$/.test(channelId)) {
                normalizedChannelId = `-100${channelId}`;
            }

            return `${normalizedChannelId}:${msgId}`;
        }
    },
    
    components: {
        TelegramAlbum: window.TelegramAlbum
    },
    
    methods: {
        // 状态检查辅助方法 - 安全地检查消息状态
        isPendingStatus(status) {
            if (window.MessageStatus && window.MessageStatus.isPending) {
                return window.MessageStatus.isPending(status);
            }
            // 降级处理：直接判断
            return status === 'pending' || status === 'send_failed';
        },

        isRejectedStatus(status) {
            if (window.MessageStatus && window.MessageStatus.isRejected) {
                return window.MessageStatus.isRejected(status);
            }
            // 降级处理：直接判断
            return status === 'rejected' || status === 'ad_rejected' || status === 'dup_rejected' || status === 'manual_rejected';
        },

        isApprovedStatus(status) {
            if (window.MessageStatus && window.MessageStatus.isApproved) {
                return window.MessageStatus.isApproved(status);
            }
            // 降级处理：直接判断
            return status === 'approved' || status === 'auto_approved' || status === 'manual_approved';
        },

        // 切换消息选择状态
        toggleSelect() {
            this.$emit('toggle-select', this.messageId);
        },

        // 根据消息ID加载并显示内容
        async loadMessageById() {
            const targetMessageId = this.message.original_message_id;

            if (!targetMessageId) {
                console.warn('没有目标消息ID');
                return;
            }

            // 如果已经在显示相同的消息，切换回原始内容
            if (this.showingDuplicate && this.duplicateMessage?.id === targetMessageId) {
                this.showingDuplicate = false;
                return;
            }

            this.duplicateLoading = true;
            try {
                // 使用统一的API配置获取消息
                const response = await axios.get(window.API.messages.getById(targetMessageId));
                if (response.data.success) {
                    // 保存消息数据
                    this.duplicateMessage = response.data.data;
                    this.showingDuplicate = true;  // 切换到显示该消息
                } else if (response.data.data && response.data.data.status === 'deleted') {
                    // 消息已被清理
                    SimpleUI.showMessage('该消息已在数据清理中被删除', 'info');
                } else {
                    SimpleUI.showMessage(response.data.message || '加载消息失败', 'error');
                }
            } catch (error) {
                console.error('加载消息失败:', error);
                SimpleUI.showMessage('加载失败: ' + (error.response?.data?.message || error.message), 'error');
            } finally {
                this.duplicateLoading = false;
            }
        },

        // 处理视频缩略图点击
        handleVideoThumbnailClick(message) {
            // 打开原始消息链接
            if (message.source_channel_link_prefix && message.source_channel_message_id) {
                const originalLink = `${message.source_channel_link_prefix}${message.source_channel_message_id}`;
                window.open(originalLink, '_blank');
            } else {
                SimpleUI.showMessage('无法打开原始消息链接', 'warning');
            }
        },

        // 处理缩略图加载错误
        handleThumbnailError(event) {
            console.error('视频缩略图加载失败:', event.target.src);
            this.mediaLoadError = true;
        },
        
        // 格式化时间
        formatTime(timeStr) {
            if (!timeStr) return '';
            try {
                // 🕐 修复时区bug：明确处理UTC时间
                const utcTimeStr = timeStr.endsWith('Z') ? timeStr : timeStr + 'Z';
                const date = new Date(utcTimeStr);
                const now = new Date();
                const diffInSeconds = Math.floor((now - date) / 1000);

                if (diffInSeconds < 60) return `${diffInSeconds}秒前`;
                if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}分钟前`;
                if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}小时前`;

                return date.toLocaleString('zh-CN', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (error) {
                return timeStr;
            }
        },

        // 格式化原消息时间为 MM-dd HH:mm 格式
        formatOriginalTime(timeStr) {
            if (!timeStr) return '';
            try {
                // 清理时间字符串，移除可能的重复时区标识
                let cleanTimeStr = timeStr.trim();

                // 如果同时有+00:00和Z，移除Z
                if (cleanTimeStr.includes('+00:00Z')) {
                    cleanTimeStr = cleanTimeStr.replace('+00:00Z', '+00:00');
                }
                // 如果没有时区标识，添加Z
                else if (!cleanTimeStr.endsWith('Z') && !cleanTimeStr.includes('+') && !cleanTimeStr.includes('-', 10)) {
                    cleanTimeStr += 'Z';
                }

                const date = new Date(cleanTimeStr);

                // 检查日期是否有效
                if (isNaN(date.getTime())) {
                    return '';
                }

                // 格式化为 MM-dd HH:mm 格式
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hour = String(date.getHours()).padStart(2, '0');
                const minute = String(date.getMinutes()).padStart(2, '0');

                return `${month}-${day} ${hour}:${minute}`;
            } catch (error) {
                return '';
            }
        },
        
        // 处理媒体错误
        handleMediaError() {
            this.mediaLoadError = true;
        },
        
        // 打开媒体预览
        openMediaPreview(url) {
            this.$emit('open-media-preview', url);
        },
        
        // 获取原消息链接
        getOriginalMessageLink() {
            if (!this.messageId) return '#';

            if (this.message.source_channel_link_prefix) {
                return `${this.message.source_channel_link_prefix}/${this.message.message_id}`;
            }

            return '#';
        },
        
        // 媒体文件是否存在
        mediaExists() {
            if (this.isCombinedMessage) {
                return this.message.media_group_display.some(media => 
                    (media.url && media.url.trim() !== '') || 
                    (media.display_url && media.display_url.trim() !== '')
                );
            }
            
            return this.message.media_display_url && 
                   this.message.media_display_url.trim() !== '' && 
                   !this.mediaLoadError;
        },
        
        
        // 操作方法被事件委托取代，不再需要Vue事件
        
        // 频道过滤方法
        filterByChannel(channelId, channelName) {
            this.$emit('filter-by-channel', channelId, channelName);
        },
        
        // 获取频道显示名称
        getChannelDisplayName(channelId) {
            // 尝试从channelInfo prop中获取完整的频道信息
            if (this.channelInfo && channelId) {
                const channelData = this.channelInfo[channelId];
                if (channelData && window.DataUtils) {
                    return window.DataUtils.getChannelDisplayName(channelData);
                }
            }
            
            // 从消息中构建频道信息
            const channelData = {
                id: channelId,
                title: this.message.source_channel_title,
                username: this.message.source_channel_username || this.extractUsernameFromChannel()
            };
            
            if (window.DataUtils && window.DataUtils.getChannelDisplayName) {
                return window.DataUtils.getChannelDisplayName(channelData);
            }
            
            // 降级处理：优先显示标题
            if (this.message.source_channel_title) {
                let displayName = this.message.source_channel_title;
                if (channelData.username) {
                    displayName += ` [${channelData.username}]`;
                }
                return displayName;
            }
            
            return this.message.source_channel || '未知频道';
        },
        
        // 尝试从source_channel中提取用户名
        extractUsernameFromChannel() {
            const sourceChannel = this.message.source_channel;
            if (typeof sourceChannel === 'string' && sourceChannel.startsWith('@')) {
                return sourceChannel.substring(1); // 移除@符号
            }
            return null;
        },
        
        // HTML转义
        escapeHtml(text) {
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return text.replace(/[&<>"']/g, m => map[m]);
        },
        
        // 转义正则特殊字符
        escapeRegExp(string) {
            return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        },
        
        // 处理图片错误
        handleImageError(message, event) {
            this.$emit('handle-image-error', message, event);
        },
        
        // 获取媒体类型图标
        getMediaTypeIcon(mediaType) {
            return this.$emit('get-media-type-icon', mediaType);
        },
        
        // 🚀 处理相册媒体点击事件
        handleAlbumMediaClick({ mediaItem, index, url }) {
            this.openMediaPreview(url);
        },
        
        // 🚀 处理单个媒体点击事件
        handleSingleMediaClick({ mediaItem, index, url }) {
            this.openMediaPreview(url);
        },
        
        // 判断消息是否为广告 - 使用全局统一函数
        isMessageAd(message) {
            return MessageUtils.isMessageAd(message);
        },

        // 使目标消息链接可点击
        makeTargetLinkClickable(content) {
            // 匹配"✅ 目标消息链接: https://t.me/xxx/xxx"格式
            const linkRegex = /(✅ 目标消息链接: )(https:\/\/t\.me\/[^\s<]+)/g;
            return content.replace(linkRegex, (match, prefix, url) => {
                return `${prefix}<a href="${url}" target="_blank" class="target-message-link" title="点击查看目标频道消息">${url}</a>`;
            });
        }
    },
    template: `
        <div class="message-content-wrapper">
            <!-- 自动转发失败提示 -->
            <div v-if="message.auto_forward_failed" class="forward-error-alert">
                <div class="error-icon">⚠️</div>
                <div class="error-content">
                    <div class="error-title">自动转发失败</div>
                    <div class="error-reason">{{ message.auto_forward_error || '未知错误' }}</div>
                    <div class="error-meta" v-if="message.auto_forward_retry_count">
                        已重试 {{ message.auto_forward_retry_count }} 次
                        <span v-if="message.auto_forward_last_retry" class="error-time">
                            · {{ formatTime(message.auto_forward_last_retry) }}
                        </span>
                    </div>
                </div>
            </div>

            <!-- 消息头部 -->
            <div class="message-header">
                <div class="message-info">
                    <!-- 选择框 -->
                    <input type="checkbox"
                           :checked="isSelected"
                           @click.stop
                           @change="toggleSelect">
                    
                    <!-- 频道信息 -->
                    <span class="message-channel">
                        📢 <a href="javascript:void(0)" 
                             @click.stop="filterByChannel(message.source_channel, getChannelDisplayName(message.source_channel))"
                             class="channel-link"
                             :title="'点击查看频道「' + getChannelDisplayName(message.source_channel) + '」的所有消息'">
                            {{ getChannelDisplayName(message.source_channel) }}
                        </a>
                    </span>
                    
                    <!-- 时间 -->
                    <span class="message-time">{{ formatTime(message.created_at) }}</span>
                </div>
                
                <!-- 状态标签 -->
                <div class="message-tags">
                    <span :class="['tag', 'tag-' + statusTag.type]">
                        {{ statusTag.text }}
                    </span>
                    <span v-if="isMessageAd(message)" class="tag tag-danger">广告</span>
                    <!-- 🎯 去重检测标签 -->
                    <span v-if="message.duplicate_status === 'suspected'"
                          class="tag tag-warning duplicate-suspected"
                          :title="'疑似重复消息 (相似度: ' + (message.similarity_score * 100).toFixed(1) + '%)'">
                        🔍 疑似重复
                    </span>
                    <span v-if="message.duplicate_status === 'confirmed'"
                          class="tag tag-danger duplicate-confirmed"
                          title="已确认为重复消息">
                        ❌ 重复
                    </span>
                    <span v-if="message.duplicate_status === 'not_duplicate'"
                          class="tag tag-success duplicate-not"
                          title="已标记为非重复">
                        ✅ 非重复
                    </span>
                    <span v-if="(message.filter_reason || message.rejection_reason) && isRejectedStatus(message.status)"
                          class="tag tag-secondary reject-reason-hover"
                          :title="message.filter_reason || message.rejection_reason">
                        拒因
                    </span>
                </div>
            </div>
            
            <!-- 消息内容 -->
            <div class="message-content">
                <!-- 消息双栏内容对比显示 -->
                <div v-if="shouldShowContentComparison" 
                     :class="['message-content-comparison', { 'unchanged': !isContentActuallyFiltered }]">
                    <!-- 左栏：过滤后内容（包含媒体） -->
                    <div class="content-column content-filtered">
                        <div class="content-column-header">
                            <!-- 对于拒绝的广告消息，显示"检测到的广告内容"标签 -->
                            <span v-if="isRejectedStatus(message.status) && isMessageAd(message)" class="content-label">
                                🚫 检测到的广告内容
                            </span>
                            <span v-else class="content-label">🔍 过滤后内容</span>
                        </div>
                        <div class="content-column-body">
                            <!-- 媒体内容 - 统一使用TelegramAlbum组件 -->
                            <div v-if="hasMediaToShow" class="column-media-section">
                                <TelegramAlbum
                                    :media-items="preparedAlbumMediaItems"
                                    :is-own="false"
                                    :max-width="380"
                                    :is-mobile="false"
                                    :spacing="2"
                                    @media-click="handleAlbumMediaClick"
                                    class="comparison-media"
                                />
                            </div>

                            <!-- 视频缩略图显示 -->
                            <div v-else-if="message.media_type === 'video' && message.thumbnail_display_url && !mediaLoadError"
                                 class="video-thumbnail-container media-content"
                                 @click="handleVideoThumbnailClick(message)">
                                <img :src="message.thumbnail_display_url"
                                     alt="视频缩略图"
                                     class="video-thumbnail"
                                     @error="handleThumbnailError">
                                <div class="video-play-overlay">
                                    <span class="play-icon">▶️</span>
                                    <span class="video-label">视频</span>
                                </div>
                            </div>

                            <!-- 媒体缺失时的占位符 -->
                            <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)"
                                 class="media-placeholder media-content">
                                <div>
                                    📷 {{ message.media_type === 'photo' ? '图片' :
                                         message.media_type === 'video' ? '视频' :
                                         message.media_type }}
                                    <div class="media-missing-text">媒体文件缺失</div>
                                </div>
                            </div>

                            <!-- 文本内容：对于拒绝的广告消息显示高亮的原始内容，其他情况显示过滤后内容 -->
                            <!-- 拒绝的广告消息：显示原始内容并高亮关键词 -->
                            <!-- 左栏：只显示过滤后的内容 -->
                            <div v-if="message.filtered_content" class="message-text" v-html="highlightedFilteredContent">
                            </div>
                            <div v-else-if="!message.media_type" class="content-empty">
                                暂无过滤后内容
                            </div>

                        </div>
                        
                        <!-- 显示被移除的隐藏链接信息 -->
                        <div v-if="message.removed_hidden_links && message.removed_hidden_links.length > 0" 
                             class="hidden-links-info">
                            <div class="hidden-links-title">
                                ⚠️ 检测到 {{ message.removed_hidden_links.length }} 个隐藏链接（已移除）：
                            </div>
                            <div v-for="(link, index) in message.removed_hidden_links" :key="index" class="hidden-link-item">
                                • "{{ link.text }}" → <span class="hidden-link-url">{{ link.url }}</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 右栏：原始内容或母本消息内容 -->
                    <div class="content-column content-original" :class="{ 'showing-duplicate': showingDuplicate }">
                        <div class="content-column-header" :class="{ 'duplicate-header': showingDuplicate }">
                            <span class="content-label" v-if="!showingDuplicate">📄 原始内容</span>
                            <span class="content-label" v-else>👑 母本消息</span>
                            <!-- 切换按钮 -->
                            <button v-if="duplicateMessage"
                                    @click="showingDuplicate = !showingDuplicate"
                                    style="margin-left: auto; padding: 2px 8px; background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.3); color: white; border-radius: 4px; font-size: 11px; cursor: pointer;">
                                {{ showingDuplicate ? '查看原始' : '查看母本' }}
                            </button>
                        </div>
                        <div class="content-column-body" v-if="!duplicateLoading">
                            <!-- 显示原始内容 -->
                            <template v-if="!showingDuplicate">
                                <!-- 原始媒体内容 - 统一使用TelegramAlbum组件 -->
                                <div v-if="hasMediaToShow" class="column-media-section">
                                <TelegramAlbum
                                    :media-items="preparedAlbumMediaItems"
                                    :is-own="false"
                                    :max-width="380"
                                    :is-mobile="false"
                                    :spacing="2"
                                    @media-click="handleAlbumMediaClick"
                                    class="comparison-media"
                                />
                            </div>
                            
                            <!-- 视频缩略图显示 -->
                            <div v-else-if="message.media_type === 'video' && message.thumbnail_display_url && !mediaLoadError"
                                 class="video-thumbnail-container media-content"
                                 @click="handleVideoThumbnailClick(message)">
                                <img :src="message.thumbnail_display_url"
                                     alt="视频缩略图"
                                     class="video-thumbnail"
                                     @error="handleThumbnailError">
                                <div class="video-play-overlay">
                                    <span class="play-icon">▶️</span>
                                    <span class="video-label">视频</span>
                                </div>
                            </div>

                            <!-- 媒体缺失时的占位符 -->
                            <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)"
                                 class="media-placeholder media-content">
                                <div>
                                    📷 {{ message.media_type === 'photo' ? '图片' :
                                         message.media_type === 'video' ? '视频' :
                                         message.media_type }}
                                    <div class="media-missing-text">媒体文件缺失</div>
                                </div>
                            </div>
                            
                                <!-- 原始的文本内容（高亮广告关键词） -->
                                <div v-if="message.content" class="message-text" v-html="highlightedOriginalContent">
                                </div>
                                <div v-else-if="!message.media_type" class="content-empty">
                                    暂无原始内容
                                </div>
                            </template>

                            <!-- 显示母本消息内容 -->
                            <template v-else-if="duplicateMessage">
                                <!-- 母本消息的媒体 - 使用TelegramAlbum组件 -->
                                <div v-if="preparedDuplicateAlbumMediaItems.length > 0" class="column-media-section">
                                    <TelegramAlbum
                                        :media-items="preparedDuplicateAlbumMediaItems"
                                        :is-own="false"
                                        :max-width="380"
                                        :is-mobile="false"
                                        :spacing="2"
                                        @media-click="handleAlbumMediaClick"
                                        class="comparison-media"
                                    />
                                </div>
                                <!-- 母本消息的过滤后文字 -->
                                <div v-if="duplicateMessage.filtered_content" class="message-text">
                                    {{ duplicateMessage.filtered_content }}
                                </div>
                                <div v-else-if="duplicateMessage.content" class="message-text">
                                    {{ duplicateMessage.content }}
                                </div>
                                <div v-else-if="preparedDuplicateAlbumMediaItems.length === 0" class="content-empty">
                                    暂无内容
                                </div>
                            </template>

                            <!-- 加载中状态 -->
                            <div v-if="duplicateLoading" class="content-empty">
                                <div class="spinner"></div>
                                加载中...
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 消息底部信息 -->
                <div class="message-footer">
                    <!-- 源消息ID -->
                    <div v-if="message.source_channel && message.message_id" class="source-message-id">
                        消息ID: #{{ message.source_channel }}:{{ message.message_id }}
                    </div>


                    <!-- 原频道链接和疑似重复信息 -->
                    <div v-if="message.source_channel_link_prefix && messageId" class="original-message-link-container">
                        <a :href="getOriginalMessageLink()"
                           target="_blank"
                           class="original-message-link"
                           @click.stop>
                            原频道链接
                        </a>
                        <span v-if="message.timestamp" class="original-time">
                            原消息发表于{{ formatOriginalTime(message.timestamp) }}
                        </span>
                        <!-- 疑似重复信息显示在原频道链接后面 -->
                        <!-- 疑似重复信息 -->
                        <template v-if="message.duplicate_status === 'suspected' && message.original_message_id">
                            <span class="duplicate-inline-info">
                                🔍 疑似重复于:
                                <a href="javascript:void(0)"
                                   class="duplicate-inline-link"
                                   @click.stop="loadMessageById"
                                   :title="'相似度: ' + (message.similarity_score * 100).toFixed(1) + '%'">
                                    #{{ message.original_message_id }}
                                </a>
                                ({{ (message.similarity_score * 100).toFixed(1) }}% 相似)
                            </span>
                        </template>
                        <!-- 确认重复信息（用于已拒绝列表） -->
                        <template v-if="message.duplicate_status === 'confirmed' && message.original_message_id">
                            <span class="duplicate-inline-info">
                                ❌ 重复于:
                                <a href="javascript:void(0)"
                                   class="duplicate-inline-link"
                                   @click.stop="loadMessageById"
                                   :title="'相似度: ' + (message.similarity_score * 100).toFixed(1) + '%'">
                                    #{{ message.original_message_id }}
                                </a>
                                ({{ (message.similarity_score * 100).toFixed(1) }}% 相似)
                            </span>
                        </template>
                    </div>
                </div>
            </div>
            
            <!-- 操作按钮 -->
            <div v-if="isPendingStatus(message.status)" class="message-actions">
                <button data-action="editMessage" :data-message-id="message.id" class="btn btn-sm btn-secondary">
                    ✏️ 编辑
                </button>
                <button
                    data-action="approveMessage"
                    :data-message-id="message.id"
                    :disabled="$parent.isPublishing && $parent.isPublishing(messageId)"
                    :class="['btn', 'btn-sm', 'btn-success',
                             $parent.isPublishing && $parent.isPublishing(messageId) ? 'disabled' : '']">
                    {{ $parent.isPublishing && $parent.isPublishing(messageId) ? '⏳ 发布中...' : '📤 发布' }}
                </button>
                <button data-action="rejectMessage" :data-message-id="message.id" class="btn btn-sm btn-danger">
                    ❌ 拒绝
                </button>


                <button :data-action="isMessageAd(message) ? 'markAsNotAd' : 'markAsAd'"
                        :data-message-id="message.id"
                        class="btn btn-sm btn-warning">
                    {{ isMessageAd(message) ? '✅ 不是广告' : '🚫 广告' }}
                </button>
                <button data-action="trainTail" :data-message-id="message.id" class="btn btn-sm btn-info">
                    ✂️ 尾部
                </button>
                <button
                    data-action="filterContent"
                    :data-message-id="message.id"
                    :disabled="$parent.isFiltering && $parent.isFiltering(messageId)"
                    :class="['btn', 'btn-sm', 'btn-primary',
                             $parent.isFiltering && $parent.isFiltering(messageId) ? 'disabled' : '']">
                    {{ $parent.isFiltering && $parent.isFiltering(messageId) ? '🔄 过滤中...' : '🎯 过滤' }}
                </button>
            </div>
            
            <!-- 已拒绝消息的差异化按钮 -->
            <div v-else-if="isRejectedStatus(message.status)" class="message-actions">
                <!-- 广告消息：显示"不是广告"按钮 -->
                <button v-if="isMessageAd(message)"
                        data-action="markAsNotAd"
                        :data-message-id="message.id"
                        class="btn btn-sm btn-warning">
                    ❌ 不是广告
                </button>
                <!-- 非广告消息：显示"恢复"按钮 -->
                <button v-else
                        data-action="restoreMessage"
                        :data-message-id="message.id"
                        class="btn btn-sm btn-warning">
                    🔄 恢复
                </button>
                <!-- 删除按钮 -->
                <button data-action="deleteMessage"
                        :data-message-id="message.id"
                        class="btn btn-sm btn-danger">
                    🗑️ 删除
                </button>
            </div>
            
            <!-- 已发送消息的操作按钮 -->
            <div v-else-if="isApprovedStatus(message.status)" class="message-actions">
                <button data-action="restoreMessage" :data-message-id="message.id" class="btn btn-sm btn-warning">
                    🔄 恢复
                </button>
                <button data-action="deleteApprovedMessage" :data-message-id="message.id" class="btn btn-sm btn-danger">
                    🗑️ 删除
                </button>
            </div>
        </div>
    `
};

// 注册组件
window.MessageContentRenderer = MessageContentRenderer;