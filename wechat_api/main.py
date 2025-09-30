import os
import xml.etree.ElementTree as ET
import requests
import re
from flask import Flask, request
from bs4 import BeautifulSoup
import logging
import json
import base64

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask应用初始化 ---
app = Flask(__name__)

# --- 环境变量加载 ---
COZE_API_KEY = os.getenv('COZE_API_KEY')
KB_ID_ARTICLES_HOT = os.getenv('KB_ID_ARTICLES_HOT')
KB_ID_REFERENCES_HOT = os.getenv('KB_ID_REFERENCES_HOT')

# --- Coze API 核心函数 ---
def create_coze_doc(kb_id, doc_name, content):
    if not all([COZE_API_KEY, kb_id]):
        logging.error("API Key或知识库ID未配置。")
        return None

    api_url = "https://api.coze.cn/open_api/knowledge/document/create"
    headers = {
        "Authorization": f"Bearer {COZE_API_KEY}",
        "Content-Type": "application/json",
        "Agw-Js-Conv": "str"
    }
    
    try:
        content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        file_type = doc_name.split('.')[-1].lower() if '.' in doc_name else 'txt'
        
        payload = {
            "dataset_id": str(kb_id),
            "document_bases": [
                {
                    "name": doc_name,
                    "source_info": {
                        "file_base64": content_base64,
                        "file_type": file_type,
                        "document_source": 0
                    }
                }
            ],
            "chunk_strategy": {
                "chunk_type": 0,
                "max_tokens": 800
            },
            "format_type": 0
        }
        
        logging.info(f"准备上传文档 '{doc_name}' (类型: {file_type}) 到知识库 '{kb_id}'...")

        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        response_data = response.json()
        logging.info(f"收到 Coze API 响应: {json.dumps(response_data, ensure_ascii=False)}")
        
        if response_data.get("code") == 0:
            doc_info = response_data.get("document_infos", [{}])[0]
            doc_id = doc_info.get("document_id")
            logging.info(f"文档上传成功！文档ID: {doc_id}")
            return response_data
        else:
            logging.error(f"Coze API 业务错误。Code: {response_data.get('code')}, Msg: {response_data.get('msg')}")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"调用 Coze API 时出错: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"服务器返回的错误详情: {e.response.text}")
        return None
    except Exception as e:
        logging.error(f"为文档 '{doc_name}' 创建时发生未知错误: {e}", exc_info=True)
        return None

# --- 数据提取模块 (可独立测试) ---
def extract_article_snippet(soup):
    """
    从文章soup中提取摘要。
    优先尝试从 'div#js_content' 中提取前150个字符。
    如果找不到该div，则回退到提取整个HTML body的前100个字符作为摘要。
    """
    # 优先策略：寻找核心内容容器 'div#js_content'
    content_div = soup.find('div', id='js_content')
    
    if content_div:
        logging.info("在 'div#js_content' 中找到内容，提取前150字符作为摘要。")
        plain_text = content_div.get_text(strip=True)
        snippet = plain_text[:150]
        return snippet

    # 回退策略：如果找不到特定容器，则从整个body提取
    logging.warning("在文章HTML中未找到 'div#js_content'，将回退到提取全文的前100个字符作为摘要。")
    
    # 尝试从<body>提取，这比从整个soup提取更精确，可以避免<head>中的脚本和样式内容
    # 如果连<body>都没有，再从整个soup对象提取
    if soup.body:
        plain_text = soup.body.get_text(strip=True)
    else:
        plain_text = soup.get_text(strip=True)
    
    if not plain_text:
        logging.error("无法从HTML中提取任何有效文本内容，无法生成摘要。")
        return None # 如果全文都没有文本，则返回None

    snippet = plain_text[:100]
    return snippet

def extract_references(soup):
    """从文章soup中提取所有文献链接和标题。"""
    references = []
    html_string = str(soup)
    ref_links = sorted(list(set(re.findall(r'https://s\.caixuan\.cc/[A-Za-z0-9]+', html_string))))
    
    if not ref_links:
        return []
        
    for ref_link in ref_links:
        try:
            a_tag = soup.find('a', href=ref_link)
            if not a_tag:
                logging.warning(f"无法为链接找到对应的<a>标签，跳过: {ref_link}")
                continue
            
            parent = a_tag.find_parent(['p', 'li', 'div'])
            ref_title = "未知标题"
            if parent:
                raw_title = parent.get_text(strip=True)
                ref_title = re.sub(r'^(来源文章|延伸阅读|相关链接)[:：\s]*', '', raw_title).strip()
            elif a_tag.get_text(strip=True):
                ref_title = a_tag.get_text(strip=True)
            else:
                ref_title = "标题提取失败"
            
            references.append({"title": ref_title, "link": ref_link})
        except Exception as e:
            logging.error(f"提取文献 '{ref_link}' 标题时出错: {e}", exc_info=True)
            
    return references

