'''
Author: LetMeFly, Guo-Chenxu, Crsuh2er0, 420xincheng, tkzzzzzz6
Date: 2023-09-12 20:49:21
LastEditors: LetMeFly.xyz
LastEditTime: 2025-11-13 22:44:00
Description: 开源于https://github.com/LetMeFly666/YuketangAutoPlayer 欢迎issue、PR
'''
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from time import sleep, monotonic
import random
import os
import re
import sys
import configparser


def create_config_template(config_path):
    """创建config.ini模板文件"""
    config = configparser.ConfigParser()
    config['Settings'] = {
        'headless': 'false',
        'browser': 'auto',
        'ui': 'auto',
        'course_url': 'https://在此填写你的课程URL',
        'cookie': '在此填写你的sessionid',
        'speed': '2',
        'implicitly_wait': '10'
    }

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('; YuketangAutoPlayer 配置文件\n')
            f.write('; headless: 是否无窗口运行 (true/false)，首次使用建议false\n')
            f.write('; browser: chrome / edge / auto，auto 表示自动探测本机已安装的浏览器\n')
            f.write('; ui: auto / common / legacy，雨课堂前端版本；auto 表示按域名判断，未知域名则运行时自动探测\n')
            f.write(';     www.yuketang.cn、changjiang.yuketang.cn（长江雨课堂）为新版(common)\n')
            f.write('; course_url: 你的课程地址，必须包含 https:// 协议头\n')
            f.write(';             例如: https://www.yuketang.cn/v2/web/studentLog/12345678\n')
            f.write('; cookie: 你的sessionid值，获取方式见README.md\n')
            f.write('; speed: 播放倍速，1 = 原速，2 = 两倍速（允许 0.5 ~ 4）\n')
            f.write('; implicitly_wait: 元素查找超时时间(秒)，一般不需要修改\n\n')
            config.write(f)
    except Exception as e:
        print(f'创建配置文件失败: {e}')


def load_config():
    """从config.ini加载配置"""
    config = configparser.ConfigParser()

    # 优先从可执行文件所在目录查找config.ini（支持打包后的exe）
    config_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'config.ini')

    if not os.path.exists(config_path):
        # 如果exe目录没有，尝试从当前工作目录查找
        config_path = os.path.join(os.getcwd(), 'config.ini')

    if not os.path.exists(config_path):
        # 如果config.ini不存在，创建模板
        print(f'未找到配置文件，正在创建模板: {config_path}')
        create_config_template(config_path)
        print('\n请编辑 config.ini 文件填写你的配置信息后重新运行程序')
        input('按回车键退出...')
        sys.exit(0)

    try:
        config.read(config_path, encoding='utf-8')
        print(f'成功加载配置文件: {config_path}')
        return config
    except Exception as e:
        print(f'读取配置文件失败: {e}')
        input('按回车键退出...')
        sys.exit(1)


# 加载配置
print('='*50)
print('YuketangAutoPlayer - 雨课堂视频自动播放器')
print('='*50)

config = load_config()

# 读取配置项
try:
    IF_HEADLESS = config.getboolean('Settings', 'headless', fallback=False)
    BROWSER = config.get('Settings', 'browser', fallback='auto').strip().lower()
    UI_MODE = config.get('Settings', 'ui', fallback='auto').strip().lower()
    COURSE_URL = config.get('Settings', 'course_url', fallback='')
    COOKIE = config.get('Settings', 'cookie', fallback='')
    PLAYBACK_SPEED = config.getfloat('Settings', 'speed', fallback=2.0)
    IMPLICITLY_WAIT = config.getint('Settings', 'implicitly_wait', fallback=10)
except Exception as e:
    print(f'\n配置文件格式错误: {e}')
    input('按回车键退出...')
    sys.exit(1)

# 验证配置
if not COURSE_URL or not COOKIE or '在此填写' in COURSE_URL or '在此填写' in COOKIE:
    print('\n错误: 检测到配置文件未正确填写!')
    print('请编辑 config.ini 文件，填写正确的 course_url 和 cookie')
    input('按回车键退出...')
    sys.exit(1)

