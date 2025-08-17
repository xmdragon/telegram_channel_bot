#!/usr/bin/env node

/**
 * JavaScript代码静态分析工具
 * 检测语法错误、API配置引用、浏览器兼容性等问题
 */

const fs = require('fs');
const path = require('path');

class JavaScriptTestAnalyzer {
    constructor() {
        this.errors = [];
        this.warnings = [];
        this.apiEndpoints = new Set();
        this.jsFiles = [];
        this.baseDir = '/Users/eric/workspace/telegram_channel_bot';
    }

    // 主要测试入口
    async runTests() {
        console.log('🔍 开始JavaScript代码静态分析...\n');
        
        try {
            // 1. 扫描所有JavaScript文件
            this.scanJavaScriptFiles();
            
            // 2. 加载API配置
            this.loadApiConfiguration();
            
            // 3. 分析每个文件
            this.analyzeFiles();
            
            // 4. 生成报告
            this.generateReport();
            
        } catch (error) {
            console.error('❌ 分析过程中发生错误:', error.message);
            this.errors.push({
                type: 'CRITICAL',
                file: 'analyzer',
                message: error.message
            });
        }
    }

    // 扫描JavaScript文件
    scanJavaScriptFiles() {
        const staticDir = path.join(this.baseDir, 'static/assets/js');
        
        const scanDir = (dir) => {
            const files = fs.readdirSync(dir);
            files.forEach(file => {
                const fullPath = path.join(dir, file);
                const stat = fs.statSync(fullPath);
                
                if (stat.isDirectory()) {
                    scanDir(fullPath);
                } else if (file.endsWith('.js')) {
                    this.jsFiles.push(fullPath);
                }
            });
        };
        
        scanDir(staticDir);
        console.log(`📁 发现 ${this.jsFiles.length} 个JavaScript文件`);
    }

    // 加载API配置
    loadApiConfiguration() {
        const apiConfigPath = path.join(this.baseDir, 'static/assets/js/config/api-endpoints.js');
        
        if (!fs.existsSync(apiConfigPath)) {
            this.errors.push({
                type: 'CRITICAL',
                file: 'api-endpoints.js',
                message: 'API配置文件不存在'
            });
            return;
        }

        try {
            const content = fs.readFileSync(apiConfigPath, 'utf8');
            
            // 提取API端点
            const apiMatches = content.match(/['"]\/api\/[^'"]+['"]/g);
            if (apiMatches) {
                apiMatches.forEach(match => {
                    const endpoint = match.replace(/['"]/g, '');
                    this.apiEndpoints.add(endpoint);
                });
            }
            
            console.log(`🔗 加载了 ${this.apiEndpoints.size} 个API端点`);
        } catch (error) {
            this.errors.push({
                type: 'CRITICAL',
                file: 'api-endpoints.js',
                message: `读取API配置失败: ${error.message}`
            });
        }
    }

    // 分析所有文件
    analyzeFiles() {
        console.log('\n📋 开始分析文件...');
        
        this.jsFiles.forEach(filePath => {
            this.analyzeFile(filePath);
        });
    }

    // 分析单个文件
    analyzeFile(filePath) {
        const relativePath = path.relative(this.baseDir, filePath);
        
        try {
            const content = fs.readFileSync(filePath, 'utf8');
            
            // 1. 语法检查
            this.checkSyntax(relativePath, content);
            
            // 2. API引用检查
            this.checkApiReferences(relativePath, content);
            
            // 3. 变量声明检查
            this.checkVariableDeclarations(relativePath, content);
            
            // 4. 异步函数检查
            this.checkAsyncPatterns(relativePath, content);
            
            // 5. 浏览器兼容性检查
            this.checkBrowserCompatibility(relativePath, content);
            
            // 6. 错误处理检查
            this.checkErrorHandling(relativePath, content);
            
        } catch (error) {
            this.errors.push({
                type: 'CRITICAL',
                file: relativePath,
                message: `读取文件失败: ${error.message}`
            });
        }
    }

    // 语法检查
    checkSyntax(file, content) {
        // 检查基本语法错误
        const syntaxIssues = [
            // 未匹配的括号
            { pattern: /\([^)]*$/, message: '可能存在未闭合的圆括号' },
            { pattern: /\{[^}]*$/, message: '可能存在未闭合的花括号' },
            { pattern: /\[[^\]]*$/, message: '可能存在未闭合的方括号' },
            
            // 未终止的字符串
            { pattern: /'[^']*$/, message: '可能存在未闭合的单引号字符串' },
            { pattern: /"[^"]*$/, message: '可能存在未闭合的双引号字符串' },
            
            // 常见错误模式
            { pattern: /function\s*\(\s*\)\s*{[^}]*$/, message: '函数定义可能未正确闭合' },
            { pattern: /if\s*\([^)]*\)\s*{[^}]*$/, message: 'if语句可能未正确闭合' }
        ];

