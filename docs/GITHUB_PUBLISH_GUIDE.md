# 飞牛_VAbot GitHub 保姆级发布教程

这份教程适合完全没发布过 GitHub 项目的用户。照着做即可。

## 一、发布前确认

打开项目目录，确认里面有这些文件：

```text
README.md
.env.example
.gitignore
Dockerfile
docker-compose.yml
requirements.txt
setup_env.py
app/
docs/
```

确认不要上传这些内容：

```text
.env
.venv/
data/
logs/
downloads/
真实保存目录
真实解析接口地址
任何 token、key、账号状态文件
```

`.env.example` 可以上传，因为它只是空模板。`.env` 不可以上传，因为它会保存用户自己的接口和路径。

## 二、安装 Git

Windows 用户：

1. 打开 https://git-scm.com/download/win
2. 下载并安装。
3. 安装过程一直点 Next 即可。
4. 安装完成后打开 PowerShell，输入：

```powershell
git --version
```

能看到版本号就成功。

Linux / 飞牛 / NAS 用户如果已经有 Git，可以跳过。没有的话按系统安装：

```bash
sudo apt update
sudo apt install -y git
git --version
```

## 三、注册 GitHub 账号

1. 打开 https://github.com
2. 点 Sign up。
3. 填邮箱、密码、用户名。
4. 按邮件提示完成验证。
5. 登录 GitHub。

## 四、创建 GitHub 仓库

1. 登录 GitHub。
2. 右上角点加号。
3. 选择 New repository。
4. Repository name 填：

```text
飞牛_VAbot
```

5. Description 可填：

```text
飞牛 NAS 本地视频、图文、音乐解析保存服务
```

6. Public / Private 自己选择。
7. 不要勾选 Add a README file。
8. 不要勾选 Add .gitignore。
9. 不要勾选 Choose a license，除非你明确知道要用什么许可证。
10. 点 Create repository。

创建后，GitHub 会显示一个仓库地址，类似：

```text
https://github.com/你的用户名/飞牛_VAbot.git
```

先把这个地址复制下来。

## 五、在本地初始化 Git

进入项目目录。

Windows PowerShell 示例：

```powershell
cd "C:\你的项目目录\飞牛_VAbot"
```

Linux / 飞牛 示例：

```bash
cd /你的项目目录/飞牛_VAbot
```

初始化：

```bash
git init
```

设置主分支名：

```bash
git branch -M main
```

查看将要提交的文件：

```bash
git status
```

如果看到 `.env`，先停下来，不要提交。确认 `.gitignore` 里有 `.env`。

## 六、检查是否误包含私人信息

运行：

```bash
git status --ignored
```

正常情况下：

- `.env` 应该被忽略。
- `data/`、`logs/`、`downloads/` 应该被忽略。

再搜索一次私人接口或真实路径：

```bash
git grep -n "你的真实接口"
git grep -n "你的真实保存路径"
```

如果你不知道搜什么，可以手动打开以下文件检查：

```text
README.md
.env.example
docker-compose.yml
app/config.py
app/parser_api.py
```

公开仓库里应该只出现示例文字，例如：

```text
https://你的接口地址
/你的/保存目录/VABot
```

不应该出现真实接口、真实 token、真实 NAS 路径。

## 七、第一次提交代码

添加文件：

```bash
git add .
```

再次确认：

```bash
git status
```

确认没有 `.env` 后提交：

```bash
git commit -m "Initial 飞牛_VAbot release"
```

## 八、连接 GitHub 仓库

把下面命令里的地址换成你自己的 GitHub 仓库地址：

```bash
git remote add origin https://github.com/你的用户名/飞牛_VAbot.git
```

确认远程地址：

```bash
git remote -v
```

应该看到类似：

```text
origin  https://github.com/你的用户名/飞牛_VAbot.git (fetch)
origin  https://github.com/你的用户名/飞牛_VAbot.git (push)
```

## 九、推送到 GitHub

```bash
git push -u origin main
```

如果 GitHub 要你登录：

- 浏览器会弹出登录页，按提示登录。
- 如果要求 token，建议安装 GitHub CLI 或使用 Git Credential Manager。

推送成功后，刷新 GitHub 仓库页面，就能看到代码。

## 十、以后怎么更新

每次改完代码，按这三步：

```bash
git status
git add .
git commit -m "Update 飞牛_VAbot"
git push
```

提交前永远先看 `git status`，确认没有 `.env`。

## 十一、使用 GitHub CLI 的发布方式

如果你已经安装 GitHub CLI：

```bash
gh auth login
```

按提示登录后，可以直接创建仓库并推送：

```bash
gh repo create 飞牛_VAbot --public --description "飞牛 NAS 本地视频、图文、音乐解析保存服务" --source . --remote origin --push
```

如果想创建私有仓库：

```bash
gh repo create 飞牛_VAbot --private --description "飞牛 NAS 本地视频、图文、音乐解析保存服务" --source . --remote origin --push
```

## 十二、用户下载你的项目后怎么用

用户看到你的 GitHub 页面后，操作如下：

```bash
git clone https://github.com/你的用户名/飞牛_VAbot.git
cd 飞牛_VAbot
cp .env.example .env
python setup_env.py
docker compose build --no-cache
docker compose up -d
```

用户必须自己填写：

```env
VABOT_HOST_SAVE_DIR=
DOUYIN_API=
XHSIMG_API=
SHORT_VIDEOS_API=
SVPARSE_API=
QSMUSIC_API=
VABOT_TOKEN=
```

你不需要、也不应该把自己的接口和保存目录写进仓库。

## 十三、出问题时看哪里

查看 Docker 日志：

```bash
docker compose logs -f
```

查看 Git 状态：

```bash
git status
```

查看远程仓库：

```bash
git remote -v
```

确认 `.env` 没有被上传：

```bash
git ls-files | grep ".env"
```

只应该看到：

```text
.env.example
```

不应该看到：

```text
.env
```
