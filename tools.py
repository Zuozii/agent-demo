"""工具系统：定义 Agent 能使用的工具，并负责执行它们。

每个工具由三部分组成：
1. schema        —— 给模型看的"说明书"（名称、描述、参数格式）
2. python 函数    —— 真正干活的代码
3. execute_tool  —— 根据模型点名的工具名，找到函数并执行
"""
import ast
import json  # noqa: F401  （本文件暂未用到，但工具参数处理经常会用它，先认识一下）
import operator
from datetime import datetime
from pathlib import Path

# 项目目录：read_file 工具只允许读这个目录里的文件，防止模型乱翻你的电脑
PROJECT_ROOT = Path(__file__).resolve().parent


# ---------- 工具 1：计算器 ----------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _eval_node(node):
    """递归计算 AST 节点。

    为什么不直接用 Python 的 eval()？因为 eval("任意字符串") 会执行任意代码，
    模型一旦被诱导传入恶意内容，后果不堪设想。
    这里用 AST（抽象语法树）把表达式拆开，只允许"数字 + 四则运算"通过。
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("只允许数字")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ValueError("只支持 + - * / // % ** 和括号")


def calculator(expression):
    """计算一个数学表达式，返回结果的字符串形式。"""
    tree = ast.parse(expression, mode="eval")
    return str(_eval_node(tree))


# ---------- 工具 2：获取当前时间 ----------

def get_current_time():
    """返回当前日期时间。模型自己不知道"现在几点"，必须靠工具。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 工具 4：统计字数 ----------

def word_count(text):
    """统计文本长度：返回字符数和单词数。"""
    chars = len(text)
    words = len(text.split())
    return f"共 {chars} 个字符，{words} 个词"


# ---------- 工具 3：读文件 ----------

def read_file(path, max_chars=4000):
    """读取项目目录内的文件。两道安全防线：目录边界 + 长度上限。"""
    # resolve() 会把 "../" 之类的路径还原成真实路径
    target = (PROJECT_ROOT / str(path)).resolve()
    # 防线 1：不允许读项目目录以外的文件（比如 ../../Windows/...）
    if target != PROJECT_ROOT and PROJECT_ROOT not in target.parents:
        return "错误：不允许读取项目目录之外的文件"
    if not target.is_file():
        return f"错误：文件不存在 {path}"
    text = target.read_text(encoding="utf-8", errors="replace")
    # 防线 2：太长的文件截断，防止撑爆模型的上下文窗口
    if len(text) > max_chars:
        return text[:max_chars] + f"\n……（已截断，全文共 {len(text)} 字符）"
    return text


# ---------- 工具登记表 ----------

# TOOLS 是给模型看的说明书。描述写得越清楚，模型越知道什么时候该用哪个工具。
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式，支持 + - * / // % ** 和括号。需要精确计算时务必使用，不要口算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如 (3+5)*2"}
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目目录内某个文件的文本内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对项目目录的文件路径，例如 README.md"},
                    "max_chars": {"type": "integer", "description": "最多读取多少字符，默认 4000"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "word_count",
            "description": "统计文本的字符数和单词数。用户问一段文字有多少字、多少词时使用，不要自己数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要统计的原文"}
                },
                "required": ["text"],
            },
        },
    },
]

# 工具名 -> 真正干活的函数
_FUNCTIONS = {
    "calculator": calculator,
    "get_current_time": get_current_time,
    "read_file": read_file,
    "word_count": word_count,
}


def execute_tool(name, arguments):
    """执行模型点名的工具。

    永远返回字符串，出错也返回错误描述而不是抛异常 ——
    因为错误信息要让模型看到，它才有机会纠正自己重试。
    """
    func = _FUNCTIONS.get(name)
    if func is None:
        return f"错误：不存在名为 {name} 的工具"
    try:
        return str(func(**arguments))
    except TypeError as e:
        return f"错误：参数不对 —— {e}"
    except Exception as e:
        return f"错误：工具执行失败 —— {type(e).__name__}: {e}"
