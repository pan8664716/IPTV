#!/usr/bin/env python3
"""
SocketIO 完整流程测试
模拟 RawResourceFetcher 的实际运行过程
"""

import socketio
import requests
import time
import threading
import uuid

class TestFetcher:
    def __init__(self):
        self.session_id = f"fetch_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self.raw_data_list = []
        self.task_finished = threading.Event()
        self.connected = threading.Event()
        self._setup_handlers()

    def _setup_handlers(self):
        """注册 WebSocket 监听事件"""
        @self.sio.on('connect', namespace='/search')
        def on_connect():
            print(f"✅ 已连接服务器 (Session: {self.session_id})")
            self.connected.set()
            self.sio.emit('join_session', {'session_id': self.session_id}, namespace='/search')

        @self.sio.on('disconnect', namespace='/search')
        def on_disconnect():
            print("⚠️ 与服务器断开连接")
            self.connected.clear()

        @self.sio.on('connect_error', namespace='/search')
        def on_connect_error(error):
            print(f"❌ 连接错误: {error}")

        @self.sio.on('error', namespace='/search')
        def on_error(error):
            print(f"❌ 服务器错误: {error}")

        @self.sio.on('result', namespace='/search')
        def on_result(data):
            channels = data.get('channels', [])
            node_ip = data.get('ip', 'Unknown')
            
            node_content = []
            for ch in channels:
                name = ch.get('name', '').strip()
                url = ch.get('url', '').strip()
                if name and url:
                    node_content.append(f"{name},{url}")
            
            if node_content:
                self.raw_data_list.append("\n".join(node_content))
                print(f"📡 已获取节点 [{node_ip}] 的资源 (当前已收集 {len(self.raw_data_list)}/25)")
            
            if len(self.raw_data_list) >= 5:  # 测试模式下只收集 5 个节点
                self.task_finished.set()

        @self.sio.on('finished', namespace='/search')
        def on_finished(data=None):
            print("🏁 后端扫描已全部完成")
            self.task_finished.set()

    def start_capture(self):
        """启动抓取流程"""
        try:
            BASE_URL = "https://iptv.809899.xyz"
            print(f"🔗 正在连接至: {BASE_URL}")
            self.sio.connect(
                BASE_URL, 
                namespaces=['/search'], 
                transports=['websocket'],
                wait_timeout=10
            )
            
            # 等待连接完全建立（最多5秒）
            if not self.connected.wait(timeout=5):
                print("❌ 连接超时：服务器无响应")
                self.task_finished.set()
                return
            
            # 发起 HTTP 请求告知后端开始搜刮
            print("📤 发送搜刮指令...")
            resp = requests.post(
                f"{BASE_URL}/api/search/start", 
                json={"keyword": "", "mode": "multicast_list", "session_id": self.session_id},
                timeout=30
            )
            resp.raise_for_status()
            print("🚀 搜刮指令下达成功，正在接收原始数据...")
            
        except socketio.exceptions.ConnectionError as e:
            print(f"❌ SocketIO 连接失败: {e}")
            self.task_finished.set()
        except requests.exceptions.RequestException as e:
            print(f"❌ HTTP 请求失败: {e}")
            self.task_finished.set()
        except Exception as e:
            print(f"❌ 启动失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            self.task_finished.set()

if __name__ == "__main__":
    print("=" * 60)
    print("测试 RawResourceFetcher 的完整流程")
    print("=" * 60)
    
    fetcher = TestFetcher()
    fetcher.start_capture()
    
    print("\n⏳ 等待数据接收... (最多等待 120 秒)")
    fetcher.task_finished.wait(timeout=120)
    
    try:
        if fetcher.sio.connected:
            fetcher.sio.disconnect()
    except:
        pass
    
    print("\n" + "=" * 60)
    print("测试结果")
    print("=" * 60)
    print(f"✅ 收集到 {len(fetcher.raw_data_list)} 个节点的数据")
    if fetcher.raw_data_list:
        print(f"\n📊 第一个节点的数据样本（前 200 字符）:")
        print(fetcher.raw_data_list[0][:200])
