FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/logs /app/data /app/temp_media

# 设置目录权限
RUN chmod -R 755 /app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python3", "main.py"]