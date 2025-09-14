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
            mediaLoadError: false
        };
    },
    
    computed: {
        // 格式化的消息内容
        formattedContent() {
            if (this.message.status === 'rejected' && this.message.filter_reason && this.message.content) {
                return this.message.content;
            }
            return this.message.filtered_content || this.message.content || '';
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
            
            if (!content || keywordsToHighlight.length === 0) {
                return content;
            }
            
            // 转义HTML特殊字符
            content = this.escapeHtml(content);
            
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
            
            // 🎯 优先从新字段ad_keywords_detail获取关键词信息
            let keywordsToHighlight = [];
            
            if (this.message.ad_keywords_detail && this.message.ad_keywords_detail.matched_keywords) {
                // 新格式：使用ad_keywords_detail
                keywordsToHighlight = this.message.ad_keywords_detail.matched_keywords;
            } else if (this.message.hit_keywords && this.message.hit_keywords.length > 0) {
                // 旧格式：使用hit_keywords
                keywordsToHighlight = this.message.hit_keywords;
            }
            
            if (!content || keywordsToHighlight.length === 0) {
                return content;
            }
            
            // 转义HTML特殊字符
            content = this.escapeHtml(content);
            
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
                
                // 使用正则替换
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
        
        // 确保消息ID包含-100前缀的格式化ID - Linus式修复
        computedMessageId() {
            const messageId = this.message.id;
            if (!messageId || !messageId.includes(':')) {
                return messageId;
            }
            
            // 如果ID已经包含-100前缀，直接返回
            if (messageId.startsWith('-100')) {
                return messageId;
            }
            
            // 分解ID并添加-100前缀
            const [channelPart, messagePart] = messageId.split(':');
            return `-100${channelPart}:${messagePart}`;
        },
        
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
                    display_url: this.message.media_display_url
                }];
            }
            
            return [];
        },
        
        // 检查是否有媒体可以显示（包括单个媒体和组合媒体）
        hasMediaToShow() {
            return this.preparedAlbumMediaItems.length > 0;
        }
    },
    
    components: {
        TelegramAlbum: window.TelegramAlbum
    },
    
    methods: {
        // 切换消息选择状态
        toggleSelect() {
            this.$emit('toggle-select', this.message.id);
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
            if (!this.message.id) return '#';
            
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
        
        
        // 🔥 Linus风格：操作方法被事件委托取代，不再需要Vue事件
        
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
        }
    },
    template: `
        <div class="message-content-wrapper">
            <!-- 消息头部 -->
            <div class="message-header">
                <div class="message-info">
                    <!-- 选择框 -->
                    <input type="checkbox" 
                           :checked="$emit('is-selected', message.id)"
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
                    <span v-if="(message.filter_reason || message.rejection_reason) && message.status === 'rejected'" 
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
                            <span class="content-label">🔍 过滤后内容</span>
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
                            
                            <!-- 过滤后的文本内容（高亮广告关键词） -->
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
                    
                    <!-- 右栏：原始内容（包含媒体） -->
                    <div class="content-column content-original">
                        <div class="content-column-header">
                            <span class="content-label">📄 原始内容</span>
                        </div>
                        <div class="content-column-body">
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
                            
                        </div>
                    </div>
                </div>
                
                <!-- 消息底部信息 -->
                <div class="message-footer">
                    <!-- 源消息ID -->
                    <div v-if="message.source_channel && message.message_id" class="source-message-id">
                        消息ID: #{{ message.source_channel }}:{{ message.message_id }}
                    </div>
                    
                    
                    <!-- 原消息链接 -->
                    <div v-if="message.source_channel_link_prefix && message.id" class="original-message-link-container">
                        <a :href="getOriginalMessageLink()" 
                           target="_blank" 
                           class="original-message-link"
                           @click.stop>
                            查看原消息
                        </a>
                    </div>
                </div>
            </div>
            
            <!-- 操作按钮 -->
            <div v-if="message.status === 'pending'" class="message-actions">
                <button data-action="editMessage" :data-message-id="message.id" class="btn btn-sm btn-secondary">
                    ✏️ 编辑
                </button>
                <button 
                    data-action="approveMessage" 
                    :data-message-id="computedMessageId" 
                    :disabled="$parent.isPublishing && $parent.isPublishing(message.id)"
                    :class="['btn', 'btn-sm', 'btn-success', 
                             $parent.isPublishing && $parent.isPublishing(message.id) ? 'disabled' : '']">
                    {{ $parent.isPublishing && $parent.isPublishing(message.id) ? '⏳ 发布中...' : '📤 发布' }}
                </button>
                <button data-action="rejectMessage" :data-message-id="computedMessageId" class="btn btn-sm btn-danger">
                    ❌ 拒绝
                </button>
                <button :data-action="isMessageAd(message) ? 'markAsNotAd' : 'markAsAd'" 
                        :data-message-id="computedMessageId" 
                        class="btn btn-sm btn-warning">
                    {{ isMessageAd(message) ? '✅ 不是广告' : '🚫 广告' }}
                </button>
                <button data-action="trainTail" :data-message-id="computedMessageId" class="btn btn-sm btn-info">
                    ✂️ 尾部
                </button>
                <button 
                    data-action="filterContent" 
                    :data-message-id="computedMessageId" 
                    :disabled="$parent.isFiltering && $parent.isFiltering(message.id)"
                    :class="['btn', 'btn-sm', 'btn-primary', 
                             $parent.isFiltering && $parent.isFiltering(message.id) ? 'disabled' : '']">
                    {{ $parent.isFiltering && $parent.isFiltering(message.id) ? '🔄 过滤中...' : '🎯 过滤' }}
                </button>
            </div>
            
            <!-- 已拒绝消息的恢复按钮 -->
            <div v-else-if="message.status === 'rejected'" class="message-actions">
                <button data-action="restoreMessage" :data-message-id="computedMessageId" class="btn btn-sm btn-warning">
                    🔄 恢复
                </button>
            </div>
            
            <!-- 已发送消息的恢复按钮 -->
            <div v-else-if="message.status === 'approved'" class="message-actions">
                <button data-action="restoreMessage" :data-message-id="computedMessageId" class="btn btn-sm btn-warning">
                    🔄 恢复
                </button>
            </div>
        </div>
    `
};

// 注册组件
window.MessageContentRenderer = MessageContentRenderer;