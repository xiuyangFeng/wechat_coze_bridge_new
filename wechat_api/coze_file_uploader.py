# coze_file_uploader.py - V3 终极版 (完美复刻成功请求)

import os
import requests
import logging
import json
import base64
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

print("--- 正在加载环境变量... ---")
if load_dotenv():
    print("成功从 .env 文件加载环境变量。")
else:
    print("警告：未找到 .env 文件。")

COZE_API_KEY = os.getenv('COZE_API_KEY', 'pat_IRbq1CIzmfEejPjFc1BSorpRlue7BmI4QEYQSoRoiYkzbZjkGValTUtm5RBM8Tdl')
TARGET_KB_ID = os.getenv('TARGET_KB_ID', '7554764213966192681') 

def upload_file_to_coze(kb_id, file_path):
    if not all([COZE_API_KEY, kb_id]):
        logging.error("API Key或知识库ID未配置。")
        return None

    if not os.path.exists(file_path):
        logging.error(f"文件不存在: {file_path}")
        return None

    api_url = "https://api.coze.cn/open_api/knowledge/document/create"
    headers = {
        "Authorization": f"Bearer {COZE_API_KEY}",
        "Content-Type": "application/json",
        "Agw-Js-Conv": "str"
    }
    
    try:
        with open(file_path, 'rb') as f:
            file_content_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        file_name = os.path.basename(file_path)
        file_type = file_name.split('.')[-1].lower() if '.' in file_name else 'txt'
        
        payload = {
            "dataset_id": str(kb_id),
            "document_bases": [
                {
                    "name": file_name,
                    "source_info": {
                        "file_base64": file_content_base64,
                        "file_type": file_type,
                        "document_source": 0 # 1. 加上 document_source
                    }
                }
            ],
            "chunk_strategy": {
                "chunk_type": 0,         # 2. chunk_type 设为 0
                "max_tokens": 800
            },
            "format_type": 0             # 3. 加上 format_type
        }
        
        logging.info(f"准备上传文件 '{file_name}' (类型: {file_type}) 到知识库 '{kb_id}'...")
        logging.info(f"请求体: {json.dumps(payload, ensure_ascii=False)}")

        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        response_data = response.json()
        logging.info(f"收到 Coze API 响应: {json.dumps(response_data, ensure_ascii=False)}")
        
        if response_data.get("code") == 0:
            doc_info = response_data.get("document_infos", [{}])[0]
            doc_id = doc_info.get("document_id")
            logging.info(f"文件上传成功！文档ID: {doc_id}")
            return response_data
        else:
            logging.error(f"Coze API 业务错误。Code: {response_data.get('code')}, Msg: {response_data.get('msg')}")
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"调用 Coze API 时出错: {e}")
        if e.response is not None:
            logging.error(f"服务器返回的错误详情: {e.response.text}")
        return None
    except Exception as e:
        logging.error(f"发生未知错误: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    # 我们继续使用 .txt 文件，因为您已经证明了它是可以的
    sample_file = 'sample_upload.txt'
    
    if not os.path.exists(sample_file):
        print(f"示例文件 '{sample_file}' 不存在，正在为您创建...")
        with open(sample_file, 'w', encoding='utf-8') as f:
            f.write("这是一个由Python脚本上传的测试文件。\n\nHello, Coze!")
        print("示例文件创建成功。")

    print("\n--- 开始执行 Coze 文件上传测试 (V3) ---")
    result = upload_file_to_coze(TARGET_KB_ID, sample_file)
    
    if result:
        print("\n--- Python 脚本测试成功 ---")
    else:
        print("\n--- Python 脚本测试失败 ---")