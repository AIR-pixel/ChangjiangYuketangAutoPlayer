'''
长江雨课堂 - 首次配置向导

目标：下载解压后双击就能跑，不用手填任何东西。

  第 1 步  拿登录凭据 —— 优先读本机 Firefox 的明文 cookie 库（秒取，不用扫码），
                        读不到就开一个可见浏览器扫码；
  第 2 步  选课程     —— 用这个凭据调站点接口列出该账号的课程，挑一门写进 config.ini。

课程列表走纯 HTTP（实测 0.2 秒返回），不值得为它单开一个浏览器。
判定"凭据还有没有效"用的也是这个接口：能列出课程就说明还有效，不打扰用户。
'''
import json
import urllib.request

import refresh_cookie

DEFAULT_HOST = 'https://' + refresh_cookie.TARGET_HOST + '/'
COURSE_LIST_API = '/v2/api/web/courses/list?identity=2'
HTTP_TIMEOUT = 12
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def host_of(url: str) -> str:
    """从课程地址里取站点根地址。"""
    return 'https://' + url.split('//', 1)[-1].split('/')[0] + '/'


def course_url_of(host: str, classroom_id) -> str:
    return f'{host.rstrip("/")}/v2/web/studentLog/{classroom_id}'


def _open(url, headers, timeout=HTTP_TIMEOUT):
    """先按系统/环境代理设置请求，失败再直连试一次。

    本机系统代理配错是很常见的情况（实测遇到过），不该让它把整个向导卡死；
    但也不能一上来就无视用户的代理设置（有人确实要靠它出去）。
    """
    last = None
    for opener in (urllib.request.build_opener(),
                   urllib.request.build_opener(urllib.request.ProxyHandler({}))):
        try:
            return opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
        except Exception as e:
            last = e
    raise last


def fetch_courses(sessionid: str, host: str):
    """列出该账号的课程。

    返回 [{'id', 'title', 'class_name', 'teacher', 'school'}]；
    凭据失效时接口会返回非 0 的 errcode，这里抛异常让调用方去换凭据。
    """
    host = host.rstrip('/') + '/'
    req_headers = {
        'Cookie': f'sessionid={sessionid}',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': UA,
        'Referer': host + 'v2/web/index',
    }
    with _open(host + COURSE_LIST_API.lstrip('/'), req_headers) as resp:
        data = json.loads(resp.read().decode('utf-8', 'replace'))

    if data.get('errcode'):
        raise RuntimeError(f"接口返回 errcode={data.get('errcode')}: {data.get('errmsg')}")

    courses = []
    for c in (data.get('data') or {}).get('list') or []:
        course = c.get('course') or {}
        if not c.get('classroom_id'):
            continue
        courses.append({
            'id': c['classroom_id'],
            'title': course.get('name') or c.get('name') or '(无标题课程)',
            'class_name': c.get('name') or '',
            'teacher': (c.get('teacher') or {}).get('name') or '',
            'school': course.get('university_name') or '',
        })
    return courses


def _ask(prompt: str, default: str = '') -> str:
    try:
        return input(prompt).strip() or default
    except EOFError:
        # 非交互环境（输出被重定向、没有控制台）下不要炸，按默认值走
        return default


def _cfg_get(cfg, key):
    try:
        return (cfg.get('Settings', key) or '').strip()
    except Exception:
        return ''


def _choose_course(courses, host: str):
    print('\n可选的课程：')
    for i, c in enumerate(courses, 1):
        print(f'  [{i}] {c["title"]}')
        detail = ' · '.join(x for x in (
            f'教学班 {c["class_name"]}' if c['class_name'] else '',
            f'教师 {c["teacher"]}' if c['teacher'] else '',
            c['school'],
        ) if x)
        if detail:
            print(f'      {detail}')
    print('  [0] 手动输入课程地址')

    while True:
        ans = _ask('\n请输入序号（直接回车 = 1）: ', '1')
        if ans.isdigit() and int(ans) <= len(courses):
            break
        print('  输入无效，请重新输入')

    index = int(ans)
    if index == 0:
        manual = _ask('请粘贴课程地址（https:// 开头）: ')
        return manual if manual.startswith('http') else None
    c = courses[index - 1]
    url = course_url_of(host, c['id'])
    print(f'  已选择: {c["title"]} -> {url}')
    return url


def ensure_ready(path: str) -> bool:
    """把 config.ini 补到"能跑"：course_url + cookie。缺哪一步就补哪一步。

    已有且仍然有效的 cookie 不会打扰用户重取 —— 判定方法是拿它去列课程，
    列得出来就说明还有效（这一步顺带把课程列表也拿到了）。
    """
    print('=' * 56)
    print('长江雨课堂 - 首次配置')
    print('=' * 56)

    cfg = refresh_cookie.read_config(path)
    url = _cfg_get(cfg, 'course_url')
    cookie = _cfg_get(cfg, 'cookie')
    host = host_of(url) if url.startswith('http') else DEFAULT_HOST

    # ---- 第 1 步：登录凭据 ----
    courses = None
    if cookie:
        try:
            courses = fetch_courses(cookie, host)
            print(f'  已保存的登录凭据仍然有效（读到 {len(courses)} 门课程）')
        except Exception as e:
            print(f'  已保存的登录凭据不可用（{type(e).__name__}: {e}），需要重新获取')

    if not cookie or courses is None:
        print('\n第 1 步 / 2：获取登录凭据')
        cookie = refresh_cookie.get_sessionid()
        if not cookie:
            print('\n没有拿到登录凭据，配置未完成。')
            return False
        refresh_cookie.set_config_value(path, 'cookie', cookie)
        print(f'  已写入 config.ini（长度 {len(cookie)}，内容不回显）')
        try:
            courses = fetch_courses(cookie, host)
        except Exception as e:
            print(f'  读取课程列表失败（{type(e).__name__}: {e}），下面手动填课程地址')
            courses = None

    # ---- 第 2 步：课程 ----
    if url.startswith('http'):
        print(f'\n第 2 步 / 2：课程地址已配置 —— {url}')
        print('  想换课程：把 config.ini 里的 course_url 清空，再跑一次即可')
        return True

    if courses:
        chosen = _choose_course(courses, host)
    else:
        print('\n第 2 步 / 2：手动输入课程地址')
        print('  拿法：浏览器进长江雨课堂 → 打开那门课 → 点「学习内容」→ 复制地址栏')
        chosen = _ask('课程地址（https:// 开头）: ')

    if not chosen or not chosen.startswith('http'):
        print('\n课程地址无效，配置未完成。')
        return False
    refresh_cookie.set_config_value(path, 'course_url', chosen)
    print(f'  已写入 config.ini: {chosen}')
    print('\n配置完成。')
    return True
