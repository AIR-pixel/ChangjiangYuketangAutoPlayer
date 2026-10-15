'''
长江雨课堂 - 视频自动播放器

长江雨课堂（changjiang.yuketang.cn）专用：无头后台运行、自动切换下一集、真实 2 倍速。

基础代码来自 https://github.com/LetMeFly666/YuketangAutoPlayer
上游作者：LetMeFly, Guo-Chenxu, Crsuh2er0, 420xincheng, tkzzzzzz6
本项目按 LGPL-2.1 授权（见 LICENSE）。实现细节与实测记录见 docs/技术细节.md
'''
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException
from typing import List
from time import sleep, monotonic, strftime
import os
import sys

import firstrun
import refresh_cookie

# 必须在任何 print 之前：重定向输出时 Windows 会退回 GBK，日志里的 `✓` 那种字符
# 会把程序打死在启动阶段；顺带把 stdout 设成逐行刷出（打包后的 exe 上实测踩到过，
# 见 docs/技术细节.md 7）
refresh_cookie.setup_output()

PLACEHOLDER_MARK = '在此填写'  # 旧版模板里的占位符；留作识别"从没填过"的老配置文件


def ts() -> str:
    """日志时间戳。挂后台无人看守时，出事的时间点就是唯一的线索。"""
    return strftime('%H:%M:%S')


def pause_exit(code: int = 0):
    """退出前停一下。

    双击 exe 时控制台会随进程一起关掉，不停留就是"闪一下就没了"、用户看不到报错；
    但输出被重定向、压根没有控制台时不能傻等，否则会挂在后台不退出。
    """
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input('按回车键退出...')
    except Exception:
        pass  # 控制台已关闭之类的情况，直接退
    sys.exit(code)


def config_path() -> str:
    """config.ini 的位置。

    优先程序自己所在目录 —— exe 模式下就是 exe 旁边，冻结路径的问题由
    refresh_cookie.app_dir() 处理；那里没有、而当前工作目录有，则沿用工作目录
    那份，兼容以前 `python main.py` 的用法。两边都没有就返回程序目录，让向导去建。
    """
    beside = refresh_cookie.config_path()
    if os.path.exists(beside):
        return beside
    legacy = os.path.join(os.getcwd(), 'config.ini')
    return legacy if os.path.exists(legacy) else beside


def _cfg_text(cfg, key: str) -> str:
    try:
        return (cfg.get('Settings', key, fallback='') or '').strip()
    except Exception:
        return ''


def needs_setup(cfg) -> bool:
    """配置还缺东西 -> 需要走一遍首次配置向导。"""
    url, cookie = _cfg_text(cfg, 'course_url'), _cfg_text(cfg, 'cookie')
    return (not url.startswith('http') or not cookie
            or PLACEHOLDER_MARK in url or PLACEHOLDER_MARK in cookie)


def load_config(path: str):
    """读配置；缺 course_url / cookie 就先跑一遍首次配置向导。

    用户那边的动作是"双击 exe"，不是"先读文档再手填文件"，所以这一步必须自动完成。
    """
    if needs_setup(refresh_cookie.read_config(path)):
        if not firstrun.ensure_ready(path):
            print('\n配置没有完成，已退出。')
            pause_exit(1)

    cfg = refresh_cookie.read_config(path)
    if not cfg.has_section('Settings'):
        print(f'\n配置文件缺少 [Settings] 段，可能已损坏: {path}')
        pause_exit(1)
    print(f'配置就绪: {path}')
    return cfg


# 加载配置
print('='*50)
print('长江雨课堂 - 视频自动播放器')
print('='*50)

CONFIG_PATH = config_path()
config = load_config(CONFIG_PATH)

# 读取配置项
try:
    # headless 缺省为 true：挂后台是主要用法，也和 README / config.ini.example 写的一致
    IF_HEADLESS = config.getboolean('Settings', 'headless', fallback=True)
    BROWSER = config.get('Settings', 'browser', fallback='auto').strip().lower()
    UI_MODE = config.get('Settings', 'ui', fallback='auto').strip().lower()
    COURSE_URL = _cfg_text(config, 'course_url')
    COOKIE = _cfg_text(config, 'cookie')
    PLAYBACK_SPEED = config.getfloat('Settings', 'speed', fallback=2.0)
    IMPLICITLY_WAIT = config.getint('Settings', 'implicitly_wait', fallback=10)
except Exception as e:
    print(f'\n配置文件格式错误: {e}')
    pause_exit(1)

# 走到这里还缺东西，说明向导被人中途掐掉了，或者文件被手改坏了
if needs_setup(config):
    print(f'\n错误: 配置里缺少可用的 course_url / cookie: {CONFIG_PATH}')
    print('重新运行本程序会再走一遍配置向导；也可以参考 config.ini.example 手动填写。')
    pause_exit(1)

# 倍速限幅：太低没意义，太高播放器会直接拒
PLAYBACK_SPEED = min(4.0, max(0.5, PLAYBACK_SPEED))

# 扫码登录最多等多久。无头模式下窗口不可见、根本没法扫，所以到时如实报错退出，
# 而不是无界地挂在那里（挂后台时"既不报错也不退出"比直接失败更难排查）。
QR_LOGIN_TIMEOUT = 300

# 页面加载上限。配合 create_driver 里的 page_load_strategy='eager'，正常情况几秒就返回，
# 真挂满这个数说明站点或网络确实出事了。设了上限 `driver.get` 才会抛 Selenium 的
# TimeoutException；不设的话会一路挂到 urllib3 的 120 秒读超时，抛出来的是 urllib3 的
# 异常，上层没法按"这一轮出错了"处理（2026-10-15 实测遇到过一次）。
PAGE_LOAD_TIMEOUT = 90

