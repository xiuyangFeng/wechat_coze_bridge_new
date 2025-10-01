# test_main.py - 单元测试和集成测试脚本
import unittest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
import os
import json
import base64

# 在导入被测试模块之前，我们需要确保环境变量已设置，
# 这样即使在测试环境中，模块也能正常加载。
os.environ['COZE_API_KEY'] = 'test_api_key'
os.environ['KB_ID_ARTICLES_HOT'] = 'test_kb_articles'
os.environ['KB_ID_REFERENCES_HOT'] = 'test_kb_references'

# 导入我们需要测试的 Flask 应用和函数
from wechat_api.main import app, extract_article_snippet, extract_references, create_coze_doc, sync_article_to_hot_kb, sync_references_to_hot_kb

# --- 测试数据 ---

# 模拟的微信文章HTML内容
SAMPLE_HTML_CONTENT = """
<div id="js_content">
    <p>这是文章的摘要部分，应该被提取。</p>
    <p>这里是更多内容...</p>
    <section>
        <p>来源文章：<a href="https://s.caixuan.cc/Ref1">第一篇参考文献标题</a></p>
    </section>
    <ul>
        <li>延伸阅读：<a href="https://s.caixuan.cc/Ref2">第二篇参考文献标题</a></li>
    </ul>
    <p>这是一个重复的链接，不应该被重复计算 <a href="https://s.caixuan.cc/Ref1">重复的标题</a></p>
</div>
"""

# 模拟的微信 `MASSSENDJOBFINISH` 事件XML负载
SAMPLE_XML_PAYLOAD = f"""
<xml>
    <ToUserName><![CDATA[gh_xxxxxxxx]]></ToUserName>
    <FromUserName><![CDATA[o_xxxxxxxx]]></FromUserName>
    <CreateTime>1677777777</CreateTime>
    <MsgType><![CDATA[event]]></MsgType>
    <Event><![CDATA[MASSSENDJOBFINISH]]></Event>
    <MsgID>1234567890123456</MsgID>
    <ArticleItems>
        <item>
            <Title><![CDATA[测试文章标题]]></Title>
            <Content><![CDATA[{SAMPLE_HTML_CONTENT}]]></Content>
        </item>
    </ArticleItems>
</xml>
"""

class TestDataExtraction(unittest.TestCase):
    """测试数据提取模块"""

    def setUp(self):
        """在每个测试前运行，创建BeautifulSoup对象"""
        self.soup = BeautifulSoup(SAMPLE_HTML_CONTENT, 'lxml')

    def test_extract_article_snippet(self):
        """测试是否能正确提取文章摘要"""
        snippet = extract_article_snippet(self.soup)
        self.assertIsNotNone(snippet)
        self.assertTrue(snippet.startswith("这是文章的摘要部分，应该被提取。"))
        self.assertLessEqual(len(snippet), 150)

    def test_extract_references(self):
        """测试是否能正确提取所有不重复的参考文献"""
        references = extract_references(self.soup)
        self.assertEqual(len(references), 2)
        
        # 检查链接是否正确且唯一
        links = {ref['link'] for ref in references}
        self.assertEqual(links, {'https://s.caixuan.cc/Ref1', 'https://s.caixuan.cc/Ref2'})

        # 检查标题是否被正确提取
        titles = {ref['title'] for ref in references}
        self.assertIn("第一篇参考文献标题", titles)
        self.assertIn("第二篇参考文献标题", titles)


