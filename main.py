import urllib.request
from urllib.parse import quote, unquote
import re
import os
from datetime import datetime, timedelta, timezone
import opencc
import time
import uuid
import requests
import socketio
import threading
import warnings

# 在Actions等受信环境中，禁用 SSL 验证时的警告
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# ===================== 全局核心配置 =====================
# 指定按TXT文件内顺序排列的分类，其余自动字典序排序，按需增删
ORDERED_CHANNEL_TYPES = ["央视频道", "卫视频道", "港澳台", "电影频道", "电视剧频道", "埋堆堆", "咪咕直播"]
# 频道名称清理字符集
REMOVAL_LIST = [
    "「IPV4」", "「IPV6」", "[ipv6]", "[ipv4]", "_电信", "电信", "（HD）", "[超清]",
    "高清", "超清", "-HD", "(HK)", "AKtv", "@", "IPV6", "🎞️", "🎦", " ",
    "[BD]", "[VGA]", "[HD]", "[SD]", "(1080p)", "(720p)", "(480p)"
]
# 网络请求配置
USER_AGENT = "PostmanRuntime-ApipostRuntime/1.1.0"
URL_FETCH_TIMEOUT = 10
# 白名单测速阈值(ms)
RESPONSE_TIME_THRESHOLD = 2000
# M3U相关配置

TVG_URL = "https://gh-proxy.com/https://github.com/pan8664716/IPTV/raw/refs/heads/main/e.xml.gz"
LOGO_URL_TPL = "https://gh-proxy.com/https://raw.githubusercontent.com/pan8664716/IPTV/refs/heads/main/logo/{}.png"
# 所有单个频道最多保留的有效源数量，可直接修改数字（-1=无限制）
# 限制每个频道最多 30 个源：平衡质量和列表大小
SINGLE_CHANNEL_MAX_COUNT = 30  

# ==========================================
# SocketIO 资源获取配置
# ==========================================
BASE_URL = "https://iptv.809899.xyz"
RAW_MERGED_RESOURCES_FILE = "raw_merged_resources.txt"
# 清理环境代理
for env_key in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(env_key, None)

# ===================== 通用工具函数 =====================
def get_project_dirs() -> dict:
    script_abspath = os.path.abspath(__file__)
    root_dir = os.path.dirname(script_abspath)
    return {
        "root": root_dir,
        "blacklist_auto": os.path.join(root_dir, "assets/whitelist-blacklist/blacklist_auto.txt"),
        "whitelist_respotime": os.path.join(root_dir, "assets/whitelist-blacklist/whitelist_respotime.txt"),
        "blacklist_manual": os.path.join(root_dir, "assets/whitelist-blacklist/blacklist_manual.txt"),
        "whitelist_manual": os.path.join(root_dir, "assets/whitelist-blacklist/whitelist_manual.txt"),
        "corrections_name": os.path.join(root_dir, "assets/corrections_name.txt"),
        "urls": os.path.join(root_dir, "assets/urls.txt"),
        "main_channel": os.path.join(root_dir, "主频道"),
        "local_channel": os.path.join(root_dir, "地方台"),
        "raw_merged_resources": os.path.join(root_dir, "assets/whitelist-blacklist/raw_merged_resources.txt")
    }

def read_txt(file_path: str, strip: bool = True, skip_empty: bool = True) -> list:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if strip:
                lines = [line.strip() for line in lines]
            if skip_empty:
                lines = [line for line in lines if line]
            return lines
    except FileNotFoundError:
        print(f"[ERROR] 文件未找到: {file_path}")
        return []
    except Exception as e:
        print(f"[ERROR] 读取文件 {file_path} 失败: {str(e)}")
        return []

def write_txt(file_path: str, data: list or str) -> None:
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if isinstance(data, list):
            data = '\n'.join([str(line) for line in data])
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data)
        print(f"[SUCCESS] 文件写入成功: {os.path.basename(file_path)}")
    except Exception as e:
        print(f"[ERROR] 写入文件 {file_path} 失败: {str(e)}")

def safe_quote_url(url: str) -> str:
    try:
        unquoted = unquote(url)
        return quote(unquoted, safe=':/?&=')
    except Exception:
        return url