# 视频页"<video> 元素出现"的等待上限。见下方 WebDriverWait 处的说明：
# page_load_strategy='eager' 之后这段等待要负责播放器渲染的时间。
VIDEO_READY_TIMEOUT = 20

# selenium 客户端会读取 HTTP(S)_PROXY，不排除本机地址的话发往 WebDriver 端口的请求
# 会被代理劫持、命令一律返回 "unhandled request"。run.bat 里也设了一份，这里再兜一次。
refresh_cookie.bypass_proxy_for_localhost()

BROWSER_PATHS = {
    'chrome': [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    ],
    'edge': [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
    ],
}
BROWSER_NAMES = {'chrome': 'Chrome', 'edge': 'Edge'}


def detect_browser():
    """browser 配置项可选 chrome / edge / auto，auto 表示自动探测本机已安装的浏览器"""
    order = [BROWSER] if BROWSER in BROWSER_NAMES else ['chrome', 'edge']
    for name in order:
        if any(os.path.exists(p) for p in BROWSER_PATHS[name]):
            return name
    return order[0]


def create_driver():
    extra = [
        # 无头模式下默认的自动播放策略会拦住 video.play()，必须放开
        '--autoplay-policy=no-user-gesture-required',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1920,1080',
        # ---- 压制渲染进程崩溃（2026-10-11 实测，详见 docs/技术细节.md 2.5）----
        # 该站视频播到几分钟后，Edge 渲染进程会以固定的 msedge.dll +0x556c74d
        # ACCESS_VIOLATION 崩掉（17 个转储地址完全一致），崩时加载着整套硬件解码链。
        # 强制软件解码 + 关掉 GPU 路径后存活时间 ~147s → ~593s，之后连跑 19 分 49 秒
        # 零崩溃。看数据像是治住了，但没拿到"绝不会再崩"的证据，所以主循环里
        # 仍保留"崩了就重建浏览器"的兜底。
        '--disable-accelerated-video-decode',
        '--disable-accelerated-video-encode',
        '--disable-gpu',
        '--disable-gpu-compositing',
        '--disable-software-rasterizer',
        '--disable-dev-shm-usage',
        # 无头下没有窗口可遮挡，这个检测只会误伤（还会触发站点的防刷暂停）
        '--disable-features=CalculateNativeWinOcclusion',
    ]
    if IF_HEADLESS:
        # 后台跑：不给窗口，也不出声。
        # 两家都是 Chromium，一律走新版无头 —— 旧版无头在 132+ 已被移除。
        extra.append('--headless=new')
        extra.append('--mute-audio')
    if BROWSER_NAME == 'edge':
        from selenium.webdriver.edge.options import Options as EdgeOptions
        option = EdgeOptions()
    else:
        option = webdriver.ChromeOptions()
    # 就绪即返回：等到 DOMContentLoaded，而不是等整个 load 事件。
    # 这站是 SPA 且挂着常驻连接，load 事件可能永远不触发 → `driver.get` 于是一路挂满
    # page_load_timeout。实测（tools/diag_startup.py，2026-10-15）：
    #   normal: 首页 90.00s + 课程页 90.01s = 180s，而且超时之后页面其实早就好了
    #   eager : 首页  2.62s + 课程页 20.83s =  23s
    # 异步渲染本来就有 sleep + 重试 + UNITS_RENDERED_JS 兜着，不用靠 load 事件保证。
    option.page_load_strategy = 'eager'
    for arg in extra:
        option.add_argument(arg)
    if BROWSER_NAME == 'edge':
        return webdriver.Edge(options=option)
    return webdriver.Chrome(options=option)


BROWSER_NAME = detect_browser()


def setup_driver(d):
    """新建 driver 之后的统一初始化。启动和崩溃重建共用，避免两处各写一遍。"""
    if not IF_HEADLESS:
        d.maximize_window()
    d.implicitly_wait(IMPLICITLY_WAIT)
    d.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return d

# 雨课堂有两套前端。新版(COMMONUI)的小节元素是 study-unit、视频标记是 span.leaf-flag；
# 旧版的小节元素是 leaf-detail、视频标记是 i.icon--shipin。
# 长江雨课堂(changjiang.yuketang.cn)与 www.yuketang.cn 前端完全同源
# （同一份 login.js，/v2/web/index 返回逐字节一致），属新版。
COMMONUI_HOSTS = ('www.yuketang.cn', 'changjiang.yuketang.cn')
# cookie 失效时被前端路由踢到登录页，可能出现的位置
LOGIN_URL_MARKS = ('pro/portal/home', 'pro/portal', '/login', 'portal/login')

homePageURL = 'https://' + COURSE_URL.split('//', 1)[-1].split('/')[0] + '/'

if UI_MODE == 'common':
    IS_COMMONUI = True
elif UI_MODE == 'legacy':
    IS_COMMONUI = False
elif any(host in homePageURL for host in COMMONUI_HOSTS):
    IS_COMMONUI = True
else:
    IS_COMMONUI = None  # 未知域名，留给 load_classes() 按 DOM 自动探测

print('\n配置信息:')
print(f'  无窗口模式: {IF_HEADLESS}')
print(f'  浏览器: {BROWSER_NAMES[BROWSER_NAME]}')
print(f'  课程URL: {COURSE_URL[:50]}...' if len(COURSE_URL) > 50 else f'  课程URL: {COURSE_URL}')
print(f'  雨课堂站点: {homePageURL}')
print(f'  UI 版本: { {True: "新版(common)", False: "旧版(legacy)", None: "待自动探测"}[IS_COMMONUI] }')
print(f'  播放倍速: {PLAYBACK_SPEED}x')
print('  Cookie已配置: ✓')
print('='*50 + '\n')

