# 使用官方的 Python 3.9 slim 镜像作为基础
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有应用代码到工作目录
COPY . .

# 暴露 Flask 应用运行的端口 (云托管通常使用 80)
EXPOSE 80

# 容器启动时执行的命令
# 使用 gunicorn 作为生产级的 WSGI 服务器来运行 Flask 应用
# 'main:app' 指的是运行 main.py 文件中的 app 实例
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:80", "main:app"]
