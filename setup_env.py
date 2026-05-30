from __future__ import annotations

from pathlib import Path


ENV_PATH = Path(".env")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_required(prompt: str) -> str:
    while True:
        value = ask(prompt)
        if value:
            return value
        print("这一项必须填写，请输入你自己的路径。")


def write_env(values: dict[str, str]) -> None:
    lines = [
        "# VABot local config. Do not upload this file to GitHub.",
        "",
        "# Save location",
        f"VABOT_HOST_SAVE_DIR={values['VABOT_HOST_SAVE_DIR']}",
        f"CREATIVE_ROOT={values['CREATIVE_ROOT']}",
        "VIDEO_DIR=",
        "MUSIC_DIR=",
        "LOG_DIR=",
        "RECORD_FILE=",
        "",
        "REQUEST_TIMEOUT=30",
        "KEEP_LIVE_RAW=false",
        "",
        "# Parser APIs. Fill only the APIs you own or are allowed to use.",
        f"DOUYIN_API={values['DOUYIN_API']}",
        f"XHSIMG_API={values['XHSIMG_API']}",
        f"SHORT_VIDEOS_API={values['SHORT_VIDEOS_API']}",
        f"SVPARSE_API={values['SVPARSE_API']}",
        f"QSMUSIC_API={values['QSMUSIC_API']}",
        "APICX_DOUYIN_LIVE_API=",
        "APICX_XHS_API=",
        "",
        "BUGPK_KEY=",
        "APICX_TOKEN=",
        "APICX_AUTH=",
        "",
        "# HTTP service",
        "VABOT_HOST=0.0.0.0",
        f"VABOT_PORT={values['VABOT_PORT']}",
        f"VABOT_TOKEN={values['VABOT_TOKEN']}",
        "VABOT_MODE_TIMEOUT_SECONDS=120",
        "VABOT_SEND_TIMEOUT_SECONDS=20",
        "",
        "# Daily 60s news",
        "VABOT_60S_ENABLED=false",
        "VABOT_60S_TIMES=08:00,20:00",
        "VABOT_60S_API=https://60s.viki.moe/v2/60s?encoding=text",
        "TZ=Asia/Shanghai",
        "",
        "# OpenClaw / WeChat, optional",
        "OPENCLAW_WEIXIN_STATE_ROOT_HOST=",
        "OPENCLAW_CONFIG_HOST=",
        "VABOT_WEIXIN_STATE_ROOT=/openclaw-weixin",
        "VABOT_OPENCLAW_CONFIG=/openclaw-config/openclaw.json",
        "VABOT_WEIXIN_ACCOUNT_ID=",
        "VABOT_WEIXIN_TO_USER_ID=",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("VABot 配置向导")
    print("请按提示填写。不会填写的解析接口可以直接回车留空。")
    print("")

    if ENV_PATH.exists():
        overwrite = ask(".env 已存在，是否覆盖？输入 yes 覆盖，其他内容取消", "no").lower()
        if overwrite not in {"yes", "y"}:
            print("已取消，没有修改 .env。")
            return 0

    save_dir = ask_required("飞牛/NAS/服务器上的真实保存目录，例如 /vol1/1000/VABot")
    creative_root = ask("容器内保存目录；Docker 用户建议保持 /creative", "/creative")
    port = ask("服务端口", "18088")
    token = ask("访问 token，建议填写一串只有你知道的字符")

    apis = {
        "DOUYIN_API": ask("抖音解析接口 DOUYIN_API"),
        "XHSIMG_API": ask("小红书图文解析接口 XHSIMG_API"),
        "SHORT_VIDEOS_API": ask("通用短视频解析接口 SHORT_VIDEOS_API"),
        "SVPARSE_API": ask("备用解析接口 SVPARSE_API"),
        "QSMUSIC_API": ask("音乐解析接口 QSMUSIC_API"),
    }
    if not any(apis.values()):
        print("提醒：你没有填写任何解析接口。服务可以启动，但解析链接时会提示未配置接口。")

    values = {
        "VABOT_HOST_SAVE_DIR": save_dir,
        "CREATIVE_ROOT": creative_root,
        "VABOT_PORT": port,
        "VABOT_TOKEN": token,
        **apis,
    }

    write_env(values)
    print("")
    print(".env 已生成。请检查保存目录和接口地址后再启动 VABot。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
