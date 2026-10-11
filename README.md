# 长江雨课堂

[长江雨课堂](https://changjiang.yuketang.cn/)（`changjiang.yuketang.cn`）的视频自动播放脚本。
无头后台运行，边跑边干别的，自动切换下一集，真实 2 倍速。

已播完的不会重播，中途关掉重跑会接着刷没看完的。

---

## 快速开始

### 1. 装环境

Python 3.8+，然后：

```bash
pip install selenium
```

浏览器用 **Edge** 或 **Chrome** 都行（脚本自动探测），**驱动不用自己下** —— selenium 4.x 会匹配对应版本。

### 2. 取 cookie

双击 `refresh_cookie.bat`。

它会优先直接读本机 Firefox 的 cookie 库（Firefox 里还登录着长江雨课堂的话秒取，不用扫码），
读不到才开浏览器让你扫码，拿到后自动写进 `config.ini`，**且不回显 cookie 内容**。

> 长江雨课堂的 `sessionid` 和 `www.yuketang.cn` 的是**两套**，必须从同一个域名下取。

### 3. 填课程地址

打开 `config.ini`，把 `course_url` 换成你的课：

```ini
[Settings]
headless = true
browser = auto
ui = auto
course_url = https://changjiang.yuketang.cn/v2/web/studentLog/1234567
cookie = 已由上一步自动填好
speed = 2
implicitly_wait = 10
```

课程地址怎么拿：进长江雨课堂 → 找到那门课 → 点「学习内容」→ 复制地址栏（要 `https://` 开头）。

### 4. 开跑

双击 `run.bat`，或者 `python main.py`。

```
目标: 国防建设
正在播放（当前标签页直达视频页）
已锁定播放速度: 2x（已拦截播放器复位 4 次；播放器 UI 可能仍显示 1.00X，属正常）
正在播放视频 | 已播 136s / 共 1183s | 实测倍速 2.02x
检测到播放结束标记，再等 5 秒
—— 已播完 1 个视频，切下一个 ——
```

## 跑完之后

结尾会明确告诉你是哪种情况，**不会把"跑失败"说成"刷完了"**：

| 结尾输出 | 含义 |
|---|---|
| `恭喜你！全部播放完毕` | 确实没有没看完的视频了 |
| `已中止: 连续 3 轮没能开始播放任何视频…` | 页面没渲染完或窗口状态异常，**不是刷完了**，重跑接着刷 |
| `已中止: 连续出错…` | 连续 3 轮抛异常，重跑接着刷 |
| `已中止: 未找到任何小节元素…` | 没登录成功 / 课程页没加载完 |

## 配置项

| 项 | 默认 | 说明 |
|---|---|---|
| `headless` | `true` | 无窗口运行。挂后台就用 `true` |
| `browser` | `auto` | `chrome` / `edge` / `auto` |
| `ui` | `auto` | 前端版本，一般别动 |
| `course_url` | — | 课程地址 |
| `cookie` | — | `sessionid`，交给 `refresh_cookie.bat` 自动填 |
| `speed` | `2` | 倍速，`1` = 原速，范围 `0.5 ~ 4` |
| `implicitly_wait` | `10` | 元素查找超时（秒），一般别动 |

## 注意事项

**必须绕开系统代理。** selenium 客户端会读 `HTTP(S)_PROXY` 环境变量，不排除本机地址的话，
发往本地 WebDriver 端口的请求会被代理劫持，所有命令一律返回 `unhandled request`。
`run.bat` 里已经设好了，`main.py` 启动时也会补上：

```bat
set "NO_PROXY=localhost,127.0.0.1,::1"
```

在 IDE / Jupyter 里跑的话，需要自己确认这个环境变量。

**倍速会缩短实际耗时。** 有些课除了看视频还查学习时长，`speed = 2` 下耗时只有一半，自己权衡。

**想开窗口看过程**（`headless = false`）也行，但该站播放器有防刷逻辑，页面一失焦就暂停视频。
脚本会顶回去，但来回拉扯可能影响进度上报，还是推荐无头。

**打包成 exe**：`pyinstaller ChangjiangYuketang.spec --clean`。

## 实现细节

倍速是怎么真的锁住的、窗口为什么会卡死 20 秒、什么情况下会误报"刷完了" ——
这些踩坑记录在 [`docs/技术细节.md`](docs/技术细节.md)。

## 来源与授权

本项目基于 **[LetMeFly666/YuketangAutoPlayer](https://github.com/LetMeFly666/YuketangAutoPlayer)** 改造，
基础代码与思路来自上游，感谢原作者 [@LetMeFly666](https://github.com/LetMeFly666) 及各位贡献者。

上游是通用的雨课堂脚本；这里针对性改成了**长江雨课堂**专用：适配 `changjiang.yuketang.cn` 的前端结构、
修掉该站特有的窗口卡死与误报完成、把 2 倍速真正做到生效。

代码按 **LGPL-2.1** 授权，见 [`LICENSE`](LICENSE)。本仓库**不含**上游打包好的 `YuketangAutoPlayer.exe`，
请从源码运行。

## 免责声明

仅供 selenium 技术的学习与实践。请勿用于违反你所在学校规定的用途，由此产生的后果由使用者自负。
