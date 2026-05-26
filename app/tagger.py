import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

PHYSICS_POINTS = [
    "力学", "压强", "浮力", "运动", "摩擦力", "重力", "弹力",
    "液体压强", "大气压强", "密度", "质量", "速度", "加速度",
    "牛顿定律", "二力平衡", "功", "功率", "机械能", "热学",
    "光学", "电学", "磁场", "浮力计算", "压强计算",
]

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model="qwen-turbo",
            api_key=os.environ.get("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0,
        )
    return _llm


def tag_question(content: str, question_type: str) -> dict:
    prompt = f"""你是初中物理老师，请分析以下物理题目，返回JSON格式：
{{
  "knowledge_points": ["考点1", "考点2"],
  "difficulty": 3
}}

knowledge_points从以下选择：{', '.join(PHYSICS_POINTS)}，最多3个。
difficulty为难度1-5，1最简单5最难，3为中等。

题型：{question_type}
题目：{content[:500]}

只返回JSON，不要其他内容。"""

    llm = _get_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content.strip()

    # strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    result = json.loads(text)
    return {
        "knowledge_points": json.dumps(result.get("knowledge_points", []), ensure_ascii=False),
        "difficulty": int(result.get("difficulty", 3)),
    }


def _default_tags() -> dict:
    return {
        "knowledge_points": json.dumps([], ensure_ascii=False),
        "difficulty": 3,
    }


def tag_question_safe(content: str, question_type: str) -> dict:
    try:
        return tag_question(content, question_type)
    except Exception:
        return _default_tags()
