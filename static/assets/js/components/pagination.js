/**
 * 统一分页组件
 *
 * 功能：
 * - 支持完整分页（首页/末页/页码/跳转）
 * - 支持简单分页（上一页/下一页）
 * - 统一的样式和交互
 * - Vue 3组件实现
 */

window.PaginationComponent = {
    name: 'pagination-component',
    props: {
        // 分页数据
        currentPage: {
            type: Number,
            default: 1
        },
        totalCount: {
            type: Number,
            default: 0
        },
        pageSize: {
            type: Number,
            default: 20
        },
        // 分页模式：'full' 完整分页，'simple' 简单分页
        mode: {
            type: String,
            default: 'full'
        },
        // 是否显示总数信息
        showInfo: {
            type: Boolean,
            default: true
        }
    },
    
    data() {
        return {
            jumpToPage: this.currentPage
        };
    },
    
    computed: {
        totalPages() {
            return Math.ceil(this.totalCount / this.pageSize);
        },
        
        // 获取分页数字（用于完整分页模式）
        pageNumbers() {
            const totalPages = this.totalPages;
            const current = this.currentPage;
            const pages = [];
            
            if (totalPages <= 7) {
                // 总页数较少，显示所有页码
                for (let i = 1; i <= totalPages; i++) {
                    pages.push(i);
                }
            } else {
                // 总页数较多，智能省略
                pages.push(1);
                
                if (current > 4) {
                    pages.push('...');
                }
                
                const start = Math.max(2, current - 2);
                const end = Math.min(totalPages - 1, current + 2);
                
                for (let i = start; i <= end; i++) {
                    pages.push(i);
                }
                
                if (current < totalPages - 3) {
                    pages.push('...');
                }
                
                if (totalPages > 1) {
                    pages.push(totalPages);
                }
            }
            
            return pages;
        }
    },
    
    watch: {
        currentPage(newVal) {
            this.jumpToPage = newVal;
        }
    },
    
    methods: {
        // 处理页面变更
        handlePageChange(page) {
            if (typeof page !== 'number' || page < 1 || page > this.totalPages || page === this.currentPage) {
                return;
            }
            this.$emit('page-change', page);
        },
        
        // 跳转到指定页面
        jumpToPageHandler() {
            const page = parseInt(this.jumpToPage);
            if (page >= 1 && page <= this.totalPages) {
                this.handlePageChange(page);
            }
        },
        
        // 处理键盘事件
        handleKeyup(event) {
            if (event.key === 'Enter') {
                this.jumpToPageHandler();
            }
        }
    },
    
    template: `
        <div class="pagination-section" v-if="totalCount > 0">
            <div class="pagination">
                <!-- 信息显示 -->
                <div class="pagination-info" v-if="showInfo">
                    共 {{ totalCount }} 条记录
                </div>
                
                <!-- 完整分页模式 -->
                <div class="pagination-controls" v-if="mode === 'full'">
                    <button @click="handlePageChange(1)" 
                            :disabled="currentPage === 1" 
                            class="btn btn-sm">首页</button>
                    <button @click="handlePageChange(currentPage - 1)" 
                            :disabled="currentPage === 1" 
                            class="btn btn-sm">上一页</button>
                    
                    <span class="page-numbers">
                        <template v-for="page in pageNumbers" :key="page">
                            <button v-if="typeof page === 'number'"
                                    @click="handlePageChange(page)"
                                    :class="{ 'active': page === currentPage }"
                                    class="btn btn-sm page-btn">
                                {{ page }}
                            </button>
                            <span v-else class="page-ellipsis">{{ page }}</span>
                        </template>
                    </span>
                    
                    <button @click="handlePageChange(currentPage + 1)" 
                            :disabled="currentPage >= totalPages" 
                            class="btn btn-sm">下一页</button>
                    <button @click="handlePageChange(totalPages)" 
                            :disabled="currentPage >= totalPages" 
                            class="btn btn-sm">末页</button>
                    
                    <div class="jump-to" v-if="totalPages > 1">
                        跳转到 
                        <input type="number" 
                               v-model.number="jumpToPage" 
                               @keyup="handleKeyup"
                               :min="1" 
                               :max="totalPages" 
                               class="page-input"> 页
                        <button @click="jumpToPageHandler" class="btn btn-sm btn-primary">跳转</button>
                    </div>
                </div>
                
                <!-- 简单分页模式 -->
                <div class="pagination-controls simple" v-else-if="mode === 'simple'">
                    <button @click="handlePageChange(currentPage - 1)" 
                            :disabled="currentPage <= 1" 
                            class="btn btn-outline">上一页</button>
                    <span class="pagination-current">
                        第 {{ currentPage }} / {{ totalPages }} 页
                    </span>
                    <button @click="handlePageChange(currentPage + 1)" 
                            :disabled="currentPage >= totalPages" 
                            class="btn btn-outline">下一页</button>
                </div>
            </div>
        </div>
    `
};