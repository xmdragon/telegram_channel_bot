/**
 * Linus风格的事件委托管理器
 * 
 * 核心哲学：
 * 1. 一个监听器处理所有事件 - 没有特殊情况
 * 2. 数据属性驱动 - 不用复杂的选择器
 * 3. 捕获阶段拦截 - 从根本上解决冒泡问题
 */

class EventDelegate {
    constructor(vm) {
        this.vm = vm;
        this.initEventListeners();
    }
    
    initEventListeners() {
        // 在捕获阶段统一处理所有点击事件
        document.addEventListener('click', this.handleClick.bind(this), true);
    }
    
    handleClick(e) {
        const target = e.target;
        
        // 处理消息操作按钮
        const action = target.dataset.action;
        const messageId = target.dataset.messageId;
        
        if (action && messageId) {
            // 立即停止事件传播
            e.preventDefault();
            e.stopPropagation();
            
            // 执行对应的操作
            if (this.vm[action]) {
                this.vm[action](messageId);
            }
            return;
        }
        
        // 处理统计面板点击
        const statKey = this.getStatKey(target);
        if (statKey) {
            e.preventDefault();
            e.stopPropagation();
            
            if (this.vm.handleStatClick) {
                this.vm.handleStatClick(statKey);
            }
            return;
        }
    }
    
    /**
     * 获取统计键值 - Linus风格的简单逻辑
     */
    getStatKey(target) {
        // 向上查找最近的 stat-card
        const statCard = target.closest('.stat-card');
        if (!statCard) return null;
        
        // 检查是否点击的是按钮区域
        if (target.closest('button, .btn, a, input, select, textarea, [role="button"]')) {
            return null;
        }
        
        // 返回数据属性中的统计键
        return statCard.dataset.statKey;
    }
    
    /**
     * 销毁事件监听器
     */
    destroy() {
        document.removeEventListener('click', this.handleClick.bind(this), true);
    }
}

// 全局导出
window.EventDelegate = EventDelegate;