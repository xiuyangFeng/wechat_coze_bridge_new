# wx_downloader.py

import requests
import os
import pytz
from datetime import datetime

# --- 时间和文件保存工具 ---
def get_current_time_string():
    tz = pytz.timezone('Asia/Shanghai')    
    current_time = datetime.now(tz)    
    time_string = current_time.strftime("%Y-%m-%d_%H-%M-%S_%f")
    return time_string[:-3]

def save_file(fpath, file_content):    
    with open(fpath, 'w', encoding='UTF-8') as f:
        f.write(file_content)

# --- 核心下载函数 ---
def download_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Connection': 'keep-alive',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.text
        else:
            print(f"下载失败: 状态码 {response.status_code} for URL {url}")
            return None
    except requests.RequestException as e:
        print(f"下载时发生网络错误: {e}")
        return None
