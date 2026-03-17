# GitHub Followers Search

一个本地桌面小程序，用来加载某个 GitHub 用户或组织的 followers，并按关键词实时筛选。

例如：

- 搜索 `Chang` 可以匹配 `Chang Yiming`
- 搜索 `cym` 也可以匹配 `Chang Yiming`

`wfs` 这类关键词之所以能命中，是因为程序除了普通子串匹配外，还支持按字母顺序的模糊匹配。

## 运行方式

确保本机安装了 Python 3.10+，然后在项目目录执行：

```powershell
python app.py
```

程序启动后：

1. 输入 GitHub 用户名、组织名，或者直接粘贴 GitHub 页面链接
2. 点击“加载 Followers”
3. 在“关键词”输入框里输入关键字进行筛选
4. 双击某一行可以直接打开对应 GitHub 主页

## 可选：提高 GitHub API 限额

如果 followers 较多，GitHub 未登录接口可能触发限流。可以先设置环境变量 `GITHUB_TOKEN`：

```powershell
$env:GITHUB_TOKEN="你的 token"
python app.py
```

## 当前实现

- 通过 GitHub REST API 拉取 followers
- 自动拉取每个 follower 的公开姓名
- 支持 login、name 的子串匹配
- 支持像 `wfs` 这样的顺序字母模糊匹配
- 本地缓存 followers 数据，减少重复请求