# 启动浏览器。这一步 + 首次打开课程页实测要几十秒（建进程、Selenium Manager 找驱动、
# 首页跳转、小节列表渲染），中间本来一个字符都不输出 —— 双击 exe 的人会以为程序死了。
# 所以从这里到第一次扫描之间都补了阶段提示，既给用户反馈，也让日志能看出时间花在哪。
print(f'{ts()} 启动浏览器（{BROWSER_NAMES[BROWSER_NAME]}，{"无窗口" if IF_HEADLESS else "有窗口"}）...')
driver = setup_driver(create_driver())
print(f'{ts()} 浏览器就绪')


def _get(url):
    """driver.get 的容错版：站点抽风导致加载超时时，页面往往已经能用了。

    挂后台跑一整晚，网络抖一下很常见。这里不让它把整轮任务作废 —— 超时也接着往下走，
    由调用方的"等元素"逻辑去判断页面到底能不能用。
    """
    try:
        driver.get(url)
    except TimeoutException:
        print(f'  提示: 打开页面超时（{PAGE_LOAD_TIMEOUT}s），继续尝试使用当前页面')

def setCookie(cookies):
    driver.delete_all_cookies()
    for name, value in cookies.items():
        driver.add_cookie({'name': name, 'value': value, 'path': '/'})


PLAYED_TITLES = set()  # 本次运行已播过/已放弃的标题，保证无人看守时绝不会原地打转
SKIPPED_STALLED = []   # 因卡住被跳过的标题，收尾时如实汇报


# 一次 JS 扫描，挑出「下一个该播的小节」并**直接返回元素句柄**。
#
# 旧实现每个小节要发 6 次元素查询，81 个小节一轮 28~31 秒；信息本来就在 DOM 里，
# 合并成一次 execute_script 后实测 0.019 秒。另外旧实现读 Selenium 的 element.text
# （渲染文本），它会把 study-unit / complete-td 这一层间歇性读成空串 ——
# 那样已完成的小节会被判成没完成、被重播；这里统一用 textContent。
# 判定口径、实测数据、差分比对过程见 docs/技术细节.md 2.7。
SCAN_TARGET_JS = '''
var mode = arguments[0], played = arguments[1];
var common = (mode === 'common');
var units = document.querySelectorAll(common ? '.study-unit' : '.leaf-detail');
var st = {total: units.length, locked: 0, notVideo: 0, expired: 0, done: 0,
          played: 0, blankTitle: 0, pending: 0};
var picked = null, pickedTitle = '';
for (var i = 0; i < units.length; i++) {
    var u = units[i];
    var txt = u.textContent || '';
    if (u.querySelector('i.icon--suo')) { st.locked++; continue; }
    var isVideo;
    if (common) {
        var flag = u.querySelector('span.leaf-flag');
        isVideo = !!(flag && flag.textContent.trim().indexOf('视频') >= 0);
    } else {
        var firstI = u.querySelector('i');
        isVideo = !!(firstI && (firstI.getAttribute('class') || '').indexOf('icon--shipin') >= 0);
    }
    if (!isVideo) { st.notVideo++; continue; }
    if (txt.indexOf('截止') >= 0) { st.expired++; continue; }
    var done = txt.indexOf('已完成') >= 0;
    if (!done) {
        var ct = u.querySelector('.complete-td');
        if (ct) {
            var m = /(\\d+(?:\\.\\d+)?)\\s*%/.exec(ct.textContent || '');
            if (m && parseFloat(m[1]) >= 99.9) { done = true; }
        }
    }
    if (done) { st.done++; continue; }
    var nt = u.querySelector('span.name-text');
    var title = nt ? (nt.textContent || '').trim()
                   : txt.replace(/\\s+/g, ' ').trim().slice(0, 60);
    // 空标题不登记、也不能当合法候选：那多半是课程页先吐了骨架、标题还没填，
    // 拿它往下走会把整轮带偏（详见 docs/技术细节.md 2.3）
    if (!title) { st.blankTitle++; continue; }
    if (played.indexOf(title) >= 0) { st.played++; continue; }
    if (picked) { st.pending++; continue; }
    picked = u;
    pickedTitle = title;
}
return [picked, pickedTitle, st];
'''


def scan_target(mode: str):
    """挑选下一个要播的小节。返回 (元素, 标题, 统计)；没有候选时元素为 None。

    返回的标题保证非空 —— 空标题一律不算候选，避免"页面没渲染完"被当成
    "这些小节都播过了"（2026-10-11 实跑就是这么误报"全部播放完毕"的）。
    """
    el, title, st = driver.execute_script(SCAN_TARGET_JS, mode, list(PLAYED_TITLES))
    return el, title, st


def at_login_page():
    """判断当前是否停在登录页。

    cookie 失效时前端不一定改 URL（实测长江雨课堂的 current_url 仍停在课程页地址），
    所以除了 URL 还要看标题和登录按钮。
    """
    if any(mark in driver.current_url for mark in LOGIN_URL_MARKS):
        return True
    if '登录' in (driver.title or ''):
        return True
    driver.implicitly_wait(0.1)
    try:
        logged_out = bool(driver.find_element(By.CLASS_NAME, 'login-btn'))
    except Exception:
        logged_out = False
    finally:
        driver.implicitly_wait(IMPLICITLY_WAIT)
    return logged_out


