#!/usr/bin/env python3
"""
SocketIO 连接诊断脚本
用于测试与 iptv.809899.xyz 的 WebSocket 连接
"""

import socketio
import requests
import time
import threading
import sys

BASE_URL = "https://iptv.809899.xyz"

def test_http_connection():
    """测试 HTTP 连接"""
    print("=" * 60)
    print("步骤 1: 测试 HTTP 连接")
    print("=" * 60)
    try:
        resp = requests.get(BASE_URL, timeout=10)
        print(f"✅ HTTP 连接成功: 状态码 {resp.status_code}")
        return True
    except Exception as e:
        print(f"❌ HTTP 连接失败: {e}")
        return False

def test_socketio_connection():
    """测试 SocketIO 连接"""
    print("\n" + "=" * 60)
    print("步骤 2: 测试 SocketIO WebSocket 连接")
    print("=" * 60)
    
    sio = socketio.Client(logger=True, engineio_logger=True)
    connection_event = threading.Event()
    error_event = threading.Event()
    error_msg = None
    
    @sio.event(namespace='/search')
    def connect():
        print("✅ SocketIO 连接成功")
        connection_event.set()
    
    @sio.on('connect_error', namespace='/search')
    def on_connect_error(error):
        nonlocal error_msg
        error_msg = error
        print(f"❌ 连接错误: {error}")
        error_event.set()
    
    @sio.on('error', namespace='/search')
    def on_error(error):
        print(f"❌ 服务器错误: {error}")
        error_event.set()
    
    @sio.on('disconnect', namespace='/search')
    def on_disconnect():
        print("⚠️ 已断开连接")
    
    try:
        print(f"🔗 正在连接至: {BASE_URL}")
        print("   使用 WebSocket 传输层...")
        
        sio.connect(
            BASE_URL,
            namespaces=['/search'],
            transports=['websocket'],
            wait_timeout=15
        )
        
        # 等待连接完全建立
        if connection_event.wait(timeout=10):
            print("✅ 连接已建立")
            time.sleep(2)  # 保持连接
            sio.disconnect()
            return True
        else:
            print("❌ 连接超时")
            return False
            
    except Exception as e:
        print(f"❌ SocketIO 连接异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            if sio.connected:
                sio.disconnect()
        except:
            pass

def test_api_endpoint():
    """测试 API 端点"""
    print("\n" + "=" * 60)
    print("步骤 3: 测试 API 端点")
    print("=" * 60)
    try:
        resp = requests.post(
            f"{BASE_URL}/api/search/start",
            json={"keyword": "", "mode": "multicast_list", "session_id": "test_123"},
            timeout=10
        )
        print(f"✅ API 端点可访问: 状态码 {resp.status_code}")
        print(f"   响应: {resp.text[:200]}")
        return True
    except Exception as e:
        print(f"❌ API 端点不可访问: {e}")
        return False

if __name__ == "__main__":
    print("\n🔍 开始诊断 SocketIO 连接问题...\n")
    
    results = []
    results.append(("HTTP 连接", test_http_connection()))
    results.append(("SocketIO 连接", test_socketio_connection()))
    results.append(("API 端点", test_api_endpoint()))
    
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + ("=" * 60))
    if all_passed:
        print("✨ 所有测试通过，可以运行 main.py")
    else:
        print("⚠️ 存在连接问题，请检查网络或服务器状态")
    
    sys.exit(0 if all_passed else 1)
