"""迷你 Agent —— 整个项目的核心，主循环不到 50 行。

运行方式：
    py agent.py            用真实大模型（需要先在 .env 里配置 API）
    py agent.py --mock     用假模型（不花钱、不需要网络，先看懂机制）
"""
import json
import sys
from pathlib import Path

from tools import TOOLS, execute_tool

MAX_STEPS = 10  # 保险丝：防止 Agent 陷入死循环烧光 API 额度

SYSTEM_PROMPT = (
    "你是一个助手，需要使用提供的工具回答问题。"
    "需要当前时间用 get_current_time，需要精确计算用 calculator，"
    "需要统计字数用 word_count，需要查看项目文件用 read_file。回答要简洁。"
)

# ── 第4课新增：跨对话记忆 ──
# 记忆本体 = 消息列表。之前它出生在 run_agent 内部（局部变量），
# 每次提问重新开始、答完就地消亡，所以 Agent"失忆"。
# 现在把它提到模块层：程序活着，记忆就活着。
memory = [{"role": "system", "content": SYSTEM_PROMPT}]


def reset_memory():
    """清空记忆、重新开始（输入 clear 触发）。给模块级变量重新赋值需要 global 声明。"""
    global memory
    memory = [{"role": "system", "content": SYSTEM_PROMPT}]
    save_memory()  # 清空也要写盘，否则下次启动又把旧记忆读回来


# ── 第5课新增：记忆的代价与治理 ──
MAX_MEMORY = 30  # 记忆上限（条数）：到顶就裁掉最旧的


def _trim_memory():
    """滑动窗口裁剪：永远保留第一条 system 提示 + 最近的消息。

    为什么必须有它：
    1. messages 只增不减 → 每次请求都重发全部历史，token 成本线性暴涨
    2. 超过模型上下文窗口 → 直接报错拒绝服务
    3. 就算没超，文本太长模型也会"lost in the middle"注意力衰减

    安全细节（code review 修出的 bug）：切割点必须落在"用户消息"上！
    带工具点名的助手消息和它的工具结果是一对，从中间下刀会拆散它们，
    API 直接报 400。所以先算出理想切割位置，再向后挪到最近的 user 消息处下刀。
    （真实系统按 token 数计预算，这里用条数近似；更高级的还有摘要压缩）
    """
    global memory
    if len(memory) <= MAX_MEMORY:
        return
    cut = len(memory) - (MAX_MEMORY - 1)  # 留 1 个位置给 system
    while cut < len(memory) and memory[cut]["role"] != "user":
        cut += 1  # 挪到下一个安全切割点（最坏情况砍光，只剩 system 重新开始）
    memory = [memory[0]] + memory[cut:]


# ── 第5课新增（续）：持久化 —— "把记忆保存成文件存起来" ──
# 记忆住在 RAM 里，程序一关就蒸发（易失）。写进 JSON 文件：重启也能续上前缘。
MEMORY_FILE = Path(__file__).resolve().parent / "memory.json"  # 和 tools.py 的 PROJECT_ROOT 同款写法


def load_memory():
    """启动时从文件恢复记忆（没有文件或文件损坏就全新开始）。"""
    global memory
    if not MEMORY_FILE.exists():
        return
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # 体检存档：必须是"非空列表 + 第一条是 system 消息"，否则发请求必炸
        if not (isinstance(data, list) and data
                and isinstance(data[0], dict) and data[0].get("role") == "system"):
            raise ValueError("存档不是合法的消息列表")
        memory = data
        # 系统提示永远用"当前代码里"的版本覆盖存档里的旧版，
        # 否则你以后改了 SYSTEM_PROMPT 也永远不会生效
        memory[0] = {"role": "system", "content": SYSTEM_PROMPT}
        print(f"（已从 {MEMORY_FILE.name} 恢复记忆，共 {len(memory)} 条）")
    except (json.JSONDecodeError, OSError, ValueError):
        # 文件坏了不该让程序崩掉：退回全新记忆
        memory = [{"role": "system", "content": SYSTEM_PROMPT}]
        print("（记忆文件损坏，已重置为全新记忆）")


def save_memory():
    """把当前记忆写入文件。每次对话后调用 = 自动存档。"""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


# ── 第8课新增：流式直播员 ──
def show(fragment):
    """模型每吐一个文字碎片，就立刻打印（不换行、强制刷新缓冲区）。"""
    print(fragment, end="", flush=True)


def run_agent(user_input, use_mock=False):
    """Agent 主循环：模型思考 -> 点名工具 -> 程序执行 -> 结果回传 -> 再思考 ……"""
    if use_mock:
        import mock_llm as llm
    else:
        import llm

    # 先整理记忆（裁掉过旧的消息），再追加这轮的话
    _trim_memory()
    memory.append({"role": "user", "content": user_input})
    messages = memory  # 起个短别名，下面的旧代码一行都不用改

    for step in range(1, MAX_STEPS + 1):
        print(f"\n── 第 {step} 步：等待模型思考（当前记忆 {len(messages)} 条）──")
        message = llm.chat(messages, tools=TOOLS, on_text=show)
        # 部分模型（如 DeepSeek）会附带 reasoning_content（思考过程）字段，
        # 这个字段只许"出"不许"进"，回传给 API 会被拒绝 —— 剥掉再入列
        message.pop("reasoning_content", None)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # 模型没有点名任何工具 -> 这是最终答案，循环结束
            answer = message.get("content") or ""
            if use_mock:
                print(f"\n【最终回答】{answer}")  # Mock 不支持流式，整段打印
            else:
                print()  # 真实模式的文字刚才已经"边生成边直播"了，这里只补个换行
            return answer

        # 模型点名了工具 -> 由【我们的程序】执行（模型自己不会执行，它只会"提请求"！）
        for call in tool_calls:
            name = call["function"]["name"]
            # 防弹衣：模型给的参数可能不是合法 JSON，解析失败就给空参数，
            # 让后面的工具执行环节返回"参数不对"的错误，模型下一轮会自己重试
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            print(f"  [工具] 模型点名：{name}，参数：{arguments}")
            result = execute_tool(name, arguments)
            print(f"  [结果] {result}")
            # 把工具结果塞回对话记录，模型下一轮就能看到
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })

    print("\n【警告】超过最大步数，强制停止。这通常意味着模型陷入了死循环。")
    return ""


def main():
    use_mock = "--mock" in sys.argv
    mode = "Mock 假模型" if use_mock else "真实模型"
    print(f"迷你 Agent 已启动（{mode}），输入 quit 退出。")
    load_memory()  # 开机恢复上次的记忆（持久化）
    while True:
        try:
            user_input = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("quit", "exit"):
            break
        # 记忆清空指令：对话太长会撑爆上下文窗口、烧token，随时可以重开
        if user_input.lower() in ("clear", "清空"):
            reset_memory()
            print("（记忆已清空，开始全新对话）")
            continue
        try:
            run_agent(user_input, use_mock=use_mock)
            save_memory()  # 每聊完一句就存档，程序重启记忆不丢
        except Exception as e:
            print(f"出错了：{e}")


if __name__ == "__main__":
    main()
