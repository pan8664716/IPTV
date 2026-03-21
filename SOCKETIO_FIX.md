# SocketIO 连接问题修复指南

## 问题描述
在 GitHub Actions 定时任务中运行时，SocketIO 连接失败：
```
❌ SocketIO 连接失败: One or more namespaces failed to connect:
💡 请检查服务器地址是否正确
📭 没有收集到任何数据，文件未生成。
```

## 根本原因
1. **网络环境差异** - Actions 环境与本地网络环境不同
2. **缺乏重试机制** - 单次连接失败直接放弃
3. **SSL 证书验证** - 某些环境的证书验证失败
4. **超时设置过短** - Actions 网络响应可能较慢
5. **transport 选项不完善** - 仅使用 websocket，缺少备选方案

## 实施的改进

### 1. 添加重试机制
- **最多重试 3 次**
- **每次间隔 5 秒**（首次连接超时后为 3 秒）
- 详细输出重试次数和进度

```python
while retry_count < max_retries:
    retry_count += 1
    print(f"🔗 正在连接至: {BASE_URL} (尝试 {retry_count}/{max_retries})")
    # ... 连接逻辑
    if retry_count < max_retries:
        time.sleep(5)
```

### 2. 优化 SocketIO 配置
- **添加 polling 作为备选 transport**
  ```python
  transports=['websocket', 'polling']  # websocket 失败时自动用 polling
  ```
- **启用自动重连机制**
  ```python
  reconnection=True, reconnection_attempts=3, reconnection_delay=1
  ```
- **增加 wait_timeout** 从 10s 改为 15s
- **添加自定义 User-Agent**

### 3. 禁用 SSL 验证
在 Actions 等受信环境中禁用 SSL 验证：
```python
# 在请求时
resp = requests.post(..., verify=False)

# 全局禁用警告
requests.packages.urllib3.disable_warnings()
```

### 4. 改进连接超时处理
- **连接超时** 从 5s 改为 10s
- **完整的异常捕获和清理**
- **每次重试前断开旧连接**

### 5. 减少日志噪音
关闭 SocketIO 的详细日志：
```python
self.sio = socketio.Client(logger=False, engineio_logger=False)
```

## 修改的文件
- `main.py` - RawResourceFetcher 类的 start_capture() 方法

## 验证
✅ 本地运行成功，能正常连接到服务器并接收数据

## 预期效果
在 GitHub Actions 中运行时：
1. 首次连接失败将自动重试
2. 如果 websocket 失败，尝试 polling transport
3. 增加成功连接的概率
4. 提供更详细的错误信息用于故障排查

## 后续建议
如果问题仍然存在，考虑：
1. 增加重试次数到 5 次
2. 调整重试间隔时间
3. 在 Actions 中添加网络诊断日志
4. 检查服务器是否有 IP 白名单限制
5. 考虑在 Actions 中使用代理或 VPN
