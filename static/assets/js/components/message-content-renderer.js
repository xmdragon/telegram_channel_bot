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
        'get-media-type-icon'
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
        
        // 是否为重复消息
        isDuplicateMessage() {
            return !!(this.message.duplicate_info && this.message.duplicate_original_id);
        },
        
        // 是否应该显示左右栏对比（始终显示，只要有内容字段或有媒体）
        shouldShowContentComparison() {
            if (this.isDuplicateMessage) {
                return true; // 重复消息总是显示对比
            }
            return !!(this.message.content && this.message.filtered_content) || 
                   !!(this.message.media_type || this.isCombinedMessage);
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
        }
    },
    
    methods: {
        // 切换消息选择状态
        toggleSelect() {
            if (this.message.status === 'pending') {
                this.$emit('toggle-select', this.message.id);
            }
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
                    media.display_url && media.display_url.trim() !== ''
                );
            }
            
            return this.message.media_display_url && 
                   this.message.media_display_url.trim() !== '' && 
                   !this.mediaLoadError;
        },
        
        // 单个操作方法
        approveMessage() {
            this.$emit('approve-message', this.message.id);
        },
        
        rejectMessage() {
            this.$emit('reject-message', this.message.id);
        },
        
        editMessage() {
            this.$emit('edit-message', this.message);
        },
        
        markAsAd() {
            this.$emit('mark-as-ad', this.message);
        },
        
        trainTail() {
            this.$emit('train-tail', this.message);
        },
        
        filterTail() {
            this.$emit('filter-tail', this.message);
        },
        
        refetchMedia() {
            this.$emit('refetch-media', this.message);
        },
        
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
        
        // 处理图片错误
        handleImageError(message, event) {
            this.$emit('handle-image-error', message, event);
        },
        
        // 获取媒体类型图标
        getMediaTypeIcon(mediaType) {
            return this.$emit('get-media-type-icon', mediaType);
        }
    },
    
    template: `
        <div class="message-content-wrapper">
            <!-- 消息头部 -->
            <div class="message-header">
                <div class="message-info">
                    <!-- 选择框 -->
                    <input type="checkbox" 
                           v-if="message.status === 'pending'"
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
                    <span v-if="message.is_ad" class="tag tag-danger">广告</span>
                    <span v-if="message.filter_reason && message.status === 'rejected'" 
                          class="tag tag-secondary reject-reason" 
                          :title="message.filter_reason">
                        拒因: {{ message.filter_reason.length > 15 ? 
                                message.filter_reason.substring(0, 15) + '...' : 
                                message.filter_reason }}
                    </span>
                </div>
            </div>
            
            <!-- 消息内容 -->
            <div class="message-content">
                <!-- 重复消息特殊对比显示 -->
                <div v-if="isDuplicateMessage" class="duplicate-comparison-layout">
                    <!-- 左栏：被拒绝的重复消息 -->
                    <div class="comparison-column duplicate-column">
                        <div class="comparison-column-header">
                            <span class="comparison-label">🚫 被拒绝消息（重复）</span>
                            <span v-if="message.duplicate_type" class="duplicate-type-tag">{{ message.duplicate_type }}</span>
                        </div>
                        <div class="comparison-column-body">
                            <!-- 重复消息的媒体内容 -->
                            <div v-if="message.media_type || isCombinedMessage" class="comparison-media-section">
                                <!-- 组合消息的媒体组 -->
                                <div v-if="isCombinedMessage" 
                                     class="media-grid media-grid-comparison"
                                     :class="'media-grid-' + (message.media_group_display.length <= 3 ? 
                                              (['single', 'double', 'triple'][message.media_group_display.length - 1]) : 
                                              'multiple')">
                                    <div v-for="(media, index) in message.media_group_display" :key="index">
                                        <img v-if="media.media_type === 'photo' && media.display_url" 
                                             :src="media.display_url"
                                             class="media-image media-comparison-item"
                                             @click.stop="openMediaPreview(media.display_url)">
                                        <video v-else-if="media.media_type === 'video' && media.display_url"
                                               :src="media.display_url"
                                               class="media-video media-comparison-item"
                                               controls>
                                        </video>
                                        <div v-else class="media-placeholder media-comparison-other">
                                            {{ media.media_type }}
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 单个媒体 -->
                                <template v-else>
                                    <img v-if="message.media_type === 'photo' && message.media_display_url && !mediaLoadError" 
                                         :src="message.media_display_url"
                                         class="media-image media-comparison"
                                         @click.stop="openMediaPreview(message.media_display_url)"
                                         @error="handleMediaError">
                                    <video v-else-if="message.media_type === 'video' && message.media_display_url"
                                           :src="message.media_display_url"
                                           class="media-video media-comparison"
                                           controls>
                                    </video>
                                    <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)" 
                                         class="media-placeholder media-comparison">
                                        <div>
                                            📷 {{ message.media_type === 'photo' ? '图片' : 
                                                 message.media_type === 'video' ? '视频' : 
                                                 message.media_type }}
                                            <div class="media-missing-text">媒体文件缺失</div>
                                        </div>
                                    </div>
                                </template>
                            </div>
                            
                            <!-- 重复消息的文本内容 -->
                            <div v-if="message.content || message.filtered_content" class="message-text comparison-text">
                                {{ message.filtered_content || message.content }}
                            </div>
                            <div v-else-if="!message.media_type" class="content-empty">
                                暂无文本内容
                            </div>
                            
                            <!-- 重复消息信息 -->
                            <div class="duplicate-message-info">
                                <div class="info-row">
                                    <span class="info-label">消息ID:</span>
                                    <span class="info-value">#{{ message.id }}</span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">时间:</span>
                                    <span class="info-value">{{ formatTime(message.created_at) }}</span>
                                </div>
                                <div v-if="message.source_channel_link_prefix && message.message_id" class="info-row">
                                    <span class="info-label">原消息:</span>
                                    <span class="info-value">
                                        <a :href="message.source_channel_link_prefix + '/' + message.message_id" 
                                           target="_blank" 
                                           class="original-message-link">
                                            查看原消息
                                        </a>
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 右栏：原始存在的消息 -->
                    <div class="comparison-column original-column">
                        <div class="comparison-column-header">
                            <span class="comparison-label">✅ 原始消息（已存在）</span>
                        </div>
                        <div class="comparison-column-body">
                            <!-- 原始消息的媒体内容 -->
                            <div v-if="message.duplicate_info && message.duplicate_info.media_type" class="comparison-media-section">
                                <!-- 组合消息的媒体组 -->
                                <div v-if="message.duplicate_info.is_combined && message.duplicate_info.media_group_display && message.duplicate_info.media_group_display.length > 0" 
                                     class="media-grid media-grid-comparison"
                                     :class="'media-grid-' + (message.duplicate_info.media_group_display.length <= 3 ? 
                                              (['single', 'double', 'triple'][message.duplicate_info.media_group_display.length - 1]) : 
                                              'multiple')">
                                    <div v-for="(media, index) in message.duplicate_info.media_group_display" :key="index">
                                        <img v-if="media.media_type === 'photo' && media.display_url" 
                                             :src="media.display_url"
                                             class="media-image media-comparison-item"
                                             @click.stop="openMediaPreview(media.display_url)">
                                        <video v-else-if="media.media_type === 'video' && media.display_url"
                                               :src="media.display_url"
                                               class="media-video media-comparison-item"
                                               controls>
                                        </video>
                                        <div v-else class="media-placeholder media-comparison-other">
                                            {{ media.media_type }}
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 单个媒体 -->
                                <template v-else>
                                    <img v-if="message.duplicate_info.media_type === 'photo' && message.duplicate_info.media_display_url" 
                                         :src="message.duplicate_info.media_display_url"
                                         class="media-image media-comparison"
                                         @click.stop="openMediaPreview(message.duplicate_info.media_display_url)">
                                    <video v-else-if="message.duplicate_info.media_type === 'video' && message.duplicate_info.media_display_url"
                                           :src="message.duplicate_info.media_display_url"
                                           class="media-video media-comparison"
                                           controls>
                                    </video>
                                    <div v-else-if="message.duplicate_info.media_type && !message.duplicate_info.media_display_url" 
                                         class="media-placeholder media-comparison">
                                        <div>
                                            📷 {{ message.duplicate_info.media_type === 'photo' ? '图片' : 
                                                 message.duplicate_info.media_type === 'video' ? '视频' : 
                                                 message.duplicate_info.media_type }}
                                            <div class="media-missing-text">媒体文件缺失</div>
                                        </div>
                                    </div>
                                </template>
                            </div>
                            
                            <!-- 原始消息的文本内容 -->
                            <div v-if="message.duplicate_info && (message.duplicate_info.filtered_content || message.duplicate_info.content)" 
                                 class="message-text comparison-text">
                                {{ message.duplicate_info.filtered_content || message.duplicate_info.content }}
                            </div>
                            <div v-else-if="message.duplicate_info && !message.duplicate_info.media_type" class="content-empty">
                                暂无文本内容
                            </div>
                            <div v-else class="content-empty">
                                加载原始消息数据中...
                            </div>
                            
                            <!-- 原始消息信息 -->
                            <div v-if="message.duplicate_info" class="duplicate-message-info">
                                <div class="info-row">
                                    <span class="info-label">消息ID:</span>
                                    <span class="info-value">#{{ message.duplicate_info.source_channel }}:{{ message.duplicate_info.message_id }}</span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">时间:</span>
                                    <span class="info-value">{{ formatTime(message.duplicate_info.created_at) }}</span>
                                </div>
                                <div class="info-row">
                                    <span class="info-label">状态:</span>
                                    <span class="info-value status-tag" :class="'tag-' + statusTag.type">
                                        {{ statusTag.text }}
                                    </span>
                                </div>
                                <div v-if="message.duplicate_info.source_channel_link_prefix && message.duplicate_info.message_id" class="info-row">
                                    <span class="info-label">原消息:</span>
                                    <span class="info-value">
                                        <a :href="message.duplicate_info.source_channel_link_prefix + '/' + message.duplicate_info.message_id" 
                                           target="_blank" 
                                           class="original-message-link">
                                            查看原消息
                                        </a>
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 常规消息双栏内容对比显示 -->
                <div v-else-if="shouldShowContentComparison" 
                     :class="['message-content-comparison', { 'unchanged': !isContentActuallyFiltered }]">
                    <!-- 左栏：过滤后内容（包含媒体） -->
                    <div class="content-column content-filtered">
                        <div class="content-column-header">
                            <span class="content-label">🔍 过滤后内容</span>
                        </div>
                        <div class="content-column-body">
                            <!-- 过滤后的媒体内容 -->
                            <div v-if="message.media_type || isCombinedMessage" class="column-media-section">
                                <!-- 组合消息的媒体组 -->
                                <div v-if="isCombinedMessage" 
                                     class="media-grid media-grid-compact"
                                     :class="'media-grid-' + (message.media_group_display.length <= 3 ? 
                                              (['single', 'double', 'triple'][message.media_group_display.length - 1]) : 
                                              'multiple')">
                                    <div v-for="(media, index) in message.media_group_display" :key="index">
                                        <!-- 组合消息中的图片 -->
                                        <img v-if="media.media_type === 'photo' && media.display_url" 
                                             :src="media.display_url"
                                             class="media-image media-group-item"
                                             @click.stop="openMediaPreview(media.display_url)">
                                        
                                        <!-- 组合消息中的视频 -->
                                        <video v-else-if="media.media_type === 'video' && media.display_url"
                                               :src="media.display_url"
                                               class="media-video media-group-item"
                                               controls>
                                        </video>
                                        
                                        <!-- 其他媒体类型 -->
                                        <div v-else class="media-placeholder media-group-other">
                                            {{ media.media_type }}
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 单个媒体（非组合消息） -->
                                <template v-else>
                                    <!-- 图片 -->
                                    <img v-if="message.media_type === 'photo' && message.media_display_url && !mediaLoadError" 
                                         :src="message.media_display_url"
                                         class="media-image media-compact"
                                         @click.stop="openMediaPreview(message.media_display_url)"
                                         @error="handleMediaError">
                                    
                                    <!-- 视频 -->
                                    <video v-else-if="message.media_type === 'video' && message.media_display_url"
                                           :src="message.media_display_url"
                                           class="media-video media-compact"
                                           controls>
                                    </video>
                                    
                                    <!-- 媒体加载失败或其他媒体类型 -->
                                    <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)" 
                                         class="media-placeholder media-compact">
                                        <div>
                                            📷 {{ message.media_type === 'photo' ? '图片' : 
                                                 message.media_type === 'video' ? '视频' : 
                                                 message.media_type }}
                                            <div class="media-missing-text">媒体文件缺失</div>
                                        </div>
                                    </div>
                                </template>
                            </div>
                            
                            <!-- 过滤后的文本内容 -->
                            <div v-if="message.filtered_content" class="message-text">
                                {{ message.filtered_content }}
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
                            <!-- 原始的媒体内容（与左栏相同） -->
                            <div v-if="message.media_type || isCombinedMessage" class="column-media-section">
                                <!-- 组合消息的媒体组 -->
                                <div v-if="isCombinedMessage" 
                                     class="media-grid media-grid-compact"
                                     :class="'media-grid-' + (message.media_group_display.length <= 3 ? 
                                              (['single', 'double', 'triple'][message.media_group_display.length - 1]) : 
                                              'multiple')">
                                    <div v-for="(media, index) in message.media_group_display" :key="index">
                                        <!-- 组合消息中的图片 -->
                                        <img v-if="media.media_type === 'photo' && media.display_url" 
                                             :src="media.display_url"
                                             class="media-image media-group-item"
                                             @click.stop="openMediaPreview(media.display_url)">
                                        
                                        <!-- 组合消息中的视频 -->
                                        <video v-else-if="media.media_type === 'video' && media.display_url"
                                               :src="media.display_url"
                                               class="media-video media-group-item"
                                               controls>
                                        </video>
                                        
                                        <!-- 其他媒体类型 -->
                                        <div v-else class="media-placeholder media-group-other">
                                            {{ media.media_type }}
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 单个媒体（非组合消息） -->
                                <template v-else>
                                    <!-- 图片 -->
                                    <img v-if="message.media_type === 'photo' && message.media_display_url && !mediaLoadError" 
                                         :src="message.media_display_url"
                                         class="media-image media-compact"
                                         @click.stop="openMediaPreview(message.media_display_url)"
                                         @error="handleMediaError">
                                    
                                    <!-- 视频 -->
                                    <video v-else-if="message.media_type === 'video' && message.media_display_url"
                                           :src="message.media_display_url"
                                           class="media-video media-compact"
                                           controls>
                                    </video>
                                    
                                    <!-- 媒体加载失败或其他媒体类型 -->
                                    <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)" 
                                         class="media-placeholder media-compact">
                                        <div>
                                            📷 {{ message.media_type === 'photo' ? '图片' : 
                                                 message.media_type === 'video' ? '视频' : 
                                                 message.media_type }}
                                            <div class="media-missing-text">媒体文件缺失</div>
                                        </div>
                                    </div>
                                </template>
                            </div>
                            
                            <!-- 原始的文本内容 -->
                            <div v-if="message.content" class="message-text">
                                {{ message.content }}
                            </div>
                            <div v-else-if="!message.media_type" class="content-empty">
                                暂无原始内容
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 单栏内容显示（当没有过滤或内容相同时） -->
                <div v-else class="single-content-display">
                    <!-- 媒体内容 -->
                    <div v-if="message.media_type" class="message-media">
                        <!-- Telegram风格组合消息媒体组 -->
                        <div v-if="isCombinedMessage" class="telegram-media-container">
                            <!-- 媒体网格 -->
                            <div class="telegram-media-grid" :class="telegramMediaGridClass">
                                <div v-for="(media, index) in displayMediaItems" 
                                     :key="index"
                                     class="media-item">
                                    
                                    <!-- 图片 -->
                                    <img v-if="media.media_type === 'photo' && media.display_url" 
                                         :src="media.display_url"
                                         class="media-content"
                                         loading="lazy"
                                         @click.stop="openMediaPreview(media.display_url)"
                                         @error="handleMediaError">
                                    
                                    <!-- 视频 -->
                                    <video v-else-if="media.media_type === 'video' && media.display_url"
                                           :src="media.display_url"
                                           class="media-content media-video"
                                           controls
                                           preload="none">
                                    </video>
                                    
                                    <!-- 其他媒体类型或加载失败 -->
                                    <div v-else class="media-placeholder">
                                        <div class="icon">
                                            {{ media.media_type === 'photo' ? '📷' :
                                               media.media_type === 'video' ? '🎬' :
                                               media.media_type === 'document' ? '📄' :
                                               '❓' }}
                                        </div>
                                        <div>{{ media.media_type }}</div>
                                        <div v-if="!media.display_url" style="color: #ff6b6b; font-size: 10px;">缺失</div>
                                    </div>
                                    
                                    <!-- 剩余媒体计数覆盖层 -->
                                    <div v-if="media.isLast && media.remainingCount > 0" 
                                         class="remaining-count"
                                         @click.stop="openMediaPreview(media.display_url)">
                                        +{{ media.remainingCount }}
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- 单个媒体（非组合消息） -->
                        <div v-else class="telegram-media-container">
                            <div class="telegram-media-grid count-1">
                                <div class="media-item">
                                    <!-- 图片 -->
                                    <img v-if="message.media_type === 'photo' && message.media_display_url && !mediaLoadError" 
                                         :src="message.media_display_url"
                                         class="media-content"
                                         loading="lazy"
                                         @click.stop="openMediaPreview(message.media_display_url)"
                                         @error="handleMediaError">
                                    
                                    <!-- 视频 -->
                                    <video v-else-if="message.media_type === 'video' && message.media_display_url"
                                           :src="message.media_display_url"
                                           class="media-content media-video"
                                           controls
                                           preload="none">
                                    </video>
                                    
                                    <!-- 媒体加载失败或其他媒体类型 -->
                                    <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)" 
                                         class="media-placeholder">
                                        <div class="icon">
                                            {{ message.media_type === 'photo' ? '📷' : 
                                              message.media_type === 'video' ? '🎬' : 
                                              message.media_type === 'document' ? '📄' :
                                              '❓' }}
                                        </div>
                                        <div>{{ message.media_type === 'photo' ? '图片' : 
                                               message.media_type === 'video' ? '视频' : 
                                               message.media_type }}</div>
                                        <div style="color: #ff6b6b; font-size: 10px;">媒体文件缺失</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 文本内容 -->
                    <div v-if="formattedContent" class="message-text">
                        {{ formattedContent }}
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
                
                <!-- 消息底部信息 -->
                <div class="message-footer">
                    <!-- 源消息ID -->
                    <div v-if="message.source_channel && message.message_id" class="source-message-id">
                        消息ID: #{{ message.source_channel }}:{{ message.message_id }}
                    </div>
                    
                    <!-- 重复消息的源ID -->
                    <div v-else-if="message.duplicate_info && message.duplicate_info.source_channel && message.duplicate_info.message_id" class="source-message-id">
                        消息ID: #{{ message.duplicate_info.source_channel }}:{{ message.duplicate_info.message_id }}
                    </div>
                    
                    <!-- 原消息链接 -->
                    <div v-if="message.source_channel_link_prefix && message.id" class="original-message-link-container">
                        🔗 原消息链接: 
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
            <div v-if="message.status === 'pending'" class="message-actions" @click.stop>
                <button @click="editMessage" class="btn btn-sm btn-secondary">
                    ✏️ 编辑
                </button>
                <button @click="approveMessage" class="btn btn-sm btn-success">
                    📤 发布
                </button>
                <button @click="rejectMessage" class="btn btn-sm btn-danger">
                    ❌ 拒绝
                </button>
                <button @click="markAsAd" class="btn btn-sm btn-warning">
                    🚫 广告
                </button>
                <button @click="trainTail" class="btn btn-sm btn-info">
                    ✂️ 尾部
                </button>
                <button @click="filterTail" class="btn btn-sm btn-primary">
                    🎯 过滤
                </button>
                <button v-if="message.media_type && !mediaExists()" 
                        @click="refetchMedia" 
                        class="btn btn-sm btn-primary">
                    🔄 补抓
                </button>
            </div>
        </div>
    `
};

// 注册组件
window.MessageContentRenderer = MessageContentRenderer;