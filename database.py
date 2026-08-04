import sqlite3
import json
import os
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "pelada.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Permanent mensalistas table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mensalistas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            estrelas INTEGER NOT NULL CHECK (estrelas >= 1 AND estrelas <= 5),
            ativo BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Active session table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('ATIVA', 'ENCERRADA')),
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            state_json TEXT NOT NULL
        );
    """)
    
    conn.commit()
    conn.close()

# Mensalista database operations
def get_all_mensalistas(query: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if query:
        cursor.execute(
            "SELECT * FROM mensalistas WHERE LOWER(nome) LIKE LOWER(?) ORDER BY nome ASC",
            (f"%{query}%",)
        )
    else:
        cursor.execute("SELECT * FROM mensalistas ORDER BY nome ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_mensalista_by_id(mensalista_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mensalistas WHERE id = ?", (mensalista_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_mensalista_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mensalistas WHERE LOWER(nome) = LOWER(?)", (name.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def add_mensalista(nome: str, estrelas: int, ativo: bool = True) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    nome_clean = nome.strip()
    if not nome_clean:
        raise ValueError("Nome não pode ser vazio.")
    if not (1 <= estrelas <= 5):
        raise ValueError("Estrelas devem ser entre 1 e 5.")
        
    cursor.execute(
        "INSERT INTO mensalistas (nome, estrelas, ativo) VALUES (?, ?, ?)",
        (nome_clean, estrelas, 1 if ativo else 0)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return get_mensalista_by_id(new_id)

def update_mensalista(mensalista_id: int, nome: str, estrelas: int, ativo: bool) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    nome_clean = nome.strip()
    if not nome_clean:
        raise ValueError("Nome não pode ser vazio.")
    if not (1 <= estrelas <= 5):
        raise ValueError("Estrelas devem ser entre 1 e 5.")
        
    cursor.execute(
        """
        UPDATE mensalistas 
        SET nome = ?, estrelas = ?, ativo = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
        """,
        (nome_clean, estrelas, 1 if ativo else 0, mensalista_id)
    )
    conn.commit()
    conn.close()
    return get_mensalista_by_id(mensalista_id)

def delete_mensalista(mensalista_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mensalistas WHERE id = ?", (mensalista_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

# Session persistence operations
def get_active_session() -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE status = 'ATIVA' ORDER BY last_saved_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        data = dict(row)
        data['state'] = json.loads(data['state_json'])
        return data
    return None

def save_session(session_id: str, state_dict: Dict[str, Any]) -> None:
    conn = get_db()
    cursor = conn.cursor()
    state_json = json.dumps(state_dict, ensure_ascii=False)
    cursor.execute("""
        INSERT INTO sessions (id, status, state_json, last_saved_at)
        VALUES (?, 'ATIVA', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            state_json = excluded.state_json,
            last_saved_at = CURRENT_TIMESTAMP,
            status = 'ATIVA'
    """, (session_id, state_json))
    conn.commit()
    conn.close()

def end_session(session_id: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET status = 'ENCERRADA', last_saved_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
