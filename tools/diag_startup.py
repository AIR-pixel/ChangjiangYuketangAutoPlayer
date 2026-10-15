# -*- coding: utf-8 -*-
"""量一下"启动到能读小节"各阶段各花多久，并对比 page_load_strategy。

为什么需要这个：站点是 SPA 且挂着常驻连接，`load` 事件可能永远不触发，
而 Selenium 的 `driver.get()` 默认等的就是 `load` 事件 —— 于是每次启动都
白白耗掉 PAGE_LOAD_TIMEOUT 的整数倍。`page_load_strategy='eager'`
（等到 DOMContentLoaded 就返回）是不是真能治，这个脚本量给你看。

只读：只创建浏览器、打开页面、数一下 DOM 元素，不点视频、不改配置。

用法：
    python tools/diag_startup.py                 # 两种策略各跑一遍
    python tools/diag_startup.py --only eager
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh_cookie  # noqa: E402  （共用 config 读取与 app_dir）

refresh_cookie.bypass_proxy_for_localhost()   # 否则驱动端口被代理劫持 -> unhandled request
refresh_cookie.setup_output()

from selenium import webdriver                      # noqa: E402
from selenium.webdriver.common.by import By         # noqa: E402

TAB_ID = 'tab-student_school_report'


def make_driver(strategy: str, headless=True):
    from selenium.webdriver.edge.options import Options
    o = Options()
    o.page_load_strategy = strategy
    if headless:
        o.add_argument('--headless=new')
    o.add_argument('--window-size=1920,1080')
    o.add_argument('--disable-gpu')
    return webdriver.Edge(options=o)


def phase(label, fn):
    t = time.time()
    try:
        result = fn()
        mark = ''
    except Exception as e:
        result, mark = None, f'  !! {type(e).__name__}'
    print(f'  {time.time() - t:7.2f}s  {label}{mark}')
    return result


def run(strategy, cookie, course_url, host):
    print(f'\n=== page_load_strategy = {strategy} ===')
    d = make_driver(strategy)
    d.set_page_load_timeout(90)
    d.implicitly_wait(10)
    try:
        def go(u):
            try:
                d.get(u)
                return 'ok'
            except Exception as e:
                return f'{type(e).__name__}'

        phase('打开首页', lambda: go(host))
        phase('注入 cookie', lambda: (d.delete_all_cookies(),
                                     d.add_cookie({'name': 'sessionid', 'value': cookie, 'path': '/'})))
        phase('打开课程页', lambda: go(course_url))
        phase('等 3 秒', lambda: time.sleep(3))
        print(f'          readyState = {d.execute_script("return document.readyState")}')
        # 必须真点一下：小节列表是点完"学习报告"标签才异步渲染出来的
        phase('点学习报告标签', lambda: d.execute_script(
            'arguments[0].click()', d.find_element(By.ID, TAB_ID)))
        phase('等 2 秒', lambda: time.sleep(2))
        n = phase('数 study-unit（含 implicitly_wait 兜底等待）',
                  lambda: len(d.find_elements(By.CLASS_NAME, 'study-unit')))
        print(f'  -> 读到 {n} 个小节')
    finally:
        d.quit()


def main():
    only = None
    if '--only' in sys.argv:
        only = sys.argv[sys.argv.index('--only') + 1]

    cfg = refresh_cookie.read_config(refresh_cookie.config_path())
    cookie = (cfg.get('Settings', 'cookie', fallback='') or '').strip()
    course_url = (cfg.get('Settings', 'course_url', fallback='') or '').strip()
    if not cookie or not course_url.startswith('http'):
        sys.exit('需要先在 config.ini 里配好 cookie 和 course_url')
    host = 'https://' + course_url.split('//', 1)[-1].split('/')[0] + '/'
    print(f'课程页: {course_url}')

    for strategy in ('eager', 'normal'):
        if only in (None, strategy):
            run(strategy, cookie, course_url, host)


if __name__ == '__main__':
    main()
