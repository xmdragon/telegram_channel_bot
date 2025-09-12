/**
 * Telegram官方风格相册组件
 * 使用官方布局算法实现完美的媒体组合显示
 */

const TelegramAlbum = {
    name: 'TelegramAlbum',
    props: {
        // 媒体项数组
        mediaItems: {
            type: Array,
            required: true,
            validator: (items) => {
                return Array.isArray(items) && items.every(item => 
                    item && typeof item === 'object' && 
                    (item.url || item.display_url) &&
                    typeof item.media_type === 'string'
                );
            }
        },
        // 是否为自己发送的消息
        isOwn: {
            type: Boolean,
            default: false
        },
        // 最大宽度
        maxWidth: {
            type: Number,
            default: 380
        },
        // 是否为移动端
        isMobile: {
            type: Boolean,
            default: false
        },
        // 是否显示索引
        showIndex: {
            type: Boolean,
            default: false
        },
        // 间距
        spacing: {
            type: Number,
            default: 2
        }
    },

    emits: [
        'media-click',
        'media-load',
        'media-error'
    ],

    data() {
        return {
            layout: null,
            containerStyle: null,
            loadingStates: {},
            errorStates: {}
        };
    },

    computed: {
        // 自动检测移动端
        isAutoMobile() {
            // 如果用户未明确设置isMobile，则自动检测
            if (this.isMobile !== false) {
                return window.innerWidth <= 768 || /Mobi|Android|iPhone|iPad/.test(navigator.userAgent);
            }
            return this.isMobile;
        },

        // 响应式最大宽度
        responsiveMaxWidth() {
            if (this.isAutoMobile) {
                // 移动端自动适配屏幕宽度
                return Math.min(this.maxWidth, window.innerWidth * 0.9);
            }
            return this.maxWidth;
        },

        // 计算布局
        computedLayout() {
            if (!this.mediaItems || this.mediaItems.length === 0) {
                return null;
            }

            // 检查依赖是否加载
            if (!window.calculateTelegramAlbumLayout) {
                console.warn('Telegram album layout function not loaded yet');
                return null;
            }

            try {
                return window.calculateTelegramAlbumLayout({
                    mediaItems: this.mediaItems.map(item => ({
                        width: item.width || 640,
                        height: item.height || 640,
                        ...item
                    })),
                    isOwn: this.isOwn,
                    isMobile: this.isAutoMobile,
                    maxWidth: this.responsiveMaxWidth,
                    spacing: this.spacing
                });
            } catch (error) {
                console.error('Telegram album layout calculation failed:', error);
                return null;
            }
        },

        // 容器样式
        albumContainerStyle() {
            if (!this.computedLayout) return {};
            
            const { width, height } = this.computedLayout.containerStyle;
            return {
                position: 'relative',
                width: `${width}px`,
                height: `${height}px`,
                overflow: 'hidden',
                borderRadius: '18px',
                background: '#000'
            };
        }
    },

    methods: {
        // 获取媒体项样式
        getMediaItemStyle(index) {
            if (!this.computedLayout) return {};
            
            const layoutItem = this.computedLayout.layout[index];
            if (!layoutItem) return {};

            const { dimensions, sides } = layoutItem;
            const { x, y, width, height } = dimensions;

            // 基础样式
            const style = {
                position: 'absolute',
                left: `${x}px`,
                top: `${y}px`,
                width: `${width}px`,
                height: `${height}px`,
                overflow: 'hidden'
            };

            // 根据边缘位置设置圆角
            const borderRadius = this.getBorderRadius(sides);
            if (borderRadius) {
                style.borderRadius = borderRadius;
            }

            return style;
        },

        // 获取底部右侧的边缘标识（安全访问）
        getBottomRightSides() {
            const AlbumRectPart = window.AlbumRectPart;
            if (!AlbumRectPart) return 0;
            return AlbumRectPart.Bottom | AlbumRectPart.Right;
        },

        // 根据边缘位置计算圆角
        getBorderRadius(sides) {
            const AlbumRectPart = window.AlbumRectPart;
            if (!AlbumRectPart) {
                return '18px'; // 如果依赖未加载，使用默认圆角
            }
            
            const radius = '18px';
            const none = '0';
            
            const topLeft = (sides & AlbumRectPart.Top) && (sides & AlbumRectPart.Left) ? radius : none;
            const topRight = (sides & AlbumRectPart.Top) && (sides & AlbumRectPart.Right) ? radius : none;
            const bottomRight = (sides & AlbumRectPart.Bottom) && (sides & AlbumRectPart.Right) ? radius : none;
            const bottomLeft = (sides & AlbumRectPart.Bottom) && (sides & AlbumRectPart.Left) ? radius : none;

            return `${topLeft} ${topRight} ${bottomRight} ${bottomLeft}`;
        },

        // 获取媒体内容样式
        getMediaContentStyle() {
            return {
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                display: 'block',
                transition: 'opacity 0.2s ease',
                cursor: 'pointer'
            };
        },

        // 处理媒体点击
        handleMediaClick(mediaItem, index) {
            this.$emit('media-click', {
                mediaItem,
                index,
                url: this.getMediaUrl(mediaItem)
            });
        },

        // 处理媒体加载 - Vue 3兼容：直接赋值替代$set
        handleMediaLoad(mediaItem, index) {
            this.loadingStates[index] = false;
            this.$emit('media-load', { mediaItem, index });
        },

        // 处理媒体错误 - Vue 3兼容：直接赋值替代$set
        handleMediaError(mediaItem, index) {
            this.errorStates[index] = true;
            this.loadingStates[index] = false;
            this.$emit('media-error', { mediaItem, index });
        },

        // 获取媒体URL
        getMediaUrl(mediaItem) {
            // 优先使用已经格式化好的 URL
            if (mediaItem.url) return mediaItem.url;
            if (mediaItem.display_url) return mediaItem.display_url;
            // 向后兼容 file_path
            if (mediaItem.file_path) {
                return mediaItem.file_path.startsWith('/') ? 
                       mediaItem.file_path : 
                       `/${mediaItem.file_path}`;
            }
            return '';
        },

        // 检查是否为视频
        isVideo(mediaItem) {
            return mediaItem.media_type === 'video';
        },

        // 检查是否为图片
        isPhoto(mediaItem) {
            return mediaItem.media_type === 'photo';
        },

        // 获取媒体类型图标
        getMediaTypeIcon(mediaType) {
            const icons = {
                photo: '📷',
                video: '🎬',
                document: '📄',
                animation: '🎬',
                sticker: '🎭'
            };
            return icons[mediaType] || '❓';
        }
    },

    template: `
        <div class="telegram-album" :style="albumContainerStyle" v-if="computedLayout">
            <div 
                v-for="(mediaItem, index) in mediaItems" 
                :key="index"
                class="media-item"
                :style="getMediaItemStyle(index)"
                @click="handleMediaClick(mediaItem, index)"
            >
                <!-- 图片媒体 -->
                <img 
                    v-if="isPhoto(mediaItem) && getMediaUrl(mediaItem)"
                    :src="getMediaUrl(mediaItem)"
                    :style="getMediaContentStyle()"
                    :alt="'媒体 ' + (index + 1)"
                    loading="lazy"
                    @load="handleMediaLoad(mediaItem, index)"
                    @error="handleMediaError(mediaItem, index)"
                />
                
                <!-- 视频媒体 -->
                <video 
                    v-else-if="isVideo(mediaItem) && getMediaUrl(mediaItem)"
                    :src="getMediaUrl(mediaItem)"
                    :style="getMediaContentStyle()"
                    preload="none"
                    controls
                    @loadedmetadata="handleMediaLoad(mediaItem, index)"
                    @error="handleMediaError(mediaItem, index)"
                />
                
                <!-- 媒体占位符 -->
                <div 
                    v-else
                    class="media-placeholder"
                    :style="{
                        width: '100%',
                        height: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: '#2a2a2a',
                        color: '#888',
                        fontSize: '12px'
                    }"
                >
                    <div style="font-size: 20px; margin-bottom: 4px;">
                        {{ getMediaTypeIcon(mediaItem.media_type) }}
                    </div>
                    <div>{{ mediaItem.media_type || '未知类型' }}</div>
                    <div v-if="!getMediaUrl(mediaItem)" style="color: #ff6b6b; font-size: 10px;">
                        媒体文件缺失
                    </div>
                </div>
                
                <!-- 媒体索引 -->
                <div 
                    v-if="showIndex"
                    class="media-index"
                    :style="{
                        position: 'absolute',
                        top: '4px',
                        left: '4px',
                        background: 'rgba(0, 0, 0, 0.7)',
                        color: '#fff',
                        fontSize: '10px',
                        padding: '2px 5px',
                        borderRadius: '3px',
                        zIndex: 2,
                        fontWeight: '600'
                    }"
                >
                    {{ index + 1 }}
                </div>
                
                <!-- 加载状态 -->
                <div 
                    v-if="loadingStates[index]"
                    class="media-loading"
                    :style="{
                        position: 'absolute',
                        top: '0',
                        left: '0',
                        right: '0',
                        bottom: '0',
                        background: 'rgba(0, 0, 0, 0.5)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#fff',
                        fontSize: '12px',
                        zIndex: 3
                    }"
                >
                    加载中...
                </div>
                
                <!-- 错误状态 -->
                <div 
                    v-if="errorStates[index]"
                    class="media-error"
                    :style="{
                        position: 'absolute',
                        top: '0',
                        left: '0',
                        right: '0',
                        bottom: '0',
                        background: 'rgba(255, 107, 107, 0.1)',
                        border: '1px dashed rgba(255, 107, 107, 0.3)',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#ff6b6b',
                        fontSize: '12px',
                        zIndex: 3
                    }"
                >
                    <div style="font-size: 20px; margin-bottom: 4px;">⚠️</div>
                    <div>加载失败</div>
                </div>
            </div>
            
            <!-- 剩余媒体计数（如果有超过显示限制的媒体） -->
            <div 
                v-if="mediaItems.length > 9"
                class="remaining-count"
                :style="{
                    position: 'absolute',
                    top: '0',
                    right: '0',
                    bottom: '0',
                    width: getMediaItemStyle(8).width,
                    background: 'rgba(0, 0, 0, 0.75)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#fff',
                    fontSize: '16px',
                    fontWeight: 'bold',
                    cursor: 'pointer',
                    zIndex: 4,
                    borderRadius: this.getBorderRadius(this.getBottomRightSides())
                }"
                @click="handleMediaClick(mediaItems[8], 8)"
            >
                +{{ mediaItems.length - 9 }}
            </div>
        </div>
        
        <!-- 布局计算失败的回退显示 -->
        <div v-else class="telegram-album-fallback" style="padding: 16px; text-align: center; color: #888;">
            <div style="margin-bottom: 8px;">📷</div>
            <div>媒体布局计算失败</div>
        </div>
    `
};

// 注册组件到全局
if (typeof window !== 'undefined') {
    window.TelegramAlbum = TelegramAlbum;
}