import os.path
import csv
import re
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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
                    "Arquivo credentials.json não encontrado. "
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

    padrao = r"^\s*(re|res|fw|fwd|enc|encaminhado|tr)\s*:\s*"

    while re.match(padrao, titulo, flags=re.IGNORECASE):
        titulo = re.sub(padrao, "", titulo, flags=re.IGNORECASE).strip()

    titulo = re.sub(r"\s+", " ", titulo)
    return titulo


def converter_data_gmail(internal_date):
    return datetime.fromtimestamp(int(internal_date) / 1000)


def listar_todas_threads_enviadas(service):
    threads = []
    page_token = None

    while True:
        resposta = service.users().threads().list(
            userId="me",
            q="in:sent",
            maxResults=500,
            pageToken=page_token
        ).execute()

        threads.extend(resposta.get("threads", []))

        page_token = resposta.get("nextPageToken")
        if not page_token:
            break

        print(f"Threads carregadas até agora: {len(threads)}")

    return threads


def extrair_todas_threads_enviadas(service):
    threads = listar_todas_threads_enviadas(service)
    resultado = []

    total_threads = len(threads)
    print(f"Threads encontradas: {total_threads}")

    for index, item in enumerate(threads, start=1):
        if index % 100 == 0:
            print(f"Processando thread {index}/{total_threads}")

        thread = service.users().threads().get(
            userId="me",
            id=item["id"],
            format="metadata",
            metadataHeaders=["Subject"]
        ).execute()

        mensagens = thread.get("messages", [])

        mensagens_enviadas = [
            msg for msg in mensagens
            if "SENT" in msg.get("labelIds", [])
        ]

        if len(mensagens_enviadas) == 0:
            continue

        titulo = "Sem assunto"
        datas = []
        message_ids = []

        for msg in mensagens_enviadas:
            headers = msg.get("payload", {}).get("headers", [])
            assunto = obter_header(headers, "Subject")

            if assunto and titulo == "Sem assunto":
                titulo = limpar_titulo(assunto)

            data = converter_data_gmail(msg["internalDate"])
            datas.append(data)
            message_ids.append(msg["id"])

        datas = sorted(datas)

        resultado.append({
            "posicao_extracao": len(resultado) + 1,
            "thread_id": item["id"],
            "titulo_completo": titulo,
            "quantidade_envios_thread": len(datas),
            "datas_envios": [d.strftime("%d/%m/%Y") for d in datas],
            "anos_envios": [str(d.year) for d in datas],
            "meses_envios": [f"{d.year}-{d.month:02d}" for d in datas],
            "primeiro_envio": datas[0].strftime("%d/%m/%Y"),
            "ultimo_envio": datas[-1].strftime("%d/%m/%Y"),
            "message_ids": message_ids
        })

    return resultado


def exportar_csv(lista, caminho="extracao_todas_threads_enviadas.csv"):
    campos = [
        "posicao_extracao",
        "thread_id",
        "titulo_completo",
        "quantidade_envios_thread",
        "datas_envios",
        "anos_envios",
        "meses_envios",
        "primeiro_envio",
        "ultimo_envio",
        "message_ids"
    ]

    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        writer.writeheader()

        for item in lista:
            writer.writerow({
                "posicao_extracao": item["posicao_extracao"],
                "thread_id": item["thread_id"],
                "titulo_completo": item["titulo_completo"],
                "quantidade_envios_thread": item["quantidade_envios_thread"],
                "datas_envios": " | ".join(item["datas_envios"]),
                "anos_envios": " | ".join(item["anos_envios"]),
                "meses_envios": " | ".join(item["meses_envios"]),
                "primeiro_envio": item["primeiro_envio"],
                "ultimo_envio": item["ultimo_envio"],
                "message_ids": " | ".join(item["message_ids"])
            })


def executar_extracao():
    service = autenticar_gmail()
    lista = extrair_todas_threads_enviadas(service)
    exportar_csv(lista)

    print("")
    print("Extração concluída.")
    print(f"Threads exportadas: {len(lista)}")
    print("Arquivo gerado: extracao_todas_threads_enviadas.csv")


if __name__ == "__main__":
    executar_extracao()