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

# 匹配题目编号：1. / 1。/ 1、/ 1．（编号后必须有内容）
_Q_NUM_RE = re.compile(r'^(\d+)[.。、．]\s*(.+)', re.DOTALL)
# 匹配单独选项：A. / A、 / A．
_OPTION_LINE_RE = re.compile(r'^[A-Da-d][.、．\s]')
# 匹配子问题：(1) （1）
_SUB_Q_RE = re.compile(r'^[（(]\d+[）)]')
# 大标题/区块标题模式：
#   "第Ⅰ卷"、"第Ⅱ卷"、"一、二、三…"、"二．" 等开头
#   含题型关键词 + "题"/"分" 且长度 < 60
_SECTION_HEADING_RE = re.compile(
    r'^(第[Ⅰ-Ⅹ一二三四五六七八九十\d]+[卷册]|[一二三四五六七八九十]+[、．.]\s*|[（(][一二三四五六七八九十]+[）)])'
)
# 题注行："第N题图"
_CAPTION_RE = re.compile(r'^第\d+题图')


def detect_type(text: str) -> str | None:
    for qtype, keywords in QUESTION_TYPES.items():
        for kw in keywords:
            if kw in text:
                return qtype
    return None


def _is_section_line(text: str) -> bool:
    """判断是否为大标题/区块行，应整体跳过不并入题目。"""
    # 数字开头的行是题目，不是区块标题
    if re.match(r'^\d', text):
        return False
    if len(text) > 80:
        return False
    if _SECTION_HEADING_RE.match(text):
        return True
    # 含题型词且含"题"或"分"，短行
    if detect_type(text) and re.search(r'[题分]', text) and len(text) < 60:
        return True
    return False


def _extract_images_from_para(para, doc) -> list[str]:
    """提取段落中所有图片，保存到 static/images/，返回文件名列表。"""
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


def _split_inline_options(text: str) -> list[str]:
    """把 'A．x\tB．y\tC．z\tD．w' 拆成列表，至少匹配到2项才认为是同行多选项。"""
    parts = re.split(r'\t|[ 　]{2,}', text)
    options = []
    for p in parts:
        p = p.strip()
        if p and _OPTION_LINE_RE.match(p):
            options.append(p)
    return options if len(options) >= 2 else []


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
        text = para.text.strip()
        img_fnames = _extract_images_from_para(para, doc)
        img_tokens = [f"[图:{f}]" for f in img_fnames]

        # 纯图片段落（无文字）
        if not text:
            if img_tokens and current_q:
                current_q["content"] += "\n" + "\n".join(img_tokens)
            continue

        # 跳过大标题/区块标题行（但先提取里面可能有的新题型）
        if _is_section_line(text):
            detected = detect_type(text)
            if detected:
                current_type = detected
            continue

        # 跳过题注行（"第12题图 第13题图…"）
        if _CAPTION_RE.match(text):
            continue

        # 检测题目编号
        m = _Q_NUM_RE.match(text)
        if m:
            flush()
            content_start = m.group(2)
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

        # 选项行
        if _OPTION_LINE_RE.match(text):
            inline = _split_inline_options(text)
            if inline:
                current_q["options"].extend(inline)
            else:
                current_q["options"].append(text)
            # 选项行附带图片（选项图）
            if img_tokens:
                current_q["options"].extend(img_tokens)
            continue

        # 子问题行
        if _SUB_Q_RE.match(text):
            parts = [text] + img_tokens
            current_q["content"] += "\n" + "\n".join(parts)
            continue

        # 其余内容（续行、图片注释等）追加到题目
        parts = [text] + img_tokens
        current_q["content"] += "\n" + "\n".join(parts)

    flush()
    return questions
