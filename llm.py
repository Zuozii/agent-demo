"""大模型 API 客户端。

用最原始的 HTTP 请求调用大模型，不装任何第三方包。
目的：让你看清楚"调模型"的本质 —— 就是发一个 HTTP POST 请求。
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid


def load_env(path=".env"):
    """读取 .env 文件里的配置到环境变量（已存在的系统环境变量优先）。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()

BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
# 该网关要求每个会话带一个固定 ID（同一会话保持一致即可，格式不限）
SESSION_ID = os.environ.get("LLM_SESSION_ID", str(uuid.uuid4()))
# 网关的防护会拦截"无名脚本"（403 或直接断连），必须声明正常的 User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
# 网络出错时的重试次数（最后一次会强制绕过代理直连）
MAX_RETRIES = 3


def chat(messages, tools=None):
    """发送一轮对话，返回模型回复的那条消息（dict）。

    messages: 到目前为止的完整对话记录，是一个 list，每条消息是 dict
    tools:    可用工具的说明书列表（OpenAI tools 格式），可以是 None

    内置网络重试：前两次走系统代理（如果有），最后一次强制直连，
    专治代理节点抽风、连接被掐断等"时断时续"的问题。
    """
    if not BASE_URL.startswith("http"):
        raise RuntimeError("请先在 .env 中填入正确的 LLM_BASE_URL（或先运行：py agent.py --mock）")
    if not API_KEY:
        raise RuntimeError("请先在 .env 中填入 LLM_API_KEY（或先运行：py agent.py --mock）")

    # 组装请求体：model + 对话记录 + 工具清单，这就是发给模型的全部内容
    # 组装请求体：model + 对话记录 + 工具清单，这就是发给模型的全部内容
    # ⚠️ 血泪教训：2026-09-07 重构时曾弄丢"if tools: payload[...]"两行，
    # 模型收不到工具菜单 → 幻觉时间、把工具名当纯文本输出（DSML泄漏）。
    # 当时误判为 temperature 的锅，靠"逐字节对比"才定位真凶。
    # 教训一：重构后必须全功能验收；教训二：疑难杂症先 diff 实际发出的字节。
    payload = {"model": MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        # 请求对象每次重建：失败过的 Request 不复用
        req = urllib.request.Request(
            url=f"{BASE_URL}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",  # API Key 放在请求头里，证明"你是谁"
                "x-opencode-session": SESSION_ID,  # 网关要求的会话标识，用于路由优化
                "User-Agent": USER_AGENT,  # 没有 UA 会被防护当恶意脚本拦截
            },
            method="POST",
        )

        # 2026-09-07 对照实验结论：本机代理对这条线路既不稳定（SSL 被掐断），
        # 又会被网关按出口 IP 路由到不处理 tools 的后端（工具调用全部失效），
        # 所以一律绕过代理直连。若换网络环境直连不通，再考虑改回走代理。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        try:
            with opener.open(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # 返回模型的那条消息，要么 content（文字回答），要么 tool_calls（点名工具）
            return data["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            # 服务器明确拒绝（Key 错、模型名错等）——重试没有意义，直接把原因抛出来
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API 返回错误 HTTP {e.code}：{body}")
        except Exception as e:
            # 网络层错误（SSL 被掐断、超时、DNS 失败……）——歇一会儿再试
            last_error = e
            print(f"  [网络] 第 {attempt}/{MAX_RETRIES} 次尝试失败：{str(e)[:60]}")
            if attempt < MAX_RETRIES:
                time.sleep(attempt)  # 退避：等 1 秒、2 秒……越挫越勇

    raise RuntimeError(f"网络重试全部失败（代理和直连都试过了）：{last_error}")
