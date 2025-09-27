"""
微信公众号文章同步到Coze知识库的Webhook服务
功能：当微信公众号发布文章时，自动将文章内容和参考链接同步到Coze平台的知识库中
"""

# 导入所需模块
import os                           # 用于获取环境变量
import hashlib                      # 用于微信服务器验证的sha1加密
import xml.etree.ElementTree as ET  # 用于解析微信推送的XML数据
import requests                     # 用于发送HTTP请求
import re                           # 用于正则表达式匹配
from flask import Flask, request, make_response  # Flask框架相关
from bs4 import BeautifulSoup       # 用于解析HTML文档
import logging                       # 用于记录日志

# 配置日志级别，便于在Vercel上查看运行日志
logging.basicConfig(level=logging.INFO)

# 初始化Flask应用
app = Flask(__name__)

# --- 环境变量配置 ---
# 从环境变量中获取配置信息，保护敏感信息不被泄露
WECHAT_TOKEN = os.getenv('WECHAT_TOKEN')         # 微信公众平台配置的Token
COZE_API_KEY = os.getenv('COZE_API_KEY')         # Coze平台的API密钥
KB_ID_ARTICLES = os.getenv('KB_ID_ARTICLES')     # 存储文章信息的知识库ID
KB_ID_REFERENCES = os.getenv('KB_ID_REFERENCES') # 存储参考链接的知识库ID

# --- Coze API 工具函数 ---
def create_coze_doc(kb_id, doc_name, content):
    """
    调用Coze API在指定知识库中创建文档
    
    参数:
        kb_id (str): 知识库ID
        doc_name (str): 文档名称
        content (str): 文档内容
    
    返回:
        dict/None: API响应结果或None（失败时）
    """
    # 检查必要参数是否存在
    if not all([COZE_API_KEY, kb_id]):
        logging.error("Coze API Key或知识库ID未配置")
        return None

    # 构造API请求
    url = "https://api.coze.com/v1/doc/create"
    headers = {
        "Authorization": f"Bearer {COZE_API_KEY}",  # API认证头部
        "Content-Type": "application/json",         # 内容类型
        "Connection": "keep-alive"                  # 保持连接，提高请求效率
    }
    payload = {
        "kb_id": kb_id,        # 知识库ID
        "doc_name": doc_name,  # 文档名称
        "doc_type": "text",    # 文档类型为文本
        "content": content     # 文档内容
    }
    
    try:
        # 发送POST请求创建文档
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()  # 检查请求是否成功
        logging.info(f"成功在知识库'{kb_id}'中创建文档'{doc_name}'")
        return response.json()
    except requests.exceptions.RequestException as e:
        # 记录请求异常
        logging.error(f"调用Coze API创建文档'{doc_name}'时出错: {e}")
        return None

# --- 通道1: 文章同步模块 ---
def sync_article_to_coze(article_title, article_url, soup):
    """
    提取文章信息并同步到Coze文章知识库
    
    参数:
        article_title (str): 文章标题
        article_url (str): 文章链接
        soup (BeautifulSoup): 解析后的文章HTML对象
    """
    logging.info("--- 开始执行通道1: 文章同步 ---")
    try:
        # 查找文章正文内容容器
        content_div = soup.find('div', id='js_content')
        if not content_div:
            logging.warning("在文章HTML中未找到'div#js_content'，跳过通道1")
            return

        # 提取纯文本内容并截取前150个字符作为摘要
        plain_text = content_div.get_text(strip=True)
        snippet = plain_text[:150]  # 文章摘要

        # 构造存储到知识库的内容格式：链接|||标题|||摘要
        content_for_kb = f"{article_url}|||{article_title}|||{snippet}"
        
        logging.info(f"已准备文章数据用于KB_ID_ARTICLES: 标题='{article_title}'")
        # 调用API创建文档
        create_coze_doc(KB_ID_ARTICLES, article_title, content_for_kb)
        logging.info("--- 通道1: 文章同步执行完毕 ---")

    except Exception as e:
        logging.error(f"通道1(文章同步)发生错误: {e}")