def traditional_to_simplified(text: str) -> str:
    if not hasattr(traditional_to_simplified, "converter"):
        traditional_to_simplified.converter = opencc.OpenCC('t2s')
    return traditional_to_simplified.converter.convert(text) if text else ""

# ===================== 黑名单/纠错字典处理 =====================
def load_blacklist(blacklist_auto_path: str, blacklist_manual_path: str) -> set:
    def _extract_black_urls(file_path):
        lines = read_txt(file_path)
        urls = []
        for line in lines:
            if "," in line:
                url = line.split(',')[1].strip()
                if url:
                    urls.append(url)
        return urls
    auto_urls = _extract_black_urls(blacklist_auto_path)
    manual_urls = _extract_black_urls(blacklist_manual_path)
    combined = set(auto_urls + manual_urls)
    print(f"[INFO] 合并黑名单URL数: {len(combined)}")
    return combined

def load_corrections(corrections_path: str) -> dict:
    corrections = {}
    lines = read_txt(corrections_path)
    for line in lines:
        if not line or "," not in line:
            continue
        parts = line.split(',')
        correct_name = parts[0].strip()
        for wrong_name in parts[1:]:
            wrong_name = wrong_name.strip()
            if wrong_name:
                corrections[wrong_name] = correct_name
    print(f"[INFO] 加载频道纠错规则数: {len(corrections)}")
    return corrections

# ===================== 频道名称/URL处理 =====================
def clean_channel_name(name: str) -> str:
    if not name:
        return ""
    for item in REMOVAL_LIST:
        name = name.replace(item, "")
    name = name.replace("CCTV-", "CCTV")
    name = name.replace("CCTV0", "CCTV")
    name = name.replace("PLUS", "+")
    name = name.replace("NewTV-", "NewTV")
    name = name.replace("iHOT-", "iHOT")
    name = name.replace("NEW", "New")
    name = name.replace("New_", "New")
    return name.strip()

def clean_url(url: str) -> str:
    if not url:
        return ""
    dollar_idx = url.rfind('$')
    return url[:dollar_idx].strip() if dollar_idx != -1 else url.strip()

def correct_channel_name(name: str, corrections: dict) -> str:
    if not name or name not in corrections:
        return name
    return corrections[name] if corrections[name] != name else name

# ===================== 频道字典加载 =====================
def load_channel_dictionaries(main_dir: str, local_dir: str) -> tuple[dict, dict, list]:
    main_channels = {
        "央视频道": "央视频道.txt", "卫视频道": "卫视频道.txt", "体育频道": "体育频道.txt",
        "电影频道": "电影.txt", "电视剧频道": "电视剧.txt", "港澳台": "港澳台.txt",
        "国际台": "国际台.txt", "纪录片": "纪录片.txt", "戏曲频道": "戏曲频道.txt",
        "解说频道": "解说频道.txt", "春晚": "春晚.txt", "NewTV": "NewTV.txt",
        "iHOT": "iHOT.txt", "儿童频道": "儿童频道.txt", "综艺频道": "综艺频道.txt",
        "埋堆堆": "埋堆堆.txt", "音乐频道": "音乐频道.txt", "游戏频道": "游戏频道.txt",
        "收音机频道": "收音机频道.txt", "直播中国": "直播中国.txt", "MTV": "MTV.txt",
        "咪咕直播": "咪咕直播.txt"
    }
    local_channels = {
        "上海频道": "上海频道.txt", "浙江频道": "浙江频道.txt", "江苏频道": "江苏频道.txt",
        "广东频道": "广东频道.txt", "湖南频道": "湖南频道.txt", "安徽频道": "安徽频道.txt",
        "海南频道": "海南频道.txt", "内蒙频道": "内蒙频道.txt", "湖北频道": "湖北频道.txt",
        "辽宁频道": "辽宁频道.txt", "陕西频道": "陕西频道.txt", "山西频道": "山西频道.txt",
        "山东频道": "山东频道.txt", "云南频道": "云南频道.txt", "北京频道": "北京频道.txt",
        "重庆频道": "重庆频道.txt", "福建频道": "福建频道.txt", "甘肃频道": "甘肃频道.txt",
        "广西频道": "广西频道.txt", "贵州频道": "贵州频道.txt", "河北频道": "河北频道.txt",
        "河南频道": "河南频道.txt", "黑龙江频道": "黑龙江频道.txt", "吉林频道": "吉林频道.txt",
        "江西频道": "江西频道.txt", "宁夏频道": "宁夏频道.txt", "青海频道": "青海频道.txt",
        "四川频道": "四川频道.txt", "天津频道": "天津频道.txt", "新疆频道": "新疆频道.txt"
    }

    main_dict = {}
    for chn_type, filename in main_channels.items():
        file_path = os.path.join(main_dir, filename)
        lines = read_txt(file_path)
        main_dict[chn_type] = lines
        print(f"[INFO] 加载主频道 {chn_type}: {len(lines)} 个")

    local_dict = {}
    for chn_type, filename in local_channels.items():
        file_path = os.path.join(local_dir, filename)
        lines = read_txt(file_path)
        local_dict[chn_type] = lines
        print(f"[INFO] 加载地方台 {chn_type}: {len(lines)} 个")

    return main_dict, local_dict

