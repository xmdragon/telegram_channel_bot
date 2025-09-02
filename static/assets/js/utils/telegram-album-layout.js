/**
 * Telegram官方媒体相册布局算法
 * 基于 https://github.com/Ajaxy/telegram-tt/blob/master/src/components/middle/message/helpers/calculateAlbumLayout.ts
 * 移植自官方Telegram Web A客户端
 */

// 布局缓存系统 - 提升性能
const layoutCache = new Map();
const CACHE_MAX_SIZE = 100; // 最大缓存100个布局

// 清理过期缓存
function cleanupCache() {
    if (layoutCache.size > CACHE_MAX_SIZE) {
        const firstKey = layoutCache.keys().next().value;
        layoutCache.delete(firstKey);
    }
}

// 生成缓存键
function getCacheKey(mediaItems, isOwn, isMobile, maxWidth, spacing) {
    const mediaSignature = mediaItems.map(m => `${m.width}x${m.height}:${m.media_type}`).join('|');
    return `${mediaSignature}:${isOwn}:${isMobile}:${maxWidth}:${spacing}`;
}

// 相册矩形边缘部分枚举
const AlbumRectPart = {
    None: 0,
    Top: 1,
    Right: 2,
    Bottom: 4,
    Left: 8,
};

/**
 * 数学工具函数
 */
function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function accumulate(list, initValue = 0) {
    return list.reduce((accumulator, item) => accumulator + item, initValue);
}

/**
 * 获取媒体宽高比数组
 * @param {Array} mediaItems - 媒体项数组，每项包含width和height
 * @param {boolean} isMobile - 是否为移动端
 * @returns {Array<number>} 宽高比数组
 */
function getRatios(mediaItems, isMobile = false) {
    return mediaItems.map(media => {
        const width = media.width || 640;
        const height = media.height || 640;
        let ratio = width / height;
        
        // 移动端适配：调整宽高比以适应小屏幕
        if (isMobile) {
            // 移动端上，过度宽的图片需要适当调整
            if (ratio > 2.5) ratio = 2.5;
            // 过度窄的图片也需要调整
            if (ratio < 0.4) ratio = 0.4;
        }
        
        return ratio;
    });
}

/**
 * 获取比例类型字符串
 * @param {Array<number>} ratios - 宽高比数组
 * @returns {string} 比例字符串 (w=宽图, q=方图, n=窄图)
 */
function getProportions(ratios) {
    return ratios.map(ratio => {
        if (ratio > 1.2) return 'w';  // 宽图
        if (ratio < 0.8) return 'n';  // 窄图
        return 'q';                   // 方图
    }).join('');
}

/**
 * 获取平均宽高比
 * @param {Array<number>} ratios - 宽高比数组
 * @returns {number} 平均宽高比
 */
function getAverageRatio(ratios) {
    return ratios.reduce((result, ratio) => ratio + result, 1) / ratios.length;
}

/**
 * 裁剪宽高比到合理范围
 * @param {Array<number>} ratios - 原始宽高比数组
 * @param {number} averageRatio - 平均宽高比
 * @returns {Array<number>} 裁剪后的宽高比数组
 */
function cropRatios(ratios, averageRatio) {
    return ratios.map(ratio => {
        return averageRatio > 1.1 ? clamp(ratio, 1, 2.75) : clamp(ratio, 0.6667, 1);
    });
}

/**
 * 计算容器尺寸
 * @param {Array} layout - 布局数组
 * @returns {Object} 容器尺寸 {width, height}
 */
function calculateContainerSize(layout) {
    const styles = { width: 0, height: 0 };
    layout.forEach(({ dimensions, sides }) => {
        if (sides & AlbumRectPart.Right) {
            styles.width = dimensions.width + dimensions.x;
        }
        if (sides & AlbumRectPart.Bottom) {
            styles.height = dimensions.height + dimensions.y;
        }
    });
    return styles;
}

/**
 * 复杂布局器 - 用于5张及以上的媒体
 * @param {Object} params - 布局参数
 * @returns {Array} 布局结果
 */