# 倍速限幅：太低没意义，太高播放器会直接拒
PLAYBACK_SPEED = min(4.0, max(0.5, PLAYBACK_SPEED))

# selenium 客户端会读取 HTTP(S)_PROXY 环境变量。若不排除本机地址，
# 发往本地 WebDriver 端口的请求会被代理劫持，命令一律返回 "unhandled request"。
for _proxy_env in ('NO_PROXY', 'no_proxy'):
    _bypass = [h for h in ('localhost', '127.0.0.1', '::1') if h not in os.environ.get(_proxy_env, '')]
    if _bypass:
        _old = os.environ.get(_proxy_env, '').strip(',')
        os.environ[_proxy_env] = f'{_old},{",".join(_bypass)}'.strip(',')

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
    ]
    if IF_HEADLESS:
        # 后台跑：不给窗口，也不出声
        extra.append('--headless=new' if BROWSER_NAME == 'edge' else '--headless')
        extra.append('--mute-audio')
    if BROWSER_NAME == 'edge':
        from selenium.webdriver.edge.options import Options as EdgeOptions
        option = EdgeOptions()
    else:
        option = webdriver.ChromeOptions()
    for arg in extra:
        option.add_argument(arg)
    if BROWSER_NAME == 'edge':
        return webdriver.Edge(options=option)
    return webdriver.Chrome(options=option)


BROWSER_NAME = detect_browser()

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

print(f'\n配置信息:')
print(f'  无窗口模式: {IF_HEADLESS}')
print(f'  浏览器: {BROWSER_NAMES[BROWSER_NAME]}')
print(f'  课程URL: {COURSE_URL[:50]}...' if len(COURSE_URL) > 50 else f'  课程URL: {COURSE_URL}')
print(f'  雨课堂站点: {homePageURL}')
print(f'  UI 版本: { {True: "新版(common)", False: "旧版(legacy)", None: "待自动探测"}[IS_COMMONUI] }')
print(f'  播放倍速: {PLAYBACK_SPEED}x')
print(f'  Cookie已配置: ✓')
print('='*50 + '\n')


driver = create_driver()
if not IF_HEADLESS:
    driver.maximize_window()
driver.implicitly_wait(IMPLICITLY_WAIT)

def str2dic(s):
    d = dict()
    for i in s.split('; '):
        temp = i.split('=')
        d[temp[0]] = temp[1]
    return d


def setCookie(cookies):
    driver.delete_all_cookies()
    for name, value in cookies.items():
        driver.add_cookie({'name': name, 'value': value, 'path': '/'})


def ifVideo(div: WebElement):
    for i in div.find_elements(By.TAG_NAME, 'i'):
        i_class = i.get_attribute('class')
        if 'icon--suo' in i_class:  # 锁的图标，表明视频未开放
            return False
    
    if IS_COMMONUI:  # www.yuketang.cn，非grsbupt.yuketang.cn，属新版ui
        try:
            span = div.find_element(By.CSS_SELECTOR, 'span.leaf-flag')
        except:
            return False
        return '视频' in span.text.strip()
    
    try:
        i = div.find_element(By.TAG_NAME, 'i')
    except:
        return False  # 每个小结后面都存在空行<li>
    i_class = i.get_attribute('class')
    return 'icon--shipin' in i_class


def is_finished(unit: WebElement):
    """判断学习单元是否已完成。

    "完成情况"列的呈现各站不同：有的直接写"已完成"文字，长江雨课堂显示完成百分比
    （实测文本形如 "9.8%" / "100%"，里面没有"已完成"字样）。若只用文字判断，
    已刷完的视频会被当成未完成反复重播。
    """
    if '已完成' in unit.text:
        return True
    try:
        complete_text = unit.find_element(By.CLASS_NAME, 'complete-td').text
    except Exception:
        return False  # 取不到完成情况列，交给上层按旧口径处理
    pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', complete_text)
    return bool(pcts) and float(pcts[0]) >= 99.9


PLAYED_TITLES = set()  # 本次运行已播过/已放弃的标题，保证无人看守时绝不会原地打转
SKIPPED_STALLED = []   # 因卡住被跳过的标题，收尾时如实汇报


