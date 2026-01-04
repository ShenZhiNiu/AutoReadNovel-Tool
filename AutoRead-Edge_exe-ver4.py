# ===================== 基础库导入 =====================
import os                      # 用于文件路径、目录操作
import json                    # 用于配置文件的 JSON 读写
import time                    # 用于 sleep、计时
import threading               # 用于后台线程（防止 GUI 卡死）
import tkinter as tk           # Tkinter GUI 主库
from tkinter import ttk, messagebox, filedialog  # Tkinter 常用组件

# ===================== Selenium 相关 =====================
from selenium import webdriver                     # 浏览器驱动核心
from selenium.webdriver.common.keys import Keys    # 键盘按键（如 PAGE_DOWN）
from selenium.webdriver import ActionChains        # 动作链（发送键盘/鼠标事件）
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import WebDriverException  # Selenium 异常类


# ===================== 默认配置 =====================
DEFAULT_URL = "https://www.baidu.com"   # 默认打开的网址
DEFAULT_READ_TIME = 5.0                # 默认翻页间隔（秒）
MIN_READ_TIME = 0.5                    # 最小允许翻页间隔
MAX_READ_TIME = 60.0                   # 最大允许翻页间隔

HEIGHT_CHANGE_THRESHOLD = 300           # 页面高度变化阈值（用于判断换章节）
BOTTOM_STABLE_COUNT = 3                 # 连续检测到“不能再下滚”的次数

FILE_NAME = "AutoNovelReader"            # 网页profile文件夹名称，仅适用windows


# ===================== profile功能相关函数 =====================
def get_app_data_dir():
    """ 返回本工具存储profile的文件目录路径 """
    base = os.getenv("LOCALAPPDATA")    # 获取 Windows 本地应用数据目录
    path = os.path.join(base, FILE_NAME) # 拼接程序专属目录
    os.makedirs(path, exist_ok=True)    # 目录不存在则创建
    return path                         # 返回目录路径

def load_config():
    # 如果配置文件不存在，返回空配置
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        # 读取 JSON 配置文件
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        # 读取失败时返回空配置
        return {}

def save_config(cfg):
    try:
        # 将配置写回 JSON 文件
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except:
        # 写入失败直接忽略
        pass


CONFIG_PATH = os.path.join(get_app_data_dir(), "config.json")  # 配置文件路径
# 目前config的功能为：记录驱动所在路径，具体是指driver.exe所在位置。因此edge和chrome驱动要放一起
config = load_config()                  # 加载配置
last_website = config.get("last_website")
if last_website:
    DEFAULT_URL = last_website
driver_dir = config.get("driver_dir")   # 读取浏览器驱动目录


# ===================== 全局状态 =====================
driver = None           # Selenium WebDriver 实例
is_pause = True         # 是否暂停滚动
is_exit = False         # 是否退出程序
read_time = DEFAULT_READ_TIME  # 当前阅读间隔

last_url = None                 # 上一次页面 URL
last_page_height = None         # 上一次页面高度
last_scroll_y = -1              # 上一次滚动位置
bottom_stable_times = 0         # 底部稳定计数器


# ===================== 工具函数 =====================
def get_page_height():
    # 获取当前页面总高度
    return driver.execute_script("return document.body.scrollHeight")

def get_scroll_y():
    # 获取当前页面滚动的 Y 坐标
    return driver.execute_script("return window.pageYOffset")

def reset_scroll_state():
    """ 重置滚动状态： - 回到页面顶部 - 清空滚动历史记录 """
    global last_scroll_y, bottom_stable_times
    last_scroll_y = -1
    bottom_stable_times = 0
    driver.execute_script("window.scrollTo(0, 0)")  # 回到页面顶部

