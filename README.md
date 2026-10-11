<!--
 * @Author: LetMeFly
 * @Date: 2023-09-22 18:26:15
 * @LastEditors: LetMeFly.xyz
 * @LastEditTime: 2025-11-13 23:45:53
-->
# YuketangAutoPlayer

雨课堂刷课脚本（雨课堂视频自动播放），基于浏览器模拟的方式运行，无需虚拟机，甚至可以以无窗口模式运行。（MOOC）

视频演示地址：[Bilibili@BV15K4y1F7EN](https://www.bilibili.com/video/BV15K4y1F7EN/)

<!-- <iframe src="//player.bilibili.com/player.html?aid=873783562&bvid=BV15K4y1F7EN&cid=1275745338&p=1" scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true"> </iframe> -->

[![](img/video-cover.jpg)](https://www.bilibili.com/video/BV15K4y1F7EN/)

---

## ⚠️ 本仓库是修改版，请先读这一节

本仓库是 [LetMeFly666/YuketangAutoPlayer](https://github.com/LetMeFly666/YuketangAutoPlayer) 的**修改版**，
原作者 [@LetMeFly666](https://github.com/LetMeFly666) 及各位贡献者，代码仍按 **LGPL-2.1** 授权（见 `LICENSE`）。

改动集中在三件事：

| 目的 | 说明 |
|---|---|
| **跑长江雨课堂** | 适配 `changjiang.yuketang.cn`，并让 UI 版本（新版/旧版）自动判定，不再写死 |
| **无人值守挂后台** | 无窗口运行 + 单轮出错不终止 + 自动切下一集 + 卡住会跳过而不是干等 |
| **真的 2 倍速** | 破解该站播放器"把倍速改回 1x"的行为，实测稳定 2.0x |

> 上游打包好的 `YuketangAutoPlayer.exe` **不包含**本仓库的改动，请按下方「方式二：从源码运行」。

---

## 与原版的差异

详细技术细节与实测数据见 [`main.py`](main.py) 里对应函数的 docstring，这里只列结论。

### 1. 新增配置项

| 配置项 | 默认 | 作用 |
|---|---|---|
| `browser` | `auto` | `chrome` / `edge` / `auto`。`auto` 自动探测本机已装哪个 |
| `ui` | `auto` | `auto` / `common` / `legacy`。雨课堂两套前端，`auto` 按域名判断，未知域名运行时按 DOM 探测 |
| `speed` | `2` | 播放倍速，`1` = 原速，允许 `0.5 ~ 4` |

### 2. 长江雨课堂适配

- `changjiang.yuketang.cn` 与 `www.yuketang.cn` 前端同源（同一份 `login.js`、`/v2/web/index` 逐字节一致），
  按新版(COMMONUI)处理。
- 新版课程页的小节列表在"学习报告"标签页下，**必须先点 `#tab-student_school_report` 才会渲染**，
  否则 `study-unit` 数量为 0。
- 该站元素存在但原生 `.click()` 会抛 `ElementNotInteractableException`，统一改走 JS 点击。
- **完成度判定不再只看"已完成"三个字**：长江雨课堂显示的是百分比
  （实测文本形如 `9.8%` / `100%`，里面没有"已完成"字样）。只看文字会导致已刷完的视频被反复重播。

### 3. 无人值守

- 单轮异常不再终止整个任务，**连续 3 轮出错**才停；出错后自动回到课程页。
- 播放结束判据从 1 个增加到 3 个：原「时间回退」标记 + `video.ended` / 接近 `duration` 显式判断
  + **5 分钟无进展的兜底放弃**（挂后台最怕把整晚耗在同一个视频上）。
- `PLAYED_TITLES`：选中即登记标题，保证即使完成度解析失败也绝不原地打转。
- 视频若是**同页跳转**而非新标签页，原来的 `driver.refresh()` 会刷到视频页，已改为重定向回课程页。
- 无头模式必须加 `--autoplay-policy=no-user-gesture-required`，否则 `video.play()` 会被自动播放策略拦住。

#### 3.1 全程只用一个窗口（修 `failed to close window in 20 seconds`）

原方案是「点标题 → 站点开新标签页 → 播完 `driver.close()`」。实测这站 `close()` 会偶发卡死 20 秒
（日志里是 `unknown error: failed to close window in 20 seconds`），窗口状态一乱，后面几轮全部作废。

现在改成**根本不开新标签页**：点标题前先注入一段脚本收编站点自己的 `window.open`，把视频 URL 截下来，
然后在当前标签页 `driver.get()` 直达视频页。

> 细节：`window.open` 必须返回一个**假窗口对象**，不能返回 `null`——站点拿到返回值会调
> `focus()` / `close()`，返回 `null` 会让它内部抛错，可能连 URL 都不给。

配套改动：`leave_video_window()` 第一步永远先拆掉自己注入的定时器与监听、置 `__ytDone`、
清 `window.onbeforeunload`，再处理窗口——否则页面卸载时会和播放器的"暂停即为不可见"逻辑互相顶，
这才是 `close()` 卡死的根因。`back_to_course_page()` 也加了上限（3 次），`close()` 失败就导航到
`about:blank`，绝不无限重试。

#### 3.2 不再误报"全部播放完毕"

实测踩到过：课程页偶尔先吐出 80 多个**空的 `study-unit` 骨架**、标题稍后才填上。此时取到的标题是空串，
而空串一旦被写进 `PLAYED_TITLES`，下一轮所有同类小节都会被判成"已播过"，最后**误报"恭喜你！全部播放完毕"**，
其实还剩几十个没刷。

现在的防线有三层：

1. `video_title()` 区分「元素不存在」（旧版 UI，走文本兜底）与「元素在但文本为空」（渲染未完成，返回空串）；
2. `_units_rendered()` 渲染守卫——小节列表拿不到标题就重载课程页重来（最多 3 次）；
3. `finish1video()` 拿到空标题直接 `return None`，**绝不写进 `PLAYED_TITLES`**；主循环把 `None` 计入
   `no_progress_rounds`，连续 3 轮没有任何进展就中止，并明确打印"这不是刷完了"。

结尾因此区分四种情形，只有真正一个不剩才会打印"全部播放完毕"：

| 结尾输出 | 含义 |
|---|---|
| `已中止: 未找到任何小节元素…` | 课程页没加载完 / 未登录 / UI 结构不认识 |
| `已中止: 连续出错…` | 连续 3 轮抛异常 |
| `已中止: 连续 3 轮没能开始播放任何视频…` | 页面渲染或窗口状态异常，**不是刷完了** |
| `恭喜你！全部播放完毕` | 确实没有未完成的小节了 |

### 4. 倍速（这块最绕，单独说明）

该站播放器自带 2 倍速按钮，但**那条路走不通**：用 CDP 原生鼠标事件确认可信点击确实打到了
倍速列表项（`isTrusted=true`、列表保持展开、`elementFromPoint` 确认无遮挡），界面值和实际速率都纹丝不动。

真正的障碍是：播放器在 `ratechange` / `timeupdate` 里**把倍速同步回它自己内部的 1x 状态**，约每 250ms 一次。

解法不是对抗，而是**吞掉"往低调"的写入**——给 `HTMLMediaElement.prototype.playbackRate`
装一层 setter，凡是想写到目标值以下的直接丢弃。被吞掉的写不改变实际值，因此不会再触发
`ratechange`，不会自激循环。再加 1 秒定时器兜底补刀。

实测 12 秒内 `currentTime` 前进 23.6s / 墙钟 11.79s = **2.002x**，`paused=false`，期间拦掉 49 次复位。

> 副作用：播放器自己的 UI 仍显示 `1.00X`（它的内部状态没被改）。纯显示问题，不影响实际速率与切集。
> 判断真实速率请用 `currentTime` 推进量，不要读 `playbackRate`。

### 5. 其他修复

- 播放器会**卸载重建 `<video>`**（外层 `xt-wrap` 的 class 带 `unload`），
  `document.querySelector("video")` 在开场会间歇性返回 `null`。原代码依赖全局 `video` 变量，
  会对着已脱离文档的僵尸元素操作。现已把倍速锁 / 静音 / 暂停续播全部改成**元素无关**。
- 播放器带**防刷逻辑**：`blur` / `visibilitychange` 时若页面失焦或不可见就 `video.pause()`。
  无头模式不受影响（`hasFocus()=true`）；**有窗口模式下切走窗口会被暂停**，已用"暂停即续播"顶回去。

### 6. 配套脚本

| 文件 | 说明 |
|---|---|
| `run.bat` | 一键运行（自动设 `NO_PROXY` 绕开系统代理，见下方「注意事项」） |
| `refresh_cookie.bat` / `refresh_cookie.py` | 自动刷新 `config.ini` 里的 `sessionid` |

`refresh_cookie.py` 两条路径：优先**直接读本机 Firefox 的 cookie 库**
（Firefox 的 cookie 是明文 SQLite，只要 Firefox 里还登录着雨课堂就能秒取，不用扫码；
全程只复制副本后以 `mode=ro` 查询，不修改 Firefox 任何文件），
失败才回退到开浏览器扫码登录。出于安全考虑，脚本**不回显 sessionid 内容**。

---

## 使用方法

### 方式一：使用打包好的 exe 文件（推荐）

1. 下载最新版本的 [`YuketangAutoPlayer.exe`](https://github.com/LetMeFly666/YuketangAutoPlayer/releases/download/v5.0/YuketangAutoPlayer.exe)
2. 将 `YuketangAutoPlayer.exe` 放到任意目录
3. 双击运行，首次运行会自动生成 `config.ini` 配置文件
4. 编辑 `config.ini` 填写你的课程URL和Cookie（获取方式见下文）
5. 再次运行即可开始自动播放

### 方式二：从源码运行

主要分为四步：

1. 配置Python环境
2. 配置浏览器驱动（推荐Chrome浏览器）
3. 设置刷课信息
4. 开始刷课

### 一、配置Python环境

使用 uv 包管理器（推荐）：

```bash
uv pip install selenium
```

或使用传统 pip：

```bash
pip install selenium
```

### 二、配置浏览器驱动

本项目默认以Chrome为例，以Windows系统为例。其他浏览器原理类似、其他操作系统原理类似。

首先电脑上要安装有[Chrome浏览器](https://www.google.cn/chrome/index.html)（别装到假的Chrome了，之前有同学装了个假Chrome后来问我为什么程序不能正常运行QAQ）

其次需要下载**对应版本的**`ChromeDriver`：[下载地址1](https://chromedriver.chromium.org/downloads)、[下载地址2](https://googlechromelabs.github.io/chrome-for-testing/)、[下载地址3](https://github.com/LetMeFly666/YuketangAutoPlayer/releases/download/v0.0/chromedriver.exe)、[教程1](https://blog.csdn.net/fighting_jiang/article/details/116298853)、[教程2](https://blog.csdn.net/zhoukeguai/article/details/113247342)、[最后的尝试](https://cn.bing.com/search?q=chromedriver%E4%B8%8B%E8%BD%BD)。（版本相差不大的话也无所谓）

将`ChromeDriver.exe`放到`环境变量`中 或 `脚本(执行)目录`下。

### 三、设置刷课信息

使用 `config.ini` 配置文件。首次运行脚本时会自动生成 `config.ini` ，也可以复制 `config.ini.example` 并重命名为 `config.ini`：

```ini
[Settings]
headless = false
browser = auto
ui = auto
course_url = 在此填写你的课程URL
cookie = 在此填写你的sessionid
speed = 2
implicitly_wait = 10
```

#### ① headless

是否以无窗口模式运行。

设为 `true` 时不弹出浏览器界面，视频仍被正常驱动播放，**可以同时做别的事情**。
本项目已支持挂后台，建议直接开 `true`。

（上游说明里提到"扫码登录不支持 headless"，那是因为扫码要人看着浏览器；
本项目配套的 `refresh_cookie.bat` 是先取 cookie 再跑主程序，因此用 cookie 登录时开 `true` 没有问题。）

#### ② browser / ui

`browser` 一般保持 `auto`。`ui` 一般保持 `auto`；只有在自动判定出错、
想强制指定新版/旧版前端时才需要手改。

#### ③ speed

播放倍速，默认 `2`。详见上方「[原版的差异 → 4. 倍速](#4-倍速这块最绕单独说明)」。

#### ④ course_url

你要刷的课的URL。

进入雨课堂，进入你想要刷的课程，点击“学习内容”，复制地址栏的url即可。

![how-to-get-url](img/how-to-get-url.jpg)

（注意是https格式的哦）

#### ⑤ cookie

COOKIE用来告诉雨课堂你是你。两种拿法：

**推荐：跑一次 `refresh_cookie.bat` 自动获取。** 它会优先从本机 Firefox 的 cookie 库里直接读
`sessionid`（Firefox 里还登录着雨课堂的话秒取，不用扫码），读不到才开浏览器让你扫码，
拿到后自动写进 `config.ini`，且不会回显 cookie 内容。

> 注意：长江雨课堂的 `sessionid` 和 `www.yuketang.cn` 的是**两套**，必须从 `course_url` 同一个域名下取。

**手动：** 登录（你们学校的）雨课堂，`打开开发者工具`（下图的步骤1，也可百度），依次点击"应用→存储→Cookie→ https&#58;&#47;&#47;xxx.yuketang... "，复制**sessionid**对应的值

![/how-to-get-cookie](img/how-to-get-cookie.jpg)

### 四、开始刷课

直接双击 `run.bat`，或者：

```python
python main.py
```

运行中会逐条打印进度，`已播 Xs / 共 Ys` 后面还会带上**实测倍速**，方便确认倍速真的生效了：

```
已锁定播放速度: 2x（已拦截播放器复位 4 次；播放器 UI 可能仍显示 1.00X，属正常）
正在播放视频 | 已播 136s / 共 1183s | 实测倍速 2.02x
```

## 注意事项

**必须绕开系统代理。** selenium 客户端会读取 `HTTP(S)_PROXY` 环境变量，若不排除本机地址，
发往本地 WebDriver 端口的请求会被代理劫持，**所有命令一律返回 `unhandled request`**
（表现为一启动就报一堆莫名错误）。`run.bat` 里已经设好了：

```bat
set "NO_PROXY=localhost,127.0.0.1,::1"
```

如果你不用 `run.bat` 而是手动 `python main.py`，`main.py` 自己也会在启动时补上这一段。
但如果你在别的宿主里跑（IDE、jupyter 等），需要自己确认环境变量。

## 打包为 EXE（可选）

如果你想要打包成独立的可执行文件：

### 准备工作

1. 确保 `chromedriver.exe` 在项目根目录
2. 安装 PyInstaller：
```bash
uv pip install pyinstaller
```

### 执行打包

手动执行：

```bash
pyinstaller YuketangAutoPlayer.spec --clean
```

打包完成后，`dist` 目录下会生成 `YuketangAutoPlayer.exe`。该 exe 文件已内置 chromedriver，可以独立运行。

## 使用提示

**挂后台**：`headless = true` 时不弹窗口，你可以正常做别的事，不必担心鼠标落到浏览器上——
因为根本没有窗口。这也是本项目推荐的用法。

若一定要开 `headless = false` 看过程，那就注意：使用过程中可以缩浏览器小窗口去干其他事情，
但尽量不要将鼠标移动到程序弹出的浏览器窗口上。因为本项目的运行原理就是模拟用户对浏览器的控制。

另外有窗口模式下该站播放器带**防刷逻辑**，页面一失焦就会暂停视频；脚本会顶回去，
但这一来一回可能影响进度上报，所以还是建议用无头模式。

**倍速**：`speed = 2` 会让视频以 2 倍速播放，**一门课的实际耗时只有视频总时长的一半**。
如果这门课除了看视频还查学习时长，请自己权衡。

**缓存**：若视频播放完毕程序正常结束，则缓存将被自动清理。若视频未播放完毕提前关掉了程序，则Windows系统下缓存位置在`%temp%/chrome_BITS_xxx`下。

## 感谢列表

+ 感谢[Github@LetMeFly666](https://github.com/LetMeFly666) 及下列所有贡献者，本仓库的全部基础工作来自上游 [YuketangAutoPlayer](https://github.com/LetMeFly666/YuketangAutoPlayer)。
+ 感谢[Github@SwordLikeRain](https://github.com/SwordLikeRain)的[Cookie错误时提示不准确的issue](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/1)（good first issue），使得程序修改后支持了每次扫码登录。
+ 感谢[BiliBili@Bacch](https://space.bilibili.com/21043185)的`AttributeError: 'WebDriver' object has no attribute 'find_elements_by_class_name'`的[报错提醒](https://www.bilibili.com/video/BV15K4y1F7EN/#reply187204230304)，使得程序修改后兼容了selenium≥4.0。
+ 感谢[BiliBili@青鹧不懂蓝桉情](https://space.bilibili.com/1208020409)提供的账号，使得程序修改后支持了`www.yuketang.cn`这种域名下的雨课堂界面。
+ 感谢[Github@420xincheng](https://github.com/420xincheng)的[没刷完视频，就自动退出的解决方法(#8)](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/8)，播放完毕一个视频刷新后等待5秒防止页面暂未加载完成。
+ 感谢[Github@Guo-Chenxu](https://github.com/Guo-Chenxu)的[`ifVideo`函数修改(#13)](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/13)，更新COMMONUI下未播放视频的判断逻辑。
+ 感谢[Github@泠辰](https://github.com/Crsuh2er0)的[已过期视频循环播放bugfix (#17)](https://github.com/LetMeFly666/YuketangAutoPlayer/pull/17)，修复了存在已过期视频时会重复播放已过期视频的问题。
+ 感谢[Github@ke tan](https://github.com/tkzzzzzz6)的[exe打包文件方式(#18)](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/18)，Windows当前新版Chrome可一键运行免除环境配置及驱动下载困扰。

## TODO

- [ ] 抽象一个获取待播放视频的函数([Suggest](https://github.com/LetMeFly666/YuketangAutoPlayer/pull/17#discussion_r2450825512)ed by Copilot)。


## 免责声明

本项目的唯一目的是：selenium技术的学习与实践。

禁止用于其他用途，下载后请于24h内删除【Doge】。

<small>若导致账号封禁（目前来看完全不会）或其他因BUG造成的损失，与本项目无关。</small>
