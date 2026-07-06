"""
YouTube 下载服务（skill: FetchYouTube）。

作为 VidSnap 的一个可选前置 skill：输入 YouTube 链接 → 下载到本地 →
交给现有的 IngestVideo / 转录 / 帧 / 笔记链路。

定位（开源本地版）：
- VidSnap 面向"用户在自己住宅 IP 上运行"的开源场景。住宅 IP 是普通用户，
  YouTube 基本不反爬，所以这里就是一层薄薄的 yt-dlp 封装 —— 不装 bgutil node 服务、
  不接 AgentGo 浏览器自动化。
- **不对反爬兜底**：按策略阶梯尽力下载，全部失败就抛 YouTubeFetchError，让 job 正常失败。
- 反爬三件套（cookie / proxy / PO Token）**全部可选**：给"某视频要登录"或"就是想在云上跑"
  的边缘情况留口子，默认都不需要。
"""
import asyncio
import os
from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..core.logging import logger

try:
    import yt_dlp
except ImportError:  # 环境未装 yt-dlp 时给清晰错误，而非 import 崩溃
    yt_dlp = None


class YouTubeFetchError(Exception):
    """YouTube 下载失败（多为云 IP 反爬）。不兜底，直接向上抛。"""


# 策略阶梯：default（让 yt-dlp 自选 client，配合 Deno 解 nsig + bgutil PO Token，实测当前最稳）→ 具体 client 兜底
_STRATEGIES = [
    {"name": "default", "player_client": None},
    {"name": "tv+web", "player_client": ["tv", "web"]},
    {"name": "mweb+web", "player_client": ["mweb", "web"]},
    {"name": "tv_embedded", "player_client": ["tv_embedded"]},
]


def _cfg(*names: str) -> str:
    """从 settings 或环境变量取第一个非空配置（都可选）。"""
    for n in names:
        v = getattr(settings, n, "") or os.getenv(n, "")
        if v:
            return str(v).strip()
    return ""


def _base_opts(out_dir: Path, resolution: str) -> dict:
    fmt = (
        "bestaudio/best"
        if resolution == "audio"
        else f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]/best"
    )
    opts: dict = {
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "format": fmt,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": logger,
        "retries": 3,
        "socket_timeout": 30,
    }
    proxy = _cfg("YOUTUBE_PROXY", "VIDSNAP_HTTPS_PROXY")
    if proxy:
        opts["proxy"] = proxy
        logger.info(f"[FetchYouTube] 使用代理: {proxy}")
    cookie = _cfg("YOUTUBE_COOKIES_FILE")
    if cookie and Path(cookie).exists():
        opts["cookiefile"] = cookie
        logger.info(f"[FetchYouTube] 使用 cookie 文件: {cookie}")
    # 从本地浏览器直接读 cookie（本地/住宅场景最省事，过 YouTube "确认非机器人"）。
    # 形如 "chrome" / "safari" / "firefox" / "chrome:Default"，缺则不用。
    browser = _cfg("YOUTUBE_COOKIES_FROM_BROWSER")
    if browser:
        opts["cookiesfrombrowser"] = tuple(browser.split(":"))
        logger.info(f"[FetchYouTube] 从浏览器读 cookie: {browser}")

    # PO Token：bgutil script 模式（本地零运维）——需装 bgutil-ytdlp-pot-provider 插件 + node/deno。
    # nsig challenge 需要 Deno（PATH 中有 deno 即可，yt-dlp 自动调用）。
    ea: dict = {}
    bgutil_script = _cfg("BGUTIL_SCRIPT_PATH")
    if bgutil_script and Path(bgutil_script).exists():
        ea["youtubepot-bgutilscript"] = {"script_path": [bgutil_script]}
        logger.info(f"[FetchYouTube] 启用 bgutil PO Token（script）: {bgutil_script}")
    opts["extractor_args"] = ea
    return opts


def _fetch_sync(url: str, out_dir: Path, resolution: str) -> Path:
    if yt_dlp is None:
        raise YouTubeFetchError("未安装 yt-dlp，请先安装 yt-dlp 后重试。")

    out_dir.mkdir(parents=True, exist_ok=True)
    last_err: Optional[Exception] = None

    for strat in _STRATEGIES:
        opts = _base_opts(out_dir, resolution)
        if strat["player_client"]:
            opts["extractor_args"].setdefault("youtube", {})["player_client"] = strat["player_client"]
        try:
            logger.info(f"[FetchYouTube] 尝试策略: {strat['name']}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
                if not path.exists():
                    for cand in (path.with_suffix(".mp4"), path.with_suffix(".mkv"), path.with_suffix(".webm")):
                        if cand.exists():
                            path = cand
                            break
                if path.exists():
                    logger.info(
                        f"[FetchYouTube] ✓ 下载成功（{strat['name']}）: {path.name} "
                        f"({path.stat().st_size // 1024 // 1024}MB)"
                    )
                    return path
                last_err = YouTubeFetchError("下载完成但找不到输出文件")
        except Exception as e:  # noqa: BLE001 —— 逐策略降级
            last_err = e
            logger.warning(f"[FetchYouTube] 策略 {strat['name']} 失败: {e}")

    raise YouTubeFetchError(
        f"YouTube 下载失败（已试 {len(_STRATEGIES)} 种策略）。住宅 IP 通常可直下；"
        f"若在云/受限网络，可配 YOUTUBE_COOKIES_FILE / YOUTUBE_PROXY 提升成功率。最后错误: {last_err}"
    )


async def fetch_youtube(url: str, out_dir: str, resolution: str = "720") -> str:
    """下载 YouTube 视频到 out_dir，返回本地文件路径。

    yt-dlp 是同步阻塞的，放线程池，避免阻塞 asyncio 事件循环（与项目其它 to_thread 用法一致）。
    """
    return str(await asyncio.to_thread(_fetch_sync, url, Path(out_dir), resolution))


def is_youtube_url(text: str) -> bool:
    """粗略判断是否 YouTube 链接。"""
    t = (text or "").strip().lower()
    return any(h in t for h in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts", "m.youtube.com/watch"))