def goto_course_page(allow_qr=True) -> bool:
    """（重新）进入课程页：先落到首页把 cookie 塞进去，再打开课程页。

    启动时和「浏览器崩了重建之后」都走这里，保证两条路径行为一致。
    重建时传 allow_qr=False —— 那时候不该停下来等人扫码。
    """
    print(f'{ts()} 打开课程页...')
    _get(homePageURL)
    setCookie({'sessionid': COOKIE})
    _get(COURSE_URL)
    sleep(3)
    if not at_login_page():
        return True
    if not allow_qr:
        print('  重建后仍停在登录页 —— cookie 可能已失效，请重跑 refresh_cookie.bat')
        return False
    print('cookie失效或设置有误，请重设cookie或选择每次扫码登录')
    if IF_HEADLESS:
        print('  提示: 当前是 headless 模式，扫码窗口不可见；要扫码请先把 headless 改成 false')
    _get(homePageURL)
    try:
        driver.find_element(By.CLASS_NAME, 'login-btn').click()
    except Exception as e:
        print(f'  找不到登录按钮（{type(e).__name__}），无法进入扫码登录')
        return False
    print(f'请扫码登录（最多等 {QR_LOGIN_TIMEOUT // 60} 分钟）')
    # 判据是"离开了登录页"，不是 URL 里出现 courselist。
    # 上游那版等的是 'courselist' in current_url —— 新版 UI 登录成功后落的是
    # /v2/web/index，而且 /v2/web/courselist 会 302 到 /v2/web/errpage，
    # 这个判据在这站永远不成立，会一路等到超时（2026-10-15 实测确认）。
    deadline = monotonic() + QR_LOGIN_TIMEOUT
    while at_login_page():
        if monotonic() > deadline:
            print(f'  等扫码超时（{QR_LOGIN_TIMEOUT}s），放弃本次登录')
            return False
        sleep(1)
    print('登录成功')
    _get(COURSE_URL)
    return True


# "浏览器/标签页已经死了"的报错特征。
#
# 这站视频播几分钟后，Edge 的渲染进程会崩（实测崩点固定为
# msedge.dll +0x556c74d 的 ACCESS_VIOLATION）。无头模式只有一个标签页，
# 标签页一崩整个 Edge 进程跟着退出，下一轮再访问就变成 InvalidSessionIdException。
# 这类异常**重试同一个 driver 永远不可能成功**，只能重建浏览器。
DEAD_SESSION_MARKS = (
    'invalid session id', 'tab crashed', 'not connected to devtools',
    'browser has closed the connection', 'session deleted', 'disconnected',
    'chrome not reachable', 'target closed', 'no such window',
)


def is_browser_gone(exc: BaseException) -> bool:
    text = f'{type(exc).__name__}: {exc}'.lower()
    return any(mark in text for mark in DEAD_SESSION_MARKS)


def session_alive() -> bool:
    """轻量探活，不抛异常。"""
    try:
        driver.window_handles
        return True
    except Exception:
        return False


def restart_browser() -> bool:
    """丢掉死掉的会话，重建浏览器并回到课程页。

    视频进度记在服务端，重开会从断点续播，所以重建几乎不丢东西。
    """
    global driver
    print(f'{ts()} 浏览器已退出（标签页崩溃会带走整个进程），正在重建…')
    try:
        driver.quit()
    except Exception:
        pass
    sleep(3)
    try:
        driver = setup_driver(create_driver())
    except Exception as e:
        print(f'  重建浏览器失败: {type(e).__name__}: {str(e).splitlines()[0][:120]}')
        return False
    try:
        return goto_course_page(allow_qr=False)
    except Exception as e:
        print(f'  重建后回课程页失败: {type(e).__name__}: {str(e).splitlines()[0][:120]}')
        return False


# 进课程页。失败（停在登录页且等扫码超时）就别往下跑了 ——
# 硬跑只会在课程页之外乱点，最后报一堆找不到小节的警告。
if not goto_course_page():
    print('未能进入课程页，退出。请先跑 refresh_cookie.bat 刷新 sessionid，或把 headless 改成 false 手动扫码。')
    try:
        driver.quit()
    except Exception:
        pass
    sleep(3)
    sys.exit(1)


PLAYER_LOCK_JS = '''
(function (cfg) {
    if (!window.__ytLock) {
        var desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'playbackRate');
        if (!desc || !desc.set) { return 'no-native-setter'; }
        window.__ytDesc = desc;
        window.__ytSpeed = 0;
        window.__ytMute = false;
        window.__ytBlocked = 0;
        Object.defineProperty(HTMLMediaElement.prototype, 'playbackRate', {
            configurable: true,
            enumerable: desc.enumerable,
            get: function () { return desc.get.call(this); },
            set: function (v) {
                // 播放器每次 ratechange/timeupdate 都写回 1，这里把"往低调"的写入直接吞掉。
                // 被吞掉的写入不改变实际值，因此不会再触发 ratechange，不会自激循环。
                if (window.__ytSpeed && v < window.__ytSpeed) {
                    window.__ytBlocked++;
                    return;
                }
                return desc.set.call(this, v);
            }
        });
        window.__ytLock = true;
        // 兜底：播放器会卸载并重建 <video>（外层 xt-wrap 带 unload 类），
        // 新元素默认 1x 且没人写它，所以定期按原型上的目标值补一刀。
        window.__ytTimer = setInterval(function () {
            var v = document.querySelector('video');
            if (!v) { return; }
            try {
                if (window.__ytSpeed && v.playbackRate < window.__ytSpeed) { v.playbackRate = window.__ytSpeed; }
                if (window.__ytMute && !v.muted) { v.muted = true; }
            } catch (e) {}
        }, 1000);
    }
    window.__ytSpeed = cfg.speed;
    window.__ytMute = cfg.mute;
    var v = document.querySelector('video');
    if (v && v.playbackRate < cfg.speed) { try { v.playbackRate = cfg.speed; } catch (e) {} }
    return 'ok';
})(arguments[0]);
'''


