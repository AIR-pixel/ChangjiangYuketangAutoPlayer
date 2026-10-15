'''
长江雨课堂 - 登录凭据（sessionid）获取 + config.ini 读写

取 sessionid 的两条路径（按顺序试）：
  1) 直接读本机 Firefox 的 cookie 库 —— Firefox 的 cookie 是明文 SQLite，
     只要 Firefox 里还登录着雨课堂就能秒取，不用扫码；
  2) 回退到开一个可见浏览器扫码登录。

出于凭据安全考虑，不打印 sessionid 的内容。
读 Firefox 全程只读：复制副本后以 mode=ro 查询，绝不修改 Firefox 的任何文件。
'''
import configparser
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from glob import glob
from time import sleep

TARGET_HOST = 'changjiang.yuketang.cn'
COOKIE_NAME = 'sessionid'
FIREFOX_PROFILES = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
SCAN_TIMEOUT = 300

BROWSER_PATHS = {
    'edge': [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
    ],
    'chrome': [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    ],
}

# 新建 config.ini 时先铺的底。带注释的完整清单在 config.ini.example（给人看的样板）。
DEFAULT_SETTINGS = (
    ('headless', 'true'),
    ('browser', 'auto'),
    ('ui', 'auto'),
    ('course_url', ''),
    ('cookie', ''),
    ('speed', '2'),
    ('implicitly_wait', '10'),
)
CONFIG_HEADER = '; 长江雨课堂 配置文件（程序自动生成，各项含义见 README.md）\n'


def app_dir() -> str:
    """程序所在目录。

    冻结（打包成 exe）时用 `sys.executable` —— 那时候 `__file__` 指向 PyInstaller
    解包出来的临时目录，config.ini 会被写到那里、随进程一起消失。

    源码运行时用 `__file__` 而不是 `sys.argv[0]`：argv[0] 是"被运行的那个脚本"的路径，
    `tools/` 里的辅助脚本一 import 本模块，它就会把程序目录算成 `tools/`。
    `__file__` 是模块自己的位置，跟谁 import 无关。
    """
    base = sys.executable if getattr(sys, 'frozen', False) else __file__
    return os.path.dirname(os.path.abspath(base))


def bypass_proxy_for_localhost():
    """把本机地址补进 NO_PROXY。

    selenium 客户端会读 `HTTP(S)_PROXY` 环境变量。浏览器驱动监听在本机端口上，
    如果不排除本机地址，发往驱动的请求会被代理劫持，所有命令一律返回
    "unhandled request" —— 看起来像 selenium 坏了，其实是代理把它截走了。
    """
    for var in ('NO_PROXY', 'no_proxy'):
        missing = [h for h in ('localhost', '127.0.0.1', '::1')
                   if h not in os.environ.get(var, '')]
        if missing:
            old = os.environ.get(var, '').strip(',')
            os.environ[var] = f'{old},{",".join(missing)}'.strip(',')


