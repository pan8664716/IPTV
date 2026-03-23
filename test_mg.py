import requests

url = "http://skyr.wuaze.com/mg.txt"

# 模拟浏览器头部，防止被服务器拒绝连接
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    # 增加 timeout 防止无限等待
    response = requests.get(url, headers=headers, timeout=15)
    
    # 检查状态码
    if response.status_code == 200:
        # 自动识别编码并打印全部内容
        response.encoding = response.apparent_encoding
        print("--- 获取内容如下 ---")
        print(response.text)
        print("--- 内容打印完毕 ---")
    else:
        print(f"❌ 服务器返回错误状态码: {response.status_code}")

except Exception as e:
    print(f"❌ 获取失败，错误原因: {e}")