# --- 通道2: 参考链接同步模块 ---
def sync_references_to_coze(soup):
    """
    提取参考链接及其标题，并同步到Coze参考链接知识库
    
    参数:
        soup (BeautifulSoup): 解析后的文章HTML对象
    """
    logging.info("--- 开始执行通道2: 参考链接同步 ---")
    try:
        # 将BeautifulSoup对象转换为字符串
        html_string = str(soup)
        # 使用正则表达式提取所有符合格式的参考链接
        ref_links = sorted(list(set(re.findall(r'https://s\.caixuan\.cc/[A-Za-z0-9]+', html_string))))

        # 如果没有找到参考链接，则直接返回
        if not ref_links:
            logging.info("未找到参考链接，跳过通道2")
            return

        logging.info(f"找到{len(ref_links)}个唯一的参考链接待处理")

        # 遍历所有参考链接
        for ref_link in ref_links:
            ref_title = "未知标题"
            try:
                # 查找包含该链接的所有<a>标签
                a_tags = soup.find_all('a', href=ref_link)
                if not a_tags:
                    logging.warning(f"未找到链接的<a>标签，跳过: {ref_link}")
                    continue
                
                # 获取第一个<a>标签
                a_tag = a_tags[0]
                # 查找父级元素（段落、列表项或div）
                parent = a_tag.find_parent(['p', 'li', 'div'])
                if parent:
                    # 从父级元素提取文本并清理
                    raw_title = parent.get_text(strip=True)
                    # 移除前缀如"来源文章"、"延伸阅读"等
                    ref_title = re.sub(r'^(来源文章|延伸阅读|相关链接)[:：\s]*', '', raw_title).strip()
                else:
                    # 如果没有父级元素，则直接使用链接文本
                    ref_title = a_tag.get_text(strip=True) or "父级元素中未找到标题"

                # 处理标题为空的情况
                if not ref_title:
                    ref_title = "标题为空"
                    logging.warning(f"提取的标题为空，链接: {ref_link}")

                # 构造存储到知识库的内容格式：标题|||链接
                content_for_kb = f"{ref_title}|||{ref_link}"
                
                logging.info(f"已准备参考链接数据用于KB_ID_REFERENCES: 标题='{ref_title}'")
                # 调用API创建文档
                create_coze_doc(KB_ID_REFERENCES, ref_title, content_for_kb)

            except Exception as e:
                logging.error(f"处理参考链接{ref_link}时出错: {e}")
                continue
        
        logging.info("--- 通道2: 参考链接同步执行完毕 ---")

    except Exception as e:
        logging.error(f"通道2(参考链接同步)发生错误: {e}")

# --- 主要Webhook端点 ---
@app.route('/api/webhook', methods=['GET', 'POST'])
def webhook():
    """
    微信公众平台Webhook接口
    处理微信服务器的GET验证请求和POST事件推送
    """
    # 处理微信服务器的GET验证请求
    if request.method == 'GET':
        # 获取微信服务器传递的参数
        signature = request.args.get('signature', '')   # 签名
        timestamp = request.args.get('timestamp', '')   # 时间戳
        nonce = request.args.get('nonce', '')           # 随机数
        echostr = request.args.get('echostr', '')       # 随机字符串

        # 检查必要参数是否完整
        if not all([WECHAT_TOKEN, signature, timestamp, nonce, echostr]):
            return "缺少参数或服务器配置错误", 400

        # 对token、timestamp和nonce按字典序排序并拼接
        data = sorted([WECHAT_TOKEN, timestamp, nonce])
        # 使用sha1加密生成签名
        sha1 = hashlib.sha1("".join(data).encode('utf-8')).hexdigest()

        # 验证签名是否匹配
        if sha1 == signature:
            # 验证成功，返回echostr
            return make_response(echostr)
        else:
            # 验证失败
            return "验证失败", 403

    # 处理微信服务器的POST事件推送
    elif request.method == 'POST':
        # 获取请求体中的XML数据
        xml_data = request.data
        # 解析XML
        root = ET.fromstring(xml_data)
        
        # 判断是否为发布完成事件
        if root.find('MsgType').text == 'event' and root.find('Event').text == 'PUBLISHJOBFINISH':
            logging.info("收到PUBLISHJOBFINISH事件")
            try:
                # 微信可能在一次推送中发送多篇文章
                for item in root.findall('.//ArticleDetail/item'):
                    # 获取文章链接
                    article_url = item.find('ArticleUrl').text
                    # 如果链接为空则跳过
                    if not article_url:
                        logging.warning("跳过缺少ArticleUrl的项目")
                        continue

                    logging.info(f"正在处理文章链接: {article_url}")
                    
                    # 请求文章页面内容
                    response = requests.get(article_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                    response.raise_for_status()  # 检查请求是否成功
                    html_content = response.text  # 获取HTML内容
                    
                    # 使用BeautifulSoup解析HTML
                    soup = BeautifulSoup(html_content, 'lxml')
                    
                    # 从HTML的<title>标签中提取文章标题
                    article_title = soup.title.string.strip() if soup.title else "无标题"
                    
                    # 执行通道1：同步文章到Coze
                    sync_article_to_coze(article_title, article_url, soup)
                    # 执行通道2：同步参考链接到Coze
                    sync_references_to_coze(soup)

            except Exception as e:
                logging.error(f"处理PUBLISHJOBFINISH事件时出错: {e}")
        
        # 返回成功响应
        return "success", 200

    # 不支持的请求方法
    return "无效的请求方法", 405

# Vercel负责服务器管理，此部分仅用于本地测试
if __name__ == '__main__':
    app.run(debug=True, port=5000)