def change2speed2():
    """把播放速度锁到配置的倍速（默认 2 倍），顺带把静音也锁住。

    播放器每约 250ms 会把倍速同步回自己内部的 1x 状态，硬对抗没用。做法是给
    HTMLMediaElement.prototype.playbackRate 装一层 setter，把"往低调"的写入直接
    丢弃 —— 实际值不变，就不会触发 ratechange，也就没有自激循环。锁装在原型上
    （播放器中途换掉 <video> 也不怕），另有 1 秒定时器兜底。站点自带的倍速 UI 是死路。

    副作用：播放器 UI 仍显示 1.00X（它的内部状态没被改），纯显示问题。
    判断真实速率要看 currentTime 推进量，不能读 playbackRate。实测见 docs/技术细节.md §3。
    """
    try:
        r = driver.execute_script(PLAYER_LOCK_JS, {'speed': PLAYBACK_SPEED, 'mute': True})
    except Exception as e:
        print(f'警告: 安装播放锁失败（不影响播放与切集）: {type(e).__name__}: {e}')
        return
    if r == 'no-native-setter':
        print('警告: 本页 playbackRate 没有原生 setter，无法锁倍速（不影响播放与切集）')
        return

    # 播放器的 <video> 是异步挂载的，还可能在开场被卸载重建，给它最多 6 秒稳定下来
    now = None
    for _ in range(6):
        sleep(1)
        try:
            now = driver.execute_script('var v = document.querySelector("video"); return v ? v.playbackRate : null;')
        except Exception as e:
            print(f'警告: 校验倍速时出错（不影响播放与切集）: {type(e).__name__}: {e}')
            return
        if now and now >= PLAYBACK_SPEED - 0.01:
            blocked = driver.execute_script('return window.__ytBlocked || 0;') or 0
            print(f'已锁定播放速度: {now}x（已拦截播放器复位 {blocked} 次；播放器 UI 可能仍显示 1.00X，属正常）')
            return

    if now is None:
        print('警告: 页面上暂时取不到 video 元素；播放锁已挂上，视频一出现会自动生效')
    else:
        print(f'警告: 倍速没锁住，当前 {now}x（不影响播放与切集，但会按原速跑）')


def js_click(element):
    """雨课堂部分站点（实测长江雨课堂课程页）上元素虽存在但原生 click 会抛
    ElementNotInteractableException，统一改走 JS 点击。"""
    driver.execute_script('arguments[0].click()', element)


# 点标题前注入：把站点的 window.open 收编，并改写 target=_blank。
#
# 原先是"让它开新标签页 → 播完再 close"，但该站 driver.close() 会偶发卡死 20 秒，
# 窗口状态一乱后面几轮全废。既然它就是用 window.open(url, '_blank') 打开视频页的，
# 把这个 URL 截下来、在当前标签页 driver.get(url) 即可 —— 全程单窗口，没有 close 可卡。
# window.open 必须返回一个假窗口对象（站点会调 focus()/close()），返回 null 会让它内部抛错。
# 细节见 docs/技术细节.md 2.4。
CAPTURE_VIDEO_URL_JS = '''
(function () {
    if (!window.__ytOpenPatched) {
        window.__ytOpenPatched = true;
        window.__ytVideoUrl = null;
        window.__ytOpenCalls = 0;
        window.open = function (u, n, f) {
            window.__ytOpenCalls++;
            if (typeof u === 'string' && u) { window.__ytVideoUrl = u; }
            return { closed: false, focus: function () {}, blur: function () {},
                     close: function () {}, document: { write: function () {} },
                     location: { href: u } };
        };
    }
    window.__ytVideoUrl = null;
    var n = 0;
    document.querySelectorAll('a[target="_blank"]').forEach(function (a) {
        a.setAttribute('target', '_self');
        n++;
    });
    return n;
})();
'''


# 小节列表是否渲染出了标题。实测（2026-10-11 实跑）：课程页偶尔会先吐出 80 多个
# 空的 study-unit 骨架、标题稍后才填上。此时若直接往下走只会取到空标题，把整轮带偏。
# 宁可重载一次课程页，也别拿半成品往下跑。
UNITS_RENDERED_JS = '''
var us = document.querySelectorAll('.study-unit');
for (var i = 0; i < us.length && i < 5; i++) {
    var nt = us[i].querySelector('span.name-text');
    if (nt && (nt.textContent || '').trim()) { return true; }
}
return false;
'''


def load_classes() -> List[WebElement]:
    """返回课程页所有小节元素，首次调用时会确定 UI 版本。

    新版(COMMONUI)的小节列表在"学习报告"标签页下，需要先点一下标签才会渲染出来；
    旧版(legacy)直接就是 leaf-detail。
    """
    global IS_COMMONUI

    def click_report_tab():
        try:
            js_click(driver.find_element(By.ID, 'tab-student_school_report'))
            return True
        except Exception:
            return False

    if IS_COMMONUI is None:  # 未知域名，按 DOM 实测判定
        click_report_tab()
        sleep(2)  # 点完标签后小节列表是异步渲染的
        driver.implicitly_wait(0.1)
        probed = len(driver.find_elements(By.CLASS_NAME, 'study-unit')) > 0
        driver.implicitly_wait(IMPLICITLY_WAIT)
        IS_COMMONUI = probed
        print(f'UI 版本自动判定: {"新版(common)" if probed else "旧版(legacy)"}')
        if probed:
            return load_classes()
        return driver.find_elements(By.CLASS_NAME, 'leaf-detail')

    if IS_COMMONUI:
        print(f'{ts()} 读取小节列表...')
        units = []
        for attempt in (1, 2, 3):
            click_report_tab()
            sleep(2)  # 小节列表是点完标签后异步渲染的，给渲染留点时间
            units = driver.find_elements(By.CLASS_NAME, 'study-unit')
            if not units or driver.execute_script(UNITS_RENDERED_JS):
                return units
            print(f'提示: 小节列表出来了但标题还是空的（第 {attempt} 次），重新加载课程页')
            _get(COURSE_URL)
            sleep(4)
        return units
    return driver.find_elements(By.CLASS_NAME, 'leaf-detail')


ABORTED_NO_CLASSES = False  # 因为一个小节都没找到而中止，结尾不能报"播放完毕"
ABORTED_ERRORS = False      # 连续出错而中止
LOCKED_VIDEOS = 0           # 页面上处于「未开放」（带锁）状态的视频数 —— 有它就别说"全部刷完"


