#!/usr/bin/env python3
"""
SocketIO连接诊断脚本
用于排查GitHub Actions环境中的网络问题
"""

import socket
import sys
import requests
import time
from urllib.parse import urlparse

BASE_URL = "https://iptv.809899.xyz"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"[{title}]")
    print('='*60)

def test_dns_resolution():
    """测试DNS解析"""
    print_section("DNS解析测试")
    parsed = urlparse(BASE_URL)
    hostname = parsed.hostname
    
    try:
        ip = socket.gethostbyname(hostname)
        print(f"✅ DNS解析成功")
        print(f"   主机名: {hostname}")
        print(f"   IP地址: {ip}")
        return True
    except socket.gaierror as e:
        print(f"❌ DNS解析失败: {e}")
        return False

def test_tcp_connection():
    """测试TCP连接"""
    print_section("TCP连接测试")
    parsed = urlparse(BASE_URL)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((hostname, port))
        sock.close()
        
        if result == 0:
            print(f"✅ TCP连接成功")
            print(f"   地址: {hostname}:{port}")
            return True
        else:
            print(f"❌ TCP连接失败 (errno: {result})")
            return False
    except Exception as e:
        print(f"❌ TCP连接异常: {e}")
        return False

def test_http_request():
    """测试HTTP请求"""
    print_section("HTTP请求测试")
    
    try:
        resp = requests.get(BASE_URL, timeout=10, verify=False)
        print(f"✅ HTTP请求成功")
        print(f"   状态码: {resp.status_code}")
        print(f"   响应大小: {len(resp.content)} bytes")
        return True
    except requests.exceptions.ConnectTimeout:
        print(f"❌ 连接超时 (10秒)")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ 连接错误: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {e}")
        return False

def test_socketio_connection():
    """测试SocketIO连接"""
    print_section("SocketIO连接测试")
    
    try:
        import socketio
        sio = socketio.Client(logger=False, engineio_logger=False)
        
        connected_flag = False
        connect_error = None
        
        @sio.on('connect')
        def on_connect():
            nonlocal connected_flag
            connected_flag = True
            print(f"✅ SocketIO根连接成功")
        
        @sio.on('connect_error')
        def on_error(error):
            nonlocal connect_error
            connect_error = error
            print(f"❌ SocketIO连接错误: {error}")
        
        try:
            sio.connect(BASE_URL, transports=['polling', 'websocket'], wait_timeout=10)
            time.sleep(1)
            
            if connected_flag:
                print(f"✅ SocketIO连接已建立")
                sio.disconnect()
                return True
            elif connect_error:
                print(f"❌ SocketIO连接失败: {connect_error}")
                return False
            else:
                print(f"❌ SocketIO连接超时")
                return False
                
        except Exception as e:
            print(f"❌ SocketIO连接异常: {e}")
            return False
            
    except ImportError:
        print(f"⚠️ python-socketio未安装")
        return False

def test_environment():
    """测试环境信息"""
    print_section("环境信息")
    
    import platform
    print(f"Python 版本: {sys.version}")
    print(f"系统平台: {platform.platform()}")
    
    # 检查是否在GitHub Actions中
    is_github_actions = 'GITHUB_ACTIONS' in __import__('os').environ
    print(f"GitHub Actions: {'✅ 是' if is_github_actions else '❌ 否'}")
    
    if is_github_actions:
        import os
        print(f"运行环境: {os.environ.get('RUNNER_OS', 'Unknown')}")

def main():
    print("""
╔═══════════════════════════════════════════════════════════╗
║          IPTV SocketIO 连接诊断工具                       ║
║                                                           ║
║ 此工具用于排查为什么Actions中SocketIO无法连接           ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    test_environment()
    
    results = {
        'DNS解析': test_dns_resolution(),
        'TCP连接': test_tcp_connection(),
        'HTTP请求': test_http_request(),
        'SocketIO': test_socketio_connection(),
    }
    
    print_section("诊断总结")
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    print("\n" + "="*60)
    if all(results.values()):
        print("✅ 所有测试都通过了！环境本身没有问题。")
        print("   问题可能在于:")
        print("   - SocketIO服务器对特定session_id的限制")
        print("   - /search namespace需要特殊的join_session参数")
        print("   - 服务器的防速率限制(rate limiting)")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"❌ 以下测试失败: {', '.join(failed)}")
        print("   这说明是环境/网络问题，不是代码问题。")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()