function layoutWithComplexLayouter({
    ratios: originalRatios,
    averageRatio,
    maxWidth,
    minWidth,
    spacing,
    maxHeight = (4 * maxWidth) / 3,
}) {
    const ratios = cropRatios(originalRatios, averageRatio);
    const count = originalRatios.length;
    const result = new Array(count);
    const attempts = [];

    const multiHeight = (offset, attemptCount) => {
        const attemptRatios = ratios.slice(offset, offset + attemptCount);
        const sum = accumulate(attemptRatios, 0);
        return (maxWidth - (attemptCount - 1) * spacing) / sum;
    };

    const pushAttempt = (lineCounts) => {
        const heights = [];
        let offset = 0;
        lineCounts.forEach((currentCount) => {
            heights.push(multiHeight(offset, currentCount));
            offset += currentCount;
        });
        attempts.push({ lineCounts, heights });
    };

    // 生成2行布局尝试
    for (let first = 1; first !== count; ++first) {
        const second = count - first;
        if (first <= 3 && second <= 3) {
            pushAttempt([first, second]);
        }
    }

    // 生成3行布局尝试
    for (let first = 1; first !== count - 1; ++first) {
        for (let second = 1; second !== count - first; ++second) {
            const third = count - first - second;
            if (first <= 3 && second <= (averageRatio < 0.85 ? 4 : 3) && third <= 3) {
                pushAttempt([first, second, third]);
            }
        }
    }

    // 生成4行布局尝试
    for (let first = 1; first !== count - 1; ++first) {
        for (let second = 1; second !== count - first; ++second) {
            for (let third = 1; third !== count - first - second; ++third) {
                const fourth = count - first - second - third;
                if (first <= 3 && second <= 3 && third <= 3 && fourth <= 4) {
                    pushAttempt([first, second, third, fourth]);
                }
            }
        }
    }

    // 找到最优布局
    let optimalAttempt = null;
    let optimalDiff = 0;
    for (let i = 0; i < attempts.length; i++) {
        const { heights, lineCounts } = attempts[i];
        const lineCount = lineCounts.length;
        const totalHeight = accumulate(heights, 0) + spacing * (lineCount - 1);
        const minLineHeight = Math.min(...heights);
        const bad1 = minLineHeight < minWidth ? 1.5 : 1;
        
        let bad2 = 1;
        for (let line = 1; line !== lineCount; ++line) {
            if (lineCounts[line - 1] > lineCounts[line]) {
                bad2 = 1.5;
                break;
            }
        }
        
        const diff = Math.abs(totalHeight - maxHeight) * bad1 * bad2;
        if (!optimalAttempt || diff < optimalDiff) {
            optimalAttempt = attempts[i];
            optimalDiff = diff;
        }
    }

    // 应用最优布局
    const optimalCounts = optimalAttempt.lineCounts;
    const optimalHeights = optimalAttempt.heights;
    const rowCount = optimalCounts.length;
    let index = 0;
    let y = 0;

    for (let row = 0; row !== rowCount; ++row) {
        const colCount = optimalCounts[row];
        const lineHeight = optimalHeights[row];
        const height = Math.round(lineHeight);
        let x = 0;

        for (let col = 0; col !== colCount; ++col) {
            const sides = AlbumRectPart.None
                | (row === 0 ? AlbumRectPart.Top : AlbumRectPart.None)
                | (row === rowCount - 1 ? AlbumRectPart.Bottom : AlbumRectPart.None)
                | (col === 0 ? AlbumRectPart.Left : AlbumRectPart.None)
                | (col === colCount - 1 ? AlbumRectPart.Right : AlbumRectPart.None);
            
            const ratio = ratios[index];
            const width = col === colCount - 1 ? maxWidth - x : Math.round(ratio * lineHeight);
            
            result[index] = {
                dimensions: { x, y, width, height },
                sides,
            };
            
            x += width + spacing;
            ++index;
        }
        y += height + spacing;
    }

    return result;
}

/**
 * 两张媒体的布局
 * @param {Object} params - 布局参数
 * @returns {Array} 布局结果
 */
