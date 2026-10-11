'''
Author: Vane（本机适配）
Description: 刷新 config.ini 里的 sessionid，两条路径：
             1) 优先直接读本机 Firefox 的 cookie 库（Firefox 的 cookie 是明文存储，
                只要 Firefox 里还登录着雨课堂就能秒取，不用扫码）
             2) Firefox 里没有有效登录时，回退到打开浏览器扫码登录
             出于凭据安全考虑，本脚本不打印 sessionid 的内容。
             全程只读：复制 cookie 库副本后查询，绝不修改 Firefox 的任何文件。
'''
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
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_DIR, 'config.ini')
FIREFOX_PROFILES = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
SCAN_TIMEOUT = 300

BROWSER_PATHS = {
    'edge': [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ],
    'chrome': [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ],
}


def write_cookie(value):
    """写进 config.ini，保留注释与其它配置项"""
    with open(CONFIG_PATH, encoding='utf-8') as f:
        text = f.read()
    # configparser 默认开启 % 插值，值里的 % 需要转义
    safe = value.replace('%', '%%')
    new_text, n = re.subn(r'(?m)^cookie\s*=.*$', 'cookie = ' + safe, text)
    if n == 0:
        new_text = text.rstrip() + '\ncookie = ' + safe + '\n'
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(new_text)


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
    """回退方案：开浏览器扫码登录"""
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    name = 'edge' if os.path.exists(BROWSER_PATHS['edge'][0]) or os.path.exists(
        BROWSER_PATHS['edge'][1]) else 'chrome'
    if name == 'edge':
        from selenium.webdriver.edge.options import Options
    else:
        from selenium.webdriver.chrome.options import Options
    option = Options()
    option.add_argument('--start-maximized')

    driver = webdriver.Edge(options=option) if name == 'edge' else webdriver.Chrome(options=option)
    try:
        driver.implicitly_wait(5)
        driver.get(f'https://{TARGET_HOST}/')
        sleep(2)
        try:
            driver.find_element(By.CLASS_NAME, 'login-btn').click()
        except Exception:
            pass
        print('=' * 56)
        print('请在浏览器窗口里用微信扫码登录（最多等 5 分钟）')
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
        driver.get(f'https://{TARGET_HOST}/v2/web/index')
        sleep(3)
        ck = driver.get_cookie(COOKIE_NAME)
        return ck['value'] if ck else None
    finally:
        driver.quit()


def main():
    if not os.path.exists(CONFIG_PATH):
        print(f'找不到 {CONFIG_PATH}，请先运行一次 run.bat 生成模板')
        return 1

    print('尝试从本机 Firefox 读取 sessionid ...')
    value = read_from_firefox()

    if not value:
        print('\nFirefox 路径不适用，改用扫码登录 ...')
        value = read_by_qrcode()

    if not value:
        print('\n失败：没有拿到 sessionid')
        return 1

    write_cookie(value)
    print('=' * 56)
    print(f'成功：sessionid 已写入 {CONFIG_PATH}（长度 {len(value)}，内容不回显）')
    print('=' * 56)
    return 0


if __name__ == '__main__':
    sys.exit(main())
