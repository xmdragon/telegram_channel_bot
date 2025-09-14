/**
 * 消息处理工具函数
 * 统一处理消息的各种判断逻辑，避免数据类型不一致导致的bug
 */

const MessageUtils = {
    /**
     * 判断消息是否为广告 - 解决字符串"False"被当作true的问题
     * @param {Object} message - 消息对象
     * @returns {boolean} - true表示是广告，false表示不是广告
     */
    isMessageAd(message) {
        const isAd = message.is_ad;
        
        // 处理字符串类型
        if (typeof isAd === 'string') {
            return isAd.toLowerCase() === 'true';
        }
        
        // 处理布尔类型和null/undefined
        return !!isAd;
    },

    /**
     * 检查消息的is_ad值是否匹配筛选条件
     * 用于精确匹配筛选功能，保持原值进行比较
     * @param {Object} message - 消息对象  
     * @param {any} filterValue - 筛选条件值（可能是true/false/'True'/'False'/null等）
     * @returns {boolean} - true表示匹配筛选条件
     */
    matchesAdFilter(message, filterValue) {
        // 如果筛选条件为null，表示不筛选
        if (filterValue === null || filterValue === undefined) {
            return true;
        }

        const messageIsAd = message.is_ad;
        
        // 统一转换为字符串进行比较，避免类型不一致
        const messageValue = String(messageIsAd).toLowerCase();
        const filterValueStr = String(filterValue).toLowerCase();
        
        return messageValue === filterValueStr;
    },

    /**
     * 获取消息的is_ad原始值，用于API传递
     * @param {Object} message - 消息对象
     * @returns {any} - 消息的is_ad原始值
     */
    getRawAdValue(message) {
        return message.is_ad;
    }
};

// 导出到全局变量
window.MessageUtils = MessageUtils;