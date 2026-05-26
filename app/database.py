import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "exam.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            question_number TEXT,
            question_type TEXT NOT NULL,  -- 单选/填空/作图/论述/实验/计算
            content TEXT NOT NULL,
            options TEXT,                 -- JSON, 选择题选项
            answer TEXT,
            analysis TEXT,
            knowledge_points TEXT,        -- JSON列表, AI打标考点
            difficulty INTEGER DEFAULT 3, -- 1-5
            ai_tagged INTEGER DEFAULT 0,  -- 0=待校正 1=已确认
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS paper_questions (
            paper_id INTEGER,
            question_id INTEGER,
            order_index INTEGER,
            FOREIGN KEY (paper_id) REFERENCES papers(id),
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );
    """)
    conn.commit()
    conn.close()