def video_title(unit: WebElement) -> str:
    """取小节标题。返回空串时必须被上层当成"页面还没渲染完"，不能当成合法标题。

    反例（2026-10-11 实跑踩到）：把空串写进 PLAYED_TITLES 之后，所有同样取不到标题的
    小节都会被 need_play 判成"已播过"，任务被误判成"全部播放完毕"——明明还剩几十个没刷。
    所以这里区分两种"取不到"：name-text 元素根本不存在（旧版 UI）走整块文本兜底；
    name-text 存在但内容为空，说明列表渲染到一半，返回空串让上层重来。
    """
    try:
        el = unit.find_element(By.CSS_SELECTOR, 'span.name-text')
    except Exception:
        return ' '.join(unit.text.split())[:60]
    return el.text.strip()


def need_play(unit: WebElement):
    """该单元是视频、未过期、尚未完成、且本次还没播过"""
    return (ifVideo(unit)
            and '截止' not in unit.text
            and not is_finished(unit)
            and video_title(unit) not in PLAYED_TITLES)


def getAllvideos_notFinished(allClasses: List[WebElement]):
    driver.implicitly_wait(0.1)  # 找不到元素时会找满implicitly_wait秒
    allVideos = []
    for thisClass in allClasses:
        if need_play(thisClass):
            print(f'找到未完成的视频: {thisClass.text.strip()}')
            allVideos.append(thisClass)
    driver.implicitly_wait(IMPLICITLY_WAIT)
    return allVideos


def get1video_notFinished(allClasses: List[WebElement]):
    for thisClass in allClasses:
        if need_play(thisClass):
            return thisClass
    return None


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
        driver.find_element(By.CLASS_NAME, 'login-btn')
        logged_out = True
    except Exception:
        logged_out = False
    driver.implicitly_wait(IMPLICITLY_WAIT)
    return logged_out


# homePageURL 与 IS_COMMONUI 已在读取配置后确定
driver.get(homePageURL)
setCookie({'sessionid': COOKIE})
driver.get(COURSE_URL)
sleep(3)
if at_login_page():
    print('cookie失效或设置有误，请重设cookie或选择每次扫码登录')
    driver.get(homePageURL)
    driver.find_element(By.CLASS_NAME, 'login-btn').click()
    print("请扫码登录")
    while 'courselist' not in driver.current_url:  # 判断是否已经登录成功
        sleep(0.5)
    print('登录成功')
    driver.get(COURSE_URL)


GET_VIDEO_JS = (
    # 优先现取现用：播放器会卸载重建 <video>，全局变量可能指向已脱离文档的旧元素
    'var v = document.querySelector("video");'
    'if (!v && typeof video !== "undefined" && video) { v = video; }'
    'if (!v) { return null; }'
)

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

    实测（2026-10-11，长江雨课堂 changjiang.yuketang.cn）：

      * 播放器自带的倍速 UI 点不动：xt-speedbutton 展开后，用 CDP 原生鼠标事件
        确实打到了 li（isTrusted=true、列表保持展开、元素未被遮挡），
        但 xt-speedvalue 不变、playbackRate 不变。那条路是死的，不走近它。
      * 直接写 video.playbackRate = 2，同步读回是 2，约 200ms 后就被改回 1。
        调用栈定位到播放器 chunk 27437.3f1750f6.js：它在 ratechange/timeupdate
        里把倍速同步回自己内部的 1x 状态，约每 250ms 改一次。
      * 正确做法不是对抗、而是"吞掉调低的写入"：给 HTMLMediaElement.prototype
        的 playbackRate 装一层 setter，凡是想写到目标值以下的，直接丢弃。
        播放器改不动实际值，也就不会反复重写，不会死循环。
        实测 12 秒内 currentTime 前进 23.6s / 墙钟 11.79s = 2.002x，paused=false，
        期间拦掉 49 次播放器复位。
      * 锁装在原型上而不是某个 video 元素上，所以播放器中途换掉 <video> 也不怕；
        再配一个 1 秒定时器兜底补刀。

    副作用：播放器自己的 UI 仍显示 1.00X（它内部状态没被改），纯显示问题，
    不影响实际倍速，也不影响播放与自动切集。
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