# --- 文章同步模块 ---
def sync_article_to_hot_kb(article_title, article_url, soup):
    logging.info("--- 开始执行文章同步模块 (写入热库) ---")
    try:
        snippet = extract_article_snippet(soup)
        if snippet is None:
            return  # 日志已在提取函数中记录
        
        # <<< 增强日志: 打印提取到的摘要内容
        logging.info(f"成功提取摘要: '{snippet[:50]}...'")
        
        content_for_kb = f"---\n文章URL: {article_url}\n文章标题: {article_title}\n文章摘要: {snippet}\n---"
        create_coze_doc(KB_ID_ARTICLES_HOT, article_title, content_for_kb)
    except Exception as e:
        logging.error(f"文章同步模块发生未知错误: {e}", exc_info=True)
    finally:
        logging.info("--- 文章同步模块执行完毕 ---")


# --- 文献同步模块 ---
def sync_references_to_hot_kb(soup):
    logging.info("--- 开始执行文献同步模块 (写入热库) ---")
    try:
        references = extract_references(soup)
        
        if not references:
            logging.info("未在文章中找到匹配的文献链接。")
            return
            
        logging.info(f"找到 {len(references)} 个唯一的文献链接需要处理。")
        
        for ref in references:
            ref_title = ref['title']
            ref_link = ref['link']
            try:
                # <<< 增强日志: 打印提取到的文献标题和链接
                logging.info(f"成功提取文献: 标题='{ref_title}', 链接='{ref_link}'")

                content_for_kb = f"---\n文献标题: {ref_title}\n文献链接: {ref_link}\n---"
                create_coze_doc(KB_ID_REFERENCES_HOT, ref_title, content_for_kb)
            except Exception as e:
                logging.error(f"处理文献链接 {ref_link} 时出错: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"文献同步模块发生未知异常: {e}", exc_info=True)
    finally:
        logging.info("--- 文献同步模块执行完毕 ---")


# --- 事件处理主路由 ---
@app.route('/', methods=['POST'])
def handle_event():
    # <<< 增强日志: 打印收到的原始请求体，非常重要！
    logging.info(f"收到新的POST请求。原始数据 (前500字节): {request.data.decode('utf-8', errors='ignore')[:500]}")

    try:
        if not request.data:
            logging.info("请求体为空，已忽略。")
            return "OK", 200

        root = ET.fromstring(request.data)
        msg_type_node = root.find('MsgType')
        event_node = root.find('Event')

        if msg_type_node is None:
            logging.warning(f"接收到一个缺少 'MsgType' 节点的XML，已忽略。")
            return "OK", 200
        
        msg_type = msg_type_node.text
        
        if msg_type == 'event' and event_node is not None:
            event = event_node.text
            
            if event == 'MASSSENDJOBFINISH':
                logging.info("接收到微信 'MASSSENDJOBFINISH' 事件。")
                
                article_items_node = root.find('ArticleItems')
                if article_items_node is None:
                    logging.warning("在 'MASSSENDJOBFINISH' 事件中未找到 'ArticleItems' 节点。")
                    return "OK", 200
                
                article_count = len(article_items_node.findall('item'))
                logging.info(f"事件中包含 {article_count} 篇文章。")

                for item in article_items_node.findall('item'):
                    try:
                        title_node = item.find('Title')
                        content_node = item.find('Content')

                        if title_node is not None and content_node is not None:
                            article_title = title_node.text
                            article_html_content = content_node.text
                            pseudo_url = f"from_mass_send_event_{root.find('MsgID').text if root.find('MsgID') is not None else 'unknown_msg_id'}"

                            # <<< 增强日志: 打印从XML中提取的关键信息
                            logging.info(f"正在处理文章: '{article_title}'。HTML内容长度: {len(article_html_content)}")
                            
                            soup = BeautifulSoup(article_html_content, 'lxml')
                            
                            sync_article_to_hot_kb(article_title, pseudo_url, soup)
                            sync_references_to_hot_kb(soup)
                        else:
                            logging.warning("在 'item' 节点中缺少 'Title' 或 'Content'，跳过此文章。")

                    except Exception as e:
                        logging.error(f"处理 'MASSSENDJOBFINISH' 中的单个文章时出错: {e}", exc_info=True)
                        continue

            else:
                logging.info(f"接收到一个非 'MASSSENDJOBFINISH' 的事件，类型: '{event}'，已忽略。")
        else:
            logging.info(f"接收到一个非事件类型的消息，类型: '{msg_type}'，已忽略。")

    except ET.ParseError as e:
        logging.error(f"处理微信POST请求时XML解析失败: {e}. 请求体: {request.data.decode('utf-8', errors='ignore')[:500]}")
    except Exception as e:
        logging.error(f"处理微信POST请求时发生未知异常: {e}", exc_info=True)

    return "OK", 200

# --- 本地调试入口 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)