class TestCozeAPI(unittest.TestCase):
    """测试Coze API核心函数"""

    @patch('wechat_api.main.requests.post')
    def test_create_coze_doc_success(self, mock_post):
        """测试Coze API调用成功的情况"""
        # 模拟一个成功的API响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "msg": "Success", "document_infos": [{"document_id": "doc_123"}]}
        mock_post.return_value = mock_response

        test_content = "some content"
        result = create_coze_doc("kb_test", "doc_name_test.txt", test_content)

        # 验证requests.post是否被正确调用
        mock_post.assert_called_once()
        
        # 验证调用的 URL
        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, "https://api.coze.cn/open_api/knowledge/document/create")

        # 验证请求体 (payload)
        called_payload = mock_post.call_args[1]['json']
        self.assertEqual(called_payload['dataset_id'], "kb_test")
        self.assertEqual(len(called_payload['document_bases']), 1)
        
        doc_base = called_payload['document_bases'][0]
        self.assertEqual(doc_base['name'], "doc_name_test.txt")
        
        source_info = doc_base['source_info']
        self.assertEqual(source_info['file_type'], 'txt')
        
        # 验证内容是否被正确地base64编码
        expected_base64 = base64.b64encode(test_content.encode('utf-8')).decode('utf-8')
        self.assertEqual(source_info['file_base64'], expected_base64)

        # 验证返回值是否符合预期
        self.assertIsNotNone(result)
        self.assertEqual(result.get("document_infos", [{}])[0].get("document_id"), "doc_123")

    @patch('wechat_api.main.requests.post')
    def test_create_coze_doc_api_error(self, mock_post):
        """测试Coze API返回业务错误的情况"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 1001, "msg": "Invalid parameter"}
        mock_post.return_value = mock_response

        result = create_coze_doc("kb_test", "doc_name_test", "some content")
        self.assertIsNone(result)

    @patch('wechat_api.main.requests.post')
    def test_create_coze_doc_request_exception(self, mock_post):
        """测试网络请求异常的情况"""
        from requests.exceptions import RequestException
        mock_post.side_effect = RequestException("Connection error")

        result = create_coze_doc("kb_test", "doc_name_test", "some content")
        self.assertIsNone(result)


class TestSyncModules(unittest.TestCase):
    """测试同步模块"""

    def setUp(self):
        self.soup = BeautifulSoup(SAMPLE_HTML_CONTENT, 'lxml')

    @patch('wechat_api.main.create_coze_doc')
    def test_sync_article_to_hot_kb(self, mock_create_doc):
        """测试文章同步模块是否正确调用create_coze_doc"""
        sync_article_to_hot_kb("测试文章", "http://example.com", self.soup)
        
        # 验证create_coze_doc被调用了一次
        mock_create_doc.assert_called_once()
        
        # 验证调用的参数是否正确
        kb_id = mock_create_doc.call_args[0][0]
        doc_name = mock_create_doc.call_args[0][1]
        content = mock_create_doc.call_args[0][2]
        
        self.assertEqual(kb_id, 'test_kb_articles')
        self.assertEqual(doc_name, "测试文章")
        self.assertIn("文章URL: http://example.com", content)
        self.assertIn("文章摘要: 这是文章的摘要部分", content)

    @patch('wechat_api.main.create_coze_doc')
    def test_sync_references_to_hot_kb(self, mock_create_doc):
        """测试文献同步模块是否为每个文献都调用了create_coze_doc"""
        sync_references_to_hot_kb(self.soup)
        
        # 验证create_coze_doc被调用了两次（因为有两个唯一文献）
        self.assertEqual(mock_create_doc.call_count, 2)
        
        # 验证其中一次调用的参数
        # call_args_list是一个包含所有调用的列表
        first_call_args = mock_create_doc.call_args_list[0][0]
        kb_id = first_call_args[0]
        doc_name = first_call_args[1]
        content = first_call_args[2]

        self.assertEqual(kb_id, 'test_kb_references')
        self.assertIn("参考文献标题", doc_name)
        self.assertIn("文献链接: https://s.caixuan.cc/", content)


class TestFlaskEndpoint(unittest.TestCase):
    """测试Flask主路由"""

    def setUp(self):
        """设置Flask测试客户端"""
        app.testing = True
        self.client = app.test_client()

    @patch('wechat_api.main.sync_article_to_hot_kb')
    @patch('wechat_api.main.sync_references_to_hot_kb')
    def test_handle_event_mass_send_finish(self, mock_sync_refs, mock_sync_article):
        """测试接收到MASSSENDJOBFINISH事件时，是否能正确触发同步函数"""
        response = self.client.post('/', data=SAMPLE_XML_PAYLOAD, content_type='application/xml')
        
        # 验证HTTP响应码
        self.assertEqual(response.status_code, 200)
        
        # 验证两个核心同步函数都被调用了
        mock_sync_article.assert_called_once()
        mock_sync_refs.assert_called_once()

        # 验证传递给同步函数的参数
        article_args = mock_sync_article.call_args[0]
        self.assertEqual(article_args[0], "测试文章标题") # title
        self.assertTrue(article_args[1].startswith("from_mass_send_event_")) # pseudo_url
        self.assertIsInstance(article_args[2], BeautifulSoup) # soup

    def test_handle_event_empty_post(self):
        """测试收到空POST请求时的情况"""
        response = self.client.post('/', data='', content_type='application/xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'OK')

    def test_handle_event_other_event(self):
        """测试收到其他类型事件时，服务是否会忽略"""
        other_event_xml = SAMPLE_XML_PAYLOAD.replace("MASSSENDJOBFINISH", "USER_ENTER_SESSION")
        response = self.client.post('/', data=other_event_xml, content_type='application/xml')
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    print("--- 开始运行测试脚本 ---")
    # 使用unittest的TestLoader来发现并运行测试
    suite = unittest.TestLoader().discover(start_dir='.', pattern='test_main.py')
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n--- 所有测试均已通过！---")
    else:
        print("\n--- 部分测试失败，请检查输出日志。 ---")
