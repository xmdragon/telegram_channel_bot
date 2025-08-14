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
        
        // 媒体网格类
        mediaGridClass() {
            if (!this.isCombinedMessage) return '';
            
            const count = this.message.media_group_display.length;
            if (count === 1) return 'media-grid-single';
            if (count === 2) return 'media-grid-double';
            if (count >= 3) return 'media-grid-triple';
            return '';
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
                    <!-- 组合消息的媒体组 -->
                    <div v-if="isCombinedMessage" 
                         class="media-grid"
                         :class="mediaGridClass">
                        <div v-for="(media, index) in message.media_group_display" :key="index">
                            <!-- 组合消息中的图片 -->
                            <img v-if="media.media_type === 'photo' && media.display_url" 
                                 :src="media.display_url"
                                 class="media-image media-group-item"
                                 loading="lazy"
                                 @click.stop="openMediaPreview(media.display_url)"
                                 @error="handleMediaError">
                            
                            <!-- 组合消息中的视频 -->
                            <video v-else-if="media.media_type === 'video' && media.display_url"
                                   :src="media.display_url"
                                   class="media-video media-group-item"
                                   controls
                                   preload="none">
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
                             class="media-image"
                             loading="lazy"
                             @click.stop="openMediaPreview(message.media_display_url)"
                             @error="handleMediaError">
                        
                        <!-- 视频 -->
                        <video v-else-if="message.media_type === 'video' && message.media_display_url"
                               :src="message.media_display_url"
                               class="media-video"
                               controls
                               preload="none">
                        </video>
                        
                        <!-- 媒体加载失败或其他媒体类型 -->
                        <div v-else-if="message.media_type && (!message.media_display_url || mediaLoadError)" 
                             class="media-placeholder">
                            <div>
                                📷 {{ message.media_type === 'photo' ? '图片' : 
                                      message.media_type === 'video' ? '视频' : 
                                      message.media_type }}
                                <div class="media-missing-text">媒体文件缺失</div>
                            </div>
                        </div>
                    </template>
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