def back_to_course_page():
    """确保回到课程页，并且不留下多余窗口。

    正常只有 1 个窗口（见 CAPTURE_VIDEO_URL_JS），这里主要是兜底：万一哪一轮
    window.open 拦截没生效、真开了新标签页，必须清掉，否则下一轮会再开一个。
    但 close 在这站有概率卡住 20 秒，所以循环有上限、失败就转 about:blank，
    绝不无限重试（详见 docs/技术细节.md 2.4）。
    """
    for _ in range(3):
        handles = driver.window_handles
        if len(handles) <= 1:
            break
        try:
            driver.switch_to.window(handles[-1])
            driver.execute_script('window.onbeforeunload = null;')
        except Exception:
            pass
        # 关窗前**重新数一遍**。上面那份 handles 是快照，这一瞬站点可能已经自己
        # 把那个标签页关掉了；此时再 close() 关掉的就是主窗口 —— 整个浏览器直接退出，
        # 下一轮就报 InvalidSessionIdException。（2026-10-11 实跑踩到过这个现象）
        if len(driver.window_handles) <= 1:
            break
        try:
            driver.close()
        except Exception as e:
            first_line = str(e).splitlines()[0][:130] if str(e) else ''
            print(f'  关闭多余窗口失败（继续）: {type(e).__name__}: {first_line}')
            try:
                driver.get('about:blank')
            except Exception:
                pass
            break

    try:
        driver.switch_to.window(driver.window_handles[0])
    except Exception as e:
        print(f'  切换回主窗口时出错（继续）: {type(e).__name__}: {e}')
    _get(COURSE_URL)
    if len(driver.window_handles) > 1:
        print(f'  注意: 当前仍有 {len(driver.window_handles)} 个窗口，下一轮可能会受影响')


def dump_dom():
    """一个小节都找不到时，把现场落盘，便于比对站点 UI 结构差异。

    落到**程序所在目录**（和 config.ini 一个地方）：双击 exe 启动时工作目录未必是那里，
    用相对路径会把文件丢到用户根本想不到、也找不到的地方。
    """
    path = os.path.join(refresh_cookie.app_dir(), '_debug_page_source.html')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        counts = {}
        for el in driver.find_elements(By.XPATH, '//*[@class]'):
            for c in (el.get_attribute('class') or '').split():
                counts[c] = counts.get(c, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:15]
        print('  页面 class 采样(出现最多): ' + ', '.join(f'{k}x{v}' for k, v in top))
        print(f'  页面源码已保存: {path}')
    except Exception as e:
        print(f'  现场落盘失败: {e}')


