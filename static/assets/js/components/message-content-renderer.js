// 消息内容渲染器组件 - 优化的消息显示组件

const MessageContentRenderer = {
    name: 'MessageContentRenderer',
    props: {
        message: {
            type: Object,
            required: true
        }
    },
    
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
        
        // 消息状态标签
        statusTag() {
            const statusMap = {
                'pending': { text: '待审核', type: 'warning' },
                'approved': { text: '已批准', type: 'success' },
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
                const date = new Date(timeStr);
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
            if (!this.message.message_id) return '#';
            
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
        }
    },
    
    template: `
        <div class="message-content-wrapper" @click="toggleSelect">
            <!-- 消息头部 -->
            <div class="message-header">
                <div class="message-info">
                    <!-- 选择框 -->
                    <input type="checkbox" 
                           v-if="message.status === 'pending'"
                           :checked="$emit('is-selected', message.id)"
                           @click.stop
                           @change="toggleSelect">
                    
                    <!-- 数据库编号 -->
                    <span class="message-id">#{{ message.id }}</span>
                    
                    <!-- 频道信息 -->
                    <span class="message-channel">
                        📢 {{ message.source_channel_title || message.source_channel || '未知频道' }}
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
                
                <!-- 原频道链接 -->
                <div v-if="message.source_channel_link_prefix && message.message_id" class="message-footer">
                    🔗 原消息链接: 
                    <a :href="getOriginalMessageLink()" 
                       target="_blank" 
                       class="original-message-link"
                       @click.stop>
                        查看原消息
                    </a>
                </div>
            </div>
            
            <!-- 操作按钮 -->
            <div v-if="message.status === 'pending'" class="message-actions" @click.stop>
                <button @click="editMessage" class="btn btn-sm btn-secondary">
                    ✏️ 编辑
                </button>
                <button @click="approveMessage" class="btn btn-sm btn-success">
                    ✅ 批准
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