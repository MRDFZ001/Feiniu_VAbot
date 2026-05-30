# 飞牛_VAbot

飞牛_VAbot 是一个面向飞牛 NAS、Linux 服务器和家用小主机的本地解析保存服务。它可以接收微信机器人、OpenClaw 或 OpenAI 兼容接口传入的分享链接，然后调用用户自己填写的解析接口，把解析出来的视频、图片、音乐保存到用户自己选择的目录。

本项目已经按公开发布要求处理：

- 不内置任何私人解析接口地址。
- 不内置作者的飞牛、NAS、服务器保存路径。
- `.env` 不会上传到 GitHub，用户需要自己复制 `.env.example` 后填写。
- 解析接口和保存目录都必须由使用者自己配置。

## 目录说明

```text
飞牛_VAbot/
  app/                     Python 源码
  docs/
    GITHUB_PUBLISH_GUIDE.md GitHub 保姆级发布教程
  .env.example             用户配置模板，不含私人接口
  docker-compose.yml       Docker 部署文件
  Dockerfile               Docker 镜像文件
  requirements.txt         Python 依赖
  setup_env.py             交互式配置向导
```

## 功能

- 支持 `/parse`、`/wechat`、`/v1/chat/completions`、`/v1/responses`。
- 支持抖音、小红书、汽水音乐等链接识别。
- 支持视频、图文、实况照片、音乐、纯音频保存。
- 支持 Docker 部署，适合飞牛 NAS、Linux 服务器、家用小主机。
- 支持可选 OpenClaw 微信通道。
- 支持可选“60 秒看世界”定时推送。

## 一、准备保存目录

先在飞牛、NAS 或服务器上创建一个专门保存文件的目录。示例：

```bash
mkdir -p /你的/保存目录/VABot
```

这个目录就是宿主机真实目录，后面要填到：

```env
VABOT_HOST_SAVE_DIR=/你的/保存目录/VABot
```

注意：这只是示例。发布到 GitHub 时不要写自己的真实路径。

## 二、准备解析接口

VABot 本身不提供解析服务。你需要自己准备可用接口，然后填到 `.env`。

常用变量：

```env
DOUYIN_API=
XHSIMG_API=
SHORT_VIDEOS_API=
SVPARSE_API=
QSMUSIC_API=
```

只填你实际拥有、允许使用的接口。没有的接口保持空白即可。

如果接口需要 key 或 token：

```env
BUGPK_KEY=
APICX_TOKEN=
APICX_AUTH=
```

这些内容属于私人配置，只放在 `.env`，不要上传 GitHub。

## 三、创建配置文件

方式一：使用配置向导。

```bash
python setup_env.py
```

按提示输入保存目录、端口、访问 token、解析接口地址即可。不会填的接口直接回车留空。

方式二：手动复制模板。

```bash
cp .env.example .env
nano .env
```

Docker 部署时至少填写：

```env
VABOT_HOST_SAVE_DIR=/你的/保存目录/VABot
CREATIVE_ROOT=/creative
VABOT_PORT=18088
VABOT_TOKEN=换成你自己的随机字符串

DOUYIN_API=
XHSIMG_API=
SHORT_VIDEOS_API=
SVPARSE_API=
QSMUSIC_API=
```

本机直接运行 Python 时，可以这样填：

```env
CREATIVE_ROOT=./downloads
VABOT_HOST_SAVE_DIR=./downloads
```

## 四、Docker 启动

确认已经安装 Docker 和 Docker Compose：

```bash
docker --version
docker compose version
```

构建镜像：

```bash
docker compose build --no-cache
```

启动服务：

```bash
docker compose up -d
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

## 五、测试服务

如果没有设置 `VABOT_TOKEN`：

```bash
curl http://127.0.0.1:18088/health
```

如果设置了 `VABOT_TOKEN`：

```bash
curl -H "X-VABOT-Token: 你的VABOT_TOKEN" http://127.0.0.1:18088/health
```

看到类似结果说明启动成功：

```json
{
  "ok": true,
  "service": "VABot"
}
```

## 六、测试解析保存

```bash
curl -X POST http://127.0.0.1:18088/parse \
  -H "Content-Type: application/json" \
  -H "X-VABOT-Token: 你的VABOT_TOKEN" \
  -d '{"text":"这里粘贴你的作品分享链接"}'