        syntaxIssues.forEach(issue => {
            if (issue.pattern.test(content)) {
                this.warnings.push({
                    type: 'SYNTAX',
                    file,
                    message: issue.message
                });
            }
        });
    }

    // API引用检查
    checkApiReferences(file, content) {
        // 查找API调用
        const apiCallPatterns = [
            /API\.(\w+)\.(\w+)/g,
            /API\[['"]([^'"]+)['"]\]/g,
            /axios\.[a-z]+\(['"]\/api\/[^'"]+['"]/g
        ];

        // 检查是否使用了API配置
        if (content.includes('API.') || content.includes('window.API')) {
            // 验证API变量是否已定义
            if (!content.includes('const API = window.API') && 
                !content.includes('window.API') && 
                !content.includes('import') && 
                file !== 'static/assets/js/config/api-endpoints.js') {
                this.warnings.push({
                    type: 'API_REFERENCE',
                    file,
                    message: 'API配置可能未正确引用'
                });
            }
        }

        // 检查硬编码的API路径
        const hardcodedApiMatches = content.match(/['"]\/api\/[^'"]+['"]/g);
        if (hardcodedApiMatches && file !== 'static/assets/js/config/api-endpoints.js') {
            hardcodedApiMatches.forEach(match => {
                const endpoint = match.replace(/['"]/g, '');
                if (!this.apiEndpoints.has(endpoint)) {
                    this.warnings.push({
                        type: 'HARDCODED_API',
                        file,
                        message: `发现硬编码API路径: ${endpoint}`
                    });
                }
            });
        }
    }

    // 变量声明检查
    checkVariableDeclarations(file, content) {
        // 检查未声明的变量
        const globalVars = ['console', 'window', 'document', 'setTimeout', 'setInterval', 
                           'Vue', 'ElementPlus', 'axios', 'API', 'authManager', 'MessageManager'];
        
        // 查找可能未声明的变量
        const variablePattern = /(?:^|\W)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?:\(|\.)/g;
        let match;
        
        while ((match = variablePattern.exec(content)) !== null) {
            const varName = match[1];
            
            // 跳过已知的全局变量和关键字
            if (globalVars.includes(varName) || 
                ['this', 'if', 'for', 'while', 'function', 'const', 'let', 'var'].includes(varName)) {
                continue;
            }
            
            // 检查是否在文件中声明
            const declarationPattern = new RegExp(`(?:var|let|const|function)\\s+${varName}\\b`);
            if (!declarationPattern.test(content) && !content.includes(`${varName} =`)) {
                // 可能的未声明变量，但不作为错误，只作为警告
                // this.warnings.push({
                //     type: 'UNDECLARED_VAR',
                //     file,
                //     message: `可能的未声明变量: ${varName}`
                // });
            }
        }
    }

    // 异步模式检查
    checkAsyncPatterns(file, content) {
        // 检查Promise使用
        const hasPromise = content.includes('Promise') || content.includes('.then(') || content.includes('.catch(');
        const hasAsyncAwait = content.includes('async ') || content.includes('await ');
        
        if (hasPromise && hasAsyncAwait) {
            // 混用Promise和async/await，给出建议
            this.warnings.push({
                type: 'ASYNC_PATTERN',
                file,
                message: '建议统一使用async/await模式而不是混用Promise'
            });
        }

        // 检查未处理的Promise
        const unhandledPromisePattern = /(?<!await\s+)(?<!return\s+)\w+\([^)]*\)\.(?:then|catch)\(/g;
        if (unhandledPromisePattern.test(content)) {
            // this.warnings.push({
            //     type: 'PROMISE_HANDLING',
            //     file,
            //     message: '可能存在未正确处理的Promise'
            // });
        }
    }

    // 浏览器兼容性检查
    checkBrowserCompatibility(file, content) {
        const compatibilityIssues = [
            { pattern: /\.replaceAll\(/, message: 'replaceAll方法可能不兼容旧版浏览器，建议使用replace+正则' },
            { pattern: /Object\.fromEntries\(/, message: 'Object.fromEntries可能不兼容IE，需要polyfill' },
            { pattern: /Promise\.allSettled\(/, message: 'Promise.allSettled可能不兼容旧版浏览器' },
            { pattern: /\.at\(/, message: '数组.at()方法可能不兼容旧版浏览器' },
            { pattern: /\?\?/, message: '空值合并操作符(??)可能不兼容旧版浏览器' },
            { pattern: /\?\.\w/, message: '可选链操作符(?.)可能不兼容旧版浏览器' }
        ];

        compatibilityIssues.forEach(issue => {
            if (issue.pattern.test(content)) {
                this.warnings.push({
                    type: 'COMPATIBILITY',
                    file,
                    message: issue.message
                });
            }
        });

        // 检查ES6+特性
        const es6Features = [
            { pattern: /const\s+\w+\s*=/, feature: 'const声明' },
            { pattern: /let\s+\w+\s*=/, feature: 'let声明' },
            { pattern: /=>\s*{/, feature: '箭头函数' },
            { pattern: /`[^`]*\$\{[^}]*\}[^`]*`/, feature: '模板字符串' },
            { pattern: /\.\.\./, feature: '扩展操作符' }
        ];

        es6Features.forEach(feature => {
            if (feature.pattern.test(content)) {
                // ES6特性是正常的，不作为警告
            }
        });
    }

    // 错误处理检查
    checkErrorHandling(file, content) {
        // 检查try-catch使用
        const hasTryCatch = content.includes('try {') && content.includes('catch');
        const hasAsyncFunction = content.includes('async ');
        
        if (hasAsyncFunction && !hasTryCatch && content.includes('await')) {
            this.warnings.push({
                type: 'ERROR_HANDLING',
                file,
                message: '异步函数中缺少错误处理(try-catch)'
            });
        }

        // 检查空的catch块
        const emptyCatchPattern = /catch\s*\([^)]*\)\s*{\s*}/g;
        if (emptyCatchPattern.test(content)) {
            this.warnings.push({
                type: 'EMPTY_CATCH',
                file,
                message: '存在空的catch块，可能忽略了错误处理'
            });
        }
    }

    // 生成测试报告
    generateReport() {
        console.log('\n📊 JavaScript代码分析报告');
        console.log('=' + '='.repeat(50));
        
        // 统计信息
        console.log(`\n📈 统计信息:`);
        console.log(`   - 分析文件数: ${this.jsFiles.length}`);
        console.log(`   - 发现错误数: ${this.errors.length}`);
        console.log(`   - 发现警告数: ${this.warnings.length}`);
        console.log(`   - API端点数: ${this.apiEndpoints.size}`);

        // 错误报告
        if (this.errors.length > 0) {
            console.log(`\n❌ 发现 ${this.errors.length} 个错误:`);
            this.errors.forEach((error, index) => {
                console.log(`   ${index + 1}. [${error.type}] ${error.file}`);
                console.log(`      ${error.message}`);
            });
        }

        // 警告报告
        if (this.warnings.length > 0) {
            console.log(`\n⚠️  发现 ${this.warnings.length} 个警告:`);
            
            // 按类型分组显示
            const warningsByType = {};
            this.warnings.forEach(warning => {
                if (!warningsByType[warning.type]) {
                    warningsByType[warning.type] = [];
                }
                warningsByType[warning.type].push(warning);
            });

            Object.keys(warningsByType).forEach(type => {
                console.log(`\n   [${type}] (${warningsByType[type].length}个):`);
                warningsByType[type].forEach((warning, index) => {
                    console.log(`     ${index + 1}. ${warning.file}`);
                    console.log(`        ${warning.message}`);
                });
            });
        }

        // API配置验证
        console.log(`\n🔗 API配置验证:`);
        if (this.apiEndpoints.size > 0) {
            console.log(`   ✅ API配置文件加载成功`);
            console.log(`   ✅ 发现 ${this.apiEndpoints.size} 个API端点`);
        } else {
            console.log(`   ❌ API配置可能有问题`);
        }

        // 总结
        console.log(`\n📋 分析总结:`);
        if (this.errors.length === 0) {
            console.log(`   ✅ 未发现严重错误`);
        } else {
            console.log(`   ❌ 发现 ${this.errors.length} 个需要修复的错误`);
        }

        if (this.warnings.length === 0) {
            console.log(`   ✅ 代码质量良好，未发现警告`);
        } else if (this.warnings.length <= 5) {
            console.log(`   ⚠️  有少量优化建议 (${this.warnings.length}个)`);
        } else {
            console.log(`   ⚠️  建议关注代码质量问题 (${this.warnings.length}个警告)`);
        }

        // 建议
        console.log(`\n💡 改进建议:`);
        console.log(`   1. 确保所有API调用都通过API配置文件`);
        console.log(`   2. 为异步操作添加适当的错误处理`);
        console.log(`   3. 考虑添加TypeScript进行类型检查`);
        console.log(`   4. 使用ESLint进行代码规范检查`);
        
        console.log('\n✅ 分析完成!');
        
        // 返回测试结果
        return {
            success: this.errors.length === 0,
            errors: this.errors,
            warnings: this.warnings,
            fileCount: this.jsFiles.length,
            apiEndpointCount: this.apiEndpoints.size
        };
    }
}

// 如果直接运行此脚本
if (require.main === module) {
    const analyzer = new JavaScriptTestAnalyzer();
    analyzer.runTests().then(() => {
        process.exit(analyzer.errors.length > 0 ? 1 : 0);
    }).catch(error => {
        console.error('分析失败:', error);
        process.exit(1);
    });
}

module.exports = JavaScriptTestAnalyzer;