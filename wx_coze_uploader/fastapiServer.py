# fastapiServer.py

import os
import json
import traceback
import logging
from fastapi import FastAPI, Request
from bs4 import BeautifulSoup
from threading import Thread
from dotenv import load_dotenv
load_dotenv()
# 从我们自己的模块中导入函数
from wx_downloader import download_html, get_current_time_string, save_file
from coze_uploader import sync_article_to_hot_kb, sync_references_to_hot_kb

# --- 日志和目录配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
SAVE_JSON_DIR = "./received_json"
if not os.path.exists(SAVE_JSON_DIR):
    os.makedirs(SAVE_JSON_DIR)

# --- FastAPI 应用实例 ---
app = FastAPI()

# --- 核心处理逻辑 ---
def process_and_upload(json_data: dict):
    """
    这是核心处理函数，它将被放在一个新线程中执行，以避免阻塞API响应。
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

            if not url:
                logging.warning(f"文章 '{title}' 缺少URL，跳过。")
                continue

            logging.info(f"正在下载文章: 《{title}》")
            html_content = download_html(url)

            if html_content:
                logging.info(f"文章下载成功，开始解析和上传到Coze。")
                soup = BeautifulSoup(html_content, 'lxml')
                
                # 1. 同步文章摘要
                sync_article_to_hot_kb(title, url, soup)
                
                # 2. 同步参考文献
                sync_references_to_hot_kb(soup)
                
                logging.info(f"《{title}》处理完毕。")
            else:
                logging.error(f"下载文章《{title}》失败，跳过处理。")
    except Exception as e:
        logging.error("处理和上传过程中发生严重错误:")
        logging.error(traceback.format_exc())

# --- API 端点 ---
@app.post("/artlist/")
async def artlist_receiver(request: Request):
    """
    接收来自 xiaokuake.com 的POST请求。
    """
    try:
        json_data = await request.json()
        
        # 异步处理：为了快速响应请求，将耗时的下载和上传任务放到后台线程执行
        # 这是一个好习惯，符合原始README中的建议
        thread = Thread(target=process_and_upload, args=(json_data,))
        thread.start()

        # (可选) 保存接收到的原始JSON数据，用于调试
        current_time = get_current_time_string() + ".json"
        save_path = os.path.join(SAVE_JSON_DIR, current_time)
        save_file(save_path, json.dumps(json_data, ensure_ascii=False, indent=4))
        logging.info(f"成功接收到推送，数据已保存至 {save_path}，并已启动后台处理线程。")
        
        return "success"

    except json.JSONDecodeError:
        logging.error("请求体不是有效的JSON格式。")
        return  "error"
    except Exception:
        logging.error("处理请求时发生未知错误:")
        logging.error(traceback.format_exc())
        return  "error"
