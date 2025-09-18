/**
 * 独立的弹窗状态管理器
 *
 * 解决数据刷新导致弹窗关闭的问题
 * 将弹窗状态与Vue组件数据分离，避免响应式更新影响
 */
class DialogStateManager {
    constructor() {
        // 独立存储所有弹窗状态
        this.states = {
            editDialog: {
                visible: false,
                messageId: null,
                filteredContent: '',
                originalMessage: null
            },
            originalMessageDialog: {
                visible: false,
                messageId: null,
                message: null,
                loading: false,
                error: null
            },
            fileDetailsDialog: {
                visible: false,
                details: {
                    fileName: '',
                    originalFileName: '',
                    path: '',
                    type: '',
                    size: '',
                    hash: '',
                    createTime: '',
                    tags: []
                }
            },
            mediaPreview: {
                show: false,
                url: null
            }
        };

        // 变化监听器
        this.listeners = new Set();
    }

    /**
     * 获取指定弹窗的状态
     */
    getState(dialogName) {
        return this.states[dialogName];
    }

    /**
     * 更新指定弹窗的状态
     */
    setState(dialogName, updates) {
        if (!this.states[dialogName]) {
            console.error(`Dialog ${dialogName} not found`);
            return;
        }

        // 深度合并更新
        if (typeof updates === 'object' && !Array.isArray(updates)) {
            Object.assign(this.states[dialogName], updates);
        } else {
            this.states[dialogName] = updates;
        }

        // 通知监听器
        this.notifyListeners(dialogName, this.states[dialogName]);
    }

    /**
     * 显示弹窗
     */
    show(dialogName, data = {}) {
        console.log(`[DialogStateManager] Showing dialog: ${dialogName}`, data);
        this.setState(dialogName, {
            ...this.states[dialogName],
            ...data,
            visible: dialogName === 'mediaPreview' ? undefined : true,
            show: dialogName === 'mediaPreview' ? true : undefined
        });
        console.log(`[DialogStateManager] Dialog state after show:`, this.states[dialogName]);
    }

    /**
     * 隐藏弹窗
     */
    hide(dialogName) {
        if (dialogName === 'mediaPreview') {
            this.setState(dialogName, { show: false, url: null });
        } else {
            this.setState(dialogName, {
                ...this.states[dialogName],
                visible: false
            });
        }
    }

    /**
     * 检查是否有弹窗打开
     */
    hasOpenDialog() {
        return this.states.editDialog.visible ||
               this.states.originalMessageDialog.visible ||
               this.states.fileDetailsDialog.visible ||
               this.states.mediaPreview.show;
    }

    /**
     * 获取所有弹窗状态
     */
    getAllStates() {
        return { ...this.states };
    }

    /**
     * 重置所有弹窗状态
     */
    resetAll() {
        for (const dialogName in this.states) {
            this.hide(dialogName);
        }
    }

    /**
     * 添加状态变化监听器
     */
    addListener(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    /**
     * 通知所有监听器
     */
    notifyListeners(dialogName, state) {
        console.log(`[DialogStateManager] Notifying ${this.listeners.size} listeners for ${dialogName}`);
        for (const listener of this.listeners) {
            try {
                listener(dialogName, state);
            } catch (error) {
                console.error('Error in dialog state listener:', error);
            }
        }
    }

    /**
     * 创建Vue响应式代理
     * 用于在Vue组件中使用，但状态实际存储在管理器中
     */
    createVueProxy(vm) {
        const proxy = {};

        for (const dialogName in this.states) {
            // 创建getter和setter
            Object.defineProperty(proxy, dialogName, {
                get: () => this.getState(dialogName),
                set: (value) => this.setState(dialogName, value),
                enumerable: true,
                configurable: true
            });
        }

        // 监听变化并触发Vue更新
        this.addListener((dialogName, state) => {
            if (vm && vm.$forceUpdate) {
                vm.$forceUpdate();
            }
        });

        return proxy;
    }
}

// 创建单例实例
window.DialogStateManager = new DialogStateManager();