def finish1video():
    global ABORTED_NO_CLASSES, LOCKED_VIDEOS
    allClasses = load_classes()
    if not allClasses:
        # 必须显式告警：否则会一路 return False，主循环结束并打印"全部播放完毕"，
        # 看起来像刷成功了，其实一个视频都没播。
        ABORTED_NO_CLASSES = True
        print(f'{ts()} 警告: 页面上没有找到任何小节元素，本次不会播放任何视频')
        print(f'  当前 UI 判定: {"新版(common)" if IS_COMMONUI else "旧版(legacy)"}')
        print(f'  当前 URL: {driver.current_url}')
        print(f'  页面标题: {driver.title}')
        print('  常见原因: 课程页没加载完 / 未登录成功 / 该站点 UI 结构与已知两套都不同')
        dump_dom()
        return False
    video, title, st = scan_target('common' if IS_COMMONUI else 'legacy')
    if video is None:
        if st['blankTitle']:
            # 有视频小节、标题却全是空的 = 课程页先吐了骨架。绝不能当成"没有未完成视频了"
            # 收工（2026-10-11 就是这么误报"全部播放完毕"的，其实还剩几十个没刷）。
            print(f'{ts()} 警告: {st["blankTitle"]} 个视频小节取不到标题，课程页很可能没渲染完，本轮放弃重来')
            return None
        LOCKED_VIDEOS = st['locked']
        print(f'{ts()} 没有未完成的视频了（小节 {st["total"]} 个: 已完成 {st["done"]}, '
              f'未开放 {st["locked"]}, 已过期 {st["expired"]}, 本次已播 {st["played"]}, '
              f'非视频 {st["notVideo"]}）')
        return False
    PLAYED_TITLES.add(title)
    print(f'{ts()} 目标: {title}（本次还剩 {1 + st["pending"]} 个视频待播）')
    driver.execute_script('arguments[0].scrollIntoView(false);', video)
    # 先收编 window.open，再点标题 —— 这样它不会开新标签页，只把视频 URL 交出来。
    try:
        retargeted = driver.execute_script(CAPTURE_VIDEO_URL_JS)
    except Exception as e:
        retargeted = 0
        print(f'  提示: 注入 window.open 拦截失败（走兜底路径）: {type(e).__name__}')
    before_handles = driver.window_handles[:]
    if IS_COMMONUI:
        # 新版：点标题文字打开视频页。实测长江雨课堂里该元素的第一个 span 是类型标签
        # (leaf-flag)，点标题 span.name-text 更可靠；原生点击失败则回退 JS 点击。
        try:
            target = video.find_element(By.CSS_SELECTOR, 'span.name-text')
        except Exception:
            target = video.find_element(By.TAG_NAME, 'span')
        try:
            target.click()
        except Exception:
            js_click(target)
    else:
        video.click()
    sleep(2)

    new_handles = [h for h in driver.window_handles if h not in before_handles]
    try:
        video_url = driver.execute_script('return window.__ytVideoUrl;')
    except Exception:
        video_url = None

    if new_handles:
        # 兜底路径：拦截没生效，站点还是开了新标签页
        driver.switch_to.window(new_handles[-1])
        opened_new_window = True
        print(f'{ts()} 正在播放（新标签页 —— window.open 拦截没生效，已改写 {retargeted} 个 target）')
    else:
        opened_new_window = False
        if video_url:
            # 拦截生效：URL 拿到了，但当前页没动，需要自己跳过去
            _get(video_url)
            print(f'{ts()} 正在播放（当前标签页直达视频页）')
        else:
            print(f'{ts()} 正在播放（站点自己完成了当前页跳转）')

    def leave_video_window():
        """离开视频页：先把注入拆干净，再处理窗口。

        第一步必须是"停掉注入的定时器、置 __ytDone、清 onbeforeunload"，
        否则页面卸载时会和播放器打架，close 直接卡死 20 秒。
        """
        try:
            driver.execute_script(
                'window.__ytDone = true;'
                'try { clearInterval(window.__ytTimer); } catch (e) {}'
                'try { clearInterval(window.__ytResumeTimer); } catch (e) {}'
                'try { clearInterval(window.__ytFinishTimer); } catch (e) {}'
                'try { window.onbeforeunload = null; } catch (e) {}'
            )
        except Exception:
            pass
        if opened_new_window:
            try:
                # 同样要先重新数：站点可能已经自己把视频标签页关掉了，
                # 这时 close() 会误关主窗口，把整个浏览器带走。
                if len(driver.window_handles) > 1:
                    driver.close()
                driver.switch_to.window(driver.window_handles[-1])
            except Exception as e:
                first_line = str(e).splitlines()[0][:130] if str(e) else ''
                print(f'  关闭视频窗口时出错（继续）: {type(e).__name__}: {first_line}')

    try:
        # 只判断 <video> 出没出现，不把元素句柄搬回 Python。
        # 顺带说明：这里刻意不写全局 video 变量 —— 播放器会卸载重建 <video>，
        # 留一个全局引用等于随时可能对着已脱离文档的僵尸元素操作。
        #
        # 20 秒：page_load_strategy='eager' 之后视频页是"DOM 就绪就返回"，
        # 播放器把 <video> 建出来还要一点时间，这段余量由这个显式等待承担
        # （元素一出现就立刻返回，正常路径不会多花时间）。
        WebDriverWait(driver, VIDEO_READY_TIMEOUT).until(
            lambda x: x.execute_script('return !!document.querySelector("video");'))
    except Exception:
        # 视频页没起来（实测会发生在上一轮窗口状态已经乱了的时候）。
        # 明确报"本轮没进展"，并把注入拆干净再退出，别把异常丢给主循环。
        print(f'{ts()} 警告: 视频页 {VIDEO_READY_TIMEOUT} 秒内没有出现 video 元素，本轮放弃')
        leave_video_window()
        return None

    # 开场几秒播放器可能还没自己开始播，短暂补一下 play()
    driver.execute_script(
        'window.__ytResumeTimer = setInterval(function () {'
        '  var v = document.querySelector("video");'
        '  if (v && v.paused) { try { v.play(); } catch (e) {} }'
        '}, 200);'
        'setTimeout(function () { clearInterval(window.__ytResumeTimer); }, 5000);'
    )
    # 结束探测器：currentTime 一旦回退就认为播完了（播放器循环时会命中）。
    # 只能认"回退" —— 往前拖 currentTime 会被站点顶回服务端记录的位置（防跳过）。
    driver.execute_script(
        'window.__ytLastPos = 0;'
        'window.__ytFinishTimer = setInterval(function () {'
        '  var v = document.querySelector("video");'
        '  if (!v) { return; }'
        '  if (v.currentTime < window.__ytLastPos) {'
        '    var m = document.createElement("span");'
        '    m.setAttribute("id", "LetMeFly_Finished");'
        '    document.body.appendChild(m);'
        '  }'
        '  window.__ytLastPos = v.currentTime;'
        '}, 200);'
    )
    # 播放器带防刷逻辑（页面失焦/不可见就 pause），这里挂到 document 捕获阶段而不是
    # 某个 video 元素上：pause 不冒泡，但捕获阶段能收到；换掉 <video> 也不会失效。
    # __ytDone 一旦置位就放手 —— 否则离开页面时这个"续播"监听会和卸载流程互相顶。
    driver.execute_script(
        'document.addEventListener("pause", function (e) {'
        '  try { if (!window.__ytDone && e.target && e.target.tagName === "VIDEO") { e.target.play(); } }'
        '  catch (err) {}'
        '}, true)'
    )
    # 锁倍速的同时也把静音锁住（1 秒定时器会持续压 muted=true）
    change2speed2()

    last_pos = -1.0
    last_t = None
    measured = None
    stalled = 0
    while True:
        # 判据一：原实现的"时间回退"标记（播放器自动循环时会命中）
        if driver.execute_script('return document.querySelector("#LetMeFly_Finished");'):
            print(f'{ts()} 检测到播放结束标记，再等 5 秒')
            sleep(5)
            leave_video_window()
            return True

        # 判据二：直接看播放器状态。播放器播完就停住不循环时，判据一永远不会命中，
        # 挂后台就会无限等下去，所以这里补上 ended / 接近结尾的显式判断。
        try:
            info = driver.execute_script(
                'var v = document.querySelector("video");'
                'if (!v) { return null; }'
                'return [v.currentTime || 0, v.duration || 0, v.ended ? 1 : 0];'
            )
        except Exception:
            info = None

        if info:
            pos, dur, ended = info
            if ended or (dur and pos >= dur - 0.5):
                print(f'{ts()} 播放已到结尾（{pos:.1f}s / {dur:.1f}s）')
                sleep(3)
                leave_video_window()
                return True
            now_t = monotonic()
            if last_t is not None and now_t > last_t and pos > last_pos:
                measured = (pos - last_pos) / (now_t - last_t)
            last_t = now_t
            if last_pos >= 0 and pos <= last_pos + 0.05:
                stalled += 1
            else:
                stalled = 0
            last_pos = pos
            speed_txt = f' | 实测倍速 {measured:.2f}x' if measured else ''
            print(f'{ts()} 正在播放视频 | 已播 {pos:.0f}s / 共 {dur:.0f}s{speed_txt}')
        else:
            stalled += 1

        # 判据三：兜底。真卡死了也要能跳到下一集，别把整晚耗在同一个视频上
        if stalled >= 100:  # 约 5 分钟没有任何前进
            print(f'{ts()} 警告: 视频 5 分钟没有前进，放弃这一集，跳到下一个')
            SKIPPED_STALLED.append(title)
            leave_video_window()
            return True
        sleep(3)


