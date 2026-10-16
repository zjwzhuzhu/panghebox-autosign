# 胖盒云电脑 H5 自动签到

每天自动调用胖盒云电脑 H5 的签到接口，领取当日时长卡奖励。部署在 GitHub Actions，无需本地常驻进程。

## 签到奖励说明

签到时 7 天一个周期，每天领一张时长卡（免费云电脑游玩分钟数）。周期第 1 天经实测为 10 分钟；第 2～7 天的具体分钟数由服务端动态返回，脚本会按接口实际返回展示，不写死。

## 凭据怎么来

H5 版登录态存在浏览器 localStorage 里，脚本需要其中两个 key 的内容：

| localStorage key | 内容 |
|---|---|
| `fufuhub_user` | `{"userInfo":{...},"token":"<JWT>"}` |
| `globalState` | `{"uid":<数字>,"uuid":"<机器uuid>","flowid":"..."}` |

**在电脑浏览器获取**：登录 https://panghebox.com/mp/cgame/login 后，按 F12 打开开发者工具，切到 Console，粘贴下面这行回车：

```javascript
console.log(JSON.stringify({token:(JSON.parse(localStorage.getItem('fufuhub_user'))||{}).token,uid:(JSON.parse(localStorage.getItem('globalState'))||{}).uid,uuid:(JSON.parse(localStorage.getItem('globalState'))||{}).uuid}))
```

**在手机浏览器获取**：在已登录的页面地址栏输入下面这行（注意开头是 `javascript:`，可能被输入法吞掉冒号，需要手动补）：

```
javascript:prompt('fufuhub_user',localStorage.getItem('fufuhub_user'));prompt('globalState',localStorage.getItem('globalState'))
```

两次弹窗分别复制出来即可。

拼成下面这个 JSON（三者都要）：

```json
{"token":"<JWT，很长一串>","uid":123456,"uuid":"<32位左右机器ID>"}
```

## token 有效期与刷新

H5 的 token 约 10 小时有效，**没有免登录刷新接口**（免刷新是 PC 客户端专有的 `checklogin`）。因此：

- 工作流每天跑一次，正常情况下当天 token 仍有效；
- 一旦日志出现 `code=3584901`，说明 token 过期，需要按上面的方法重新取一份，更新 GitHub Secret `PANGHEBOX_CREDENTIALS`；
- 建议每次更新后，顺手在 Actions 页面手动触发一次运行确认能通。

## 仓库配置

Secret（Settings → Secrets and variables → Actions → Secrets）：

| 名称 | 值 |
|---|---|
| `PANGHEBOX_CREDENTIALS` | 上面拼好的 JSON |

工作流 `.github/workflows/signin.yml` 用北京时间离散时隙触发（避开整点拥堵）：

| cron (UTC) | 北京时间 | 用途 |
|---|---|---|
| `37 16 * * *` | 00:37 | 主签到 |
| `21 20 * * *` | 04:21 | 备用 |
| `43 0 * * *` | 08:43 | 备用 |
| `12 4 * * *` | 12:12 | 兜底 |

已签到的后续时隙会在 10 秒内直接退出，不消耗任何配额。每次运行前还会随机休眠 1～15 分钟，避免固定时间指纹。

> Fork 仓库的定时任务默认是禁用的，需要在 Actions 页面点一次 **Enable workflow**（或用 API 打开），否则 schedule 不会触发。

## 本地手动跑

```bat
set PANGHEBOX_CREDENTIALS={"token":"...","uid":123,"uuid":"..."}
D:\Anaconda\python.exe run_signin.py
```

## 目录结构

```
panghebox_autosign/signin.py   签到主逻辑（纯 requests，无浏览器依赖）
run_signin.py                  入口
.github/workflows/signin.yml   GitHub Actions 定时任务
```
