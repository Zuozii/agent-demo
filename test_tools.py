"""agent-demo 的第一批单元测试（第9课）。

运行方式：
    py -3.12 -X utf8 -m pytest test_tools.py -v

pytest 的发现规则：文件名 test_ 开头、测试函数名 test_ 开头，它就会自动找到并运行。
"""

import pytest

import agent
from tools import calculator, word_count, read_file, execute_tool


# ---------- 工具函数本身的正确性 ----------

def test_calculator_basic():
    """计算器能算对——用的是第3课验收时的真实案例。"""
    assert calculator("(3+5)*12+100") == "196"


def test_word_count():
    """字数统计——第2课验收时的真实案例。"""
    assert word_count("今天学习 Python 真开心") == "共 15 个字符，3 个词"


def test_read_file_blocks_outside_project():
    """安全防线1：试图读项目目录之外的文件必须被拦截（AST/路径安全）。"""
    result = read_file("../../Windows/win.ini")
    assert result.startswith("错误")


def test_read_file_missing_file():
    """不存在的文件 → 返回错误说明，而不是让程序崩溃。"""
    result = read_file("不存在的文件.txt")
    assert result.startswith("错误")


# ---------- execute_tool：调度器的"好脾气"哲学 ----------

def test_execute_tool_dispatches_by_name():
    """按名字调度：模型点 calculator，就该真的执行 calculator。"""
    assert execute_tool("calculator", {"expression": "7*8"}) == "56"


def test_execute_tool_unknown_tool_returns_error_text():
    """点了不存在的工具 → 不崩溃，返回错误文字让模型自己纠正。"""
    result = execute_tool("不存在的工具", {})
    assert "不存在" in result


def test_execute_tool_bad_params_returns_error_text():
    """参数缺失（比如防弹衣塞进来的空参数）→ 返回错误文字。"""
    result = execute_tool("word_count", {})
    assert result.startswith("错误")


def test_execute_tool_catches_crash_as_text():
    """工具内部崩溃（1/0 除零）→ 也变成错误文字，而不是炸穿主循环。"""
    result = execute_tool("calculator", {"expression": "1/0"})
    assert result.startswith("错误")


# ---------- 计算器的安全白名单：AST 只放行数学 ----------

def test_calculator_rejects_dangerous_code():
    """安全防线2：试图借计算器执行系统命令，必须被 AST 白名单拒绝。

    注意：这里测的是"拒绝"，所以用 pytest.raises 断言"必须抛异常"——
    和上面"错误变文字"并不矛盾：calculator 直接调用会抛，
    经 execute_tool 调用才被转成文字。
    """
    with pytest.raises(ValueError):
        calculator("__import__('os').system('echo hacked')")


# ---------- 记忆裁剪：既瘦身又不能拆散工具对 ----------

def fresh_memory():
    """测试辅助：把 agent 的记忆重置为全新状态（不碰磁盘上的 memory.json）。"""
    agent.memory = [{"role": "system", "content": agent.SYSTEM_PROMPT}]


def tool_pairs_intact(msgs):
    """校验器：每条 tool 消息的前一条必须是带 tool_calls 的 assistant。"""
    for i, m in enumerate(msgs):
        if m.get("role") == "tool":
            prev = msgs[i - 1]
            if not (prev.get("role") == "assistant" and prev.get("tool_calls")):
                return False
    return True


def test_trim_memory_keeps_system_head():
    """裁剪后 system 提示必须还排在第一位。"""
    fresh_memory()
    for i in range(40):
        agent.memory.append({"role": "user", "content": f"填充消息{i}"})
    agent._trim_memory()
    assert agent.memory[0]["role"] == "system"
    assert len(agent.memory) <= agent.MAX_MEMORY


def test_trim_memory_never_splits_tool_pairs():
    """裁剪的安全切点必须落在 user 消息上——绝不拆散 assistant(tool_calls) 和 tool 结果。"""
    fresh_memory()
    for i in range(20):
        agent.memory.append({"role": "user", "content": f"消息{i}"})
    agent.memory.append({"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "calculator", "arguments": "{}"}}
    ]})
    agent.memory.append({"role": "tool", "tool_call_id": "c1", "content": "42"})
    for i in range(10):
        agent.memory.append({"role": "user", "content": f"尾巴{i}"})
    agent._trim_memory()
    assert agent.memory[0]["role"] == "system"
    assert tool_pairs_intact(agent.memory)