# ===================== 频道分类核心 =====================
class ChannelClassifier:
    def __init__(self, main_dict: dict, local_dict: dict, blacklist: set):
        self.main_dict = main_dict
        self.local_dict = local_dict
        self.blacklist = blacklist
        self.channel_data = {}
        self.other_lines = []
        self.other_urls = set()
        self.all_urls = {}
        # === 全局单频道限流 新增：单频道计数字典 ===
        self.single_chn_count = {}  # key: 频道名(如CCTV1), value: 已添加源数量
        # 初始化分类数据
        for chn_type in list(main_dict.keys()) + list(local_dict.keys()):
            self.channel_data[chn_type] = []
            self.all_urls[chn_type] = set()

    def check_url_exist(self, chn_type: str, url: str) -> bool:
        if url in self.all_urls.get(chn_type, set()) or "127.0.0.1" in url:
            return True
        return False

    # === 全局单频道限流 ===
    def is_single_chn_limit(self, channel_name: str) -> bool:
        if SINGLE_CHANNEL_MAX_COUNT == -1:
            return False  # -1表示无限制
        # 获取该频道已添加数量，默认0
        current_count = self.single_chn_count.get(channel_name, 0)
        # 达到上限返回True，否则False
        if current_count >= SINGLE_CHANNEL_MAX_COUNT:
            return True
        return False

    def add_channel_line(self, chn_type: str, line: str, url: str):
        self.channel_data[chn_type].append(line)
        self.all_urls[chn_type].add(url)
        # === 全局单频道限流 新增：更新单频道计数 ===
        channel_name = line.split(',')[0].strip()
        self.single_chn_count[channel_name] = self.single_chn_count.get(channel_name, 0) + 1

    def add_other_line(self, line: str, url: str):
        if url not in self.other_urls and url not in self.blacklist:
            self.other_urls.add(url)
            self.other_lines.append(line)

    # === 全局单频道限流 ===
    def classify(self, channel_name: str, channel_url: str, line: str):
        # 先判断：黑名单/空URL → 跳过；单频道达上限 → 跳过
        if channel_url in self.blacklist or not channel_url or self.is_single_chn_limit(channel_name):
            return
        # 原有分类逻辑不变
        for chn_type, chn_names in self.main_dict.items():
            if channel_name in chn_names and not self.check_url_exist(chn_type, channel_url):
                self.add_channel_line(chn_type, line, channel_url)
                return
        for chn_type, chn_names in self.local_dict.items():
            if channel_name in chn_names and not self.check_url_exist(chn_type, channel_url):
                self.add_channel_line(chn_type, line, channel_url)
                return
        self.add_other_line(line, channel_url)

    def get_channel_data(self, chn_type: str) -> list:
        return self.channel_data.get(chn_type, [])

    def get_all_other(self) -> list:
        return self.other_lines

# ===================== 数据处理与生成 =====================
def is_m3u_content(text: str) -> bool:
    if not text:
        return False
    first_line = text.strip().splitlines()[0].strip()
    return first_line.startswith("#EXTM3U")