consecutive_errors = 0
no_progress_rounds = 0
total_played = 0
browser_deaths = 0            # 连续几次"浏览器崩了"，跑通一轮就清零
force_restart = False         # 刚抓到浏览器崩溃，下一轮开头强制重建
ABORTED_NO_PROGRESS = False   # 连续几轮一个视频都没真正开起来
ABORTED_BROWSER = False       # 浏览器反复崩溃、重建也起不来
while True:
    # 浏览器/标签页崩了就重建。
    # tab 崩溃会带走整个 Edge 进程（无头下只有一个标签页），而这类异常**重试同一个
    # driver 永远不可能成功** —— 以前就是这里白烧 3 轮重试、然后整个任务终止。
    # 视频进度记在服务端，重建后从断点续播，几乎不丢东西。
    if force_restart or not session_alive():
        force_restart = False
        browser_deaths += 1
        if browser_deaths > 6:
            ABORTED_BROWSER = True
            print(f'{ts()} 浏览器已经连续崩了 {browser_deaths - 1} 次、重建后仍跑不起来，停止。')
            break
        if restart_browser():
            print(f'{ts()} 重建完成，接着刷（这是第 {browser_deaths} 次重建）')
        else:
            sleep(10)
        continue

    try:
        played = finish1video()
        consecutive_errors = 0
        browser_deaths = 0
    except Exception as e:
        if is_browser_gone(e):
            # 不算"逻辑出错"，不烧重试预算 —— 交给循环开头去重建浏览器
            print(f'{ts()} 标签页/浏览器崩溃: {type(e).__name__}: {str(e).splitlines()[0][:120]}')
            force_restart = True
            continue
        # 挂后台无人看守，单轮异常不能把整个任务带走
        consecutive_errors += 1
        print(f'{ts()} 本轮出错（连续第 {consecutive_errors} 次）: {type(e).__name__}: {e}')
        if consecutive_errors >= 3:
            ABORTED_ERRORS = True
            print('连续 3 轮出错，停止。已播完的进度都已记录，重跑即可接着刷。')
            break
        sleep(10)
        # 回落到课程页，避免卡在残留的视频窗口里
        try:
            back_to_course_page()
        except Exception:
            pass
        sleep(5)
        continue

    # finish1video 返回 None = 本轮没真正开起来任何视频（页面没渲染完、视频页没起来等）。
    # 这种情况绝不能当成"没有未完成视频了"直接收工 —— 2026-10-11 实跑就是这么
    # 误报"全部播放完毕"的，其实还剩几十个没刷。
    if played is None:
        no_progress_rounds += 1
        print(f'{ts()} 本轮没有任何进展（连续第 {no_progress_rounds} 次），回课程页重来')
        if no_progress_rounds >= 3:
            ABORTED_NO_PROGRESS = True
            print('连续 3 轮没有任何进展，停止。这不是"刷完了"，请检查上面的警告。')
            break
        try:
            back_to_course_page()
        except Exception:
            pass
        sleep(5)
        continue

    no_progress_rounds = 0
    if not played:
        break
    total_played += 1
    print(f'{ts()} —— 已播完 {total_played} 个视频，切下一个 ——')
    back_to_course_page()
    sleep(5)  # thanks for @420xincheng's #8


try:
    driver.quit()
except Exception:
    pass   # 会话早死了的时候 quit 也会抛，没必要因此留个 traceback
if ABORTED_NO_CLASSES:
    print(f'{ts()} 已中止: 未找到任何小节元素，视频没有被播放，请查看上面的警告信息')
elif ABORTED_ERRORS:
    print(f'{ts()} 已中止: 连续出错，任务没有跑完。重跑会接着刷没完成的。')
elif ABORTED_BROWSER:
    print(f'{ts()} 已中止: 浏览器反复崩溃，重建也起不来（本次共播出 {total_played} 个）。')
    print('  重跑会接着刷。若反复出现，多半是浏览器本身的问题，试试更新 Edge 或换 Chrome。')
elif ABORTED_NO_PROGRESS:
    print(f'{ts()} 已中止: 连续 3 轮没能开始播放任何视频（本次共播出 {total_played} 个）。')
    print('  这不代表刷完了。常见原因是课程页没渲染完或窗口状态异常，重跑一般能接着刷。')
else:
    if LOCKED_VIDEOS:
        # "未开放"（带锁）的视频不是"已刷完"。别把它们算进成功里。
        print(f'{ts()} 本次结束: 没有可播的视频了，但还有 {LOCKED_VIDEOS} 个视频处于未开放（带锁）状态，'
              f'不算全部刷完（本次共播出 {total_played} 个）')
    else:
        print(f'{ts()} 恭喜你！全部播放完毕（本次共播出 {total_played} 个视频）')
    if SKIPPED_STALLED:
        print(f'注意: 有 {len(SKIPPED_STALLED)} 个视频因播放卡住被跳过，重跑会再试:')
        for t in SKIPPED_STALLED:
            print(f'  - {t}')

sleep(2)
# 收尾也停一下：双击 exe 时窗口不该在用户看清结果之前就自己关掉。
# 挂后台 / 输出被重定向时 pause_exit 会自动跳过这一步，不会卡住。
pause_exit(0)