function layoutTwo(params) {
    const { ratios, proportions, averageRatio } = params;
    
    // 两张宽图且比例相近 - 上下布局
    if (proportions === 'ww' && averageRatio > 1.4 && Math.abs(ratios[1] - ratios[0]) < 0.2) {
        return layoutTwoTopBottom(params);
    }
    // 两张同类型图 - 左右等宽布局
    if (proportions === 'ww' || proportions === 'qq') {
        return layoutTwoLeftRightEqual(params);
    }
    // 不同类型 - 左右不等宽布局
    return layoutTwoLeftRight(params);
}

/**
 * 两张媒体上下布局
 */
function layoutTwoTopBottom({ ratios, maxWidth, spacing, maxHeight }) {
    const height = Math.round(Math.min(
        maxWidth / ratios[0],
        Math.min(maxWidth / ratios[1], (maxHeight - spacing) / 2)
    ));

    return [{
        dimensions: { x: 0, y: 0, width: maxWidth, height },
        sides: AlbumRectPart.Left | AlbumRectPart.Top | AlbumRectPart.Right,
    }, {
        dimensions: { x: 0, y: height + spacing, width: maxWidth, height },
        sides: AlbumRectPart.Left | AlbumRectPart.Bottom | AlbumRectPart.Right,
    }];
}

/**
 * 两张媒体左右等宽布局
 */
function layoutTwoLeftRightEqual({ ratios, maxWidth, spacing, maxHeight }) {
    const width = (maxWidth - spacing) / 2;
    const height = Math.round(Math.min(
        width / ratios[0],
        Math.min(width / ratios[1], maxHeight)
    ));
    
    return [{
        dimensions: { x: 0, y: 0, width, height },
        sides: AlbumRectPart.Top | AlbumRectPart.Left | AlbumRectPart.Bottom,
    }, {
        dimensions: { x: width + spacing, y: 0, width, height },
        sides: AlbumRectPart.Top | AlbumRectPart.Right | AlbumRectPart.Bottom,
    }];
}

/**
 * 两张媒体左右不等宽布局
 */
function layoutTwoLeftRight({ ratios, minWidth, maxWidth, spacing, maxHeight }) {
    const minimalWidth = Math.round(1.5 * minWidth);
    const secondWidth = Math.min(
        Math.round(Math.max(
            0.4 * (maxWidth - spacing),
            (maxWidth - spacing) / ratios[0] / (1 / ratios[0] + 1 / ratios[1])
        )),
        maxWidth - spacing - minimalWidth
    );
    const firstWidth = maxWidth - secondWidth - spacing;
    const height = Math.min(
        maxHeight,
        Math.round(Math.min(firstWidth / ratios[0], secondWidth / ratios[1]))
    );

    return [{
        dimensions: { x: 0, y: 0, width: firstWidth, height },
        sides: AlbumRectPart.Top | AlbumRectPart.Left | AlbumRectPart.Bottom,
    }, {
        dimensions: { x: firstWidth + spacing, y: 0, width: secondWidth, height },
        sides: AlbumRectPart.Top | AlbumRectPart.Right | AlbumRectPart.Bottom,
    }];
}

/**
 * 三张媒体的布局
 * @param {Object} params - 布局参数
 * @returns {Array} 布局结果
 */
function layoutThree(params) {
    const { proportions } = params;
    // 第一张是窄图 - 左大右小布局
    return proportions[0] === 'n'
        ? layoutThreeLeftAndOther(params)
        : layoutThreeTopAndOther(params);
}

/**
 * 三张媒体左大右小布局
 */
function layoutThreeLeftAndOther({ maxHeight, spacing, ratios, maxWidth, minWidth }) {
    const firstHeight = maxHeight;
    const thirdHeight = Math.round(Math.min(
        (maxHeight - spacing) / 2,
        (ratios[1] * (maxWidth - spacing)) / (ratios[2] + ratios[1])
    ));
    const secondHeight = firstHeight - thirdHeight - spacing;
    const rightWidth = Math.max(
        minWidth,
        Math.round(Math.min(
            (maxWidth - spacing) / 2,
            Math.min(thirdHeight * ratios[2], secondHeight * ratios[1])
        ))
    );
    const leftWidth = Math.min(
        Math.round(firstHeight * ratios[0]),
        maxWidth - spacing - rightWidth
    );

    return [{
        dimensions: { x: 0, y: 0, width: leftWidth, height: firstHeight },
        sides: AlbumRectPart.Top | AlbumRectPart.Left | AlbumRectPart.Bottom,
    }, {
        dimensions: { x: leftWidth + spacing, y: 0, width: rightWidth, height: secondHeight },
        sides: AlbumRectPart.Top | AlbumRectPart.Right,
    }, {
        dimensions: { x: leftWidth + spacing, y: secondHeight + spacing, width: rightWidth, height: thirdHeight },
        sides: AlbumRectPart.Bottom | AlbumRectPart.Right,
    }];
}