```

只保存或提取音频：

```bash
curl -X POST http://127.0.0.1:18088/parse \
  -H "Content-Type: application/json" \
  -H "X-VABOT-Token: 你的VABOT_TOKEN" \
  -d '{"text":"这里粘贴你的作品分享链接", "mode":"audio"}'
```

默认分类：

- 视频、图文、实况照片：`CREATIVE_ROOT/video`
- 音乐、音频：`CREATIVE_ROOT/music`
- 解析记录：`CREATIVE_ROOT/logs/解析记录.txt`

Docker 部署时，容器内的 `/creative` 会映射到你填写的 `VABOT_HOST_SAVE_DIR`。

## 七、接入微信 / OpenClaw

飞牛_VAbot 提供 OpenAI 兼容接口，可以作为 OpenClaw 或其他微信机器人的本地模型接口。

接口地址：

```text
http://你的服务器IP:18088/v1/chat/completions
```

模型名：

```text
vabot
```

如果设置了 `VABOT_TOKEN`，请求头需要带：

```text
Authorization: Bearer 你的VABOT_TOKEN
```

或：

```text
X-VABOT-Token: 你的VABOT_TOKEN
```

微信里发送作品链接后，VABot 会回复解析结果和保存位置。

## 八、可选：OpenClaw 微信状态文件

不使用 OpenClaw 时，本节全部跳过。

使用 OpenClaw 时，在 `.env` 填写自己的路径：

```env
OPENCLAW_WEIXIN_STATE_ROOT_HOST=/你的/openclaw-weixin目录
OPENCLAW_CONFIG_HOST=/你的/openclaw.json
VABOT_WEIXIN_ACCOUNT_ID=你的微信通道账号ID
VABOT_WEIXIN_TO_USER_ID=要推送到的微信用户或群ID
```

然后在 `docker-compose.yml` 里取消下面两行注释：

```yaml
# - ${OPENCLAW_WEIXIN_STATE_ROOT_HOST}:${VABOT_WEIXIN_STATE_ROOT:-/openclaw-weixin}:ro
# - ${OPENCLAW_CONFIG_HOST}:${VABOT_OPENCLAW_CONFIG:-/openclaw-config/openclaw.json}:ro
```

## 九、可选：每天 60 秒看世界

默认关闭：

```env
VABOT_60S_ENABLED=false
```

需要开启时：

```env
VABOT_60S_ENABLED=true
VABOT_60S_TIMES=08:00,20:00
VABOT_60S_API=https://60s.viki.moe/v2/60s?encoding=text
TZ=Asia/Shanghai
```

重启：

```bash
docker compose up -d --force-recreate
```

## 十、发布到 GitHub 前检查

不要上传：

- `.env`
- `.venv/`
- `data/`
- `logs/`
- `downloads/`
- 真实保存目录
- 任何私人解析接口、token、key、OpenClaw 状态文件

本项目已经提供 `.gitignore`。正常情况下这些文件不会被提交。

完整保姆级 GitHub 发布教程见：

[docs/GITHUB_PUBLISH_GUIDE.md](docs/GITHUB_PUBLISH_GUIDE.md)

## 常见问题

### 1. 提示未配置保存目录

说明还没有填写 `CREATIVE_ROOT` 或 Docker 没有正确加载 `.env`。

Docker 用户检查：

```env
VABOT_HOST_SAVE_DIR=/你的/真实/保存目录
CREATIVE_ROOT=/creative
```

Python 直接运行用户检查：

```env
CREATIVE_ROOT=./downloads
VABOT_HOST_SAVE_DIR=./downloads
```

### 2. 返回“未配置任何解析接口”

说明 `.env` 里的解析接口为空。至少填写一个可用接口，例如：

```env
DOUYIN_API=https://你的接口地址
```

### 3. 能解析但下载失败

常见原因：

- 解析接口返回的直链已过期。
- 服务器无法访问直链。
- 保存目录没有写入权限。
- `REQUEST_TIMEOUT` 太短。

先看日志：

```bash
docker compose logs -f
```

### 4. 不想用 Docker，可以直接运行吗

可以。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_env.py
python -m app.server
```

Windows PowerShell 激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup_env.py
python -m app.server
```

## 免责声明

本项目仅用于个人学习和自动化整理。请确保你使用的解析接口、下载内容和保存行为符合相关平台规则、版权要求及当地法律法规。
