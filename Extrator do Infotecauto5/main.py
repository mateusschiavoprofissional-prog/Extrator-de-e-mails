import os
import csv
import re
import json
import time
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# Permissao somente leitura do Gmail.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Arquivos usados pelo processo.
ARQUIVO_CACHE = "cache_mensagens_enviadas.jsonl"
ARQUIVO_CSV = "extracao_todas_threads_enviadas.csv"
ARQUIVO_ERROS = "log_erros.txt"

# Quantidade de requisicoes paralelas.
# Se der erro de limite da API, reduza para 8 ou 6.
# Se estiver estavel, pode testar 16.
MAX_WORKERS = 12

# MODO COMPLETO:
# Busca tudo que esta na pasta/label SENT do Gmail.
# Nao depende de ano, after, before ou newer_than.
PERIODOS = [
    ("todos_enviados", ""),
]

# MODO SEMANAL, se quiser usar depois:
# PERIODOS = [
#     ("semana_atual", "in:sent newer_than:7d"),
# ]

# MODO POR ANO, se quiser usar depois:
# PERIODOS = [
#     ("2026", "in:sent after:2026/01/01 before:2027/01/01"),
#     ("2025", "in:sent after:2025/01/01 before:2026/01/01"),
#     ("2024", "in:sent after:2024/01/01 before:2025/01/01"),
#     ("2023", "in:sent after:2023/01/01 before:2024/01/01"),
#     ("2022", "in:sent after:2022/01/01 before:2023/01/01"),
#     ("2021", "in:sent after:2021/01/01 before:2022/01/01"),
#     ("2020", "in:sent after:2020/01/01 before:2021/01/01"),
# ]