def sleep_with_pause(seconds):
    """ 用来实现滚动间隔，且可以随时暂时或退出
    而且不同于普通的改变速度后，要等到下次滚动生效
    但为了更稳定，仅在间隔改变较大时才会立刻生效
     """
    global read_time
    copy_read_time = read_time

    # 每0.1秒检查一次工具状态，暂停时无限循环，结束时0.1秒后退出
    refresh_time = 0.1
    passed_time = 0
    while passed_time < copy_read_time:
        if is_pause:         # 如果暂停，则等待
            time.sleep(refresh_time)
            continue
        if is_exit:          # 检测是否退出程序
            return False

        if abs(read_time - copy_read_time) > 3:
            copy_read_time = read_time
        time.sleep(refresh_time)     # 正常等待
        passed_time += refresh_time
    return True

def get_driver_path(browser):
    # 根据浏览器类型返回对应驱动路径
    if not driver_dir:
        return None

    if browser == "Edge":
        path = os.path.join(driver_dir, "msedgedriver.exe")
    else:
        path = os.path.join(driver_dir, "chromedriver.exe")

    return path if os.path.exists(path) else None


# ===================== 浏览器 Profile 目录 =====================
def get_profile_dir(browser):
    """
    返回浏览器用户数据目录（用于保存登录状态）
    """
    base = os.getenv("LOCALAPPDATA")
    profile_root = os.path.join(base, FILE_NAME, "profiles", browser)
    os.makedirs(profile_root, exist_ok=True)
    return profile_root

def clear_browser_cache(driver):
    """
    清除浏览器 HTTP 缓存，不影响 Cookie / 登录态
    """
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})
    except Exception as e:
        print("清缓存失败:", e)


