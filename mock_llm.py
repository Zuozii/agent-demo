"""假模型：不花钱、不需要网络，专门用来演示 Agent 的运行机制。

它的"智商"只有三条规则，但它返回的数据格式和真模型一模一样。
看懂了它，就看懂了真模型返回的 tool_calls 到底长什么样。
"""
import json
import re

_call_counter = 0


def _tool_call(name, arguments_json):
    """伪造一个模型点名工具的消息（格式与真实 API 完全一致）。"""
    global _call_counter
    _call_counter += 1
    return {
        "id": f"call_mock_{_call_counter}",
        "type": "function",
        "function": {"name": name, "arguments": arguments_json},
    }


def chat(messages, tools=None):
    """模拟真模型的 chat()：输入对话记录，输出一条消息。"""
    last = messages[-1]

    # 情况 1：上一条是工具返回的结果 → 基于它给出最终回答
    if last["role"] == "tool":
        return {
            "role": "assistant",
            "content": f"（Mock 模型）工具告诉我的结果是：{last['content']}，以上就是答案。",
        }

    text = last.get("content") or ""

    # 情况 2：问题里出现数学式 → 点名 calculator 工具
    candidates = re.findall(r"[\d\.\+\-\*\/\(\)\s%]+", text)
    expr = max(candidates, key=len).strip() if candidates else ""
    if expr and re.search(r"\d", expr) and re.search(r"[\+\-\*\/]", expr):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("calculator", json.dumps({"expression": expr}))],
        }

    # 情况 3.5：问字数 → 点名 word_count 工具
    # 必须放在"问时间"规则前面：像「今天…有多少字」同时包含两类关键词，
    # 具体规则要优先匹配，否则会被宽泛规则抢走（规则引擎的经典坑）
    if "多少字" in text or "字数" in text:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("word_count", json.dumps({"text": text}))],
        }

    # 情况 3：问时间 → 点名 get_current_time 工具
    if any(k in text for k in ("几点", "时间", "日期", "今天")):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("get_current_time", "{}")],
        }

    # 情况 4：不需要工具，直接回答
    return {
        "role": "assistant",
        "content": "（Mock 模型）我只是个只有三条规则的假模型。试试问我：「现在几点」或「帮我算 (3+5)*12」",
    }
