import re
import json
import hashlib
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

STATIC_IMAGES_DIR = Path(__file__).parent.parent / "static" / "images"

QUESTION_TYPES = {
    "单选": ["单选", "选择题"],
    "填空": ["填空"],
    "作图": ["作图"],
    "论述": ["论述", "简答"],
    "实验": ["实验", "探究"],
    "计算": ["计算"],
}

# 匹配题目编号开头：1. / 1。/ 1、/ 1．
_Q_NUM_RE = re.compile(r'^(\d+)[.。、．]\s*(.+)', re.DOTALL)
# 匹配单独选项行（A. / A、 / A．）
_OPTION_LINE_RE = re.compile(r'^([A-Da-d])[.、．\s](.+)')
# 匹配子问题编号 (1) （1）
_SUB_Q_RE = re.compile(r'^[（(]\d+[）)]')
# 区块标题：含题型关键词且含"题"或"分"
_SECTION_RE = re.compile(r'[题分]')


def detect_type(text: str) -> str | None:
    for qtype, keywords in QUESTION_TYPES.items():
        for kw in keywords:
            if kw in text:
                return qtype
    return None


def _extract_images_from_para(para, doc) -> list[str]:
    """提取段落中所有图片，保存到 static/images，返回文件名列表。"""
    STATIC_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filenames = []
    for drawing in para._element.findall(".//" + qn("w:drawing")):
        blip = drawing.find(".//" + qn("a:blip"))
        if blip is None:
            continue
        rid = blip.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
        )
        if not rid:
            continue
        rel = doc.part.rels.get(rid)
        if rel is None:
            continue
        img_data = rel.target_part.blob
        ext = rel.target_ref.rsplit(".", 1)[-1].lower()
        fname = hashlib.md5(img_data).hexdigest()[:12] + "." + ext
        dest = STATIC_IMAGES_DIR / fname
        if not dest.exists():
            dest.write_bytes(img_data)
        filenames.append(fname)
    return filenames


def _para_tokens(para, doc) -> list[str]:
    """将段落拆成文本+图片占位符的 token 列表。"""
    tokens = []
    text = para.text.strip()
    if text:
        tokens.append(text)
    for fname in _extract_images_from_para(para, doc):
        tokens.append(f"[图:{fname}]")
    return tokens


def _split_inline_options(text: str) -> list[str]:
    """把 'A．x\tB．y\tC．z\tD．w' 这类同行选项拆成列表。"""
    # 按制表符或 2+ 空格分割，再过滤掉不像选项的片段
    parts = re.split(r'\t|[ 　]{2,}', text)
    options = []
    for p in parts:
        p = p.strip()
        if p and re.match(r'^[A-Da-d][.、．\s]', p):
            options.append(p)
    return options


def parse_docx(file_path: str) -> list[dict]:
    doc = Document(file_path)
    questions: list[dict] = []
    current_type = "单选"
    current_q: dict | None = None

    def flush():
        nonlocal current_q
        if current_q:
            current_q["options"] = json.dumps(
                current_q["options"], ensure_ascii=False
            )
            questions.append(current_q)
            current_q = None

    for para in doc.paragraphs:
        tokens = _para_tokens(para, doc)
        if not tokens:
            continue

        # 纯图片段落（无文字）：追加到当前题目
        text = para.text.strip()
        if not text and tokens:
            if current_q:
                current_q["content"] += "\n" + "\n".join(tokens)
            continue

        # 检测区块标题（含题型关键词 + "题"/"分"）
        detected = detect_type(text)
        if detected and _SECTION_RE.search(text) and len(text) < 50:
            current_type = detected
            continue

        # 检测题目编号
        m = _Q_NUM_RE.match(text)
        if m:
            flush()
            content_start = m.group(2)
            # 把该段落的图片占位符也拼入题干
            img_tokens = [t for t in tokens if t.startswith("[图:")]
            if img_tokens:
                content_start += "\n" + "\n".join(img_tokens)
            current_q = {
                "question_number": m.group(1),
                "question_type": current_type,
                "content": content_start,
                "options": [],
                "answer": "",
                "analysis": "",
            }
            continue

        if current_q is None:
            continue

        # 检测选项行（单独一行 A. / B. 格式）
        mo = _OPTION_LINE_RE.match(text)
        if mo:
            # 先尝试拆分同行多选项
            inline = _split_inline_options(text)
            if len(inline) >= 2:
                current_q["options"].extend(inline)
            else:
                current_q["options"].append(text)
            # 该行可能同时含图片（选项图）
            for t in tokens:
                if t.startswith("[图:"):
                    current_q["options"].append(t)
            continue

        # 子问题编号行
        if _SUB_Q_RE.match(text):
            current_q["content"] += "\n" + "\n".join(tokens)
            continue

        # 其余内容追加到题目（含图片题注行如"第12题图…"）
        current_q["content"] += "\n" + "\n".join(tokens)

    flush()
    return questions