def setup_output():
    """把 stdout/stderr 固定成「UTF-8 + 逐行刷出」。

    两件事都是被实际场景逼出来的，缺一样都会在"挂后台跑一整晚"时咬人：

    1) **编码**。Windows 上 stdout 被重定向（`exe > run.log`、管道、被调度器接管）
       时，Python 不走控制台那套 UTF-16 通道，而是退回系统 ANSI 代码页（简中 = GBK）。
       于是日志里只要有一个 GBK 表外的字符 —— 比如那个 `✓` —— 就会 UnicodeEncodeError
       把程序打死在启动阶段。实测打包后的 exe 重定向输出就是这么崩的。
       errors='replace' 保证以后再有类似字符最多显示成 `?`，不会连带整个任务一起没。

    2) **行缓冲**。重定向后 stdout 默认是 8KB 块缓冲：日志要攒够一大坨才落盘，
       进程被 kill 时缓冲区里的一整段直接丢掉。而"跑一半被人关掉/超时被杀"
       恰恰是这类后台任务的常态 —— 恰恰是最需要日志的时候什么都没有。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding='utf-8', errors='replace',
                                   line_buffering=True)
        except Exception:
            pass  # 不是 TextIOWrapper（被换过、已关闭等）就算了，不值得因此报错


def config_path() -> str:
    return os.path.join(app_dir(), 'config.ini')


def read_config(path):
    """读 config.ini。插值关掉 —— % 在 sessionid / URL 里只是普通字符。"""
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(path, encoding='utf-8')
    return cfg


def set_config_value(path: str, key: str, value: str):
    """把 `key = value` 写进 config.ini 的 [Settings]。

    文件不存在就按 DEFAULT_SETTINGS 新建；已存在则只改这一行，
    其余内容（注释、别的项、用户自己的改动）原样保留。
    """
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        text = CONFIG_HEADER + '\n[Settings]\n' + ''.join(f'{k} = {v}\n' for k, v in DEFAULT_SETTINGS)

    pattern = rf'(?m)^{re.escape(key)}\s*=.*$'
    # 用函数当替换体，避免 value 里的反斜杠被当成 re 的转义
    new_text, n = re.subn(pattern, lambda m: f'{key} = {value}', text)
    if n == 0:
        if '[Settings]' not in text:
            text = text.rstrip('\n') + '\n\n[Settings]\n'
        i = text.index('[Settings]') + len('[Settings]')
        j = text.find('\n[', i)              # 下一个 section 的开头
        j = len(text.rstrip('\n')) if j < 0 else j
        new_text = text[:j].rstrip('\n') + f'\n{key} = {value}\n' + text[j:].lstrip('\n')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_text)


def write_cookie(value: str, path: str = None):
    """把 sessionid 写进 config.ini（不回显内容）。"""
    set_config_value(path or config_path(), COOKIE_NAME, value)


def read_from_firefox():
    """从最新的 Firefox profile 里读 sessionid（只读副本）"""
    dbs = glob(os.path.join(FIREFOX_PROFILES, '*', 'cookies.sqlite'))
    if not dbs:
        print('  Firefox: 没找到任何 profile 的 cookies.sqlite')
        return None
    dbs.sort(key=os.path.getmtime, reverse=True)
    src = dbs[0]
    print(f'  Firefox profile: {os.path.basename(os.path.dirname(src))}')

    tmp = tempfile.mkdtemp(prefix='yap_ck_')
    try:
        for fn in ('cookies.sqlite', 'cookies.sqlite-wal', 'cookies.sqlite-journal'):
            p = os.path.join(os.path.dirname(src), fn)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(tmp, fn))
        con = sqlite3.connect(f'file:{os.path.join(tmp, "cookies.sqlite")}?mode=ro', uri=True)
        row = con.execute(
            'SELECT value FROM moz_cookies WHERE host = ? AND name = ?',
            (TARGET_HOST, COOKIE_NAME),
        ).fetchone()
        con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not row or not row[0]:
        print(f'  Firefox: 库里没有 {TARGET_HOST} 的 {COOKIE_NAME}（可能没在那里登录过）')
        return None
    print(f'  Firefox: 取到 {COOKIE_NAME}，长度 {len(row[0])}')
    return row[0]


def read_by_qrcode():
    """回退方案：开一个可见浏览器扫码登录"""
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    name = 'edge' if any(os.path.exists(p) for p in BROWSER_PATHS['edge']) else 'chrome'
    if name == 'edge':
        from selenium.webdriver.edge.options import Options
    else:
        from selenium.webdriver.chrome.options import Options
    option = Options()
    option.add_argument('--start-maximized')

    driver = webdriver.Edge(options=option) if name == 'edge' else webdriver.Chrome(options=option)
    try:
        driver.implicitly_wait(5)
        # 同上：不设上限的话站点抽风会一路挂到 urllib3 的 120 秒读超时
        driver.set_page_load_timeout(60)
        try:
            driver.get(f'https://{TARGET_HOST}/')
        except Exception:
            pass  # 超时也接着试，页面往往已经能用了
        sleep(2)
        try:
            driver.find_element(By.CLASS_NAME, 'login-btn').click()
        except Exception:
            pass
        print('=' * 56)
        print(f'请在浏览器窗口里用微信扫码登录（最多等 {SCAN_TIMEOUT // 60} 分钟）')
        print('=' * 56)

        waited = 0
        stable = 0
        while waited < SCAN_TIMEOUT:
            sleep(1)
            waited += 1
            on_login = ('登录' in (driver.title or '')) or ('/web/?next=' in driver.current_url)
            if on_login:
                stable = 0
            else:
                stable += 1
                if stable >= 2:
                    break
            if waited % 15 == 0:
                print(f'  等待扫码中... {waited}s')

        if waited >= SCAN_TIMEOUT:
            print('超时，没检测到登录成功')
            return None
        try:
            driver.get(f'https://{TARGET_HOST}/v2/web/index')
        except Exception:
            pass
        sleep(3)
        ck = driver.get_cookie(COOKIE_NAME)
        return ck['value'] if ck else None
    finally:
        driver.quit()


def get_sessionid(use_firefox=True, use_qr=True):
    """按顺序取 sessionid；都没拿到就返回 None。"""
    if use_firefox:
        try:
            value = read_from_firefox()
        except Exception as e:
            # 读库只是"省一次扫码"的捷径，任何意外（库损坏、权限、格式变化）
            # 都不该让流程带 traceback 死掉 —— 回退扫码即可。
            print(f'  Firefox: 读取失败（{type(e).__name__}: {e}），改用扫码')
            value = None
        if value:
            return value
    if use_qr:
        return read_by_qrcode()
    return None


def main():
    """独立入口：只换 sessionid，不碰 course_url。给 refresh_cookie.bat 用。"""
    setup_output()
    path = config_path()
    value = get_sessionid()          # 内部顺序就是「先 Firefox，读不到再扫码」
    if not value:
        print('\n失败：没有拿到 sessionid')
        return 1

    write_cookie(value, path)
    print('=' * 56)
    print(f'成功：sessionid 已写入 {path}（长度 {len(value)}，内容不回显）')
    print('=' * 56)
    return 0


if __name__ == '__main__':
    sys.exit(main())
