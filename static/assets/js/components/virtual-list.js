// 虚拟列表组件 - 解决大量消息渲染性能问题

const VirtualList = {
    name: 'VirtualList',
    props: {
        items: {
            type: Array,
            default: () => []
        },
        itemHeight: {
            type: Number,
            default: 200
        },
        containerHeight: {
            type: Number,
            default: 600
        },
        bufferSize: {
            type: Number,
            default: 5
        }
    },
    
    data() {
        return {
            scrollTop: 0,
            containerRef: null
        };
    },
    
    computed: {
        // 可见区域内的项目数量
        visibleCount() {
            return Math.ceil(this.containerHeight / this.itemHeight);
        },
        
        // 当前滚动位置对应的起始索引
        startIndex() {
            const index = Math.floor(this.scrollTop / this.itemHeight);
            return Math.max(0, index - this.bufferSize);
        },
        
        // 结束索引
        endIndex() {
            const index = this.startIndex + this.visibleCount + this.bufferSize * 2;
            return Math.min(this.items.length - 1, index);
        },
        
        // 实际渲染的项目
        visibleItems() {
            return this.items.slice(this.startIndex, this.endIndex + 1);
        },
        
        // 容器总高度
        totalHeight() {
            return this.items.length * this.itemHeight;
        },
        
        // 上方偏移量
        offsetY() {
            return this.startIndex * this.itemHeight;
        }
    },
    
    mounted() {
        this.containerRef = this.$refs.container;
        this.containerRef.addEventListener('scroll', this.handleScroll, { passive: true });
    },
    
    beforeUnmount() {
        if (this.containerRef) {
            this.containerRef.removeEventListener('scroll', this.handleScroll);
        }
    },
    
    methods: {
        handleScroll(e) {
            this.scrollTop = e.target.scrollTop;
            
            // 检查是否接近底部，触发加载更多
            const { scrollTop, scrollHeight, clientHeight } = e.target;
            const scrollPercentage = (scrollTop + clientHeight) / scrollHeight;
            
            if (scrollPercentage > 0.9) {
                this.$emit('load-more');
            }
        },
        
        // 滚动到指定项目
        scrollToItem(index) {
            if (this.containerRef) {
                this.containerRef.scrollTop = index * this.itemHeight;
            }
        },
        
        // 获取项目在虚拟列表中的实际索引
        getItemIndex(virtualIndex) {
            return this.startIndex + virtualIndex;
        }
    },
    
    template: `
        <div 
            ref="container"
            class="virtual-list-container"
            :style="{ height: containerHeight + 'px', overflow: 'auto' }"
        >
            <div class="virtual-list-phantom" :style="{ height: totalHeight + 'px' }"></div>
            <div 
                class="virtual-list-content"
                :style="{ transform: 'translateY(' + offsetY + 'px)' }"
            >
                <div
                    v-for="(item, index) in visibleItems"
                    :key="item.id || (startIndex + index)"
                    class="virtual-list-item"
                    :style="{ height: itemHeight + 'px' }"
                >
                    <slot :item="item" :index="getItemIndex(index)"></slot>
                </div>
            </div>
        </div>
    `
};

// 注册全局组件
window.VirtualList = VirtualList;