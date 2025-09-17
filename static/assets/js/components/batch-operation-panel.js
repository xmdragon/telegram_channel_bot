// 批量操作面板组件 - 提升批量操作效率

const BatchOperationPanel = {
    name: 'BatchOperationPanel',
    props: {
        selectedMessages: {
            type: Array,
            default: () => []
        },
        totalMessages: {
            type: Number,
            default: 0
        },
        buttonVisibility: {
            type: Object,
            default: () => ({})
        },
        filteredMessages: {
            type: Array,
            default: () => []
        }
    },
    
    data() {
        return {
            isProcessing: false,
            operationProgress: {
                current: 0,
                total: 0,
                status: '',
                visible: false
            },
            smartFilterEnabled: false
        };
    },
    
    computed: {
        selectedCount() {
            return this.selectedMessages.length;
        },
        
        canSelectAll() {
            return this.totalMessages > 0;
        },
        
        isAllSelected() {
            return this.selectedCount === this.totalMessages && this.totalMessages > 0;
        },
        
        hasSelection() {
            return this.selectedCount > 0;
        },
        
        // 分析选中消息的状态分布
        selectedMessageDetails() {
            if (!this.hasSelection || !this.filteredMessages.length) {
                return {
                    pending: 0,
                    approved: 0,
                    rejected: 0,
                    total: 0
                };
            }
            
            const details = {
                pending: 0,
                approved: 0,
                rejected: 0,
                total: this.selectedCount
            };
            
            // 根据选中的消息ID找到对应的消息对象
            const selectedMessageObjs = this.filteredMessages.filter(msg => 
                this.selectedMessages.includes(msg.id)
            );
            
            selectedMessageObjs.forEach(msg => {
                switch (msg.status) {
                    case 'pending':
                        details.pending++;
                        break;
                    case 'approved':
                        details.approved++;
                        break;
                    case 'rejected':
                        details.rejected++;
                        break;
                }
            });
            
            return details;
        },
        
        // 按钮显示控制
        shouldShowApprove() {
            return this.hasSelection && this.selectedMessageDetails.pending > 0;
        },
        
        shouldShowReject() {
            return this.hasSelection && this.selectedMessageDetails.pending > 0;
        },
        
        shouldShowDelete() {
            return this.hasSelection && (this.selectedMessageDetails.approved > 0 || this.selectedMessageDetails.rejected > 0);
        }
    },
    
    methods: {
        
        // 清空选择
        clearSelection() {
            this.$emit('clear-selection');
        },
        
        // 批量发布（带进度条）
        async batchApprove(event) {
            // 防止事件冒泡
            if (event) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
            }
            
            if (!this.hasSelection) return;
            
            if (!confirm(`确定要发布 ${this.selectedCount} 条消息吗？`)) {
                return;
            }
            
            await this.executeBatchOperation('approve', '发布中...');
        },
        
        // 批量拒绝（带进度条）
        async batchReject() {
            if (!this.hasSelection) return;
            
            if (!confirm(`确定要拒绝 ${this.selectedCount} 条消息吗？`)) {
                return;
            }
            
            await this.executeBatchOperation('reject', '拒绝中...');
        },
        
        // 批量删除（带确认）
        async batchDelete() {
            if (!this.hasSelection) return;
            
            const confirmed = await this.showDeleteConfirmation();
            if (!confirmed) return;
            
            await this.executeBatchOperation('delete', '删除中...');
        },
        
        // 执行批量操作
        async executeBatchOperation(operation, statusText) {
            this.isProcessing = true;
            this.operationProgress = {
                current: 0,
                total: this.selectedCount,
                status: statusText,
                visible: true
            };
            
            try {
                // 分批处理，避免一次性请求过多
                const batchSize = 20;
                const messageIds = [...this.selectedMessages];
                const batches = this.chunkArray(messageIds, batchSize);
                
                for (let i = 0; i < batches.length; i++) {
                    const batch = batches[i];
                    
                    try {
                        await this.processBatch(operation, batch);
                        this.operationProgress.current += batch.length;
                        
                        // 更新进度
                        this.$emit('progress-update', {
                            current: this.operationProgress.current,
                            total: this.operationProgress.total,
                            percentage: Math.round((this.operationProgress.current / this.operationProgress.total) * 100)
                        });
                        
                        // 短暂延迟避免服务器压力
                        if (i < batches.length - 1) {
                            await this.delay(200);
                        }
                        
                    } catch (error) {
                        console.error(`批处理第 ${i + 1} 批失败:`, error);
                        // 继续处理剩余批次
                    }
                }
                
                // 操作完成
                this.$emit('batch-operation-complete', {
                    operation,
                    processedCount: this.operationProgress.current,
                    totalCount: this.operationProgress.total
                });
                
                if (window.MessageManager) {
                    MessageManager.success(`${statusText.replace('中...', '')}完成: ${this.operationProgress.current}/${this.operationProgress.total}`);
                }
                
            } catch (error) {
                console.error('批量操作失败:', error);
                if (window.MessageManager) {
                    MessageManager.error(`${statusText.replace('中...', '')}失败: ${error.message}`);
                }
            } finally {
                this.isProcessing = false;
                this.operationProgress.visible = false;
                
                // 延迟清空选择，让用户看到结果
                setTimeout(() => {
                    this.clearSelection();
                }, 1000);
            }
        },
        
        // 处理单个批次
        async processBatch(operation, messageIds) {
            // 根据操作类型选择对应的API端点
            let endpoint;
            switch (operation) {
                case 'approve':
                    endpoint = API.messages.batchApprove;
                    break;
                case 'reject':
                    endpoint = API.messages.batchReject;
                    break;
                case 'delete':
                    endpoint = API.messages.batchDelete;
                    break;
                default:
                    throw new Error(`未知的批量操作: ${operation}`);
            }
            
            const response = await axios.post(endpoint, { message_ids: messageIds });
            
            if (!response.data.success) {
                throw new Error(response.data.message || `批量${operation}失败`);
            }
            
            return response.data;
        },
        
        // 数组分块
        chunkArray(array, chunkSize) {
            const chunks = [];
            for (let i = 0; i < array.length; i += chunkSize) {
                chunks.push(array.slice(i, i + chunkSize));
            }
            return chunks;
        },
        
        // 延迟函数
        delay(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        },
        
        // 删除确认对话框
        showDeleteConfirmation() {
            return new Promise((resolve) => {
                const modal = document.createElement('div');
                modal.className = 'batch-delete-modal';
                modal.innerHTML = `
                    <div class="modal-overlay">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h3>⚠️ 确认删除</h3>
                            </div>
                            <div class="modal-body">
                                <p>您即将删除 <strong>${this.selectedCount}</strong> 条消息。</p>
                                <p style="color: #dc3545; font-weight: bold;">此操作不可撤销！</p>
                                <div class="delete-options">
                                    <label>
                                        <input type="checkbox" id="deleteReviewMessages"> 同时删除审核群中的相关消息
                                    </label>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button class="btn btn-secondary" onclick="this.closest('.batch-delete-modal').remove(); resolve(false)">取消</button>
                                <button class="btn btn-danger" onclick="
                                    const deleteReview = document.getElementById('deleteReviewMessages').checked;
                                    this.closest('.batch-delete-modal').remove(); 
                                    resolve({ confirmed: true, deleteReview });
                                ">确认删除</button>
                            </div>
                        </div>
                    </div>
                `;
                
                // 注入resolve函数
                modal.querySelector('.btn-danger').onclick = () => {
                    const deleteReview = modal.querySelector('#deleteReviewMessages').checked;
                    modal.remove();
                    resolve({ confirmed: true, deleteReview });
                };
                
                modal.querySelector('.btn-secondary').onclick = () => {
                    modal.remove();
                    resolve({ confirmed: false });
                };
                
                document.body.appendChild(modal);
            });
        },
        
    },
    
    template: `
        <div class="batch-operation-panel">
            <!-- 选择控制区 -->
            <div class="selection-controls">
                <div class="selection-info">
                    <span class="selected-count" :class="{ 'has-selection': hasSelection }" v-if="hasSelection">
                        已选择: {{ selectedCount }} / {{ totalMessages }}
                    </span>
                </div>
                
                <div class="selection-actions">
                    <!-- 智能全选和反选按钮已删除 -->
                </div>
            </div>
            
            
            <!-- 批量操作区 -->
            <div class="batch-operations" v-if="hasSelection">
                <div class="button-group">
                    <button
                        v-if="shouldShowApprove"
                        class="btn btn-success"
                        :disabled="isProcessing"
                        @click="batchApprove($event)"
                    >
                        <span v-if="isProcessing && operationProgress.status.includes('发布')" class="spinner"></span>
                        📤 发布 ({{ selectedMessageDetails.pending }})
                    </button>

                    <button
                        v-if="shouldShowReject"
                        class="btn btn-warning"
                        :disabled="isProcessing"
                        @click="batchReject"
                    >
                        <span v-if="isProcessing && operationProgress.status.includes('拒绝')" class="spinner"></span>
                        ❌ 拒绝 ({{ selectedMessageDetails.pending }})
                    </button>

                    <button
                        v-if="shouldShowDelete"
                        class="btn btn-danger"
                        :disabled="isProcessing"
                        @click="batchDelete"
                    >
                        <span v-if="isProcessing && operationProgress.status.includes('删除')" class="spinner"></span>
                        🗑️ 删除 ({{ selectedMessageDetails.approved + selectedMessageDetails.rejected }})
                    </button>
                    
                    <button
                        class="btn btn-secondary"
                        @click="clearSelection"
                        :disabled="isProcessing"
                    >
                        🗑️ 清空
                    </button>
                </div>
            </div>
            
            <!-- 进度条 -->
            <div class="operation-progress" v-if="operationProgress.visible">
                <div class="progress-header">
                    <span>{{ operationProgress.status }}</span>
                    <span>{{ operationProgress.current }} / {{ operationProgress.total }}</span>
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar" 
                         :style="{ width: Math.round((operationProgress.current / operationProgress.total) * 100) + '%' }">
                    </div>
                </div>
            </div>
        </div>
    `
};

// 注册组件
window.BatchOperationPanel = BatchOperationPanel;