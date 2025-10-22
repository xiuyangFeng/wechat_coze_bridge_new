# 微信文章 Coze 知识库上传器 (WeChat Article to Coze KB Uploader)

这是一个功能强大的、基于 FastAPI 的 Web 服务，旨在自动化处理微信公众号文章，并将其核心内容智能上传到指定的 Coze 知识库。它不仅仅是一个简单的转发器，还内置了文章去重、公众号白名单过滤、后台异步处理等高级功能，确保了数据处理的效率和准确性。

## 核心功能

- **Webhook 异步处理**: 通过 `/artlist/` 端点接收外部服务（如 Webhook）推送的文章列表。服务会立即返回成功响应，并在后台线程中执行耗时的下载和上传任务，有效避免请求超时。
- **文章去重机制**: 服务会记录所有已成功处理文章的 `sn` 参数，并将其保存在本地的 `processed_sns.txt` 文件中。对于后续接收到的重复文章，系统会自动跳过，避免知识库内容冗余。
- **公众号白名单**: 内置一个 `BIZ_WHITELIST`，只有在白名单内的公众号发布的文章才会被处理，让您能精确控制知识库的内容来源。
- **智能内容提取**:
    - **摘要提取**: 自动从文章 HTML 中提取正文摘要，作为核心内容上传。
    - **参考文献识别**: 智能识别并提取文末的参考文献链接和标题，将其作为独立的知识库条目。
- **双知识库上传**:
    - **文章库**: 将文章的标题、URL 和摘要上传到一个指定的知识库（例如：热点文章库）。
    - **文献库**: 将提取出的参考文献分别上传到另一个知识库（例如：文献引用库），构建关系型知识网络。
- **灵活配置**: 通过 `.env` 文件轻松配置 Coze API Key 和目标知识库 ID，无需修改代码即可完成部署。
- **日志与调试**:
    - 记录详细的运行日志，便于追踪和调试。
    - 所有接收到的原始 JSON 请求都会被存档在 `./received_json` 目录下，方便问题排查。

## 工作流程

当一个请求到达服务时，会触发以下一系列自动化操作：

1.  **接收请求**: FastAPI 应用在 `POST /artlist/` 端点接收到 JSON 格式的文章列表。
2.  **快速响应**: 服务立即返回 `success` 响应，并将请求数据交由一个独立的后台线程处理。
3.  **后台处理**:
    a.  **遍历文章**: 逐一处理列表中的每篇文章。
    b.  **白名单过滤**: 检查文章的发布公众号是否在 `BIZ_WHITELIST` 中，若不在则跳过。
    c.  **URL 解析与去重**: 解析文章 URL 中的 `sn` 参数，并与 `processed_sns.txt` 中的记录比对，若重复则跳过。
    d.  **内容下载**: 模拟浏览器下载文章的完整 HTML 内容。
    e.  **内容解析**: 使用 BeautifulSoup 解析 HTML，提取文章摘要和参考文献。
    f.  **上传至 Coze**:
        - 调用 Coze API，将文章摘要上传到文章知识库。
        - 调用 Coze API，将每条参考文献上传到文献知识库。
    g.  **记录SN**: 文章成功处理后，将其 `sn` 写入 `processed_sns.txt` 文件，用于未来去重。

## 项目结构

```
wx_coze_uploader/
├── fastapiServer.py      # FastAPI 服务主入口，负责接收请求、去重、白名单过滤和调度任务
├── coze_uploader.py      # 封装了与 Coze API 的所有交互，以及 HTML 内容提取逻辑
├── wx_downloader.py      # 负责模拟浏览器下载微信文章的 HTML 内容
├── requirements.txt      # 项目依赖的 Python 包
├── .env                  # (需手动创建) 环境变量配置文件
├── processed_sns.txt     # (自动生成) 存储已处理文章的SN，用于去重
└── README.md             # 本文档
```

-   `fastapiServer.py`: 核心业务逻辑层。它不仅启动 FastAPI 应用，还管理着文章的去重、白名单过滤，并通过线程实现异步处理。
-   `coze_uploader.py`: Coze API 的封装层。它负责构建请求、调用 Coze 的 `document/create` API，并包含了从 HTML 中提取文章摘要和参考文献的核心函数。
-   `wx_downloader.py`: 一个简单的下载工具，提供 `download_html` 函数来获取指定 URL 的 HTML 内容。

## 安装与配置

### 1. 克隆项目

```bash
git clone <your-repository-url>
cd wx_coze_uploader
```

### 2. 创建并激活虚拟环境 (推荐)

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

### 3. 安装依赖

项目依赖已在 `requirements.txt` 中列出。

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

在 `wx_coze_uploader` 目录下创建一个名为 `.env` 的文件，并填入您的 Coze API 密钥和知识库 ID：

```env
# 你的 Coze API Key
COZE_API_KEY="your_coze_api_key_here"

# 用于存储文章摘要的知识库 ID
KB_ID_ARTICLES_HOT="your_article_kb_id_here"

# 用于存储参考文献的知识库 ID
KB_ID_REFERENCES_HOT="your_reference_kb_id_here"
```

### 5. (可选) 配置白名单

打开 `fastapiServer.py` 文件，找到 `BIZ_WHITELIST` 变量，将您需要处理的公众号名称添加进去：

```python
# fastapiServer.py
BIZ_WHITELIST = {"医工交叉园地", "另一个公众号"} # 在这里添加白名单
```

## 运行服务

使用 `uvicorn` 来启动 FastAPI 服务。为了确保服务可以被外部访问，请务必指定 host 为 `0.0.0.0`。

```bash
uvicorn fastapiServer:app --host 0.0.0.0 --port 8000
```

*如果您需要使用特定端口（例如 29212），请相应修改命令。*

服务启动后，将在 `http://0.0.0.0:8000` 监听请求。

## API 使用说明

### 端点: `POST /artlist/`

该端点用于接收文章列表数据。

#### 请求体 (Request Body)

请求体必须是 JSON 格式，并且包含一个 `data` 字段，其值为一个文章对象列表。每个文章对象应包含 `url`, `title`, 和 `bizname`。

```json
{
  "data": [
    {
      "url": "https://mp.weixin.qq.com/s/xxxxxxxxxxxx",
      "title": "文章标题一",
      "bizname": "医工交叉园地"
    },
    {
      "url": "https://mp.weixin.qq.com/s/yyyyyyyyyyyy",
      "title": "文章标题二",
      "bizname": "另一个公众号"
    }
  ]
}
```

#### 响应

-   **成功**: 如果请求被成功接收，服务会立即返回纯文本 `success`，并开始在后台处理数据。
-   **失败**: 如果请求体不是有效的 JSON 或处理过程中发生内部错误，将返回纯文本 `error`。

---

*该 README.md 由 Cline 优化生成。*
