# coze_uploader.py

import os
import requests
import re
from bs4 import BeautifulSoup
import logging
import json
import base64

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 从环境变量加载配置 ---
COZE_API_KEY = os.getenv('COZE_API_KEY')
KB_ID_ARTICLES_HOT = os.getenv('KB_ID_ARTICLES_HOT')
KB_ID_REFERENCES_HOT = os.getenv('KB_ID_REFERENCES_HOT')

if not all([COZE_API_KEY, KB_ID_ARTICLES_HOT, KB_ID_REFERENCES_HOT]):
    logging.warning("警告：一个或多个环境变量 (COZE_API_KEY, KB_ID_ARTICLES_HOT, KB_ID_REFERENCES_HOT) 未设置！")

# --- Coze API 核心函数 ---
def create_coze_doc(kb_id, doc_name, content):
    if not all([COZE_API_KEY, kb_id]):
        logging.error("API Key或知识库ID未配置，无法上传。")
        return None

    api_url = "https://api.coze.cn/open_api/knowledge/document/create"
    headers = {
        "Authorization": f"Bearer {COZE_API_KEY}",
        "Content-Type": "application/json",
        "Agw-Js-Conv": "str"
    }
    
    try:
        content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        file_type = 'txt' # 我们总是以纯文本形式上传
        
        payload = {
            "dataset_id": str(kb_id),
            "document_bases": [{
                "name": doc_name,
                "source_info": {
                    "file_base64": content_base64,
                    "file_type": file_type,
                    "document_source": 0
                }
            }],
            "chunk_strategy": {"chunk_type": 0, "max_tokens": 800},
            "format_type": 0
        }
        
        logging.info(f"准备上传文档 '{doc_name}' 到知识库 '{kb_id}'...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        response_data = response.json()
        if response_data.get("code") == 0:
            doc_id = response_data.get("document_infos", [{}])[0].get("document_id")
            logging.info(f"文档上传成功！文档ID: {doc_id}")
            return response_data
        else:
            logging.error(f"Coze API 业务错误: Code={response_data.get('code')}, Msg={response_data.get('msg')}")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"调用 Coze API 时出错: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"服务器返回的错误详情: {e.response.text}")
        return None
    except Exception as e:
        logging.error(f"为文档 '{doc_name}' 创建时发生未知错误: {e}", exc_info=True)
        return None

# --- 数据提取模块 ---
def extract_article_snippet(soup):
    content_div = soup.find('div', id='js_content')
    if content_div:
        plain_text = content_div.get_text(strip=True)
        return plain_text[:150] # 提取摘要
    
    logging.warning("未找到 'div#js_content'，将从全文提取摘要。")
    if soup.body:
        return soup.body.get_text(strip=True)[:100]
    return soup.get_text(strip=True)[:100]

# coze_uploader.py

def extract_references(soup):
    """
    从文章soup中提取所有 s.caixuan.cc 格式的链接。
    新版：能同时处理<a>标签的href链接和纯文本链接。
    """
    references = []
    html_string = str(soup)
    
    # 步骤1: 像以前一样，用正则表达式找出所有符合格式的链接字符串
    ref_links = sorted(list(set(re.findall(r'https://s\.caixuan\.cc/[A-Za-z0-9]+', html_string))))
    
    if not ref_links:
        logging.info("在文章HTML中未找到 s.caixuan.cc 格式的链接字符串。")
        return []
        
    logging.info(f"找到了 {len(ref_links)} 个 s.caixuan.cc 格式的链接字符串，正在尝试解析...")
    
    for ref_link in ref_links:
        ref_title = "文献原文链接" # 先设置一个默认标题
        
        # 步骤2: 优先尝试把它当作一个<a>标签来查找 (处理旧情况)
        a_tag = soup.find('a', href=ref_link)
        
        if a_tag:
            # 如果找到了<a>标签，就尝试提取更精确的标题
            logging.info(f"链接 '{ref_link[:30]}...' 是一个<a>标签，尝试提取标题。")
            parent = a_tag.find_parent(['p', 'li', 'div'])
            if parent:
                raw_title = parent.get_text(strip=True)
                # 清理常见的引导词
                ref_title = re.sub(r'^(来源文章|延伸阅读|相关链接)[:：\s]*', '', raw_title).strip()
            elif a_tag.get_text(strip=True):
                ref_title = a_tag.get_text(strip=True)
        else:
            # 如果找不到<a>标签，就说明它是一个纯文本链接 (处理新情况)
            logging.info(f"链接 '{ref_link[:30]}...' 是纯文本，使用默认标题。")
            # 在这里我们可以保持使用默认标题 "文献原文链接"
            pass 
        
        references.append({"title": ref_title, "link": ref_link})
        
    return references

# --- 同步(上传)模块 ---
def sync_article_to_hot_kb(article_title, article_url, soup):
    logging.info(f"--- 开始同步文章: '{article_title}' ---")
    snippet = extract_article_snippet(soup)
    if not snippet:
        logging.error("无法提取文章摘要，同步中止。")
        return
        
    content_for_kb = f"---\n文章URL: {article_url}\n文章标题: {article_title}\n文章摘要: {snippet}\n---"
    create_coze_doc(KB_ID_ARTICLES_HOT, article_title, content_for_kb)

def sync_references_to_hot_kb(soup):
    logging.info("--- 开始同步文章中的参考文献 ---")
    references = extract_references(soup)
    
    if not references:
        logging.info("未找到参考文献。")
        return
            
    logging.info(f"找到 {len(references)} 篇参考文献。")
    for ref in references:
        content_for_kb = f"---\n文献标题: {ref['title']}\n文献链接: {ref['link']}\n---"
        create_coze_doc(KB_ID_REFERENCES_HOT, ref['title'], content_for_kb)