def convert_m3u_to_txt(m3u_content: str) -> list:
    lines = [line.strip() for line in m3u_content.split('\n') if line.strip()]
    txt_lines, channel_name = [], ""
    for line in lines:
        if line.startswith("#EXTM3U"):
            continue
        elif line.startswith("#EXTINF"):
            channel_name = line.split(',')[-1].strip()
        elif line.startswith(("http", "rtmp", "p3p")):
            if channel_name:
                txt_lines.append(f"{channel_name},{line}")
        elif "#genre#" not in line and "," in line and "://" in line:
            if re.match(r'^[^,]+,[^\s]+://[^\s]+$', line):
                txt_lines.append(line)
    return txt_lines

# ==========================================
# 资源获取器 (WebSocket/SocketIO)
# ==========================================
class RawResourceFetcher:
    def __init__(self):
        self.session_id = f"fetch_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        # 禁用日志以减少输出噪音
        self.sio = socketio.Client(logger=False, engineio_logger=False, reconnection=True, reconnection_attempts=3, reconnection_delay=1)
        self.raw_data_list = []  # 存储每个节点的原始文本
        self.task_finished = threading.Event()
        self.connected = threading.Event()
        self._setup_handlers()

    def _setup_handlers(self):
        """注册 WebSocket 监听事件"""
        # 根namespace事件
        @self.sio.on('connect')
        def on_root_connect():
            print(f"✅ 已连接至根服务器")

        @self.sio.on('connect_error')
        def on_root_connect_error(error):
            print(f"❌ 根服务器连接错误: {error}")

        @self.sio.on('disconnect')
        def on_root_disconnect():
            print("⚠️ 与根服务器断开连接")
        
        # /search namespace事件
        @self.sio.on('connect', namespace='/search')
        def on_connect():
            print(f"✅ 已连接到 /search namespace (Session: {self.session_id})")
            self.connected.set()
            self.sio.emit('join_session', {'session_id': self.session_id}, namespace='/search')

        @self.sio.on('disconnect', namespace='/search')
        def on_disconnect():
            print("⚠️ 与 /search namespace 断开连接")
            self.connected.clear()

        @self.sio.on('connect_error', namespace='/search')
        def on_connect_error(error):
            print(f"❌ /search namespace 连接错误: {error}")

        @self.sio.on('error', namespace='/search')
        def on_error(error):
            print(f"❌ /search namespace 服务器错误: {error}")

        @self.sio.on('result', namespace='/search')
        def on_result(data):
            # 每个节点的数据通常包含 channels 列表
            # 我们将 channels 转换回 '频道名,链接' 的原始文本格式
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
            
            # 达到 25 个节点提前结束
            if len(self.raw_data_list) >= 25:
                self.task_finished.set()

        @self.sio.on('finished', namespace='/search')
        def on_finished(data=None):
            print("🏁 后端扫描已全部完成")
            self.task_finished.set()

    def start_capture(self):
        """启动抓取流程（带重试机制）"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                retry_count += 1
                print(f"🔗 正在连接至: {BASE_URL} (尝试 {retry_count}/{max_retries})")
                
                # 单次连接到指定namespace，支持多transport
                self.sio.connect(
                    BASE_URL, 
                    namespaces=['/search'],
                    transports=['polling', 'websocket'],  # polling更稳定
                    wait_timeout=20,
                    headers={'User-Agent': USER_AGENT}
                )
                
                # 等待连接完全建立（最多15秒）
                if not self.connected.wait(timeout=15):
                    print("❌ 连接超时：无法建立namespace连接")
                    if self.sio.connected:
                        try:
                            self.sio.disconnect()
                        except:
                            pass
                    if retry_count < max_retries:
                        print(f"⏳ 等待 5 秒后重试...")
                        time.sleep(5)
                        # 重建sio实例
                        self.sio = socketio.Client(logger=False, engineio_logger=False, reconnection=True, reconnection_attempts=1, reconnection_delay=1)
                        self._setup_handlers()
                        continue
                    else:
                        print("⚠️ 达到最大重试次数，激活fallback模式")
                        self.task_finished.set()
                        return
                    self.task_finished.set()
                    return
                
                # 发起 HTTP 请求告知后端开始搜刮
                print("📤 发送搜刮指令...")
                resp = requests.post(
                    f"{BASE_URL}/api/search/start", 
                    json={"keyword": "", "mode": "multicast_list", "session_id": self.session_id},
                    timeout=30,
                    verify=False  # 在Actions等受信环境中禁用SSL验证
                )
                resp.raise_for_status()
                print("🚀 搜刮指令下达成功，正在接收原始数据...")
                return  # 成功，退出重试循环
                
            except socketio.exceptions.ConnectionError as e:
                error_msg = str(e)
                print(f"❌ SocketIO 连接失败 (第 {retry_count} 次)")
                print(f"   - 错误: {error_msg}")
                if self.sio.connected:
                    try:
                        self.sio.disconnect()
                    except:
                        pass
                if retry_count < max_retries:
                    print(f"⏳ 等待 5 秒后重试...")
                    time.sleep(5)
                    # 重建sio实例
                    self.sio = socketio.Client(logger=False, engineio_logger=False, reconnection=True, reconnection_attempts=1, reconnection_delay=1)
                    self._setup_handlers()
                else:
                    print(f"💡 已达最大重试次数，SocketIO连接失败")
                    print(f"   - 将继续处理已有本地数据...")
                    self.task_finished.set()
            except requests.exceptions.RequestException as e:
                print(f"❌ HTTP 请求失败 (第 {retry_count} 次): {e}")
                if self.sio.connected:
                    try:
                        self.sio.disconnect()
                    except:
                        pass
                if retry_count < max_retries:
                    print(f"⏳ 等待 5 秒后重试...")
                    time.sleep(5)
                else:
                    self.task_finished.set()
                    
            except Exception as e:
                print(f"❌ 启动失败 (第 {retry_count} 次): {type(e).__name__}: {e}")
                if self.sio.connected:
                    try:
                        self.sio.disconnect()
                    except:
                        pass
                import traceback
                traceback.print_exc()
                if retry_count < max_retries:
                    print(f"⏳ 等待 5 秒后重试...")
                    time.sleep(5)
                else:
                    self.task_finished.set()

def save_raw_file(data_list, filename):
    """将收集到的列表直接合并写入文件"""
    if not data_list:
        print("📭 没有收集到任何数据，文件未生成。")
        return

    # 直接用换行符连接所有节点的原始文本
    final_content = "\n".join(data_list)
    # 追加到文件末尾，保持原有内容不变
    if os.path.exists(filename):
        with open(filename, 'a', encoding='utf-8') as f:
            f.write("\n" + final_content)
    else:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(final_content)
    
    print(f"\n✨ 聚合完成！")
    print(f"📂 原始 TXT 已保存至: {os.path.abspath(filename)}")
    print(f"💡 现在你可以将此文件交给 pan8664716/IPTV 项目进行精细化分类了。")

def process_single_line(line: str, classifier: ChannelClassifier, corrections: dict):
    if "#genre#" in line or "#EXTINF:" in line or "," not in line or "://" not in line:
        return
    try:
        channel_name, channel_address = line.split(',', 1)
    except ValueError:
        return
    # 频道名标准化（简繁转换→清理→纠错）
    channel_name = traditional_to_simplified(channel_name)
    channel_name = clean_channel_name(channel_name)
    channel_name = correct_channel_name(channel_name, corrections)
    channel_address = clean_url(channel_address)
    new_line = f"{channel_name},{channel_address}"
    # 传入标准化后的频道名做分类（保证计数统一）
    classifier.classify(channel_name, channel_address, new_line)

def sort_channel_data(channel_data: list, chn_type: str, cfg_list: list) -> list:
    if not channel_data:
        return channel_data
    
    if chn_type in ORDERED_CHANNEL_TYPES:
        cfg_index_map = {cfg_name: idx for idx, cfg_name in enumerate(cfg_list)}
        def _ordered_key(line):
            name = line.split(',')[0] if ',' in line else ""
            return cfg_index_map.get(name, len(cfg_list))
        return sorted(channel_data, key=_ordered_key)
    else:
        def _dict_key(line):
            name = line.split(',')[0] if ',' in line else ""
            pure_name = re.sub(r'[^\w\u4e00-\u9fff]', '', name)
            return pure_name if pure_name else name
        return sorted(channel_data, key=_dict_key)

def generate_live_text(classifier: ChannelClassifier, main_dict: dict) -> tuple[list, list]:
    bj_time = datetime.now(timezone.utc) + timedelta(hours=8)
    formatted_time = bj_time.strftime("%Y%m%d %H:%M")
    version = f"{formatted_time},http://ottrrs.hl.chinamobile.com/PLTV/88888888/224/3221226537/index.m3u8"
    header = ["更新时间,#genre#", version, '\n']

    # 生成lite精简版
    lite_lines = header.copy()
    lite_sort_types = [
        "央视频道", "卫视频道", "港澳台", "电影频道", "电视剧频道", "综艺频道",
        "NewTV", "iHOT", "体育频道", "咪咕直播", "埋堆堆", "音乐频道", "游戏频道", "解说频道"
    ]
    for chn_type in lite_sort_types:
        chn_data = classifier.get_channel_data(chn_type)
        sorted_data = sort_channel_data(chn_data, chn_type, main_dict[chn_type])
        lite_lines += [f"{chn_type},#genre#"] + sorted_data + ['\n']
    lite_lines = lite_lines[:-1] if lite_lines and lite_lines[-1] == '\n' else lite_lines

    # 补全剩余生成full版
    full_lines = lite_lines.copy() + ['\n']
    full_other_types = [
        "儿童频道", "国际台", "纪录片", "戏曲频道", "上海频道", "湖南频道",
        "湖北频道", "广东频道", "浙江频道", "山东频道", "江苏频道", "安徽频道",
        "海南频道", "内蒙频道", "辽宁频道", "陕西频道", "山西频道", "云南频道",
        "北京频道", "重庆频道", "福建频道", "甘肃频道", "广西频道", "贵州频道",
        "河北频道", "河南频道", "黑龙江频道", "吉林频道", "江西频道", "宁夏频道",
        "青海频道", "四川频道", "天津频道", "新疆频道", "春晚", "直播中国", "MTV", "收音机频道"
    ]
    for chn_type in full_other_types:
        chn_data = classifier.get_channel_data(chn_type)
        sort_list = main_dict.get(chn_type, []) or classifier.local_dict.get(chn_type, [])
        sorted_data = sort_channel_data(chn_data, chn_type, sort_list)
        full_lines += [f"{chn_type},#genre#"] + sorted_data + ['\n']
    full_lines = full_lines[:-1] if full_lines and full_lines[-1] == '\n' else full_lines

    return full_lines, lite_lines

def make_m3u(txt_file: str, m3u_file: str, tvg_url: str, logo_tpl: str):
    try:
        if not os.path.exists(txt_file):
            print(f"[ERROR] M3U源文件不存在: {txt_file}")
            return
        m3u_content = f"#EXTM3U x-tvg-url=\"{tvg_url}\"\n"
        lines = read_txt(txt_file, strip=True, skip_empty=True)
        group_name = ""
        for line in lines:
            if "," not in line:
                continue
            parts = line.split(',', 1)
            if len(parts) != 2:
                continue
            if "#genre#" in parts[1]:
                group_name = parts[0].strip()
                continue
            channel_name, channel_url = parts[0].strip(), parts[1].strip()
            if not channel_url or "://" not in channel_url:
                continue
            logo_url = logo_tpl.format(channel_name)
            m3u_content += (
                f"#EXTINF:-1  tvg-name=\"{channel_name}\" tvg-logo=\"{logo_url}\"  group-title=\"{group_name}\",{channel_name}\n"
                f"{channel_url}\n"
            )
        write_txt(m3u_file, m3u_content)
    except Exception as e:
        print(f"[ERROR] 生成M3U失败 {m3u_file}: {str(e)}")

# ===================== 主函数执行 =====================
if __name__ == "__main__":
    timestart = datetime.now()
    print(f"[START] 程序开始执行: {timestart.strftime('%Y%m%d %H:%M:%S')}")
    dirs = get_project_dirs()
    
    blacklist = load_blacklist(dirs["blacklist_auto"], dirs["blacklist_manual"])
    corrections = load_corrections(dirs["corrections_name"])
    main_dict, local_dict = load_channel_dictionaries(dirs["main_channel"], dirs["local_channel"])
    classifier = ChannelClassifier(main_dict, local_dict, blacklist)

    raw_output_path = dirs["raw_merged_resources"]
    # 如果之前存在的原始文件过旧（超过24小时），则删除它以避免使用过时数据
    if os.path.exists(raw_output_path):
        os.remove(raw_output_path)

    # 先从 http://skyr.wuaze.com/mg.txt 获取所有资源，保存到 assets/whitelist-blacklist/raw_merged_resources.txt，后续处理时优先使用这个文件
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get("http://skyr.wuaze.com/mg.txt", headers=headers, timeout=URL_FETCH_TIMEOUT)
        if response.status_code == 200:
            # 自动识别编码并打印全部内容
            response.encoding = response.apparent_encoding
            save_raw_file([response.text], raw_output_path)
        else:
            print(f"⚠️ 获取 mg.txt 失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"⚠️ 获取 mg.txt 失败: {e}")




    print(f"[PROCESS] 处理 SocketIO 聚合源（优先处理）")
    # 启动 SocketIO 资源抓取
    fetcher = RawResourceFetcher()
    fetcher.start_capture()
    
    # 等待直到：抓够25个节点 OR 后端扫描完 OR 达到7.5分钟超时
    fetcher.task_finished.wait(timeout=450)
    
    # 安全断开连接
    try:
        if fetcher.sio.connected:
            fetcher.sio.disconnect()
    except Exception as e:
        print(f"⚠️ 断开连接时出错: {e}")
    
    # 保存原始文件到黑白名单目录
    save_raw_file(fetcher.raw_data_list[:25], raw_output_path)
    
    # 处理原始文件中的内容 - 最优先处理
    if os.path.exists(raw_output_path):
        classifier.other_lines.append(f"SocketIO聚合源,#genre#")
        raw_lines = read_txt(raw_output_path)
        for line in raw_lines:
            process_single_line(line, classifier, corrections)
        classifier.other_lines.append('\n')

    print(f"[PROCESS] 处理手动白名单")
    whitelist_manual = read_txt(dirs["whitelist_manual"])
    classifier.other_lines.append("白名单,#genre#")
    for line in whitelist_manual:
        process_single_line(line, classifier, corrections)

    print(f"[PROCESS] 处理自动白名单（响应时间<{RESPONSE_TIME_THRESHOLD}ms）")
    whitelist_respotime = read_txt(dirs["whitelist_respotime"])
    classifier.other_lines.append("白名单测速,#genre#")
    for line in whitelist_respotime:
        if "#genre#" in line or "," not in line or "://" not in line:
            continue
        parts = line.split(",")
        try:
            # 移除 'ms' 并去除空格
            time_str = parts[0].replace('ms', '').strip()
            # 转换为浮点数，空字符串返回无穷大
            resp_time = float(time_str) if time_str else float('inf')
        except (ValueError, IndexError, AttributeError):
            resp_time = float('inf')
            
        if resp_time < RESPONSE_TIME_THRESHOLD:
            process_single_line(",".join(parts[1:]), classifier, corrections)

    print(f"[GENERATE] 生成live.txt/live_lite.txt")
    live_full, live_lite = generate_live_text(classifier, main_dict)
    live_full_path = os.path.join(dirs["root"], "live.txt")
    live_lite_path = os.path.join(dirs["root"], "live_lite.txt")
    others_path = os.path.join(dirs["root"], "others.txt")
    write_txt(live_full_path, live_full)
    write_txt(live_lite_path, live_lite)
    write_txt(others_path, classifier.other_lines)

    print(f"[GENERATE] 生成M3U文件")
    make_m3u(live_full_path, os.path.join(dirs["root"], "live.m3u"), TVG_URL, LOGO_URL_TPL)
    make_m3u(live_lite_path, os.path.join(dirs["root"], "live_lite.m3u"), TVG_URL, LOGO_URL_TPL)

    timeend = datetime.now()
    elapsed = timeend - timestart
    minutes, seconds = int(elapsed.total_seconds() // 60), int(elapsed.total_seconds() % 60)
    blacklist_count = len(blacklist)
    live_count = len(live_full)
    others_count = len(classifier.other_lines)
    
    print("=" * 60)
    print(f"[END] 程序执行完成: {timeend.strftime('%Y%m%d %H:%M:%S')}")
    print(f"[STAT] 执行时间: {minutes} 分 {seconds} 秒")
    print(f"[STAT] live.txt行数: {live_count}")
    print(f"[STAT] others.txt行数: {others_count}")
    print("=" * 60)







