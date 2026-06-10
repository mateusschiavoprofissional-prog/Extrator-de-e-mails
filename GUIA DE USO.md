# 📖 Manual Completo do Usuário e Guia de Ajuste de Pesos

> [!IMPORTANT]
> **Acesso na Rede Local (LAN)**
> Como o aplicativo está configurado para rodar na sua máquina e escutar todas as conexões da rede, outras pessoas na mesma rede/Wi-Fi podem acessar o painel diretamente pelo navegador utilizando os seguintes links:
> * **Link Principal (Recomendado):** [http://192.168.200.133:5210](http://192.168.200.133:5210)
> * **Alternativas (Caso o principal não conecte):**
>   - [http://192.168.56.1:5210](http://192.168.56.1:5210)
>   - [http://192.168.148.1:5210](http://192.168.148.1:5210)
>   - [http://192.168.159.1:5210](http://192.168.159.1:5210)
>
> *Nota: Certifique-se de que o servidor está ativado e rodando no seu computador (usando o arquivo `iniciar_servidor.bat`).*

---

Bem-vindo ao manual oficial do **Radar de Reenvios**. Este guia foi elaborado especialmente para ajudar tanto usuários leigos (explicando como usar todas as funções visuais do painel) quanto desenvolvedores ou administradores que desejam ajustar as regras e os pesos de pontuação diretamente no código.

---

## 🌟 O que é o Radar de Reenvios?

Este aplicativo é um sistema inteligente que analisa e-mails enviados para **identificar, agrupar e ranquear assuntos que se repetem ou são reenviados**. Ele ajuda você a descobrir quais informativos, diagramas, esquemas elétricos ou respostas comerciais são mais utilizados no seu dia a dia, classificando-os por volume e por recência (dando mais relevância a e-mails novos).

---

## 💻 1. Manual de Uso do Dashboard (Para Usuários)

Abaixo explicamos o que faz cada botão, filtro e gráfico do painel do aplicativo.

### 🔄 Barra de Sincronização e Controles do Gmail
Na parte superior direita do cabeçalho, você verá os botões de controle que servem para puxar dados diretamente do seu Gmail de forma automática:
* **▶️ Iniciar:** Pede permissão para acessar a conta do Gmail do perfil selecionado (se for a primeira vez) e começa a baixar os e-mails enviados. O progresso é exibido em uma barra azul em tempo real.
* **⏸️ Pausar:** Interrompe o processo temporariamente se você precisar. Clicar em "Iniciar" novamente retoma exatamente de onde você parou.
* **⏹️ Parar:** Interrompe a extração atual. Os dados já processados continuam guardados no banco.
* **🔄 Reiniciar:** Apaga todo o histórico do banco de dados do perfil atual e inicia uma sincronização completamente nova do zero com o Gmail.

---

### 📊 Painel de Métricas (Cartões de Cima)
Estes cartões mostram um resumo instantâneo dos dados:
1. **E-mails Analisados:** O número total de mensagens lidas da sua caixa de saída.
2. **Reenvios Detectados:** A quantidade total de reenvios (mensagens repetidas ou encaminhadas).
3. **E-mail Mais Reenviado:** O assunto que teve o maior número bruto de envios na história.
4. **Mais Relevante (Score):** O e-mail que está no topo do ranking considerando a fórmula de recência (e-mails novos ganham muito mais destaque que e-mails antigos).

---

### 📈 Gráficos de Tendência
* **Distribuição Mensal:** Linha que mostra o fluxo de reenvios mês a mês. Ótimo para ver picos de atividade ao longo do ano.
* **Distribuição Anual:** Barras coloridas exibindo o volume agrupado por ano, facilitando identificar em qual período a mensagem foi mais ativa.

---

### 🔍 Filtros e Busca da Tabela
Você pode refinar o ranking exibido na tabela usando as seguintes ferramentas na barra cinza:
* **Campo de Busca (Lupa):** Digite qualquer palavra-chave (ex: *"Toyota"* ou *"Vidro"*) para filtrar instantaneamente os e-mails que contêm esse texto no assunto.
* **Todos os Anos (Filtro por Ano):** Permite isolar apenas os e-mails cujo ano de maior atividade foi o selecionado (ex: ver apenas e-mails dominantes de 2026).
* **Ordenação (Filtro de Ordem):** 
  - **Ordenar por Score (Recência):** Coloca no topo os e-mails novos e quentes, mesmo que tenham poucas repetições.
  - **Ordenar por Qtd. Total:** Coloca no topo os e-mails que foram enviados mais vezes no total bruto da história.
* **📥 Exportar CSV:** Faz o download automático de um arquivo de planilha (`.csv`) com a tabela exata e com os filtros que você aplicou na tela, ideal para abrir no Excel.

---

### 📋 Visualizando Ocorrências e Copiando o Título (Modal de Detalhes)
Ao dar um clique duplo ou clicar em qualquer e-mail listado na tabela, uma janela pop-up (Modal) se abrirá mostrando:
* A data do primeiro e do último envio.
* Um gráfico mensal de ocorrências exclusivo daquele assunto.
* A lista detalhada de cada vez que o e-mail foi enviado com a data e hora exatas.
* **📋 Botão Copiar (Novidade):** Ao lado do título grande do e-mail no topo da janela, existe um botão cinza **"Copiar"**. Ao clicar nele:
  1. O assunto completo é copiado automaticamente para a área de transferência do seu computador (pronto para colar onde precisar).
  2. O botão se transforma em um aviso verde **`✅ Copiado!`** por 1.5 segundos para confirmar visualmente a ação.

---

## 📂 2. Como Importar Dados por Arquivos (Upload)

Se você já possui um arquivo extraído anteriormente e não deseja conectar a API do Gmail, você pode utilizar a função de **Importação de Arquivo**:

1. Clique no botão **⚙️ Configurações** no canto superior direito do dashboard.
2. Na parte inferior da tela, localize a área tracejada chamada **"Importar Dados de E-mails Extraídos"**.
3. Você pode **arrastar e soltar** seu arquivo diretamente dentro do quadrado tracejado ou **clicar** nele para abrir as pastas do seu computador e selecionar o arquivo.
4. **Formatos Suportados:** Arquivos nas extensões `.json`, `.jsonl`, `.csv` ou `.txt`.
5. **Geração de Perfil Automática:** Ao finalizar o upload, o sistema fará o seguinte de forma 100% automática:
   - Criará um banco de dados novinho e isolado para esse arquivo.
   - Gerará um perfil em **"Perfis Disponíveis"** com o nome `Upload: [Nome do seu arquivo]`.
   - Ativará este perfil e atualizará o dashboard na mesma hora com esses dados importados e ranqueados!

---

## 👥 3. O que são e Como Usar os "Perfis Disponíveis"?

O Radar de Reenvios foi desenhado para suportar múltiplos usuários ou caixas de e-mail na mesma máquina. 

### Como Criar e Usar Perfis:
1. Vá na tela de **⚙️ Configurações**.
2. No formulário de cadastro, preencha o nome do perfil (ex: *"E-mail Comercial"*) e o nome da pasta na raiz do projeto onde estão as credenciais do Google daquele e-mail (ex: `Infotecauto`).
3. Uma vez criado, ele aparecerá na lista de **"Perfis Disponíveis"**.
4. Clicando no botão **"Ativar"** ao lado de qualquer perfil cadastrado, o dashboard muda de banco de dados instantaneamente, permitindo que você navegue nos dados de diferentes e-mails de forma independente e isolada.

---

## 🛠️ 4. Guia de Calibração e Pesos do Ranking (Para Administradores)

Se você deseja ajustar os critérios que decidem qual e-mail é considerado "Mais Relevante" e assume o topo do ranking, você deve ajustar a configuração diretamente no código Python.

### Onde ajustar?
Abra o arquivo **[`app.py`](file:///c:/extrator-gmail/app.py)** a partir da linha **254**. Você verá o bloco `PESOS_RANKING`:

```python
PESOS_RANKING = {
    "anos": {
        2026: 200.0,  # Peso para e-mails enviados em 2026 (ano corrente)
        2025: 30.0,   # Peso para e-mails de 2025
        2024: 10.0,   # Peso para e-mails de 2024
        2023: 3.0,    # Peso para e-mails de 2023
        2022: 1.0,    # Peso para e-mails de 2022
        "outros": 0.1 # Peso para e-mails de anos anteriores
    },
    "bonus_eh_reenvio": 20.0,
    "bonus_recencia_12m": 15.0,
    "multiplicador_volume_total": 0.5
}
```

### Explicação Detalhada dos Parâmetros:

#### 📅 A. Pesos Anuais (`anos`)
Define a pontuação base que cada envio recebe de acordo com o ano. Valores maiores dão peso exponencial a e-mails novos. 
* *Exemplo:* Com o peso de 2026 configurado em `200.0` e 2023 em `3.0`, basta **1 único envio** em 2026 para ganhar de **66 envios** de 2023 no ranking!

#### ✉️ B. Bônus de Reenvio Detectado (`bonus_eh_reenvio`)
Uma pontuação extra fixa que é somada a cada evento individual se ele possuir formatação clássica de encaminhamento ou reenvio (como prefixos `Fwd:`, `Enc:`, etc.). 
* *Utilidade:* Ajuda a destacar e-mails que comprovadamente foram encaminhados em vez de apenas possuírem títulos iguais enviados individualmente.

#### ⏱️ C. Bônus de Recência de 12 Meses (`bonus_recencia_12m`)
Adiciona uma pontuação bônus a qualquer envio que tenha ocorrido nos últimos 365 dias corridos a partir da data de hoje.
* *Utilidade:* Faz com que assuntos que voltaram a ser enviados recentemente dêem um salto rápido para o topo do ranking.

#### 📈 D. Multiplicador de Volume Total (`multiplicador_volume_total`)
Controla o quanto a quantidade absoluta de mensagens infla o score final. A fórmula matemática aplicada é:
$$\text{Score Final} = \text{Soma dos Pesos Individuais} \times (1 + (\text{Total de Envios} - 1) \times \text{multiplicador\_volume})$$
* **Como calibrar:**
  - **`0.5` (Equilibrado):** Cada reenvio adicional após o primeiro soma 50% a mais no score. É o equilíbrio perfeito entre recência e volume.
  - **`1.0` ou mais (Foco em Volume):** Dá enorme peso à repetição de envios, fazendo e-mails muito antigos e volumosos subirem.
  - **`0.0` (Foco Temporal):** Ignora a multiplicação por quantidade. A relevância será calculada puramente pelas datas e anos dos e-mails.
