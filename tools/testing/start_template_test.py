#!/usr/bin/env python3
"""
Vue 模板渲染测试服务器

用于验证Vue模板渲染修复是否有效
"""
import http.server
import socketserver
import os
import sys
from pathlib import Path

def main():
    # 切换到项目根目录
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)
    
    print(f"🚀 启动Vue模板测试服务器")
    print(f"📁 工作目录: {project_root}")
    
    PORT = 8888
    
    class TestHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            # 添加CORS头和缓存控制
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            super().end_headers()
            
        def do_GET(self):
            # 如果访问根目录，重定向到测试页面
            if self.path == '/':
                self.send_response(302)
                self.send_header('Location', '/tools/testing/test_vue_template_rendering.html')
                self.end_headers()
                return
            super().do_GET()
    
    try:
        with socketserver.TCPServer(("", PORT), TestHTTPRequestHandler) as httpd:
            print(f"🌐 测试服务器启动成功！")
            print(f"📍 访问地址: http://localhost:{PORT}")
            print(f"🔧 测试页面: http://localhost:{PORT}/tools/testing/test_vue_template_rendering.html")
            print(f"💡 按 Ctrl+C 停止服务器")
            print(f"-" * 50)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n⏹️ 服务器已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()