def autenticar_gmail():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                raise FileNotFoundError(
                    "Arquivo credentials.json nao encontrado. "
                    "Coloque o arquivo baixado do Google Cloud na mesma pasta do main.py."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def obter_header(headers, nome):
    for header in headers:
        if header.get("name", "").lower() == nome.lower():
            return header.get("value", "")
    return ""


def limpar_titulo(assunto):
    if not assunto:
        return "Sem assunto"

    titulo = assunto.strip()

    # Remove prefixos comuns, mas mantem o titulo completo do e-mail.
    # Exemplo:
    # "RES: ENC: Fwd: Diagrama da injecao..." vira "Diagrama da injecao..."
    padrao = r"^\s*(re|res|fw|fwd|enc|encaminhado|tr)\s*:\s*"

    while re.match(padrao, titulo, flags=re.IGNORECASE):
        titulo = re.sub(padrao, "", titulo, flags=re.IGNORECASE).strip()

    titulo = re.sub(r"\s+", " ", titulo)

    return titulo


def converter_data_gmail(internal_date):
    return datetime.fromtimestamp(int(internal_date) / 1000)


def registrar_erro(texto):
    with open(ARQUIVO_ERROS, "a", encoding="utf-8") as arquivo:
        arquivo.write(texto + "\n")


def carregar_ids_ja_processados():
    ids = set()

    if not os.path.exists(ARQUIVO_CACHE):
        return ids

    with open(ARQUIVO_CACHE, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            try:
                item = json.loads(linha)
                message_id = item.get("message_id")

                if message_id:
                    ids.add(message_id)

            except Exception:
                continue

    return ids


def listar_mensagens_enviadas(service, query):
    mensagens = []
    page_token = None

    while True:
        parametros = {
            "userId": "me",
            "labelIds": ["SENT"],
            "maxResults": 500,
            "pageToken": page_token,
            "fields": "nextPageToken,messages(id,threadId)"
        }

        # Se query estiver vazia, busca tudo que tem label SENT.
        # Isso blinda a extracao para nao depender de ano, after, before ou newer_than.
        if query:
            parametros["q"] = query

        resposta = service.users().messages().list(
            **parametros
        ).execute()

        mensagens.extend(resposta.get("messages", []))

        print(f"Mensagens enviadas encontradas ate agora: {len(mensagens)}")

        page_token = resposta.get("nextPageToken")

        if not page_token:
            break

    return mensagens


def buscar_metadata_mensagem(message_id):
    """
    Busca somente metadados.
    Nao baixa corpo.
    Nao baixa anexos.

    Extrai:
    - message_id
    - thread_id
    - titulo_original
    - titulo_completo
    - data_envio
    - data_hora_envio
    - ano
    - mes
    - timestamp
    """

    service = autenticar_gmail()

    tentativas = 0

    while tentativas < 3:
        try:
            msg = service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject"],
                fields="id,threadId,internalDate,payload/headers"
            ).execute()

            headers = msg.get("payload", {}).get("headers", [])
            assunto_original = obter_header(headers, "Subject")
            titulo_limpo = limpar_titulo(assunto_original)

            data = converter_data_gmail(msg["internalDate"])

            return {
                "message_id": msg["id"],
                "thread_id": msg["threadId"],
                "titulo_original": assunto_original or "Sem assunto",
                "titulo_completo": titulo_limpo,
                "data_envio": data.strftime("%d/%m/%Y"),
                "data_hora_envio": data.strftime("%d/%m/%Y %H:%M:%S"),
                "ano": str(data.year),
                "mes": f"{data.year}-{data.month:02d}",
                "timestamp": data.timestamp()
            }

        except Exception as erro:
            tentativas += 1
            texto_erro = (
                f"Erro ao buscar mensagem {message_id}. "
                f"Tentativa {tentativas}. Erro: {erro}"
            )
            print(texto_erro)
            registrar_erro(texto_erro)
            time.sleep(2 * tentativas)

    return None


def salvar_cache(item):
    with open(ARQUIVO_CACHE, "a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(item, ensure_ascii=False) + "\n")


def extrair_periodo(nome_periodo, query):
    print("")
    print("========================================")
    print(f"PROCESSANDO PERIODO: {nome_periodo}")

    if query:
        print(f"QUERY: {query}")
    else:
        print("QUERY: sem filtro - buscando tudo com label SENT")

    print("========================================")

    service = autenticar_gmail()

    mensagens = listar_mensagens_enviadas(service, query=query)

    ids_ja_processados = carregar_ids_ja_processados()

    mensagens_pendentes = [
        msg for msg in mensagens
        if msg["id"] not in ids_ja_processados
    ]

    print("")
    print(f"Total encontrado no periodo {nome_periodo}: {len(mensagens)}")
    print(f"Ja processadas em cache: {len(mensagens) - len(mensagens_pendentes)}")
    print(f"Pendentes para processar agora: {len(mensagens_pendentes)}")
    print("")

    if not mensagens_pendentes:
        print(f"Nada pendente para o periodo {nome_periodo}.")
        return

    processadas = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {
            executor.submit(buscar_metadata_mensagem, msg["id"]): msg
            for msg in mensagens_pendentes
        }

        for futuro in as_completed(futuros):
            item_original = futuros[futuro]

            try:
                item = futuro.result()

                if item:
                    salvar_cache(item)
                    processadas += 1

                if processadas % 100 == 0:
                    print(
                        f"Periodo {nome_periodo}: "
                        f"{processadas}/{len(mensagens_pendentes)} mensagens processadas"
                    )

            except Exception as erro:
                texto_erro = f"Erro geral na mensagem {item_original.get('id')}: {erro}"
                print(texto_erro)
                registrar_erro(texto_erro)

    print("")
    print(f"Periodo {nome_periodo} concluido.")
    print(f"Mensagens processadas neste periodo: {processadas}")


def carregar_cache():
    itens = []

    if not os.path.exists(ARQUIVO_CACHE):
        return itens

    with open(ARQUIVO_CACHE, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            try:
                item = json.loads(linha)
                itens.append(item)
            except Exception:
                continue

    return itens


def remover_duplicidades_cache_em_memoria(itens):
    """
    Remove duplicidades por message_id apenas para gerar o CSV.
    Nao altera o arquivo JSONL original.
    """
    vistos = set()
    unicos = []

    for item in itens:
        message_id = item.get("message_id")

        if not message_id:
            continue

        if message_id in vistos:
            continue

        vistos.add(message_id)
        unicos.append(item)

    return unicos


def gerar_csv_por_thread():
    print("")
    print("========================================")
    print("GERANDO CSV FINAL AGRUPADO POR THREAD")
    print("========================================")

    itens = carregar_cache()

    if not itens:
        print("Nenhum item encontrado no cache. Nada para exportar.")
        return

    total_linhas_cache = len(itens)

    itens = remover_duplicidades_cache_em_memoria(itens)

    total_unicos = len(itens)
    duplicidades = total_linhas_cache - total_unicos

    print(f"Linhas no cache: {total_linhas_cache}")
    print(f"Mensagens unicas no cache: {total_unicos}")
    print(f"Duplicidades ignoradas no CSV: {duplicidades}")

    grupos = defaultdict(list)

    for item in itens:
        thread_id = item.get("thread_id")

        if not thread_id:
            continue

        grupos[thread_id].append(item)

    resultado = []

    for thread_id, mensagens in grupos.items():
        mensagens_ordenadas = sorted(
            mensagens,
            key=lambda x: x.get("timestamp", 0)
        )

        titulo = mensagens_ordenadas[0].get("titulo_completo", "Sem assunto")

        total_envios_thread = len(mensagens_ordenadas)

        datas_horas_todos = [
            m.get("data_hora_envio", m.get("data_envio", ""))
            for m in mensagens_ordenadas
        ]

        anos_todos = [
            m.get("ano", "")
            for m in mensagens_ordenadas
        ]

        meses_todos = [
            m.get("mes", "")
            for m in mensagens_ordenadas
        ]

        message_ids = [
            m.get("message_id", "")
            for m in mensagens_ordenadas
        ]

        resultado.append({
            "thread_id": thread_id,
            "titulo_completo": titulo,
            "total_envios_thread": total_envios_thread,
            "primeiro_envio": datas_horas_todos[0],
            "ultimo_envio": datas_horas_todos[-1],
            "datas_horas_todos_envios": " | ".join(datas_horas_todos),
            "anos_todos_envios": " | ".join(anos_todos),
            "meses_todos_envios": " | ".join(meses_todos),
            "message_ids": " | ".join(message_ids)
        })

    # Ordenacao inicial apenas para facilitar leitura.
    # O ranking definitivo sera aplicado depois no arquivo de processamento.
    resultado = sorted(
        resultado,
        key=lambda x: x["total_envios_thread"],
        reverse=True
    )

    campos = [
        "posicao_extracao",
        "thread_id",
        "titulo_completo",
        "total_envios_thread",
        "primeiro_envio",
        "ultimo_envio",
        "datas_horas_todos_envios",
        "anos_todos_envios",
        "meses_todos_envios",
        "message_ids"
    ]

    with open(ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(
            arquivo,
            fieldnames=campos,
            delimiter=";"
        )

        writer.writeheader()

        for index, item in enumerate(resultado, start=1):
            linha = {
                "posicao_extracao": index,
                "thread_id": item["thread_id"],
                "titulo_completo": item["titulo_completo"],
                "total_envios_thread": item["total_envios_thread"],
                "primeiro_envio": item["primeiro_envio"],
                "ultimo_envio": item["ultimo_envio"],
                "datas_horas_todos_envios": item["datas_horas_todos_envios"],
                "anos_todos_envios": item["anos_todos_envios"],
                "meses_todos_envios": item["meses_todos_envios"],
                "message_ids": item["message_ids"]
            }

            writer.writerow(linha)

    print("")
    print("CSV gerado com sucesso.")
    print(f"Arquivo: {ARQUIVO_CSV}")
    print(f"Total de threads exportadas: {len(resultado)}")
    print(f"Total de mensagens unicas no cache: {len(itens)}")


def executar_por_periodos():
    print("")
    print("========================================")
    print("INICIANDO EXTRACAO GMAIL")
    print("========================================")
    print(f"MAX_WORKERS: {MAX_WORKERS}")
    print("")

    for nome_periodo, query in PERIODOS:
        extrair_periodo(nome_periodo, query)

    gerar_csv_por_thread()

    print("")
    print("PROCESSO FINALIZADO.")
    print(f"Cache gerado/atualizado: {ARQUIVO_CACHE}")
    print(f"CSV gerado/atualizado: {ARQUIVO_CSV}")


if __name__ == "__main__":
    executar_por_periodos()