# ===================== 自动阅读线程 =====================
def start_read_novel():
    # 声明将要修改的全局变量（线程中必须显式声明）
    # driver：Selenium 浏览器实例, last_url：用于判断是否跳转到新章节, last_page_height：用于判断页面内容是否发生明显变化
    global driver, last_url, last_page_height
    # last_scroll_y：上一次滚动的 Y 坐标 bottom_stable_times：连续检测到“滚动无变化”的次数 is_pause：当前是否处于暂停状态
    global last_scroll_y, bottom_stable_times, is_pause
    # ===================== 读取 GUI 输入 =====================
    # 从 GUI 输入框中获取用户输入的网址，并去除首尾空白
    # 这里只做 strip，不做合法性校验（校验在 on_start 中已完成）
    url = entry_url.get().strip()
    # 从下拉框中获取当前选择的浏览器类型（Edge / Chrome）
    browser = browser_var.get()
    # ===================== 浏览器驱动路径校验 =====================
    # 根据浏览器类型，拼出对应的驱动可执行文件路径
    driver_path = get_driver_path(browser)
    # 如果没有找到驱动（未配置或文件不存在）
    if not driver_path:
        # 弹出错误提示框，阻止继续执行
        messagebox.showerror(
            "驱动未配置",
            "未找到对应浏览器驱动"
        )
        return  # 直接结束线程函数

    # ===================== 启动浏览器 =====================
    try:
        # --------- Edge 浏览器启动流程 ---------
        if browser == "Edge":
            # 获取 Edge 专属的用户数据目录
            # 作用：保存登录状态、cookie、阅读进度等
            profile_dir = get_profile_dir("Edge")
            # 创建 Edge 启动参数对象
            options = EdgeOptions()
            # 浏览器启动后最大化窗口（避免可视区域变化）
            options.add_argument("--start-maximized")
            # 指定用户数据目录（非常关键，否则每次都是全新浏览器）
            options.add_argument(f"--user-data-dir={profile_dir}")
            # 使用 Default profile（与真实 Edge 浏览器一致）
            options.add_argument("--profile-directory=Default")

            # 创建 Edge 浏览器实例 service 指定驱动路径 options 指定启动参数
            driver = webdriver.Edge(
                service=EdgeService(driver_path),
                options=options
            )
        # --------- Chrome 浏览器启动流程（与 Edge 基本一致） ---------
        else:
            profile_dir = get_profile_dir("Chrome")
            options = ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument(f"--user-data-dir={profile_dir}")
            options.add_argument("--profile-directory=Default")

            driver = webdriver.Chrome(
                service=ChromeService(driver_path),
                options=options
            )

    # 捕获所有浏览器启动异常（驱动版本不匹配、权限问题等）
    except Exception as e:
        messagebox.showerror("浏览器启动失败",str(e))
        return

    # 缓存清除
    #clear_browser_cache(driver)
    # ===================== 页面初始化 =====================
    # 打开用户指定的小说章节页面
    driver.get(url)
    # 创建动作链对象 后续所有 PageDown 操作都通过它来发送
    action = ActionChains(driver)
    # 记录当前页面 URL 用于后续判断是否跳转到了新章节
    last_url = driver.current_url
    # 获取并记录当前页面的总高度 用于检测“章节切换 / 内容刷新”
    last_page_height = get_page_height()
    # 重置滚动状态： - 回到页面顶部 - 清空滚动历史记录
    reset_scroll_state()
    # 启动后默认先暂停 等用户点击“继续”或检测到新章节
    is_pause = False
    update_state("滚动中")
    # ===================== 主循环：自动阅读核心 =====================
    while not is_exit:
        if not driver:
            time.sleep(0.2)
            continue
        # try:
        #     current_url = driver.current_url
        #     current_height = get_page_height()
        # except WebDriverException:
        #     is_pause = True
        #     break
        # 当网址变化或页面高度剧变，进入滚动态并回到顶部
        # if (current_url != last_url or
        #     abs(current_height - last_page_height) > HEIGHT_CHANGE_THRESHOLD
        # ):
        #     last_url = current_url
        #     last_page_height = current_height
        #     reset_scroll_state()
        #     is_pause = False
        #     update_state("滚动中")

        # 如果当前处于暂停状态 不滚动、不计时，仅短暂 sleep 防止 CPU 占满
        if is_pause:
            time.sleep(0.1)
            continue
        # 可被“暂停 / 退出”打断的等待 read_time 代表“模拟人类阅读时间”
        if not sleep_with_pause(read_time):
            break  # 如果返回 False，说明程序正在退出

        try:
            # 模拟用户按下 PageDown 键 比直接 JS 滚动更像真实用户行为
            action.send_keys(Keys.PAGE_DOWN).perform()
            # 清空动作链缓存，防止动作堆积
            action.reset_actions()
            # 获取当前页面的滚动位置
            current_scroll = get_scroll_y()
        except WebDriverException:
            messagebox.showerror('error', 'run PageDown action fail')
            is_pause = True
            break
        # ===================== 底部检测逻辑 =====================
        # 如果滚动位置和上一次完全一样 说明已经滚不动了（到页面底部）
        if current_scroll == last_scroll_y:
            bottom_stable_times += 1  # 累加“无变化”次数
            # 如果连续多次检测到无法滚动
            if bottom_stable_times >= BOTTOM_STABLE_COUNT:
                is_pause = True
                update_state("暂停（已到页面底部）")
        else:
            # 只要还能滚动，就清空底部计数
            bottom_stable_times = 0

        # 更新上一次滚动位置
        last_scroll_y = current_scroll

    # ===================== 循环while not is_exit结束 =====================
    # 如果线程结束且浏览器仍然存在
    if driver and is_exit is True:
        driver.quit()  # 关闭浏览器，释放系统资源
    elif driver:
        is_pause = True


# ===================== GUI =====================
root = tk.Tk()
root.title("网页自动滚动工具")
root.geometry("720x460") # 界面初始尺寸像素值
root.resizable(False, False) # 是否可调节宽高

def update_state(text):
    """
    更新界面的运行状态提示文本，用root.after(0)是tkinter异步刷新技巧，避免循环中更新界面导致软件卡死
    :param text: 要显示的状态文字，如：未开始、滚动中、已停止、网址错误等
    """
    root.after(0, lambda: lbl_state.config(text=f"状态：{text}"))

