import json
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.database import get_conn
from app.parser import parse_docx
from app.tagger import tag_question_safe
from app.exporter import build_word, build_pdf

router = APIRouter()

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")


@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    """上传Word卷子，解析入库并AI打标"""
    raw_name = file.filename or "unknown.docx"
    # 统一文件名编码为UTF-8（修复Windows浏览器上传时的GBK乱码）
    try:
        filename = raw_name.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        filename = raw_name

    if not filename.endswith(".docx"):
        raise HTTPException(400, "只支持.docx格式")

    dest = UPLOAD_DIR / filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    questions = parse_docx(str(dest))
    if not questions:
        raise HTTPException(422, "未能解析到题目，请检查文件格式")

    conn = get_conn()

    # 记录试卷来源
    cur = conn.execute(
        "INSERT INTO papers (title, source_file) VALUES (?, ?)",
        (filename.replace(".docx", ""), filename),
    )
    paper_id = cur.lastrowid

    inserted = 0
    for i, q in enumerate(questions):
        tags = tag_question_safe(q["content"], q["question_type"])
        cur = conn.execute(
            """INSERT INTO questions
               (source_file, question_number, question_type, content, options, answer, analysis,
                knowledge_points, difficulty, ai_tagged)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                filename,
                q["question_number"],
                q["question_type"],
                q["content"],
                q["options"],
                q["answer"],
                q["analysis"],
                tags["knowledge_points"],
                tags["difficulty"],
            ),
        )
        conn.execute(
            "INSERT INTO paper_questions (paper_id, question_id, order_index) VALUES (?, ?, ?)",
            (paper_id, cur.lastrowid, i),
        )
        inserted += 1

    conn.commit()
    conn.close()

    return {"message": f"成功导入{inserted}道题", "paper_id": paper_id}


@router.get("/questions")
def list_questions(
    question_type: str = None,
    knowledge_point: str = None,
    difficulty_min: int = 1,
    difficulty_max: int = 5,
    unconfirmed_only: bool = False,
):
    """题库筛选"""
    conn = get_conn()
    sql = "SELECT * FROM questions WHERE difficulty BETWEEN ? AND ?"
    params = [difficulty_min, difficulty_max]

    if question_type:
        sql += " AND question_type = ?"
        params.append(question_type)
    if knowledge_point:
        sql += " AND knowledge_points LIKE ?"
        params.append(f"%{knowledge_point}%")
    if unconfirmed_only:
        sql += " AND ai_tagged = 0"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.put("/questions/{qid}")
def update_question(qid: int, data: dict):
    """人工校正题目标签"""
    allowed = {"knowledge_points", "difficulty", "answer", "analysis", "ai_tagged"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "无有效字段")

    if "knowledge_points" in updates and isinstance(updates["knowledge_points"], list):
        updates["knowledge_points"] = json.dumps(updates["knowledge_points"], ensure_ascii=False)

    conn = get_conn()
    sets = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE questions SET {sets} WHERE id=?", [*updates.values(), qid])
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/generate")
def generate_paper(data: dict):
    """组卷并输出Word+PDF"""
    title = data.get("title", "物理试卷")
    question_ids = data.get("question_ids", [])

    if not question_ids:
        raise HTTPException(400, "请选择题目")

    conn = get_conn()
    placeholders = ",".join("?" * len(question_ids))
    rows = conn.execute(
        f"SELECT * FROM questions WHERE id IN ({placeholders})", question_ids
    ).fetchall()
    conn.close()

    questions = [dict(r) for r in rows]
    safe_title = title.replace(" ", "_").replace("/", "-")
    word_path = str(OUTPUT_DIR / f"{safe_title}.docx")
    pdf_path = str(OUTPUT_DIR / f"{safe_title}.pdf")

    build_word(title, questions, word_path)
    build_pdf(word_path, pdf_path)

    return {
        "word": f"/download/{safe_title}.docx",
        "pdf": f"/download/{safe_title}.pdf",
    }


@router.get("/download/{file_path:path}")
def download_file(file_path: str):
    import urllib.parse
    name = urllib.parse.unquote(file_path, encoding="utf-8")
    path = OUTPUT_DIR / name
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(path), filename=name)
