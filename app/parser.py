import re
import json
from docx import Document


QUESTION_TYPES = {
    "单选": ["单选", "选择题"],
    "填空": ["填空"],
    "作图": ["作图"],
    "论述": ["论述", "简答"],
    "实验": ["实验", "探究"],
    "计算": ["计算"],
}


def detect_type(section_title: str) -> str:
    for qtype, keywords in QUESTION_TYPES.items():
        for kw in keywords:
            if kw in section_title:
                return qtype
    return "其他"


def parse_docx(file_path: str) -> list[dict]:
    doc = Document(file_path)
    questions = []
    current_type = "单选"
    current_q = None
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    for line in lines:
        # 检测题型分区标题
        for qtype, keywords in QUESTION_TYPES.items():
            if any(kw in line for kw in keywords) and ("题" in line or "分" in line):
                current_type = qtype
                break

        # 检测题目编号（1. 或 1、）
        m = re.match(r'^(\d+)[.、．]\s*(.+)', line)
        if m:
            if current_q:
                questions.append(current_q)
            current_q = {
                "question_number": m.group(1),
                "question_type": current_type,
                "content": m.group(2),
                "options": [],
                "answer": "",
                "analysis": "",
            }
            continue

        # 检测选项（A. B. C. D.）
        if current_q and re.match(r'^[A-Da-d][.、．\s]', line):
            current_q["options"].append(line)
            continue

        # 检测子问题（(1) (2)）
        if current_q and re.match(r'^[（(]\d+[）)]', line):
            current_q["content"] += "\n" + line
            continue

        # 追加到当前题目内容
        if current_q:
            current_q["content"] += "\n" + line

    if current_q:
        questions.append(current_q)

    # 序列化选项为JSON
    for q in questions:
        q["options"] = json.dumps(q["options"], ensure_ascii=False)

    return questions
