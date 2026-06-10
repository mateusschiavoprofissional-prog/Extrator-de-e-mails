import sqlite3
import os
import json
from datetime import datetime

CONFIG_PATH = "config.json"

def obter_perfil_ativo_folder():
    if not os.path.exists(CONFIG_PATH):
        return ""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            active_name = config.get("active_profile", "Default")
            profiles = config.get("profiles", [])
            for p in profiles:
                if p["name"] == active_name:
                    return p["folder"]
    except Exception as e:
        print(f"Erro ao ler config.json: {e}")
    return ""

def obter_db_path():
    folder = obter_perfil_ativo_folder()
    if folder:
        # Garante que a pasta existe
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "radar_reenvios.db")
    return "radar_reenvios.db"

def obter_conexao():
    db_path = obter_db_path()
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_banco():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    # Tabela de emails enviados
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emails_enviados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gmail_message_id TEXT UNIQUE,
        thread_id TEXT,
        data_envio TEXT,
        ano_envio INTEGER,
        mes_envio INTEGER,
        assunto_original TEXT,
        assunto_limpo TEXT,
        eh_reenvio BOOLEAN,
        id_email_reenviado TEXT
    )
    """)
    
    # Tabela de emails reenviados (agrupamentos/ranking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emails_reenviados (
        id_email_reenviado TEXT PRIMARY KEY,
        titulo TEXT,
        total_reenvios INTEGER,
        primeiro_reenvio TEXT,
        ultimo_reenvio TEXT,
        ano_maioria INTEGER,
        mes_maioria TEXT,
        reenvios_12m INTEGER DEFAULT 0,
        score REAL
    )
    """)
    
    # Tabela de eventos de reenvio individuais
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reenvios_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_email_reenviado TEXT,
        gmail_message_id TEXT UNIQUE,
        data_reenvio TEXT,
        ano INTEGER,
        mes INTEGER,
        peso_recencia REAL
    )
    """)
    
    # Tabela de metadados do sistema
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadados_sistema (
        chave TEXT PRIMARY KEY,
        valor TEXT
    )
    """)
    
    # Criar índices para performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_enviados_reenvio ON emails_enviados(eh_reenvio)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_enviados_grupo ON emails_enviados(id_email_reenviado)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eventos_grupo ON reenvios_eventos(id_email_reenviado)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reenviados_score ON emails_reenviados(score DESC)")
    
    conn.commit()
    conn.close()

def limpar_banco():
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS emails_enviados")
    cursor.execute("DROP TABLE IF EXISTS emails_reenviados")
    cursor.execute("DROP TABLE IF EXISTS reenvios_eventos")
    cursor.execute("DROP TABLE IF EXISTS metadados_sistema")
    conn.commit()
    conn.close()
    inicializar_banco()

def obter_status_sincronizacao():
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM metadados_sistema WHERE chave = 'status_extracao'")
    status = cursor.fetchone()
    cursor.execute("SELECT valor FROM metadados_sistema WHERE chave = 'ultima_extracao'")
    ultima = cursor.fetchone()
    cursor.execute("SELECT valor FROM metadados_sistema WHERE chave = 'progresso_atual'")
    progresso = cursor.fetchone()
    
    conn.close()
    return {
        "status": status["valor"] if status else "idle",
        "ultima_extracao": ultima["valor"] if ultima else None,
        "progresso": int(progresso["valor"]) if progresso else 0
    }

def atualizar_status_sincronizacao(status=None, ultima=None, progresso=None):
    conn = obter_conexao()
    cursor = conn.cursor()
    if status is not None:
        cursor.execute("INSERT OR REPLACE INTO metadados_sistema (chave, valor) VALUES ('status_extracao', ?)", (status,))
    if ultima is not None:
        cursor.execute("INSERT OR REPLACE INTO metadados_sistema (chave, valor) VALUES ('ultima_extracao', ?)", (ultima,))
    if progresso is not None:
        cursor.execute("INSERT OR REPLACE INTO metadados_sistema (chave, valor) VALUES ('progresso_atual', ?)", (str(progresso),))
    conn.commit()
    conn.close()