/**
 * 三张媒体上大下小布局
 */
function layoutThreeTopAndOther({ maxWidth, ratios, maxHeight, spacing }) {
    const firstWidth = maxWidth;
    const firstHeight = Math.round(Math.min(firstWidth / ratios[0], 0.66 * (maxHeight - spacing)));
    const secondWidth = (maxWidth - spacing) / 2;
    const secondHeight = Math.min(
        maxHeight - firstHeight - spacing,
        Math.round(Math.min(secondWidth / ratios[1], secondWidth / ratios[2]))
    );
    const thirdWidth = firstWidth - secondWidth - spacing;

    return [{
        dimensions: { x: 0, y: 0, width: firstWidth, height: firstHeight },
        sides: AlbumRectPart.Left | AlbumRectPart.Top | AlbumRectPart.Right,
    }, {
        dimensions: { x: 0, y: firstHeight + spacing, width: secondWidth, height: secondHeight },
        sides: AlbumRectPart.Bottom | AlbumRectPart.Left,
    }, {
        dimensions: { x: secondWidth + spacing, y: firstHeight + spacing, width: thirdWidth, height: secondHeight },
        sides: AlbumRectPart.Bottom | AlbumRectPart.Right,
    }];
}

/**
 * 四张媒体的布局
 * @param {Object} params - 布局参数
 * @returns {Array} 布局结果
 */
function layoutFour(params) {
    const { proportions } = params;
    // 第一张是宽图 - 上大下小布局
    return proportions[0] === 'w'
        ? layoutFourTopAndOther(params)
        : layoutFourLeftAndOther(params);
}

/**
 * 四张媒体上大下小布局
 */
function layoutFourTopAndOther({ maxWidth, ratios, spacing, maxHeight, minWidth }) {
    const w = maxWidth;
    const h0 = Math.round(Math.min(w / ratios[0], 0.66 * (maxHeight - spacing)));
    const h = Math.round((maxWidth - 2 * spacing) / (ratios[1] + ratios[2] + ratios[3]));
    const w0 = Math.max(minWidth, Math.round(Math.min(0.4 * (maxWidth - 2 * spacing), h * ratios[1])));
    const w2 = Math.round(Math.max(Math.max(minWidth, 0.33 * (maxWidth - 2 * spacing)), h * ratios[3]));
    const w1 = w - w0 - w2 - 2 * spacing;
    const h1 = Math.min(maxHeight - h0 - spacing, h);

    return [{
        dimensions: { x: 0, y: 0, width: w, height: h0 },
        sides: AlbumRectPart.Left | AlbumRectPart.Top | AlbumRectPart.Right,
    }, {
        dimensions: { x: 0, y: h0 + spacing, width: w0, height: h1 },
        sides: AlbumRectPart.Bottom | AlbumRectPart.Left,
    }, {
        dimensions: { x: w0 + spacing, y: h0 + spacing, width: w1, height: h1 },
        sides: AlbumRectPart.Bottom,
    }, {
        dimensions: { x: w0 + spacing + w1 + spacing, y: h0 + spacing, width: w2, height: h1 },
        sides: AlbumRectPart.Right | AlbumRectPart.Bottom,
    }];
}

/**
 * 四张媒体左大右小布局
 */