def update_speed_label():
    """更新界面的当前滚动间隔（速度）提示文本，保留1位小数"""
    lbl_speed.config(text=f"当前间隔：{read_time:.1f}s")

def choose_driver_dir():
    global driver_dir                 # 使用全局变量 driver_dir
    path = filedialog.askdirectory(    # 弹出文件夹选择对话框
        title="选择浏览器驱动所在文件夹"
    )
    if not path:                       # 如果用户取消选择
        return                         # 直接返回，不做任何事

    driver_dir = path                  # 保存用户选择的路径
    config["driver_dir"] = driver_dir  # 写入配置字典
    #save_config(config)                # 保存到 config.json
    lbl_driver.config(                 # 更新界面上的文字提示
        text=f"驱动目录：{driver_dir}"
    )

# ===================== 界面控件-配置区 =====================
# 1. 小说章节网址 输入区域
ttk.Label(root, text="网址：").place(x=20, y=30)
# 创建网址输入框，宽度80字符，足够容纳任意网址
entry_url = tk.Entry(root, width=80)
entry_url.place(x=20, y=60) # 放到窗口的（x,y）位置
# 输入框默认填充预设的网址
entry_url.insert(0, DEFAULT_URL)

# 2. 阅读间隔(滚动速度) 输入区域
ttk.Label(root, text="设定滚动间隔（秒）：").place(x=20, y=100)
# 创建间隔输入框，宽度10字符，仅需输入数字即可
entry_speed = tk.Entry(root, width=10)
entry_speed.place(x=160, y=100)
# 输入框默认填充预设的间隔值（数字转字符串，Entry只支持字符串）
entry_speed.insert(0, str(DEFAULT_READ_TIME))

# 3. 浏览器选择 下拉框区域
ttk.Label(root, text="浏览器：").place(x=300, y=100)
# 创建字符串变量，绑定下拉框，设置默认选中Edge浏览器
browser_var = tk.StringVar(value="Edge")
# 创建下拉选择框，仅允许选择，禁止手动输入，避免用户填错
ttk.Combobox(
    root,
    textvariable=browser_var,  # 选项的值会赋值给该变量
    values=["Edge", "Chrome"],  # 可选浏览器列表
    state="readonly",           # 只读状态，只能选择不能输入
    width=10
).place(x=360, y=100)

ttk.Button(root, text="选择驱动目录", command=choose_driver_dir).place(x=20, y=140)
# tk.Label相比ttk.label支持更多功能，如改字体颜色
lbl_driver = tk.Label(
    root,
    text=f"驱动目录：{driver_dir if driver_dir else '未设置'}",
    fg="blue"
)
lbl_driver.place(x=140, y=145)

from urllib.parse import urlparse, urlunparse
def normalize_url(raw):
    # 1. 空值/纯空格校验：None、空字符串、全空白字符串直接返回None
    if not raw or not isinstance(raw, str) or raw.strip() == "":
        return None
    # 2. 清洗URL：去除首尾所有空白字符（空格、制表符、全角空格等）
    clean_url = raw.strip()
    # 3. 统一协议处理：补全协议头+自动去重重复协议+协议转小写
    clean_url = clean_url.lower()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    # 4. 使用urlparse解析URL，拆分各部分（scheme/协议, netloc/域名, path/路径等）
    parsed = urlparse(clean_url)
    # 5. 核心校验：域名(netloc)为空则为无效URL，返回None
    if not parsed.netloc:
        return None
    # 6. 标准化处理：移除默认端口（http:80、https:443）
    netloc = parsed.netloc
    if parsed.scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif parsed.scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    # 7. 重组URL各部分，保持path/query/fragment不变，只标准化协议和域名
    normalized_parts = (
        parsed.scheme,  # 协议（已小写）
        netloc,  # 域名（已去默认端口）
        parsed.path,  # 路径
        parsed.params,  # 扩展参数
        parsed.query,  # 查询参数
        parsed.fragment  # 锚点
    )
    normalized_url = urlunparse(normalized_parts)
    # 8. 终极标准化：移除URL末尾的斜杠（核心刚需）
    if normalized_url.endswith("/"):
        normalized_url = normalized_url[:-1]
    return normalized_url