def mute1video():
    """静音。走 video.muted，不依赖 xt-volumebutton。

    这里刻意不读 main.py 里的全局 video 变量：播放器会卸载重建 <video>，
    拿旧变量可能对着一个已脱离文档的僵尸元素静音，而真正在播的那个照样出声。
    """
    try:
        return driver.execute_script(
            'var v = document.querySelector("video");'
            'if (!v) { return null; }'
            'v.muted = true;'
            'return v.muted;'
        )
    except Exception as e:
        print(f'警告: 静音失败（不影响播放与切集）: {type(e).__name__}: {e}')
        return None


def js_click(element):
    """雨课堂部分站点（实测长江雨课堂课程页）上元素虽存在但原生 click 会抛
    ElementNotInteractableException，统一改走 JS 点击。"""
    driver.execute_script('arguments[0].click()', element)


# 点标题前注入：把站点的 window.open 收编，并改写 target=_blank。
#
# 为什么非要这么做（2026-10-11 实跑踩到）：原先是"让它开新标签页 → 播完再 close"，
# 结果 driver.close() 在这站偶发卡死 20 秒（failed to close window in 20 seconds），
# 窗口管理当场错乱，后面连着几轮全废。
# 实测该站就是调 window.open(url, '_blank') 打开视频页的，把这个 URL 截下来以后
# 在当前标签页直接 driver.get(url) 一样能出可播的视频页 —— 全程只有一个窗口，
# 不需要 close，也就没有卡死的可能。
# window.open 必须返回一个假窗口对象：站点拿到返回值会调 focus()/close()，
# 直接返回 null 会让它内部抛错，可能连 URL 都不给。
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


def _units_rendered(units) -> bool:
    """小节列表是否渲染出了标题。

    实测（2026-10-11 实跑）：课程页偶尔会先吐出 80 多个空的 study-unit 骨架、
    标题稍后才填上。此时若直接往下走，取到的是空标题，会把整轮任务带偏
    （见 video_title 的说明）。宁可重载一次课程页，也别拿半成品往下跑。
    """
    driver.implicitly_wait(0.1)
    try:
        for u in units[:5]:
            if video_title(u):
                return True
        return False
    finally:
        driver.implicitly_wait(IMPLICITLY_WAIT)


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
        units = []
        for attempt in (1, 2, 3):
            click_report_tab()
            sleep(2)  # 小节列表是点完标签后异步渲染的，给渲染留点时间
            units = driver.find_elements(By.CLASS_NAME, 'study-unit')
            if not units or _units_rendered(units):
                return units
            print(f'提示: 小节列表出来了但标题还是空的（第 {attempt} 次），重新加载课程页')
            driver.get(COURSE_URL)
            sleep(4)
        return units
    return driver.find_elements(By.CLASS_NAME, 'leaf-detail')


ABORTED_NO_CLASSES = False  # 因为一个小节都没找到而中止，结尾不能报"播放完毕"
ABORTED_ERRORS = False      # 连续出错而中止