function layoutFourLeftAndOther({ maxHeight, ratios, maxWidth, spacing, minWidth }) {
    const h = maxHeight;
    const w0 = Math.round(Math.min(h * ratios[0], 0.6 * (maxWidth - spacing)));
    const w = Math.round((maxHeight - 2 * spacing) / (1 / ratios[1] + 1 / ratios[2] + 1 / ratios[3]));
    const h0 = Math.round(w / ratios[1]);
    const h1 = Math.round(w / ratios[2]);
    const h2 = h - h0 - h1 - 2 * spacing;
    const w1 = Math.max(minWidth, Math.min(maxWidth - w0 - spacing, w));

    return [{
        dimensions: { x: 0, y: 0, width: w0, height: h },
        sides: AlbumRectPart.Top | AlbumRectPart.Left | AlbumRectPart.Bottom,
    }, {
        dimensions: { x: w0 + spacing, y: 0, width: w1, height: h0 },
        sides: AlbumRectPart.Top | AlbumRectPart.Right,
    }, {
        dimensions: { x: w0 + spacing, y: h0 + spacing, width: w1, height: h1 },
        sides: AlbumRectPart.Right,
    }, {
        dimensions: { x: w0 + spacing, y: h0 + h1 + 2 * spacing, width: w1, height: h2 },
        sides: AlbumRectPart.Bottom | AlbumRectPart.Right,
    }];
}

/**
 * 主要布局计算函数
 * @param {Object} options - 配置选项
 * @param {Array} options.mediaItems - 媒体项数组，每项包含width和height
 * @param {boolean} options.isOwn - 是否为自己发送的消息
 * @param {boolean} options.isMobile - 是否为移动端
 * @param {number} options.maxWidth - 最大宽度 (默认380px)
 * @param {number} options.spacing - 间距 (默认2px)
 * @returns {Object} 布局结果 {layout: Array, containerStyle: {width, height}}
 */
function calculateTelegramAlbumLayout({
    mediaItems,
    isOwn = false,
    isMobile = false,
    maxWidth = 380,
    spacing = 2,
}) {
    // 参数验证 - 提升健壮性
    if (!Array.isArray(mediaItems) || mediaItems.length === 0) {
        throw new Error('mediaItems must be a non-empty array');
    }
    if (mediaItems.length > 10) {
        console.warn('Telegram album layout only supports up to 10 media items');
        mediaItems = mediaItems.slice(0, 10);
    }
    
    // 移动端适配：自动调整最大宽度
    if (isMobile && maxWidth === 380) {
        // 移动端使用更小的最大宽度，适应屏幕
        maxWidth = Math.min(320, window.innerWidth ? window.innerWidth * 0.9 : 320);
    }
    
    // 缓存检查 - 提升性能
    const cacheKey = getCacheKey(mediaItems, isOwn, isMobile, maxWidth, spacing);
    if (layoutCache.has(cacheKey)) {
        return layoutCache.get(cacheKey);
    }
    
    const ratios = getRatios(mediaItems, isMobile);
    const proportions = getProportions(ratios);
    const averageRatio = getAverageRatio(ratios);
    const albumCount = ratios.length;
    const forceCalc = ratios.some(ratio => ratio > 2);
    const maxHeight = maxWidth;

    let layout;

    const params = {
        ratios,
        proportions,
        averageRatio,
        maxWidth,
        minWidth: 100,
        maxHeight,
        spacing,
    };

    if (albumCount >= 5 || forceCalc) {
        layout = layoutWithComplexLayouter(params);
    } else if (albumCount === 2) {
        layout = layoutTwo(params);
    } else if (albumCount === 3) {
        layout = layoutThree(params);
    } else if (albumCount === 4) {
        layout = layoutFour(params);
    } else {
        // 单张媒体
        const width = Math.min(maxWidth, mediaItems[0].width || maxWidth);
        const height = Math.min(maxHeight, mediaItems[0].height || maxHeight);
        layout = [{
            dimensions: { x: 0, y: 0, width, height },
            sides: AlbumRectPart.Top | AlbumRectPart.Right | AlbumRectPart.Bottom | AlbumRectPart.Left,
        }];
    }

    // 构建结果
    const result = {
        layout,
        containerStyle: calculateContainerSize(layout),
    };
    
    // 存储缓存 - 提升性能
    cleanupCache(); // 确保缓存不会无限增长
    layoutCache.set(cacheKey, result);
    
    return result;
}

// 暴露到全局
if (typeof window !== 'undefined') {
    window.calculateTelegramAlbumLayout = calculateTelegramAlbumLayout;
    window.AlbumRectPart = AlbumRectPart;
    // 暴露缓存用于测试和调试
    window.layoutCache = layoutCache;
}