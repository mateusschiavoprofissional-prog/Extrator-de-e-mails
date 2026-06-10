import os
import re
import csv
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request as FastAPIRequest, UploadFile, File
import unicodedata
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import csv
import io

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import database

app = FastAPI(title="Radar de Reenvios Dashboard")

# Configuração de CORS para evitar o erro "Failed to fetch"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_PATH = "config.json"

def inicializar_configuracao():
    if not os.path.exists(CONFIG_PATH):
        dados_iniciais = {
            "active_profile": "Default",
            "profiles": [
                {"name": "Default", "folder": ""}
            ]
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(dados_iniciais, f, indent=4, ensure_ascii=False)

inicializar_configuracao()
database.inicializar_banco()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Estado em memória da extração atual
class ExtracaoStatus:
    status = "idle"  # idle, running, paused, stopped
    total_mensagens = 0
    mensagens_processadas = 0
    reenvios_detectados = 0
    erro = None
    mensagens_lista = []
    indice_atual = 0
    run_id = 0  # Identificador para ignorar tarefas de execuções anteriores

status_extracao = ExtracaoStatus()

class ProfileModel(BaseModel):
    name: str
    folder: str

class ActiveProfileModel(BaseModel):
    name: str

# Helpers de caminhos
def obter_perfil_paths():
    folder = database.obter_perfil_ativo_folder()
    if folder:
        return {
            "credentials": os.path.join(folder, "credentials.json"),
            "token": os.path.join(folder, "token.json"),
            "folder": folder
        }
    return {
        "credentials": "credentials.json",
        "token": "token.json",
        "folder": ""
    }

def obter_gmail_service():
    paths = obter_perfil_paths()
    if not os.path.exists(paths["token"]):
        raise HTTPException(status_code=401, detail="Não autenticado. Por favor, faça login com o Google.")
        
    creds = Credentials.from_authorized_user_file(paths["token"], SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(paths["token"], "w", encoding="utf-8") as token:
                token.write(creds.to_json())
        else:
            raise HTTPException(status_code=401, detail="Sessão expirada. Refaça a autenticação.")
            
    return build("gmail", "v1", credentials=creds)

# Endpoint leve para checar status de autenticação (sem gerar novo flow OAuth)
@app.get("/api/auth-status")
def get_auth_status():
    paths = obter_perfil_paths()
    
    if not os.path.exists(paths["credentials"]):
        return {
            "authenticated": False,
            "status": "no_credentials",
            "message": f"Arquivo credentials.json não encontrado na pasta '{paths['folder'] or 'raiz'}'."
        }
    
    if os.path.exists(paths["token"]):
        try:
            creds = Credentials.from_authorized_user_file(paths["token"], SCOPES)
            if creds.valid or creds.refresh_token:
                return {"authenticated": True, "status": "authorized"}
        except Exception:
            pass
    
    return {"authenticated": False, "status": "pending"}

# Endpoints de Autenticação Web-Based (não bloqueante)
@app.get("/api/auth-url")
def get_auth_url(request: FastAPIRequest):
    paths = obter_perfil_paths()
    
    if os.path.exists(paths["token"]):
        # Verificar validade básica do token
        try:
            creds = Credentials.from_authorized_user_file(paths["token"], SCOPES)
            if creds.valid or creds.refresh_token:
                return {"authenticated": True}
        except Exception:
            pass
            
    if not os.path.exists(paths["credentials"]):
        return {
            "authenticated": False, 
            "error": f"Arquivo credentials.json não encontrado na pasta '{paths['folder'] or 'raiz'}'. Coloque o arquivo nela."
        }
        
    # URL de redirecionamento do callback local
    redirect_uri = f"http://localhost:5210/callback"
    
    flow = InstalledAppFlow.from_client_secrets_file(
        paths["credentials"], 
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    app.state.oauth_flow = flow
    
    return {"authenticated": False, "auth_url": auth_url}

@app.get("/callback")
def oauth_callback(code: str):
    paths = obter_perfil_paths()
    try:
        if hasattr(app.state, "oauth_flow") and app.state.oauth_flow:
            flow = app.state.oauth_flow
        else:
            redirect_uri = f"http://localhost:5210/callback"
            flow = InstalledAppFlow.from_client_secrets_file(
                paths["credentials"], 
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Garante a pasta de destino do token
        if paths["folder"]:
            os.makedirs(paths["folder"], exist_ok=True)
            
        with open(paths["token"], "w", encoding="utf-8") as token:
            token.write(creds.to_json())
            
        return HTMLResponse(content="""
            <html>
                <body style="font-family: 'Plus Jakarta Sans', sans-serif; text-align: center; padding-top: 100px; background: #0f0c1b; color: #fff;">
                    <div style="max-width: 500px; margin: 0 auto; background: rgba(22,17,45,0.8); border: 1px solid rgba(255,255,255,0.1); padding: 40px; border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);">
                        <h2 style="color: #10b981; margin-bottom: 20px;">Autenticação Concluída!</h2>
                        <p style="color: #9ca3af; line-height: 1.6;">O token de acesso foi salvo com sucesso. Você pode fechar esta aba e voltar ao painel do Radar de Reenvios para iniciar a extração.</p>
                        <button onclick="window.close()" style="margin-top: 30px; background: #6366f1; border: none; color: #fff; padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer;">Fechar Janela</button>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(content=f"""
            <html>
                <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background: #0f0c1b; color: #fff;">
                    <h2 style="color: #ef4444;">Erro na Autenticação</h2>
                    <p>{str(e)}</p>
                </body>
            </html>
        """)

# Regras de Negócio e Parser
def normalizar_para_id(assunto):
    """Gera um ID único para agrupamento pelo título limpo (Une 'Fwd: X' com 'X')."""
    if not assunto:
        return "sem_assunto"
    # Remove prefixos (Fwd, Re, Enc, RV, AW, etc) de forma agressiva em vários idiomas
    t = re.sub(r"(?i)^\s*((re|res|fw|fwd|enc|encaminhado|tr|forward|rv|aw|wg|rv|aw|wg)\s*[:\-]\s*)+", "", assunto)
    # Remove tags entre colchetes ou chaves (mantém parênteses)
    t = re.sub(r"\[.*?\]|\{.*?\}", "", t).strip()
    t = re.sub(r"\s+", " ", t).strip()
    # Remove acentos
    t = "".join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    # Mantém apenas letras e números
    id_limpo = re.sub(r"[^a-zA-Z0-9]", "", t).lower()
    return id_limpo if id_limpo else "assunto_generico"

def limpar_titulo_visual(assunto):
    """Limpa o título para exibição na tabela, mantendo legibilidade."""
    if not assunto:
        return "Sem assunto"
    # Remove prefixos de encaminhamento/resposta de forma agressiva
    t = re.sub(r"(?i)^\s*((re|res|fw|fwd|enc|encaminhado|tr|forward|rv|aw|wg|rv|aw|wg)\s*[:\-]\s*)+", "", assunto)
    # Remove tags entre colchetes ou chaves (mantém parênteses)
    t = re.sub(r"\[.*?\]|\{.*?\}", "", t).strip()
    # Normaliza múltiplos espaços
    return re.sub(r"\s+", " ", t).strip()

def obter_header(headers, nome):
    for header in headers:
        if header.get("name", "").lower() == nome.lower():
            return header.get("value", "")
    return ""

def eh_reenvio(assunto, snippet):
    assunto_lower = assunto.lower() if assunto else ""
    snippet_lower = snippet.lower() if snippet else ""
    
    for prefixo in ["fwd:", "fw:", "enc:", "encaminhado:", "forward:"]:
        if prefixo in assunto_lower:
            return True
            
    if re.search(r"\b(fwd|fw|enc|forward)\b", assunto_lower):
        return True
        
    if "mensagem encaminhada" in snippet_lower or "forwarded message" in snippet_lower:
        return True
        
    return False

# =========================================================================
# CONFIGURAÇÃO GERAL DE PESOS E PARÂMETROS DO RANKING
# Altere os valores neste bloco para ajustar a importância de cada critério.
# =========================================================================
PESOS_RANKING = {
    # 1. Pesos por ano de envio (quanto mais novo, mais relevante)
    "anos": {
        2026: 100.0,  # Ano corrente
        2025: 30.0,
        2024: 10.0,
        2023: 3.0,
        2022: 1.0,
        "outros": 0.1
    },
    
    # 2. Bônus fixo somado ao score para cada e-mail com reenvio detectado ("Fwd:", "Enc:", etc.)
    "bonus_eh_reenvio": 20.0,
    
    # 3. Bônus fixo para cada e-mail enviado recentemente (nos últimos 12 meses)
    "bonus_recencia_12m": 25.0,
    
    # 4. Multiplicador de volume total (escalona a pontuação total pelo volume de mensagens do grupo)
    # Ex: se for 0.5, cada reenvio adicional após o primeiro soma 50% extra do peso calculado.
    # Se for 0.0, o volume de reenvios não multiplica a pontuação.
    "multiplicador_volume_total": 0.5
}

def calcular_peso_recencia(ano):
    """Retorna o peso base do ano cadastrado em PESOS_RANKING."""
    return PESOS_RANKING["anos"].get(ano, PESOS_RANKING["anos"]["outros"])

def calcular_score_grupo(rows):
    """Calcula a pontuação final de relevância (score) do grupo com base nas configurações de pesos."""
    score_total = 0.0
    total_messages = len(rows)
    now_dt = datetime.now()
    
    for row in rows:
        # 1. Peso base do ano
        ano_envio = row.get("ano_envio")
        peso_ano = PESOS_RANKING["anos"].get(ano_envio, PESOS_RANKING["anos"]["outros"])
        
        # 2. Bônus de reenvio real
        peso_reenvio = PESOS_RANKING["bonus_eh_reenvio"] if row.get("eh_reenvio") else 0.0
        
        # 3. Bônus por recência de 12 meses
        peso_recencia_12m = 0.0
        dstr = row.get("data_envio")
        if dstr:
            try:
                dt_envio = None
                if len(dstr) >= 10:
                    try:
                        dt_envio = datetime(int(dstr[:4]), int(dstr[5:7]), int(dstr[8:10]))
                    except ValueError:
                        pass
                if not dt_envio:
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                        try:
                            dt_envio = datetime.strptime(str(dstr), fmt)
                            break
                        except ValueError:
                            pass
                if dt_envio:
                    dias_diferenca = (now_dt - dt_envio).days
                    if dias_diferenca <= 365:
                        peso_recencia_12m = PESOS_RANKING["bonus_recencia_12m"]
            except:
                pass
                
        score_total += (peso_ano + peso_reenvio + peso_recencia_12m)
        
    # 4. Multiplicador por volume total
    mult_vol = PESOS_RANKING["multiplicador_volume_total"]
    if mult_vol > 0:
        score_total = score_total * (1 + (total_messages - 1) * mult_vol)
        
    return round(score_total, 2)

def recalcular_ranking(conn):
    from collections import Counter
    cursor = conn.cursor()
    
    # 1. Obter todos os grupos distintos
    cursor.execute("SELECT DISTINCT id_email_reenviado FROM emails_enviados")
    grupos = [row[0] for row in cursor.fetchall() if row[0]]
    
    # Limpar tabelas dependentes
    cursor.execute("DELETE FROM emails_reenviados")
    cursor.execute("DELETE FROM reenvios_eventos")
    
    for grupo in grupos:
        # Obter todas as mensagens desse grupo
        cursor.execute("""
            SELECT gmail_message_id, thread_id, data_envio, ano_envio, mes_envio, assunto_original, assunto_limpo, eh_reenvio
            FROM emails_enviados
            WHERE id_email_reenviado = ?
        """, (grupo,))
        rows = [dict(r) for r in cursor.fetchall()]
        
        total_messages = len(rows)
        
        # Inserir na tabela de eventos
        for row in rows:
            peso = calcular_peso_recencia(row["ano_envio"])
            cursor.execute("""
                INSERT OR IGNORE INTO reenvios_eventos (id_email_reenviado, gmail_message_id, data_reenvio, ano, mes, peso_recencia)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (grupo, row["gmail_message_id"], row["data_envio"], row["ano_envio"], row["mes_envio"], peso))
        
        # Calcular datas de primeiro e ultimo
        datas_str = [row["data_envio"] for row in rows if row["data_envio"]]
        primeiro = min(datas_str) if datas_str else None
        ultimo = max(datas_str) if datas_str else None
        
        # score total calculado pela função unificada
        score_total = calcular_score_grupo(rows)
        
        # título para exibição (usar o do e-mail mais recente ou o primeiro assunto_limpo)
        rows_sorted = sorted(rows, key=lambda r: r["data_envio"] or "", reverse=True)
        titulo = rows_sorted[0]["assunto_limpo"] if rows_sorted else grupo
        
        # ano_maioria
        anos = [r["ano_envio"] for r in rows if r["ano_envio"]]
        ano_maioria = Counter(anos).most_common(1)[0][0] if anos else datetime.now().year
        
        # mes_maioria
        meses = [f"{r['ano_envio']}-{r['mes_envio']:02d}" for r in rows if r["ano_envio"] and r["mes_envio"]]
        mes_maioria = Counter(meses).most_common(1)[0][0] if meses else ""
        
        # reenvios_12m
        cursor.execute("""
            SELECT COUNT(*) FROM reenvios_eventos
            WHERE id_email_reenviado = ? AND data_reenvio >= date('now', '-12 months')
        """, (grupo,))
        qtd_12m = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT OR REPLACE INTO emails_reenviados 
            (id_email_reenviado, titulo, total_reenvios, primeiro_reenvio, ultimo_reenvio, ano_maioria, mes_maioria, reenvios_12m, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (grupo, titulo, total_messages, primeiro, ultimo, ano_maioria, mes_maioria, qtd_12m, score_total))


# Processo Asíncrono de Loop com Controle de Estado (Start, Pause, Stop)
async def loop_extracao():
    global status_extracao
    current_run_id = status_extracao.run_id
    
    try:
        service = obter_gmail_service()
        
        # Se for o início do processo (lista vazia)
        if not status_extracao.mensagens_lista:
            # Limpar tabelas para nova extração limpa no banco de dados ativo
            database.limpar_banco()
            database.atualizar_status_sincronizacao(status="running", progresso=0)
            
            # Buscar e-mails enviados
            query = 'in:sent'
            
            mensagens = []
            page_token = None
            
            while True:
                # Se for cancelado enquanto carrega lista
                if status_extracao.status == "stopped" or status_extracao.run_id != current_run_id:
                    return
                    
                resposta = await asyncio.to_thread(
                    lambda: service.users().messages().list(
                        userId="me",
                        q=query,
                        maxResults=500,
                        pageToken=page_token
                    ).execute()
                )
                
                mensagens.extend(resposta.get("messages", []))
                page_token = resposta.get("nextPageToken")
                
                status_extracao.total_mensagens = len(mensagens)
                await asyncio.sleep(0.05)
                if not page_token:
                    break
                    
            status_extracao.mensagens_lista = mensagens
            status_extracao.total_mensagens = len(mensagens)
            status_extracao.indice_atual = 0
            
        total = status_extracao.total_mensagens
        
        if total == 0:
            status_extracao.status = "completed"
            database.atualizar_status_sincronizacao(status="idle", ultima=datetime.now().strftime("%d/%m/%Y %H:%M"), progresso=100)
            return

        chunk_size = 20
        
        while status_extracao.indice_atual < total:
            # Controladores de pausa/parada no loop
            if status_extracao.status == "paused":
                database.atualizar_status_sincronizacao(status="paused")
                return
            elif status_extracao.status == "stopped" or status_extracao.run_id != current_run_id:
                # Não limpa o banco aqui para evitar conflito com o comando de reiniciar
                status_extracao.mensagens_lista = []
                status_extracao.indice_atual = 0
                status_extracao.total_mensagens = 0
                status_extracao.reenvios_detectados = 0
                database.atualizar_status_sincronizacao(status="idle", progresso=0)
                return
                
            chunk = status_extracao.mensagens_lista[status_extracao.indice_atual : status_extracao.indice_atual + chunk_size]
            
            # Função assíncrona para buscar uma única mensagem
            async def baixar_uma_mensagem(item):
                try:
                    # Instancia um service thread-local isolado para garantir segurança SSL e evitar concorrência no httplib2
                    thread_service = obter_gmail_service()
                    return await asyncio.to_thread(
                        lambda: thread_service.users().messages().get(
                            userId="me",
                            id=item["id"],
                            format="metadata",
                            metadataHeaders=["Subject", "Date"],
                        ).execute()
                    )
                except Exception as e:
                    print(f"Erro ao baixar mensagem {item['id']}: {e}")
                    return None

            # Executa buscas do chunk concorrentemente
            tasks = [baixar_uma_mensagem(item) for item in chunk]
            resultados = await asyncio.gather(*tasks)
            
            # Salvar resultados do chunk no banco
            conn = database.obter_conexao()
            cursor = conn.cursor()
            
            grupos_modificados = set()
            
            for msg in resultados:
                if not msg:
                    continue
                
                try:
                    msg_id = msg["id"]
                    thread_id = msg["threadId"]
                    snippet = msg.get("snippet", "")
                    headers = msg.get("payload", {}).get("headers", [])
                    
                    assunto = obter_header(headers, "Subject")
                    data_str = obter_header(headers, "Date")
                    
                    data_match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}:\d{2}:\d{2})", data_str)
                    if data_match:
                        dia, mes_nome, ano, hora = data_match.groups()
                        meses_dict = {
                            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
                        }
                        mes = meses_dict.get(mes_nome[:3].capitalize(), 1)
                        # Inclui hora, minuto e segundo para o cálculo do score
                        h, m, s = map(int, hora.split(':'))
                        dt = datetime(int(ano), mes, int(dia), h, m, s)
                    else:
                        dt = datetime.fromtimestamp(int(msg["internalDate"]) / 1000)
                    
                    ano_envio = dt.year
                    mes_envio = dt.month
                    data_formatada = dt.strftime("%Y-%m-%d %H:%M:%S")
                    
                    assunto_limpo = limpar_titulo_visual(assunto)
                    id_grupo = normalizar_para_id(assunto)
                    
                    # Agora usa a função de detecção real
                    is_forward = eh_reenvio(assunto, snippet)
                    
                    cursor.execute("""
                    INSERT OR IGNORE INTO emails_enviados 
                    (gmail_message_id, thread_id, data_envio, ano_envio, mes_envio, assunto_original, assunto_limpo, eh_reenvio, id_email_reenviado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (msg_id, thread_id, data_formatada, ano_envio, mes_envio, assunto, assunto_limpo, is_forward, id_grupo))
                    
                    status_extracao.reenvios_detectados += 1
                    grupos_modificados.add(id_grupo)
                        
                except Exception as e:
                    print(f"Erro ao processar mensagem no banco: {e}")
            
            conn.commit()
            
            # ATUALIZAÇÃO OTIMIZADA: Recalcula apenas os grupos afetados neste chunk
            if grupos_modificados:
                from collections import Counter
                for grupo in grupos_modificados:
                    cursor.execute("""
                        SELECT gmail_message_id, thread_id, data_envio, ano_envio, mes_envio, assunto_original, assunto_limpo, eh_reenvio
                        FROM emails_enviados WHERE id_email_reenviado = ?
                    """, (grupo,))
                    rows = [dict(r) for r in cursor.fetchall()]
                    
                    total_messages = len(rows)
                    
                    # Primeiro, deletar eventos antigos deste grupo
                    cursor.execute("DELETE FROM reenvios_eventos WHERE id_email_reenviado = ?", (grupo,))
                    
                    # Inserir eventos de reenvio
                    for row in rows:
                        peso = calcular_peso_recencia(row["ano_envio"])
                        cursor.execute("""
                            INSERT OR IGNORE INTO reenvios_eventos (id_email_reenviado, gmail_message_id, data_reenvio, ano, mes, peso_recencia)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (grupo, row["gmail_message_id"], row["data_envio"], row["ano_envio"], row["mes_envio"], peso))
                    
                    # Calcular datas de primeiro e ultimo
                    datas_str = [row["data_envio"] for row in rows if row["data_envio"]]
                    primeiro = min(datas_str) if datas_str else None
                    ultimo = max(datas_str) if datas_str else None
                    
                    # score total calculado pela função unificada
                    score_total = calcular_score_grupo(rows)
                    
                    rows_sorted = sorted(rows, key=lambda r: r["data_envio"] or "", reverse=True)
                    titulo = rows_sorted[0]["assunto_limpo"] if rows_sorted else grupo
                    
                    anos = [r["ano_envio"] for r in rows if r["ano_envio"]]
                    ano_pred = Counter(anos).most_common(1)[0][0] if anos else datetime.now().year
                    
                    meses = [f"{r['ano_envio']}-{r['mes_envio']:02d}" for r in rows if r["ano_envio"] and r["mes_envio"]]
                    mes_pred = Counter(meses).most_common(1)[0][0] if meses else ""
                    
                    cursor.execute("""
                        SELECT COUNT(*) FROM reenvios_eventos 
                        WHERE id_email_reenviado = ? AND data_reenvio >= date('now', '-12 months')
                    """, (grupo,))
                    qtd_12m = cursor.fetchone()[0]
                    
                    cursor.execute("""
                    INSERT OR REPLACE INTO emails_reenviados 
                    (id_email_reenviado, titulo, total_reenvios, primeiro_reenvio, ultimo_reenvio, 
                     ano_maioria, mes_maioria, reenvios_12m, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (grupo, titulo, total_messages, primeiro, ultimo, 
                          ano_pred, mes_pred, qtd_12m, score_total))
                
                conn.commit()
            conn.close()
            
            # Incrementa o progresso
            status_extracao.indice_atual += len(chunk)
            status_extracao.mensagens_processadas = status_extracao.indice_atual
            
            # Atualiza status e progresso no SQLite
            progresso_pct = int((status_extracao.indice_atual / total) * 100)
            database.atualizar_status_sincronizacao(status="running", progresso=progresso_pct)
            
            # Pequeno intervalo assíncrono para aliviar o processador e o loop
            await asyncio.sleep(0.2)
            
        # Recalcular ranking final
        conn = database.obter_conexao()
        recalcular_ranking(conn)
        conn.close()
        
        status_extracao.status = "completed"
        status_extracao.mensagens_lista = []
        database.atualizar_status_sincronizacao(
            status="idle", 
            ultima=datetime.now().strftime("%d/%m/%Y %H:%M"), 
            progresso=100
        )
        
    except Exception as e:
        status_extracao.status = "error"
        status_extracao.erro = str(e)
        database.atualizar_status_sincronizacao(status="error", progresso=0)
        print(f"Erro na extração: {e}")

# Endpoints de controle da sincronização (Iniciar, Pausar, Parar)

@app.post("/api/sync/start")
def start_sync(background_tasks: BackgroundTasks):
    if status_extracao.status == "running":
        return {"status": "already_running", "message": "A extração já está rodando."}
        
    status_extracao.status = "running"
    background_tasks.add_task(loop_extracao)
    return {"status": "started", "message": "Extração iniciada."}

@app.post("/api/sync/pause")
def pause_sync():
    if status_extracao.status != "running":
        return {"status": "error", "message": "A extração não está ativa para ser pausada."}
    status_extracao.status = "paused"
    return {"status": "paused", "message": "Extração pausada."}

@app.post("/api/sync/stop")
def stop_sync():
    status_extracao.status = "stopped"
    return {"status": "stopped", "message": "Extração interrompida e limpa."}

@app.post("/api/sync/restart")
def restart_sync(background_tasks: BackgroundTasks):
    # Incrementa o run_id para invalidar qualquer loop de extração que esteja rodando agora
    status_extracao.run_id += 1
    status_extracao.status = "idle"
    status_extracao.mensagens_lista = []
    status_extracao.total_mensagens = 0
    status_extracao.indice_atual = 0
    status_extracao.mensagens_processadas = 0
    status_extracao.reenvios_detectados = 0
    status_extracao.erro = None
    
    # Limpa o banco de dados
    database.limpar_banco()
    database.atualizar_status_sincronizacao(status="idle", progresso=0)
    
    # Inicia nova extração do zero
    status_extracao.status = "running"
    background_tasks.add_task(loop_extracao)
    return {"status": "restarted", "message": "Banco limpo e extração reiniciada do zero."}

@app.post("/api/upload-data")
async def upload_data(file: UploadFile = File(...)):
    """Processa upload de arquivos JSON, JSONL, CSV ou TXT criando e ativando um novo perfil."""
    filename = file.filename.lower()
    print(f"\n[INFO] Recebido upload do arquivo para novo perfil: {filename}")
    
    try:
        content = await file.read()
        records = []
        if filename.endswith(".json"):
            try:
                records = json.loads(content)
                if not isinstance(records, list):
                    records = [records]
            except Exception as e:
                print(f"[ERROR] Falha ao parsear JSON: {e}")
                raise HTTPException(status_code=400, detail=f"JSON inválido: {str(e)}")
        elif filename.endswith(".jsonl") or filename.endswith(".txt"):
            lines = content.decode('utf-8', errors='ignore').splitlines()
            for idx, line in enumerate(lines, start=1):
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except Exception as parse_err:
                        print(f"[WARNING] Erro de parse na linha {idx}: {parse_err}")
        elif filename.endswith(".csv"):
            try:
                stream = io.StringIO(content.decode('utf-8-sig', errors='ignore'))
                reader = csv.DictReader(stream, delimiter=';')
                records = list(reader)
            except Exception as e:
                print(f"[ERROR] Falha ao parsear CSV: {e}")
                raise HTTPException(status_code=400, detail=f"CSV inválido: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail="Formato não suportado. Use JSON, JSONL, CSV ou TXT.")

        print(f"[INFO] Total de registros decodificados: {len(records)}")

        if not records:
            return {"status": "error", "message": "Arquivo vazio ou sem registros válidos."}

        # 1. Definir e criar pasta do Perfil baseado no nome do arquivo
        base_name = os.path.splitext(file.filename)[0]
        # Remove caracteres inválidos para pastas
        safe_folder_name = re.sub(r'[\\/:*?"<>|\s]', '_', base_name)
        profile_folder = os.path.join("uploads", safe_folder_name)
        os.makedirs(profile_folder, exist_ok=True)
        
        profile_name = f"Upload: {base_name}"
        db_path = os.path.join(profile_folder, "radar_reenvios.db")
        print(f"[INFO] Criando/atualizando banco de dados do perfil em: {db_path}")

        # 2. Conectar ao novo banco de dados específico e inicializar schema do zero
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Limpar tabelas caso já existissem
        cursor.execute("DROP TABLE IF EXISTS emails_enviados")
        cursor.execute("DROP TABLE IF EXISTS emails_reenviados")
        cursor.execute("DROP TABLE IF EXISTS reenvios_eventos")
        cursor.execute("DROP TABLE IF EXISTS metadados_sistema")
        
        # Criar Tabelas
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
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadados_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
        """)
        
        # Índices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enviados_reenvio ON emails_enviados(eh_reenvio)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enviados_grupo ON emails_enviados(id_email_reenviado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_eventos_grupo ON reenvios_eventos(id_email_reenviado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reenviados_score ON emails_reenviados(score DESC)")

        # 3. Inserir dados
        inserted_count = 0
        for rec in records:
            msg_id = rec.get("message_id") or rec.get("id") or rec.get("gmail_message_id")
            thread_id = rec.get("thread_id") or rec.get("threadId") or ""
            titulo_original = rec.get("titulo_original") or rec.get("titulo_completo") or rec.get("assunto_original") or rec.get("subject") or rec.get("título completo")
            
            if not msg_id or not titulo_original:
                continue

            # Parsing de data robusto
            dt = None
            ts = rec.get("timestamp")
            if ts not in (None, ''):
                try:
                    dt = datetime.fromtimestamp(float(ts))
                except:
                    pass
            
            if not dt:
                dstr = rec.get("data_hora_envio") or rec.get("data_envio") or rec.get("date") or rec.get("data")
                if dstr:
                    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                        try:
                            dt = datetime.strptime(str(dstr), fmt)
                            break
                        except ValueError:
                            pass
            
            if not dt:
                dt = datetime.now()

            id_grupo = normalizar_para_id(titulo_original)
            assunto_limpo = limpar_titulo_visual(titulo_original)
            
            data_formatada = dt.strftime("%Y-%m-%d %H:%M:%S")
            ano = dt.year
            mes = dt.month
            
            is_forward = eh_reenvio(titulo_original, "")
            
            cursor.execute("""
                INSERT OR IGNORE INTO emails_enviados 
                (gmail_message_id, thread_id, data_envio, ano_envio, mes_envio, assunto_original, assunto_limpo, eh_reenvio, id_email_reenviado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (msg_id, thread_id, data_formatada, ano, mes, titulo_original, assunto_limpo, is_forward, id_grupo))
            inserted_count += 1
            
        conn.commit()
        print(f"[INFO] Registros inseridos no banco do novo perfil: {inserted_count}")
        
        # 4. Recalcular ranking no novo banco
        recalcular_ranking(conn)
        
        # Atualiza metadados de sincronização no novo banco
        cursor.execute("INSERT OR REPLACE INTO metadados_sistema (chave, valor) VALUES ('status_extracao', 'idle')")
        cursor.execute("INSERT OR REPLACE INTO metadados_sistema (chave, valor) VALUES ('ultima_extracao', ?)", (datetime.now().strftime("%d/%m/%Y %H:%M"),))
        cursor.execute("INSERT OR REPLACE INTO metadados_sistema (chave, valor) VALUES ('progresso_atual', '100')")
        
        conn.commit()
        conn.close()

        # 5. Registrar Perfil no config.json e ativá-lo
        if not os.path.exists(CONFIG_PATH):
            inicializar_configuracao()
            
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Verificar se o perfil já existia nos cadastrados
        exists = False
        for p in config["profiles"]:
            if p["name"] == profile_name:
                p["folder"] = profile_folder
                exists = True
                break
                
        if not exists:
            config["profiles"].append({
                "name": profile_name,
                "folder": profile_folder
            })
            
        # Ativa o perfil recém importado
        config["active_profile"] = profile_name
        
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        print(f"[INFO] Perfil '{profile_name}' criado e ativado com sucesso!")
        return {"status": "success", "message": f"Importação concluída! Perfil '{profile_name}' criado e ativado."}
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo de perfil: {str(e)}")

@app.get("/api/status")
def get_status():
    db_status = database.obter_status_sincronizacao()
    conn = database.obter_conexao()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM reenvios_eventos")
        reenvios_count = cursor.fetchone()[0]
    except Exception:
        reenvios_count = 0
    conn.close()
    
    return {
        "status": status_extracao.status,
        "mensagens_processadas": status_extracao.mensagens_processadas,
        "total_mensagens": status_extracao.total_mensagens,
        "reenvios_detectados": reenvios_count,
        "erro": status_extracao.erro,
        "ultima_extracao": db_status["ultima_extracao"],
        "progresso": db_status["progresso"]
    }

# Endpoints de Perfis
@app.get("/api/profiles")
def list_profiles():
    if not os.path.exists(CONFIG_PATH):
        inicializar_configuracao()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/profiles")
def add_profile(profile: ProfileModel):
    if re.search(r'[\\/:*?"<>|]', profile.folder):
        raise HTTPException(status_code=400, detail="O nome da pasta contém caracteres inválidos.")
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    for p in config["profiles"]:
        if p["name"].lower() == profile.name.lower():
            raise HTTPException(status_code=400, detail="Já existe um perfil com este nome.")
            
    config["profiles"].append({
        "name": profile.name,
        "folder": profile.folder
    })
    
    if profile.folder:
        os.makedirs(profile.folder, exist_ok=True)
        
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
        
    return {"status": "success", "message": f"Perfil '{profile.name}' criado."}

@app.post("/api/profiles/active")
def set_active_profile(model: ActiveProfileModel):
    # Ao trocar de perfil, cancela qualquer extração rodando
    status_extracao.status = "stopped"
    status_extracao.mensagens_lista = []
    status_extracao.total_mensagens = 0
    status_extracao.indice_atual = 0
    status_extracao.reenvios_detectados = 0
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    found = False
    for p in config["profiles"]:
        if p["name"] == model.name:
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
        
    config["active_profile"] = model.name
    
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
        
    database.inicializar_banco()
    
    return {"status": "success", "message": f"Perfil ativo alterado para '{model.name}'."}

def obter_ranking_dinamico(busca="", ano="", data_inicio="", data_fim="", ordenacao="score"):
    conn = database.obter_conexao()
    cursor = conn.cursor()
    
    query_filtros = []
    params = []
    
    if ano:
        query_filtros.append("ano_envio = ?")
        params.append(int(ano))
    if data_inicio:
        query_filtros.append("data_envio >= ?")
        params.append(f"{data_inicio} 00:00:00")
    if data_fim:
        query_filtros.append("data_envio <= ?")
        params.append(f"{data_fim} 23:59:59")
        
    where_clause = " WHERE " + " AND ".join(query_filtros) if query_filtros else ""
    
    cursor.execute(f"""
        SELECT id_email_reenviado, data_envio, ano_envio, mes_envio, assunto_limpo, eh_reenvio
        FROM emails_enviados
        {where_clause}
    """, params)
    all_emails = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    from collections import defaultdict, Counter
    
    grouped = defaultdict(list)
    for email in all_emails:
        grouped[email["id_email_reenviado"]].append(email)
        
    dynamic_ranking = []
    for id_grupo, group_rows in grouped.items():
        group_rows_sorted = sorted(group_rows, key=lambda r: r["data_envio"] or "", reverse=True)
        titulo = group_rows_sorted[0]["assunto_limpo"] if group_rows_sorted else id_grupo
        
        if busca and busca.lower() not in titulo.lower():
            continue
            
        total_reenvios = len(group_rows)
        datas_str = [r["data_envio"] for r in group_rows if r["data_envio"]]
        primeiro = min(datas_str) if datas_str else None
        ultimo = max(datas_str) if datas_str else None
        
        score_total = calcular_score_grupo(group_rows)
        
        anos = [r["ano_envio"] for r in group_rows if r["ano_envio"]]
        ano_maioria = Counter(anos).most_common(1)[0][0] if anos else datetime.now().year
        
        meses = [f"{r['ano_envio']}-{r['mes_envio']:02d}" for r in group_rows if r["ano_envio"] and r["mes_envio"]]
        mes_maioria = Counter(meses).most_common(1)[0][0] if meses else ""
        
        now_dt = datetime.now()
        qtd_12m = 0
        for r in group_rows:
            dstr = r["data_envio"]
            if dstr and len(dstr) >= 10:
                try:
                    dt = datetime(int(dstr[:4]), int(dstr[5:7]), int(dstr[8:10]))
                    if (now_dt - dt).days <= 365:
                        qtd_12m += 1
                except:
                    pass
                    
        dynamic_ranking.append({
            "id_email_reenviado": id_grupo,
            "titulo": titulo,
            "total_reenvios": total_reenvios,
            "primeiro_reenvio": primeiro,
            "ultimo_reenvio": ultimo,
            "ano_maioria": ano_maioria,
            "mes_maioria": mes_maioria,
            "reenvios_12m": qtd_12m,
            "score": score_total
        })
        
    ordem_campo = "score" if ordenacao == "score" else "total_reenvios"
    dynamic_ranking.sort(
        key=lambda x: (
            x[ordem_campo],
            x["reenvios_12m"],
            x["ultimo_reenvio"] or ""
        ),
        reverse=True
    )
    return dynamic_ranking

# Endpoints do Dashboard
@app.get("/api/stats")
def get_stats(
    busca: str = Query("", description="Filtro por palavra-chave"),
    ano: str = Query("", description="Filtro por ano"),
    data_inicio: str = Query("", description="Data inicial no formato YYYY-MM-DD"),
    data_fim: str = Query("", description="Data final no formato YYYY-MM-DD")
):
    if ano or data_inicio or data_fim or busca:
        conn = database.obter_conexao()
        cursor = conn.cursor()
        
        query_filtros = []
        params = []
        
        if ano:
            query_filtros.append("ano_envio = ?")
            params.append(int(ano))
        if data_inicio:
            query_filtros.append("data_envio >= ?")
            params.append(f"{data_inicio} 00:00:00")
        if data_fim:
            query_filtros.append("data_envio <= ?")
            params.append(f"{data_fim} 23:59:59")
            
        where_clause = " WHERE " + " AND ".join(query_filtros) if query_filtros else ""
        
        cursor.execute(f"""
            SELECT id_email_reenviado, data_envio, ano_envio, mes_envio, assunto_limpo, eh_reenvio
            FROM emails_enviados
            {where_clause}
        """, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        from collections import defaultdict, Counter
        
        grouped = defaultdict(list)
        for r in rows:
            grouped[r["id_email_reenviado"]].append(r)
            
        ranking_list = []
        for id_grupo, g_rows in grouped.items():
            g_rows_sorted = sorted(g_rows, key=lambda x: x["data_envio"] or "", reverse=True)
            titulo = g_rows_sorted[0]["assunto_limpo"] if g_rows_sorted else id_grupo
            
            if busca and busca.lower() not in titulo.lower():
                continue
                
            ranking_list.append({
                "titulo": titulo,
                "total_reenvios": len(g_rows),
                "score": calcular_score_grupo(g_rows)
            })
            
        total_analisados = len(rows)
        total_reenvios = sum(item["total_reenvios"] for item in ranking_list)
        
        if ranking_list:
            sorted_by_qty = sorted(ranking_list, key=lambda x: x["total_reenvios"], reverse=True)
            mais_reenviado = f"{sorted_by_qty[0]['titulo']} ({sorted_by_qty[0]['total_reenvios']}x)"
            
            sorted_by_score = sorted(ranking_list, key=lambda x: x["score"], reverse=True)
            mais_relevante = f"{sorted_by_score[0]['titulo']} (Score: {sorted_by_score[0]['score']})"
        else:
            mais_reenviado = "Nenhum"
            mais_relevante = "Nenhum"
            
        anos_list = [r["ano_envio"] for r in rows if r["ano_envio"]]
        if list(anos_list):
            ano_val, ano_qty = Counter(anos_list).most_common(1)[0]
            ano_maior_volume = f"{ano_val} ({ano_qty} reenvios)"
        else:
            ano_maior_volume = "Nenhum"
            
        meses_list = [f"{r['ano_envio']}-{r['mes_envio']:02d}" for r in rows if r["ano_envio"] and r["mes_envio"]]
        if list(meses_list):
            mes_val, mes_qty = Counter(meses_list).most_common(1)[0]
            try:
                parts = mes_val.split("-")
                mes_maior_volume = f"{parts[1]}/{parts[0]} ({mes_qty} reenvios)"
            except:
                mes_maior_volume = f"{mes_val} ({mes_qty} reenvios)"
        else:
            mes_maior_volume = "Nenhum"
            
        return {
            "total_analisados": total_analisados,
            "total_reenvios": total_reenvios,
            "mais_reenviado": mais_reenviado,
            "mais_relevante": mais_relevante,
            "ano_maior_volume": ano_maior_volume,
            "mes_maior_volume": mes_maior_volume
        }
    else:
        conn = database.obter_conexao()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM emails_enviados")
        total_analisados = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM reenvios_eventos")
        total_reenvios = cursor.fetchone()[0]
        
        cursor.execute("SELECT titulo, total_reenvios FROM emails_reenviados ORDER BY total_reenvios DESC, score DESC LIMIT 1")
        mais_reenviado_row = cursor.fetchone()
        mais_reenviado = f"{mais_reenviado_row['titulo']} ({mais_reenviado_row['total_reenvios']}x)" if mais_reenviado_row else "Nenhum"
        
        cursor.execute("SELECT titulo, score FROM emails_reenviados ORDER BY score DESC, total_reenvios DESC LIMIT 1")
        mais_relevante_row = cursor.fetchone()
        mais_relevante = f"{mais_relevante_row['titulo']} (Score: {mais_relevante_row['score']})" if mais_relevante_row else "Nenhum"
        
        cursor.execute("SELECT ano, COUNT(*) as qtd FROM reenvios_eventos GROUP BY ano ORDER BY qtd DESC LIMIT 1")
        ano_row = cursor.fetchone()
        ano_maior_volume = f"{ano_row['ano']} ({ano_row['qtd']} reenvios)" if ano_row else "Nenhum"
        
        cursor.execute("SELECT ano, mes, COUNT(*) as qtd FROM reenvios_eventos GROUP BY ano, mes ORDER BY qtd DESC LIMIT 1")
        mes_row = cursor.fetchone()
        mes_maior_volume = f"{mes_row['mes']:02d}/{mes_row['ano']} ({mes_row['qtd']} reenvios)" if mes_row else "Nenhum"
        
        conn.close()
        
        return {
            "total_analisados": total_analisados,
            "total_reenvios": total_reenvios,
            "mais_reenviado": mais_reenviado,
            "mais_relevante": mais_relevante,
            "ano_maior_volume": ano_maior_volume,
            "mes_maior_volume": mes_maior_volume
        }

@app.get("/api/ranking")
def get_ranking(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    busca: str = Query("", description="Filtro por palavra-chave"),
    ano: str = Query("", description="Filtro por ano"),
    data_inicio: str = Query("", description="Data inicial no formato YYYY-MM-DD"),
    data_fim: str = Query("", description="Data final no formato YYYY-MM-DD"),
    ordenacao: str = Query("score", description="score ou total_reenvios")
):
    offset = (page - 1) * limit
    
    if ano or data_inicio or data_fim:
        dynamic_ranking = obter_ranking_dinamico(busca, ano, data_inicio, data_fim, ordenacao)
        total_registros = len(dynamic_ranking)
        ranking_paginado = dynamic_ranking[offset : offset + limit]
        total_paginas = (total_registros + limit - 1) // limit
        
        return {
            "dados": ranking_paginado,
            "pagina_atual": page,
            "limite": limit,
            "total_registros": total_registros,
            "total_paginas": total_paginas
        }
    else:
        conn = database.obter_conexao()
        cursor = conn.cursor()
        
        query_filtros = []
        params = []
        
        if busca:
            query_filtros.append("titulo LIKE ?")
            params.append(f"%{busca}%")
            
        where_clause = " WHERE " + " AND ".join(query_filtros) if query_filtros else ""
        ordem_campo = "score" if ordenacao == "score" else "total_reenvios"
        ordem_final = f"{ordem_campo} DESC, reenvios_12m DESC, ultimo_reenvio DESC"
        
        cursor.execute(f"SELECT COUNT(*) FROM emails_reenviados{where_clause}", params)
        total_registros = cursor.fetchone()[0]
        
        params_paginados = params + [limit, offset]
        cursor.execute(f"""
            SELECT * 
            FROM emails_reenviados
            {where_clause}
            ORDER BY {ordem_final}
            LIMIT ? OFFSET ?
        """, params_paginados)
        
        rows = cursor.fetchall()
        conn.close()
        
        ranking = [dict(row) for row in rows]
        total_paginas = (total_registros + limit - 1) // limit
        
        return {
            "dados": ranking,
            "pagina_atual": page,
            "limite": limit,
            "total_registros": total_registros,
            "total_paginas": total_paginas
        }

@app.get("/api/detalhes/{id_email_reenviado}")
def get_detalhes(
    id_email_reenviado: str,
    ano: str = Query("", description="Filtro por ano"),
    data_inicio: str = Query("", description="Data inicial no formato YYYY-MM-DD"),
    data_fim: str = Query("", description="Data final no formato YYYY-MM-DD")
):
    conn = database.obter_conexao()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM emails_reenviados WHERE id_email_reenviado = ?", (id_email_reenviado,))
    grupo_row = cursor.fetchone()
    
    if not grupo_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
        
    grupo = dict(grupo_row)
    
    query_filtros = ["e.id_email_reenviado = ?"]
    params = [id_email_reenviado]
    
    if ano:
        query_filtros.append("e.ano_envio = ?")
        params.append(int(ano))
    if data_inicio:
        query_filtros.append("e.data_envio >= ?")
        params.append(f"{data_inicio} 00:00:00")
    if data_fim:
        query_filtros.append("e.data_envio <= ?")
        params.append(f"{data_fim} 23:59:59")
        
    where_clause = " WHERE " + " AND ".join(query_filtros)
    
    cursor.execute(f"""
        SELECT e.gmail_message_id, e.thread_id, e.data_envio, e.assunto_original, e.ano_envio, e.mes_envio, e.eh_reenvio
        FROM emails_enviados e
        {where_clause}
        ORDER BY e.data_envio DESC
    """, params)
    ocorrencias = [dict(r) for r in cursor.fetchall()]
    
    if ano or data_inicio or data_fim:
        grupo["total_reenvios"] = len(ocorrencias)
        grupo["score"] = calcular_score_grupo(ocorrencias)
        
        datas_str = [oc["data_envio"] for oc in ocorrencias if oc["data_envio"]]
        grupo["primeiro_reenvio"] = min(datas_str) if datas_str else None
        grupo["ultimo_reenvio"] = max(datas_str) if datas_str else None
        
    cursor.execute(f"""
        SELECT e.ano_envio || '-' || printf('%02d', e.mes_envio) as mes_ano, COUNT(*) as qtd
        FROM emails_enviados e
        {where_clause}
        GROUP BY e.ano_envio, e.mes_envio 
        ORDER BY e.ano_envio ASC, e.mes_envio ASC
    """, params)
    distribuicao_mensal = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        "grupo": grupo,
        "ocorrencias": ocorrencias,
        "distribuicao_mensal": distribuicao_mensal
    }

@app.get("/api/chart-data")
def get_chart_data(
    ano: str = Query("", description="Filtro por ano"),
    data_inicio: str = Query("", description="Data inicial no formato YYYY-MM-DD"),
    data_fim: str = Query("", description="Data final no formato YYYY-MM-DD")
):
    if ano or data_inicio or data_fim:
        conn = database.obter_conexao()
        cursor = conn.cursor()
        
        query_filtros = []
        params = []
        
        if ano:
            query_filtros.append("ano_envio = ?")
            params.append(int(ano))
        if data_inicio:
            query_filtros.append("data_envio >= ?")
            params.append(f"{data_inicio} 00:00:00")
        if data_fim:
            query_filtros.append("data_envio <= ?")
            params.append(f"{data_fim} 23:59:59")
            
        where_clause = " WHERE " + " AND ".join(query_filtros) if query_filtros else ""
        
        cursor.execute(f"""
            SELECT ano_envio as ano, COUNT(*) as qtd 
            FROM emails_enviados
            {where_clause}
            GROUP BY ano_envio ORDER BY ano_envio ASC
        """, params)
        anual = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute(f"""
            SELECT ano_envio || '-' || printf('%02d', mes_envio) as mes_ano, COUNT(*) as qtd
            FROM emails_enviados
            {where_clause}
            GROUP BY ano_envio, mes_envio ORDER BY ano_envio ASC, mes_envio ASC
        """, params)
        mensal = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return {
            "anual": anual,
            "mensal": mensal
        }
    else:
        conn = database.obter_conexao()
        cursor = conn.cursor()
        
        cursor.execute("SELECT ano, COUNT(*) as qtd FROM reenvios_eventos GROUP BY ano ORDER BY ano ASC")
        anual = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT ano || '-' || printf('%02d', mes) as mes_ano, COUNT(*) as qtd
            FROM reenvios_eventos GROUP BY ano, mes ORDER BY ano ASC, mes ASC
        """)
        mensal = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "anual": anual,
            "mensal": mensal
        }

@app.get("/api/export-html")
def export_html(tema: str = Query("purple")):
    conn = database.obter_conexao()
    cursor = conn.cursor()
    
    # 1. Stats
    cursor.execute("SELECT COUNT(*) FROM emails_enviados")
    total_analisados = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM reenvios_eventos")
    total_reenvios = cursor.fetchone()[0]
    cursor.execute("SELECT titulo, total_reenvios, score FROM emails_reenviados ORDER BY total_reenvios DESC, score DESC LIMIT 1")
    mais_reenviado_row = cursor.fetchone()
    mais_reenviado = f"{mais_reenviado_row['titulo']} ({mais_reenviado_row['total_reenvios']}x)" if mais_reenviado_row else "Nenhum"
    cursor.execute("SELECT titulo, score FROM emails_reenviados ORDER BY score DESC, total_reenvios DESC LIMIT 1")
    mais_relevante_row = cursor.fetchone()
    mais_relevante = f"{mais_relevante_row['titulo']} (Score: {mais_relevante_row['score']})" if mais_relevante_row else "Nenhum"
    cursor.execute("SELECT ano, COUNT(*) as qtd FROM reenvios_eventos GROUP BY ano ORDER BY qtd DESC LIMIT 1")
    ano_row = cursor.fetchone()
    ano_maior_volume = f"{ano_row['ano']} ({ano_row['qtd']} reenvios)" if ano_row else "Nenhum"
    cursor.execute("SELECT ano, mes, COUNT(*) as qtd FROM reenvios_eventos GROUP BY ano, mes ORDER BY qtd DESC LIMIT 1")
    mes_row = cursor.fetchone()
    mes_maior_volume = f"{mes_row['mes']:02d}/{mes_row['ano']} ({mes_row['qtd']} reenvios)" if mes_row else "Nenhum"
    
    stats = {
        "total_analisados": total_analisados,
        "total_reenvios": total_reenvios,
        "mais_reenviado": mais_reenviado,
        "mais_relevante": mais_relevante,
        "ano_maior_volume": ano_maior_volume,
        "mes_maior_volume": mes_maior_volume
    }
    
    # 2. Chart data
    cursor.execute("SELECT ano, COUNT(*) as qtd FROM reenvios_eventos GROUP BY ano ORDER BY ano ASC")
    anual = [dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT ano || '-' || printf('%02d', mes) as mes_ano, COUNT(*) as qtd
        FROM reenvios_eventos GROUP BY ano, mes ORDER BY ano ASC, mes ASC
    """)
    mensal = [dict(row) for row in cursor.fetchall()]
    chart_data = {
        "anual": anual,
        "mensal": mensal
    }
    
    # 3. ALL items in ranking (complete dataset)
    cursor.execute("""
        SELECT * 
        FROM emails_reenviados
        ORDER BY score DESC, reenvios_12m DESC, ultimo_reenvio DESC
    """)
    ranking = [dict(row) for row in cursor.fetchall()]
    
    # 4. Details for ALL items — use bulk queries instead of N individual queries
    details = {}
    # Initialize all entries from ranking list
    for item in ranking:
        details[item["id_email_reenviado"]] = {
            "grupo": item,
            "ocorrencias": [],
            "distribuicao_mensal": []
        }
    
    # Batch load all occurrences in a single query
    cursor.execute("""
        SELECT r.id_email_reenviado, e.gmail_message_id, e.thread_id, e.data_envio, e.assunto_original, e.eh_reenvio
        FROM reenvios_eventos r
        JOIN emails_enviados e ON r.gmail_message_id = e.gmail_message_id
        ORDER BY r.id_email_reenviado, r.data_reenvio DESC
    """)
    for row in cursor.fetchall():
        rid = row["id_email_reenviado"]
        if rid in details:
            details[rid]["ocorrencias"].append({
                "gmail_message_id": row["gmail_message_id"],
                "thread_id": row["thread_id"],
                "data_envio": row["data_envio"],
                "assunto_original": row["assunto_original"],
                "eh_reenvio": row["eh_reenvio"]
            })
    
    # Batch load all monthly distributions in a single query
    cursor.execute("""
        SELECT id_email_reenviado,
               ano || '-' || printf('%02d', mes) as mes_ano,
               COUNT(*) as qtd
        FROM reenvios_eventos
        GROUP BY id_email_reenviado, ano, mes
        ORDER BY id_email_reenviado, ano ASC, mes ASC
    """)
    for row in cursor.fetchall():
        rid = row["id_email_reenviado"]
        if rid in details:
            details[rid]["distribuicao_mensal"].append({
                "mes_ano": row["mes_ano"],
                "qtd": row["qtd"]
            })
        
    conn.close()
    
    # 5. Read profile information
    active_profile = "Default"
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
                active_profile = config_data.get("active_profile", "Default")
        except Exception:
            pass
            
    # 6. Load file assets and construct static page
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        with open("static/css/styles.css", "r", encoding="utf-8") as f:
            styles_content = f.read()
        with open("static/js/dashboard.js", "r", encoding="utf-8") as f:
            js_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar arquivos estáticos do sistema: {str(e)}")
        
    # Inject classes/attributes based on theme parameter
    body_class = 'static-export theme-orange' if tema == 'orange' else 'static-export'
    html_content = html_content.replace("<body", f'<body class="{body_class}"')
    
    # Replace stylesheets
    html_content = re.sub(r'<link[^>]*href="[^"]*styles.css[^"]*"[^>]*>', f'<style>\n{styles_content}\n</style>', html_content)
    # Construct embedded JSON
    embedded_data_json = json.dumps({
        "stats": stats,
        "chartData": chart_data,
        "ranking": ranking,
        "details": details,
        "activeProfile": active_profile
    }, ensure_ascii=False)
    
    # Build fetch mock script
    mock_fetch_script = f"""
    <script>
    (function() {{
        window.isStaticExport = true;
        localStorage.setItem('app-theme', '{tema}');
        window.embeddedData = {embedded_data_json};
 
        const originalFetch = window.fetch;
        window.fetch = async function(url, options) {{
            const urlObj = new URL(url, window.location.href);
            const pathname = urlObj.pathname;
            
            if (pathname.endsWith('/api/status')) {{
                return new Response(JSON.stringify({{
                    "status": "idle",
                    "progresso": 100,
                    "total_processar": 0,
                    "total_processados": 0,
                    "ultima_sincronizacao": "Offline / Exportado",
                    "erro": null
                }}), {{ headers: {{ 'Content-Type': 'application/json' }} }});
            }}
            
            if (pathname.endsWith('/api/auth-status')) {{
                return new Response(JSON.stringify({{
                    "authenticated": true,
                    "email": "visualizacao@offline.local"
                }}), {{ headers: {{ 'Content-Type': 'application/json' }} }});
            }}
            
            if (pathname.endsWith('/api/profiles')) {{
                return new Response(JSON.stringify({{
                    "active_profile": window.embeddedData.activeProfile,
                    "profiles": [{{ "name": window.embeddedData.activeProfile, "folder": "" }}]
                }}), {{ headers: {{ 'Content-Type': 'application/json' }} }});
            }}
            
            if (pathname.endsWith('/api/stats')) {{
                return new Response(JSON.stringify(window.embeddedData.stats), {{ headers: {{ 'Content-Type': 'application/json' }} }});
            }}
            
            if (pathname.endsWith('/api/chart-data')) {{
                return new Response(JSON.stringify(window.embeddedData.chartData), {{ headers: {{ 'Content-Type': 'application/json' }} }});
            }}
            
            if (pathname.includes('/api/detalhes/')) {{
                const idx = pathname.indexOf('/api/detalhes/');
                const id = decodeURIComponent(pathname.substring(idx + '/api/detalhes/'.length));
                const detail = window.embeddedData.details[id];
                if (detail) {{
                    const ano = urlObj.searchParams.get('ano') || '';
                    const data_inicio = urlObj.searchParams.get('data_inicio') || '';
                    const data_fim = urlObj.searchParams.get('data_fim') || '';
                    
                    const parseDate = (rawDate) => {{
                        if (!rawDate) return null;
                        const str = rawDate.trim();
                        if (str.includes('/')) {{
                            const parts = str.split(' ');
                            const dateParts = parts[0].split('/');
                            if (dateParts.length < 3) return null;
                            const timeParts = parts[1] ? parts[1].split(':') : [0, 0, 0];
                            const d = new Date(
                                parseInt(dateParts[2]),
                                parseInt(dateParts[1]) - 1,
                                parseInt(dateParts[0]),
                                parseInt(timeParts[0]) || 0,
                                parseInt(timeParts[1]) || 0,
                                parseInt(timeParts[2]) || 0
                            );
                            return isNaN(d.getTime()) ? null : d;
                        }} else {{
                            const isoStr = str.replace(' ', 'T');
                            const d = new Date(isoStr);
                            return isNaN(d.getTime()) ? null : d;
                        }}
                    }};
                    
                    if (ano || data_inicio || data_fim) {{
                        const matchingOcs = detail.ocorrencias.filter(oc => {{
                            const ocDate = parseDate(oc.data_envio);
                            if (!ocDate) return false;
                            
                            if (ano) {{
                                const yearInt = parseInt(ano);
                                const ocYear = ocDate.getFullYear();
                                if (yearInt <= 2021) {{
                                    if (ocYear > 2021) return false;
                                }} else {{
                                    if (ocYear !== yearInt) return false;
                                }}
                            }}
                            
                            if (data_inicio) {{
                                const di = new Date(data_inicio + "T00:00:00");
                                if (ocDate < di) return false;
                            }}
                            
                            if (data_fim) {{
                                const df = new Date(data_fim + "T23:59:59");
                                if (ocDate > df) return false;
                            }}
                            
                            return true;
                        }});
                        
                        let firstDateStr = null;
                        let lastDateStr = null;
                        let firstDate = null;
                        let lastDate = null;
                        
                        matchingOcs.forEach(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (!d) return;
                            if (!firstDate || d < firstDate) {{
                                firstDate = d;
                                firstDateStr = oc.data_envio;
                            }}
                            if (!lastDate || d > lastDate) {{
                                lastDate = d;
                                lastDateStr = oc.data_envio;
                            }}
                        }});
                        
                        const PESOS = {{
                            anos: {{
                                2026: 100.0,
                                2025: 30.0,
                                2024: 10.0,
                                2023: 3.0,
                                2022: 1.0,
                                outros: 0.1
                            }},
                            bonus_eh_reenvio: 20.0,
                            bonus_recencia_12m: 15.0,
                            multiplicador_volume_total: 0.5
                        }};
                        
                        const now = new Date();
                        let score_total = 0.0;
                        matchingOcs.forEach(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (!d) return;
                            const y = d.getFullYear();
                            const peso_ano = PESOS.anos[y] || PESOS.anos.outros;
                            const peso_reenvio = oc.eh_reenvio ? PESOS.bonus_eh_reenvio : 0.0;
                            let peso_recencia_12m = 0.0;
                            if ((now - d) / (1000 * 60 * 60 * 24) <= 365) {{
                                peso_recencia_12m = PESOS.bonus_recencia_12m;
                            }}
                            score_total += (peso_ano + peso_reenvio + peso_recencia_12m);
                        }});
                        
                        if (PESOS.multiplicador_volume_total > 0) {{
                            score_total = score_total * (1 + (matchingOcs.length - 1) * PESOS.multiplicador_volume_total);
                        }}
                        score_total = Math.round(score_total * 100) / 100;
                        
                        const monthlyCounts = {{}};
                        matchingOcs.forEach(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (!d) return;
                            const mm = String(d.getMonth() + 1).padStart(2, '0');
                            const key = `${{d.getFullYear()}}-${{mm}}`;
                            monthlyCounts[key] = (monthlyCounts[key] || 0) + 1;
                        }});
                        
                        const distribuicao_mensal = Object.keys(monthlyCounts).sort().map(key => ({{
                            mes_ano: key,
                            qtd: monthlyCounts[key]
                        }}));
                        
                        return new Response(JSON.stringify({{
                            grupo: {{
                                ...detail.grupo,
                                total_reenvios: matchingOcs.length,
                                score: score_total,
                                primeiro_reenvio: firstDateStr,
                                ultimo_reenvio: lastDateStr
                            }},
                            ocorrencias: matchingOcs,
                            distribuicao_mensal: distribuicao_mensal
                        }}), {{ headers: {{ 'Content-Type': 'application/json' }} }});
                    }} else {{
                        return new Response(JSON.stringify(detail), {{ headers: {{ 'Content-Type': 'application/json' }} }});
                    }}
                }} else {{
                    return new Response(JSON.stringify({{ error: "Não embutido nesta visualização" }}), {{ status: 404, headers: {{ 'Content-Type': 'application/json' }} }});
                }}
            }}
            
            if (pathname.endsWith('/api/ranking')) {{
                const busca = urlObj.searchParams.get('busca') || '';
                const ano = urlObj.searchParams.get('ano') || '';
                const data_inicio = urlObj.searchParams.get('data_inicio') || '';
                const data_fim = urlObj.searchParams.get('data_fim') || '';
                const ordenacao = urlObj.searchParams.get('ordenacao') || 'score';
                const page = parseInt(urlObj.searchParams.get('page') || '1');
                const limit = parseInt(urlObj.searchParams.get('limit') || '100');
                
                let filtered = [];
                const hasTimeFilter = !!(ano || data_inicio || data_fim);
                
                const parseDate = (rawDate) => {{
                    if (!rawDate) return null;
                    const str = rawDate.trim();
                    if (str.includes('/')) {{
                        const parts = str.split(' ');
                        const dateParts = parts[0].split('/');
                        if (dateParts.length < 3) return null;
                        const timeParts = parts[1] ? parts[1].split(':') : [0, 0, 0];
                        const d = new Date(
                            parseInt(dateParts[2]),
                            parseInt(dateParts[1]) - 1,
                            parseInt(dateParts[0]),
                            parseInt(timeParts[0]) || 0,
                            parseInt(timeParts[1]) || 0,
                            parseInt(timeParts[2]) || 0
                        );
                        return isNaN(d.getTime()) ? null : d;
                    }} else {{
                        const isoStr = str.replace(' ', 'T');
                        const d = new Date(isoStr);
                        return isNaN(d.getTime()) ? null : d;
                    }}
                }};

                for (const item of window.embeddedData.ranking) {{
                    if (busca) {{
                        const searchLower = busca.toLowerCase();
                        if (!item.titulo.toLowerCase().includes(searchLower)) {{
                            continue;
                        }}
                    }}
                    
                    if (hasTimeFilter) {{
                        const detail = window.embeddedData.details[item.id_email_reenviado];
                        if (!detail || !detail.ocorrencias) {{
                            continue;
                        }}
                        
                        const matchingOcs = detail.ocorrencias.filter(oc => {{
                            const ocDate = parseDate(oc.data_envio);
                            if (!ocDate) return false;
                            
                            if (ano) {{
                                const yearInt = parseInt(ano);
                                const ocYear = ocDate.getFullYear();
                                if (yearInt <= 2021) {{
                                    if (ocYear > 2021) return false;
                                }} else {{
                                    if (ocYear !== yearInt) return false;
                                }}
                            }}
                            
                            if (data_inicio) {{
                                const di = new Date(data_inicio + "T00:00:00");
                                if (ocDate < di) return false;
                            }}
                            
                            if (data_fim) {{
                                const df = new Date(data_fim + "T23:59:59");
                                if (ocDate > df) return false;
                            }}
                            
                            return true;
                        }});
                        
                        if (matchingOcs.length === 0) {{
                            continue;
                        }}
                        
                        const total_reenvios = matchingOcs.length;
                        let firstDate = null;
                        let lastDate = null;
                        let firstDateStr = null;
                        let lastDateStr = null;
                        
                        matchingOcs.forEach(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (!d) return;
                            if (!firstDate || d < firstDate) {{
                                firstDate = d;
                                firstDateStr = oc.data_envio;
                            }}
                            if (!lastDate || d > lastDate) {{
                                lastDate = d;
                                lastDateStr = oc.data_envio;
                            }}
                        }});
                        
                        const years = matchingOcs.map(oc => {{
                            const d = parseDate(oc.data_envio);
                            return d ? d.getFullYear() : null;
                        }}).filter(y => y !== null);
                        
                        let ano_maioria = item.ano_maioria;
                        if (years.length > 0) {{
                            const counts = {{}};
                            let maxCount = 0;
                            years.forEach(y => {{
                                counts[y] = (counts[y] || 0) + 1;
                                if (counts[y] > maxCount) {{
                                    maxCount = counts[y];
                                    ano_maioria = y;
                                }}
                            }});
                        }}
                        
                        const months = matchingOcs.map(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (!d) return null;
                            const mm = String(d.getMonth() + 1).padStart(2, '0');
                            return `${{d.getFullYear()}}-${{mm}}`;
                        }}).filter(m => m !== null);
                        
                        let mes_maioria = item.mes_maioria;
                        if (months.length > 0) {{
                            const counts = {{}};
                            let maxCount = 0;
                            months.forEach(m => {{
                                counts[m] = (counts[m] || 0) + 1;
                                if (counts[m] > maxCount) {{
                                    maxCount = counts[m];
                                    mes_maioria = m;
                                }}
                            }});
                        }}
                        
                        const now = new Date();
                        let reenvios_12m = 0;
                        matchingOcs.forEach(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (d && (now - d) / (1000 * 60 * 60 * 24) <= 365) {{
                                reenvios_12m++;
                            }}
                        }});
                        
                        const PESOS = {{
                            anos: {{
                                2026: 100.0,
                                2025: 30.0,
                                2024: 10.0,
                                2023: 3.0,
                                2022: 1.0,
                                outros: 0.1
                            }},
                            bonus_eh_reenvio: 20.0,
                            bonus_recencia_12m: 15.0,
                            multiplicador_volume_total: 0.5
                        }};
                        
                        let score_total = 0.0;
                        matchingOcs.forEach(oc => {{
                            const d = parseDate(oc.data_envio);
                            if (!d) return;
                            const y = d.getFullYear();
                            const peso_ano = PESOS.anos[y] || PESOS.anos.outros;
                            const peso_reenvio = oc.eh_reenvio ? PESOS.bonus_eh_reenvio : 0.0;
                            let peso_recencia_12m = 0.0;
                            if ((now - d) / (1000 * 60 * 60 * 24) <= 365) {{
                                peso_recencia_12m = PESOS.bonus_recencia_12m;
                            }}
                            score_total += (peso_ano + peso_reenvio + peso_recencia_12m);
                        }});
                        
                        if (PESOS.multiplicador_volume_total > 0) {{
                            score_total = score_total * (1 + (total_reenvios - 1) * PESOS.multiplicador_volume_total);
                        }}
                        score_total = Math.round(score_total * 100) / 100;
                        
                        filtered.push({{
                            ...item,
                            total_reenvios,
                            primeiro_reenvio: firstDateStr,
                            ultimo_reenvio: lastDateStr,
                            ano_maioria,
                            mes_maioria,
                            reenvios_12m,
                            score: score_total
                        }});
                    }} else {{
                        filtered.push(item);
                    }}
                }}
                
                filtered.sort((a, b) => {{
                    let valA = ordenacao === 'score' ? a.score : a.total_reenvios;
                    let valB = ordenacao === 'score' ? b.score : b.total_reenvios;
                    if (valB !== valA) return valB - valA;
                    if (b.reenvios_12m !== a.reenvios_12m) return b.reenvios_12m - a.reenvios_12m;
                    return new Date(b.ultimo_reenvio) - new Date(a.ultimo_reenvio);
                }});
                
                const totalRegistros = filtered.length;
                const offset = (page - 1) * limit;
                const pagedData = filtered.slice(offset, offset + limit);
                const totalPaginas = Math.ceil(totalRegistros / limit);
                
                return new Response(JSON.stringify({{
                    "dados": pagedData,
                    "pagina_atual": page,
                    "limite": limit,
                    "total_registros": totalRegistros,
                    "total_paginas": totalPaginas
                }}), {{ headers: {{ 'Content-Type': 'application/json' }} }});
            }}
            
            try {{
                return await originalFetch(url, options);
            }} catch(e) {{
                return new Response(JSON.stringify({{ error: "Offline" }}), {{ status: 503 }});
            }}
        }};
    }})();
    </script>
    """
    
    # Replace dashboard.js script
    html_content = re.sub(
        r'<script[^>]*src="[^"]*dashboard.js[^"]*"[^>]*>\s*</script>',
        f'{mock_fetch_script}\n<script>\n{js_content}\n</script>',
        html_content
    )
    
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": "attachment; filename=visualizacao_radar_reenvios.html"}
    )

@app.get("/api/export-csv")
def export_csv(
    busca: str = Query("", description="Filtro por palavra-chave"),
    ano: str = Query("", description="Filtro por ano"),
    data_inicio: str = Query("", description="Data inicial no formato YYYY-MM-DD"),
    data_fim: str = Query("", description="Data final no formato YYYY-MM-DD"),
    ordenacao: str = Query("score", description="score ou total_reenvios")
):
    if ano or data_inicio or data_fim:
        rows = obter_ranking_dinamico(busca, ano, data_inicio, data_fim, ordenacao)
    else:
        conn = database.obter_conexao()
        cursor = conn.cursor()
        
        query_filtros = []
        params = []
        
        if busca:
            query_filtros.append("titulo LIKE ?")
            params.append(f"%{busca}%")
            
        where_clause = " WHERE " + " AND ".join(query_filtros) if query_filtros else ""
        ordem_campo = "score" if ordenacao == "score" else "total_reenvios"
        
        cursor.execute(f"""
            SELECT titulo, total_reenvios, primeiro_reenvio, ultimo_reenvio, ano_maioria, mes_maioria, score, id_email_reenviado
            FROM emails_reenviados
            {where_clause}
            ORDER BY {ordem_campo} DESC, total_reenvios DESC
        """, params)
        
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow([
        "Posição", "E-mail Reenviado", "Quantidade de Reenvios", 
        "Primeiro Reenvio", "Último Reenvio", "Ano Predominante", 
        "Mês Predominante", "Score Ponderado"
    ])
    
    for idx, row in enumerate(rows, start=1):
        writer.writerow([
            idx,
            row["titulo"],
            row["total_reenvios"],
            row["primeiro_reenvio"],
            row["ultimo_reenvio"],
            row["ano_maioria"],
            row["mes_maioria"],
            row["score"]
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=radar_reenvios_ranking.csv"}
    )

os.makedirs("static", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("\n[INFO] Servidor do Radar de Reenvios iniciando em: http://localhost:5210")
    uvicorn.run("app:app", host="0.0.0.0", port=5210, reload=True)
