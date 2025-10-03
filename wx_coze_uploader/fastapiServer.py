# fastapiServer.py

import os
import json
import traceback
import logging
from fastapi import FastAPI, Request
from bs4 import BeautifulSoup
from threading import Thread, Lock
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# --- 加载环境变量 (例如 COZE_API_KEY) ---
load_dotenv()

# --- 从我们自己的模块中导入函数 ---
from wx_downloader import download_html, get_current_time_string, save_file
from coze_uploader import sync_article_to_hot_kb, sync_references_to_hot_kb


BIZ_WHITELIST = {"医工交叉园地"} # 白名单公众号名单

# =========================================================

# --- 日志和目录配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
SAVE_JSON_DIR = "./received_json"
if not os.path.exists(SAVE_JSON_DIR):
    os.makedirs(SAVE_JSON_DIR)

# --- 去重逻辑相关 ---
SNS_FILE = "processed_sns.txt" # 用于保存已处理文章sn的持久化文件
PROCESSED_SNS = set()          # 用于在内存中快速查找的集合
sns_lock = Lock()              # 线程锁，防止多线程同时写文件导致冲突

def load_processed_sns():
    """在服务启动时，从文件中加载所有已处理过的sn记录到内存中"""
    try:
        if not os.path.exists(SNS_FILE):
            # 如果文件不存在，创建一个空文件
            with open(SNS_FILE, 'w') as f:
                pass
            logging.info(f"'{SNS_FILE}' 文件不存在，已创建。")
            return
            
        with open(SNS_FILE, "r") as f:
            for line in f:
                PROCESSED_SNS.add(line.strip())
        logging.info(f"成功加载 {len(PROCESSED_SNS)} 条已处理的文章SN记录。")
    except Exception as e:
        logging.error(f"加载SN记录文件时出错: {e}")

# --- 核心处理逻辑 ---
def process_and_upload(json_data: dict):
    """
    这是核心处理函数，在一个独立的后台线程中执行。
    """
    try:
        artlist = json_data.get("data", [])
        if not artlist:
            logging.info("接收到的JSON中没有data字段或data为空。")
            return

        logging.info(f"开始处理 {len(artlist)} 篇文章。")
        for item in artlist:
            url = item.get("url")
            title = item.get("title", "无标题")
            
            # 步骤1: 白名单过滤
            bizname= item.get("bizname")
            if bizname not in BIZ_WHITELIST:
                logging.info(f"公众号名字 '{bizname}' 不在白名单中，已跳过文章《{title}》。")
                continue # 跳过当前文章，处理下一篇

            # 步骤2: 文章去重
            try:
                parsed_url = urlparse(url)
                params = parse_qs(parsed_url.query)
                sn = params.get('sn', [None])[0]

                if not sn:
                    logging.warning(f"文章《{title}》的URL中缺少'sn'参数，无法去重，跳过。 URL: {url}")
                    continue

                if sn in PROCESSED_SNS:
                    logging.info(f"检测到重复文章《{title}》(sn: {sn[:10]}...)，已跳过。")
                    continue
            except Exception as e:
                logging.error(f"解析URL或检查SN时出错: {e}，跳过文章《{title}》")
                continue
            
            # --- 所有检查通过，开始处理 ---
            logging.info(f"正在下载文章: 《{title}》 (sn: {sn[:10]}...)")
            html_content = download_html(url)

            if html_content:
                logging.info(f"文章下载成功，开始解析和上传到Coze。")
                soup = BeautifulSoup(html_content, 'lxml')
                
                # 1. 同步文章摘要到Coze
                sync_article_to_hot_kb(title, url, soup)
                
                # 2. 同步参考文献到Coze
                sync_references_to_hot_kb(soup,title)
                
                # 步骤3: 处理成功后，记录SN以备将来去重
                with sns_lock:
                    PROCESSED_SNS.add(sn)
                    with open(SNS_FILE, "a") as f:
                        f.write(sn + "\n")
                
                logging.info(f"《{title}》处理完毕。")
            else:
                logging.error(f"下载文章《{title}》失败，跳过处理。")
    except Exception as e:
        logging.error("处理和上传过程中发生严重错误:")
        logging.error(traceback.format_exc())

# --- FastAPI 应用实例 ---
app = FastAPI()

# --- 服务启动时执行的操作 ---
# 1. 加载已处理的文章SN列表
load_processed_sns()

# --- API 端点 ---
@app.post("/artlist/")
async def artlist_receiver(request: Request):
    """
    接收来自 xiaokuake.com 的POST请求。
    """
    try:
        json_data = await request.json()
        
        # 将耗时的处理任务放到后台线程，快速响应请求
        thread = Thread(target=process_and_upload, args=(json_data,))
        thread.start()

        # (可选) 保存接收到的原始JSON数据，用于调试
        current_time = get_current_time_string() + ".json"
        save_path = os.path.join(SAVE_JSON_DIR, current_time)
        save_file(save_path, json.dumps(json_data, ensure_ascii=False, indent=4))
        logging.info(f"成功接收到推送，数据已保存至 {save_path}，并已启动后台处理线程。")
        
        # 按照文档建议，返回纯文本 "success"
        return "success"

    except json.JSONDecodeError:
        logging.error("请求体不是有效的JSON格式。")
        return "error"
    except Exception:
        logging.error("处理请求时发生未知错误:")
        logging.error(traceback.format_exc())
        return "error"