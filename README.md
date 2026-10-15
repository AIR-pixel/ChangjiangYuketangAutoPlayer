# 长江雨课堂

[长江雨课堂](https://changjiang.yuketang.cn/)（`changjiang.yuketang.cn`）的视频自动播放脚本。
无头后台运行，边跑边干别的，自动切换下一集，真实 2 倍速。

已播完的不会重播，中途关掉重跑会接着刷没看完的。

---

## 快速开始

**不用手填任何东西**：第一次运行会自己弹配置向导 —— 先自动取登录凭据，再列出你账号
下的课程让你挑一门，然后开刷。凭据过期了程序也会自己重新获取。

### A. 不想装 Python：用打包好的 exe

从 [Release](https://github.com/AIR-pixel/ChangjiangYuketangAutoPlayer/releases/latest) 下载
[`ChangjiangYuketangAutoPlayer_1.1.0_portable.zip`](https://github.com/AIR-pixel/ChangjiangYuketangAutoPlayer/releases/latest/download/ChangjiangYuketangAutoPlayer_1.1.0_portable.zip)，
解压，**双击里面的 exe**，按提示挑一门课就完了。

- **Windows 10 / 11**，需要 **Edge** 或 **Chrome**（一般自带 Edge），**驱动不用管** —— 首次运行
  会联网下载匹配的那一版，之后走本地缓存。
- exe 没有代码签名，SmartScreen 可能提示「未知发布者」，点「更多信息」→「仍要运行」即可。
- 配置存在 exe 旁边自动生成的 `config.ini` 里。**想换课程**：把里面 `course_url` 那一行清空再运行。

### B. 从源码跑

```bash
pip install selenium          # Python 3.8+
```

然后双击 `run.bat`（或 `python main.py`）。首次运行同样会走向导，不用手填 `config.ini`。

浏览器用 **Edge** 或 **Chrome** 都行（脚本自动探测）。

> 取凭据这一步优先直接读本机 Firefox 的 cookie 库 —— Firefox 里还登录着长江雨课堂的话秒取，
> 不用扫码；读不到才开一个浏览器窗口让你扫码。全程**不回显 cookie 内容**。
>
> 长江雨课堂的 `sessionid` 和 `www.yuketang.cn` 的是**两套**，必须从同一个域名下取。
> 只想换凭据、不动课程的话，单独双击 `refresh_cookie.bat` 即可。

跑起来大概长这样：

```
21:39:25 启动浏览器（Edge，无窗口）...
21:39:27 浏览器就绪
21:39:27 打开课程页...
21:39:50 读取小节列表...
目标: 国防建设（本次还剩 37 个视频待播）
正在播放（当前标签页直达视频页）
已锁定播放速度: 2x（已拦截播放器复位 4 次；播放器 UI 可能仍显示 1.00X，属正常）
正在播放视频 | 已播 136s / 共 1183s | 实测倍速 2.02x
检测到播放结束标记，再等 5 秒
—— 已播完 1 个视频，切下一个 ——
```

（实际日志每行都带 `HH:MM:SS` 前缀 —— 挂后台无人看守时，出事的时间点就是唯一的线索。
启动那几行是故意加的：建浏览器 + 首次打开课程页要几十秒，中间一个字符都不输出的话，
双击 exe 的人会以为程序死了。）

## 跑完之后

结尾会明确告诉你是哪种情况，**不会把"跑失败"说成"刷完了"**：

| 结尾输出 | 含义 |
|---|---|
| `恭喜你！全部播放完毕` | 确实没有没看完的视频了 |
| `本次结束: 没有可播的视频了，但还有 N 个视频处于未开放（带锁）状态…` | 剩下的还没到开放时间，不算刷完，过几天再跑 |
| `已中止: 连续 3 轮没能开始播放任何视频…` | 页面没渲染完或窗口状态异常，**不是刷完了**，重跑接着刷 |
| `已中止: 连续出错…` | 连续 3 轮抛异常，重跑接着刷 |
| `已中止: 未找到任何小节元素…` | 没登录成功 / 课程页没加载完 |

## 配置项

| 项 | 默认 | 说明 |
|---|---|---|
| `headless` | `true` | 无窗口运行。挂后台就用 `true` |
| `browser` | `auto` | `chrome` / `edge` / `auto` |
| `ui` | `auto` | 前端版本，一般别动 |
| `course_url` | — | 课程地址。留空 = 下次运行重新挑课（由向导填） |
| `cookie` | — | `sessionid`。失效时程序会自动重新获取，不用手抄 |
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

**打包成 exe**：双击 `build.bat`（或 `python tools/build_exe.py`）。产物落在 `dist/`：
一个单文件 exe，外加一个含 `使用说明.txt` 的 zip —— 可以直接发给别人。
已发布过的版本不想被悄悄重打的话，脚本默认拒绝覆盖同名 zip，加 `--force` 才动。

## 实现细节

倍速是怎么真的锁住的、窗口为什么会卡死 20 秒、什么情况下会误报"刷完了"、
为什么"挑下一集"一次 JS 就够（旧写法一轮要 30 秒）、**为什么启动一度白等 3 分钟**——
这些踩坑记录在 [`docs/技术细节.md`](docs/技术细节.md)。

怀疑程序慢/卡在某一阶段，可以跑 `python tools/diag_startup.py`：它会量出
"建浏览器 / 打开首页 / 打开课程页 / 读到小节"各花多久。只读，不点视频、不改配置。

## 来源与授权

本项目基于 **[LetMeFly666/YuketangAutoPlayer](https://github.com/LetMeFly666/YuketangAutoPlayer)** 改造，
基础代码与思路来自上游，感谢原作者 [@LetMeFly666](https://github.com/LetMeFly666) 及各位贡献者。

上游是通用的雨课堂脚本；这里针对性改成了**长江雨课堂**专用：适配 `changjiang.yuketang.cn` 的前端结构、
修掉该站特有的窗口卡死与误报完成、把 2 倍速真正做到生效、免掉启动时白等的 3 分钟，
并加上首次配置向导与一键打包（上游要求手填 `config.ini`）。

代码按 **LGPL-2.1** 授权，见 [`LICENSE`](LICENSE)。上游打包好的 `YuketangAutoPlayer.exe`
不随本仓库分发；这里自己的免安装包由 `build.bat` 从源码现打（见「注意事项」）。

## 免责声明

仅供 selenium 技术的学习与实践。请勿用于违反你所在学校规定的用途，由此产生的后果由使用者自负。