def back_to_course_page():
    """确保回到课程页，并且不留下多余窗口。

    正常情况下现在只有 1 个窗口（点标题不再开新标签页，见 CAPTURE_VIDEO_URL_JS），
    这里主要是兜底：万一哪一轮 window.open 拦截没生效、真开了新标签页，
    必须把它清掉，否则下一轮点击又会多开一个，窗口越堆越多。

    但 close 本身在这站有概率卡住 20 秒（2026-10-11 实跑：
    "failed to close window in 20 seconds"），所以：
      - 循环有上限，绝不无限重试；
      - close 失败就把那个窗口导航到 about:blank，至少别让它停在视频页继续占资源；
      - 无论如何最后都重定向回课程页。
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
    driver.get(COURSE_URL)
    if len(driver.window_handles) > 1:
        print(f'  注意: 当前仍有 {len(driver.window_handles)} 个窗口，下一轮可能会受影响')


def dump_dom():
    """一个小节都找不到时，把现场落盘，便于比对站点 UI 结构差异"""
    try:
        with open('_debug_page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        counts = {}
        for el in driver.find_elements(By.XPATH, '//*[@class]'):
            for c in (el.get_attribute('class') or '').split():
                counts[c] = counts.get(c, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:15]
        print('  页面 class 采样(出现最多): ' + ', '.join(f'{k}x{v}' for k, v in top))
        print(f'  页面源码已保存: {os.path.abspath("_debug_page_source.html")}')
    except Exception as e:
        print(f'  现场落盘失败: {e}')


def finish1video():
    global ABORTED_NO_CLASSES
    allClasses = load_classes()
    if not allClasses:
        # 必须显式告警：否则会一路 return False，主循环结束并打印"全部播放完毕"，
        # 看起来像刷成功了，其实一个视频都没播。
        ABORTED_NO_CLASSES = True
        print('警告: 页面上没有找到任何小节元素，本次不会播放任何视频')
        print(f'  当前 UI 判定: {"新版(common)" if IS_COMMONUI else "旧版(legacy)"}')
        print(f'  当前 URL: {driver.current_url}')
        print(f'  页面标题: {driver.title}')
        print('  常见原因: 课程页没加载完 / 未登录成功 / 该站点 UI 结构与已知两套都不同')
        dump_dom()
        return False
    print('正在寻找未完成的视频，请耐心等待')
    allVideos = getAllvideos_notFinished(allClasses)
    if not allVideos:
        return False
    video = allVideos[0]
    title = video_title(video)
    if not title:
        # 关键防线：空标题绝不能进 PLAYED_TITLES。否则这一轮的"页面没渲染完"
        # 会被永久记成"这些小节都播过了"，下一轮直接报"全部播放完毕"收工。
        print('警告: 选中的小节连标题都取不到，课程页很可能没渲染完，本轮放弃重来')
        return None
    PLAYED_TITLES.add(title)
    print(f'目标: {title}')
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
        print(f'正在播放（新标签页 —— window.open 拦截没生效，已改写 {retargeted} 个 target）')
    else:
        opened_new_window = False
        if video_url:
            # 拦截生效：URL 拿到了，但当前页没动，需要自己跳过去
            driver.get(video_url)
            print('正在播放（当前标签页直达视频页）')
        else:
            print('正在播放（站点自己完成了当前页跳转）')

    def leave_video_window():
        """离开视频页。先把注入拆干净，再处理窗口。

        不管后面走哪个分支，第一步都必须是"停掉自己注入的定时器和监听、置 __ytDone"，
        否则页面卸载时会和播放器打架，close 直接卡死 20 秒
        （2026-10-11 实跑：failed to close window in 20 seconds）。
        """
        try:
            driver.execute_script(
                'window.__ytDone = true;'
                'try { clearInterval(window.__ytTimer); } catch (e) {}'
                'try { clearInterval(videoPlay); } catch (e) {}'
                'try { window.onbeforeunload = null; } catch (e) {}'
            )
        except Exception:
            pass
        if opened_new_window:
            try:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
            except Exception as e:
                first_line = str(e).splitlines()[0][:130] if str(e) else ''
                print(f'  关闭视频窗口时出错（继续）: {type(e).__name__}: {first_line}')

    try:
        WebDriverWait(driver, 10).until(lambda x: driver.execute_script('video = document.querySelector("video"); console.log(video); return video;'))  # 这里即使2次sleep3s选中的video还是null
    except Exception:
        # 视频页没起来（实测会发生在上一轮窗口状态已经乱了的时候）。
        # 明确报"本轮没进展"，并把注入拆干净再退出，别把异常丢给主循环。
        print('警告: 视频页 10 秒内没有出现 video 元素，本轮放弃')
        leave_video_window()
        return None

    driver.execute_script('videoPlay = setInterval(function() {var v = document.querySelector("video"); if (v && v.paused) {v.play();}}, 200);')
    driver.execute_script('setTimeout(() => clearInterval(videoPlay), 5000)')
    driver.execute_script('addFinishMark = function() {finished = document.createElement("span"); finished.setAttribute("id", "LetMeFly_Finished"); document.body.appendChild(finished); console.log("Finished");}')
    driver.execute_script('lastDuration = 0; setInterval(() => {var v = document.querySelector("video"); if (!v) {return;} nowDuration = v.currentTime; if (nowDuration < lastDuration) {addFinishMark()}; lastDuration = nowDuration}, 200)')
    # 播放器带防刷逻辑（页面失焦/不可见就 pause），这里挂到 document 捕获阶段而不是
    # 全局 video 变量上：pause 不冒泡，但捕获阶段能收到；换掉 <video> 也不会失效。
    # __ytDone 一旦置位就放手 —— 否则离开页面时这个"续播"监听会和卸载流程互相顶。
    driver.execute_script(
        'document.addEventListener("pause", function (e) {'
        '  try { if (!window.__ytDone && e.target && e.target.tagName === "VIDEO") { e.target.play(); } }'
        '  catch (err) {}'
        '}, true)'
    )
    mute1video()
    change2speed2()

    last_pos = -1.0
    last_t = None
    measured = None
    stalled = 0
    while True:
        # 判据一：原实现的"时间回退"标记（播放器自动循环时会命中）
        if driver.execute_script('return document.querySelector("#LetMeFly_Finished");'):
            print('检测到播放结束标记，再等 5 秒')
            sleep(5)
            leave_video_window()
            return True

        # 判据二：直接看播放器状态。播放器播完就停住不循环时，判据一永远不会命中，
        # 挂后台就会无限等下去，所以这里补上 ended / 接近结尾的显式判断。
        try:
            info = driver.execute_script(
                GET_VIDEO_JS + 'return [v.currentTime || 0, v.duration || 0, v.ended ? 1 : 0];'
            )
        except Exception:
            info = None

        if info:
            pos, dur, ended = info
            if ended or (dur and pos >= dur - 0.5):
                print(f'播放已到结尾（{pos:.1f}s / {dur:.1f}s）')
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
            print(f'正在播放视频 | 已播 {pos:.0f}s / 共 {dur:.0f}s{speed_txt}')
        else:
            stalled += 1

        # 判据三：兜底。真卡死了也要能跳到下一集，别把整晚耗在同一个视频上
        if stalled >= 100:  # 约 5 分钟没有任何前进
            print('警告: 视频 5 分钟没有前进，放弃这一集，跳到下一个')
            SKIPPED_STALLED.append(title)
            leave_video_window()
            return True
        sleep(3)
    return False


consecutive_errors = 0
no_progress_rounds = 0
total_played = 0
ABORTED_NO_PROGRESS = False   # 连续几轮一个视频都没真正开起来
while True:
    try:
        played = finish1video()
        consecutive_errors = 0
    except Exception as e:
        # 挂后台无人看守，单轮异常不能把整个任务带走
        consecutive_errors += 1
        print(f'本轮出错（连续第 {consecutive_errors} 次）: {type(e).__name__}: {e}')
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
        print(f'本轮没有任何进展（连续第 {no_progress_rounds} 次），回课程页重来')
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
    print(f'—— 已播完 {total_played} 个视频，切下一个 ——')
    back_to_course_page()
    sleep(5)  # thanks for @420xincheng's #8

driver.quit()
if ABORTED_NO_CLASSES:
    print('已中止: 未找到任何小节元素，视频没有被播放，请查看上面的警告信息')
elif ABORTED_ERRORS:
    print('已中止: 连续出错，任务没有跑完。重跑会接着刷没完成的。')
elif ABORTED_NO_PROGRESS:
    print(f'已中止: 连续 3 轮没能开始播放任何视频（本次共播出 {total_played} 个）。')
    print('  这不代表刷完了。常见原因是课程页没渲染完或窗口状态异常，重跑一般能接着刷。')
else:
    print(f'恭喜你！全部播放完毕（本次共播出 {total_played} 个视频）')
    if SKIPPED_STALLED:
        print(f'注意: 有 {len(SKIPPED_STALLED)} 个视频因播放卡住被跳过，重跑会再试:')
        for t in SKIPPED_STALLED:
            print(f'  - {t}')
sleep(5)
