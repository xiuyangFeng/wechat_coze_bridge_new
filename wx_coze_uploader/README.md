# 微信文章 Coze 知识库上传器 (WeChat Article to Coze KB Uploader)

这是一个基于 FastAPI 的 Web 服务，旨在接收包含微信文章链接的 JSON 数据，自动下载文章内容，提取文章摘要和参考文献，并将它们分别上传到指定的 Coze 知识库中。

## 功能特性

- **Webhook 接收**: 通过一个 `/artlist/` POST 端点接收外部服务推送的文章列表。
- **异步处理**: 接收到请求后，立即返回成功响应，并在后台线程中处理耗时的下载和上传任务，避免请求超时。
- **内容提取**:
    - 自动从文章 HTML 中提取正文摘要。
    - 智能识别并提取文末的参考文献链接和标题。
- **Coze 知识库集成**:
    - 将文章摘要上传到一个指定的知识库（例如：热点文章库）。
    - 将参考文献作为独立文档上传到另一个知识库（例如：文献引用库）。
- **配置灵活**: 通过环境变量配置 Coze API Key 和目标知识库 ID，方便部署和管理。
- **日志记录**: 记录详细的运行日志，便于追踪和调试。

## 项目结构

```
wx_coze_uploader/
├── fastapiServer.py      # FastAPI Web服务主入口，负责接收请求和调度任务
├── coze_uploader.py      # 负责与 Coze API 交互，包括内容提取和文档上传
├── wx_downloader.py      # 负责下载微信文章的 HTML 内容
└── README.md             # 本文档
```

- `fastapiServer.py`: 启动一个 FastAPI 应用，提供 `/artlist/` 接口。接收到数据后，它会创建一个新的线程来调用处理函数，实现异步处理。
- `coze_uploader.py`: 封装了所有与 Coze 相关的逻辑。它调用 Coze 的 `document/create` API 来上传文档，并包含从 HTML 中提取文章摘要和参考文献的函数。
- `wx_downloader.py`: 提供一个 `download_html` 函数，模拟浏览器行为来获取指定 URL 的 HTML 内容。

## 安装与配置

### 1. 克隆项目

```bash
git clone <your-repository-url>
cd wx_coze_uploader
```

### 2. 安装依赖

建议使用虚拟环境。项目依赖 `fastapi`, `uvicorn`, `requests`, `beautifulsoup4`, `python-dotenv`, `pytz`, `lxml`。

首先，创建 `requirements.txt` 文件：
```txt
fastapi
uvicorn[standard]
requests
beautifulsoup4
python-dotenv
pytz
lxml
```

然后通过 pip 安装：
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

在 `wx_coze_uploader` 目录下创建一个 `.env` 文件，并填入您的 Coze API 密钥和知识库 ID：

```env
# 你的 Coze API Key
COZE_API_KEY="your_coze_api_key_here"

# 用于存储文章摘要的知识库 ID
KB_ID_ARTICLES_HOT="your_article_kb_id_here"

# 用于存储参考文献的知识库 ID
KB_ID_REFERENCES_HOT="your_reference_kb_id_here"
```

## 运行服务

使用 `uvicorn` 来启动 FastAPI 服务：

一定要使用‘python -m uvicorn fastapiServer:app --host 0.0.0.0 --port 29212’将端口暴露为 29212。

```bash
uvicorn fastapiServer:app --host 0.0.0.0 --port 8000
```

服务启动后，将在 `http://0.0.0.0:8000` 监听请求。

## API 使用说明

### 端点: `POST /artlist/`

该端点用于接收文章列表数据。

#### 请求体 (Request Body)

请求体必须是 JSON 格式，结构如下：

```json
{
  "data": [
    {
      "url": "https://mp.weixin.qq.com/s/xxxxxxxxxxxx",
      "title": "文章标题一"
    },
    {
      "url": "https://mp.weixin.qq.com/s/yyyyyyyyyyyy",
      "title": "文章标题二"
    }
  ]
}
```

#### 成功响应

如果请求被成功接收，服务会立即返回 `success` 字符串，并开始在后台处理数据。

#### 失败响应

如果请求体不是有效的 JSON 或处理过程中发生内部错误，将返回 `error` 字符串。

---

*该 README.md 由 Cline 生成。*