# ===== 启动按钮逻辑 =====
def on_start():
    global read_time, is_exit, is_pause

    raw_url = entry_url.get()           # 从输入框获取原始 URL
    url = normalize_url(raw_url)        # 标准化 URL
    if not url:                         # URL 校验失败
        messagebox.showerror(
            "网址错误",
            "请输入完整网址"
        )
        return
    config["last_website"] = url
    try:
        read_time = float(entry_speed.get())  # 读取翻页间隔
    except:
        read_time = DEFAULT_READ_TIME         # 转换失败使用默认值
    # 限制翻页速度范围，即min<read<max
    read_time = max(MIN_READ_TIME,
        min(MAX_READ_TIME, read_time) )
    update_speed_label()                # 更新界面显示
    is_exit = False                     # 重置退出标志
    is_pause = True                     # 初始状态为暂停
    # 启动后台线程（防止 GUI 卡死）
    threading.Thread(
        target=start_read_novel,
        daemon=True
    ).start()

# ===== 控制区 =====
def toggle_pause():
    """ 对暂停和滚动的切换 """
    global is_pause
    if not driver:
        messagebox.showinfo("提示", "浏览器未启动")
        return
    is_pause = not is_pause
    update_state("暂停" if is_pause else "滚动中")

def speed_set():
    global read_time
    read_time = max(MIN_READ_TIME, min(MAX_READ_TIME, float(entry_speed.get()) )
                    )
    update_speed_label()

def speed_up():
    """ 翻滚加速 """
    global read_time
    read_time = max(MIN_READ_TIME, read_time - 1.0)
    update_speed_label()

def speed_down():
    """ 翻滚减速 """
    global read_time
    read_time = min(MAX_READ_TIME, read_time + 1.0)
    update_speed_label()

def clear_cache_manually():
    if not driver:
        messagebox.showinfo("提示", "浏览器尚未启动")
        return
    clear_browser_cache(driver)


def close_browser_only():
    global driver, is_pause
    if not driver:
        messagebox.showinfo("提示", "当前没有打开的浏览器")
        return
    try:
        driver.quit()
    except:
        pass
    driver = None
    is_pause = True
    update_state("浏览器已关闭（暂停）")

def exit_program():
    global is_exit
    is_exit = True
    try:
        if driver:
            driver.quit()
    except:
        pass
    save_config(config)
    root.destroy()



tk.Button(
    root, text="🚀 启动自动阅读",
    width=30, bg="#009688", fg="white",
    command=on_start
).place(x=200, y=180)
tk.Button(root, text="⏯ 暂停/继续", width=12, command=toggle_pause).place(x=100, y=260)
tk.Button(root, text="⏩ 更快翻页", width=10, command=speed_up).place(x=230, y=260)
tk.Button(root, text="⏪ 更慢翻页", width=10, command=speed_down).place(x=330, y=260)
tk.Button(root, text="🌐 关闭网页", width=12, bg="#f0ad4e", fg="white",
          command=close_browser_only).place(x=440, y=260)
tk.Button(root, text="❌ 结束程序", width=10, bg="#d9534f", fg="white",
          command=exit_program).place(x=580, y=260)
tk.Button(root,text="🧹 清除缓存", width=10, command=clear_cache_manually).place(x=580, y=300)
tk.Button(root, text="速度设定", width=10, command=speed_set).place(x=100, y=300)


lbl_speed = tk.Label(
    root,
    text=f"当前间隔：{read_time:.1f}s"
)
lbl_speed.place(x=320, y=320)
lbl_state = tk.Label(
    root,
    text="状态：未启动",
    font=("微软雅黑", 10, "bold")
)
lbl_state.place(x=280, y=350)

root.mainloop()
