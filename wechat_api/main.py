# main.py - 微信云托管部署版本 V4.0

import os
import xml.etree.ElementTree as ET
import requests
import re
from flask import Flask, request
from bs4 import BeautifulSoup
import logging

# --- 日志配置 ---
# 配置日志记录，方便在云托管环境中查看服务运行状态和排查问题。
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask应用初始化 ---
app = Flask(__name__)

# --- 环境变量加载 ---
# 从微信云托管的环境变量中直接获取配置信息，无需 .env 文件。
# 这种方式更安全、更符合云原生应用的实践。
COZE_API_KEY = os.getenv('COZE_API_KEY')
KB_ID_ARTICLES_HOT = os.getenv('KB_ID_ARTICLES_HOT')
KB_ID_REFERENCES_HOT = os.getenv('KB_ID_REFERENCES_HOT')

# --- Coze API 核心函数 (业务逻辑，保持不变) ---
def create_coze_doc(kb_id, doc_name, content):
    """
    调用 Coze API 在指定的知识库中创建一篇新文档。

    :param kb_id: 目标知识库的ID。
    :param doc_name: 要创建的文档的标题。
    :param content: 文档的内容。
    :return: 成功则返回API响应的JSON数据，失败则返回None。
    """
    # 检查API密钥和知识库ID是否已配置
    if not all([COZE_API_KEY, kb_id]):
        logging.error("Coze API Key或目标知识库ID (kb_id) 未配置。")
        return None
    
    api_url = "https://api.coze.cn/open/v1/docs/create"
    headers = {
        "Authorization": f"Bearer {COZE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "*/*"
    }
    payload = {"kb_id": kb_id, "doc_name": doc_name, "doc_type": "text", "content": content}
    
    try:
        # 发送POST请求到Coze API，设置20秒超时
        response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        # 如果HTTP状态码不是2xx，则抛出异常
        response.raise_for_status()
        response_data = response.json()
        
        # 根据Coze返回的业务码判断操作是否成功
        if response_data.get("code") == 0:
            logging.info(f"成功在知识库 '{kb_id}' 中创建文档 '{doc_name}'。")
            return response_data
        else:
            logging.error(f"Coze API 业务错误。文档: '{doc_name}', Code: {response_data.get('code')}, Msg: {response_data.get('msg')}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"调用Coze API为文档 '{doc_name}' 创建时出错: {e}")
        return None
    except ValueError:
        logging.error(f"解析Coze API响应失败，非JSON格式。响应内容: {response.text}")
        return None

# --- 文章同步模块 (业务逻辑，保持不变) ---
def sync_article_to_hot_kb(article_title, article_url, soup):
    """
    从文章HTML中提取摘要，并将其同步到Coze的“文章-增量库”。

    :param article_title: 文章标题。
    :param article_url: 文章链接。
    :param soup: 使用BeautifulSoup解析后的文章HTML对象。
    """
    logging.info("--- 开始执行文章同步模块 (写入热库) ---")
    try:
        # 查找文章正文所在的div
        content_div = soup.find('div', id='js_content')
        if not content_div:
            logging.warning("在文章HTML中未找到 'div#js_content'，无法提取摘要。")
            return
        
        # 提取纯文本并截取前150个字符作为摘要
        plain_text = content_div.get_text(strip=True)
        snippet = plain_text[:150]
        
        # 格式化内容并调用Coze API创建文档
        content_for_kb = f"---\n文章URL: {article_url}\n文章标题: {article_title}\n文章摘要: {snippet}\n---"
        create_coze_doc(KB_ID_ARTICLES_HOT, article_title, content_for_kb)
    except Exception as e:
        logging.error(f"文章同步模块发生未知错误: {e}")
    finally:
        logging.info("--- 文章同步模块执行完毕 ---")


# --- 文献同步模块 (业务逻辑，保持不变) ---
def sync_references_to_hot_kb(soup):
    """
    从文章HTML中提取所有符合特定格式的文献链接，并同步到Coze的“文献-增量库”。

    :param soup: 使用BeautifulSoup解析后的文章HTML对象。
    """
    logging.info("--- 开始执行文献同步模块 (写入热库) ---")
    try:
        html_string = str(soup)
        # 使用正则表达式查找所有 'https://s.caixuan.cc/' 格式的链接
        ref_links = sorted(list(set(re.findall(r'https://s\.caixuan\.cc/[A-Za-z0-9]+', html_string))))
        
        if not ref_links:
            logging.info("未在文章中找到匹配的文献链接。")
            return
            
        logging.info(f"找到 {len(ref_links)} 个唯一的文献链接需要处理。")
        
        for ref_link in ref_links:
            try:
                # 查找包含该链接的<a>标签
                a_tag = soup.find('a', href=ref_link)
                if not a_tag:
                    logging.warning(f"无法为链接找到对应的<a>标签，跳过: {ref_link}")
                    continue
                
                # 尝试从父级标签（<p>, <li>, <div>）获取更完整的标题文本
                parent = a_tag.find_parent(['p', 'li', 'div'])
                ref_title = "未知标题"
                if parent:
                    raw_title = parent.get_text(strip=True)
                    # 清理标题前的引导词
                    ref_title = re.sub(r'^(来源文章|延伸阅读|相关链接)[:：\s]*', '', raw_title).strip()
                elif a_tag.get_text(strip=True):
                    ref_title = a_tag.get_text(strip=True)
                else:
                    ref_title = "标题提取失败"
                
                # 格式化内容并调用Coze API创建文档
                content_for_kb = f"---\n文献标题: {ref_title}\n文献链接: {ref_link}\n---"
                create_coze_doc(KB_ID_REFERENCES_HOT, ref_title, content_for_kb)
            except Exception as e:
                logging.error(f"处理文献链接 {ref_link} 时出错: {e}")
    except Exception as e:
        logging.error(f"文献同步模块发生未知错误: {e}")
    finally:
        logging.info("--- 文献同步模块执行完毕 ---")


# --- 事件处理主路由 (V4.0 核心重构) ---
@app.route('/', methods=['POST'])
def handle_event():
    try:
        # 1. 检查请求体是否为空
        if not request.data:
            logging.info("接收到一个空的POST请求，已忽略。")
            return "OK", 200

        # 2. 解析XML
        root = ET.fromstring(request.data)

        # 3. 【关键修改】防御性地获取节点和文本
        msg_type_node = root.find('MsgType')
        event_node = root.find('Event')

        # 4. 如果连最基本的MsgType都没有，直接忽略
        if msg_type_node is None:
            logging.warning(f"接收到一个缺少 'MsgType' 节点的XML，已忽略。内容: {request.data[:500]}")
            return "OK", 200
        
        msg_type = msg_type_node.text
        
        # 5. 确保是事件类型，并且Event节点存在
        if msg_type == 'event' and event_node is not None:
            event = event_node.text
            # 6. 我们只关心 PUBLISHJOBFINISH 事件
            if event == 'PUBLISHJOBFINISH':
                logging.info("接收到微信 'PUBLISHJOBFINISH' 事件。")
                
                article_items = root.findall('.//ArticleResult/item')
                if not article_items:
                    logging.warning("在 'PUBLISHJOBFINISH' 事件中未找到任何文章项目。")
                
                for item in article_items:
                    # 也对文章节点进行防御性检查
                    article_url_node = item.find('ArticleUrl')
                    article_title_node = item.find('Title')
                    
                    if article_url_node is not None and article_url_node.text:
                        article_url = article_url_node.text
                        article_title = article_title_node.text if article_title_node is not None else "无标题"
                        
                        logging.info(f"正在处理文章: '{article_title}'")
                        response = requests.get(article_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.text, 'lxml')
                        
                        sync_article_to_hot_kb(article_title, article_url, soup)
                        sync_references_to_hot_kb(soup)
            else:
                # 忽略其他所有类型的事件
                logging.info(f"接收到一个非 'PUBLISHJOBFINISH' 的事件，类型: '{event}'，已忽略。")
        else:
            # 忽略所有非事件类型的消息
            logging.info(f"接收到一个非事件类型的消息，类型: '{msg_type}'，已忽略。")

    except ET.ParseError as e:
        logging.error(f"处理微信POST请求时XML解析失败: {e}. 请求体: {request.data[:500]}")
    except Exception as e:
        logging.error(f"处理微信POST请求时发生未知异常: {e}", exc_info=True) # exc_info=True会打印更详细的错误堆栈

    # 无论如何，都告诉微信我们处理完了
    return "OK", 200

# --- 本地调试入口 (可选) ---
# 如果直接运行此文件 (python main.py)，则会启动一个本地开发服务器。
# 这在云托管环境中不会被执行，因为gunicorn会直接加载app实例。
if __name__ == '__main__':
    # 监听所有网络接口的8080端口，方便本地测试
    app.run(host='0.0.0.0', port=8080, debug=True)
