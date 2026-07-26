import math # TEM QUE ESTAR NO TOPO DO ARQUIVO!
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DE ACESSO (MANTENHA A QUE VOCÊ JÁ TEM) ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "credentials.json"

def get_client():
    """Retorna o cliente autorizado do Google Sheets."""
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    return gspread.authorize(creds)

def get_sheet(nome_planilha="OMR Sistema 2.0"):
    """Abre a planilha e retorna o objeto spreadsheet."""
    client = get_client()
    return client.open(nome_planilha)

# =====================================================================
# FUNÇÕES EXISTENTES DO OMR (MANTENHA AS SUAS AQUI)
# =====================================================================
# ... (suas funções antigas de OMR continuam aqui) ...


# =====================================================================
#  NOVAS FUNÇÕES - FASE 2: CADASTRO DE AVALIAÇÕES
# =====================================================================

def get_proximo_id(spreadsheet, nome_aba, coluna_id="A"):
    """
    Lê a última linha da coluna de ID e retorna o próximo número.
    Ex: Se a última linha tem ID 5, retorna 6.
    """
    worksheet = spreadsheet.worksheet(nome_aba)
    dados = worksheet.col_values(1)  # Coluna A sempre tem o ID
    
    # Filtra apenas valores numéricos (ignora cabeçalho e vazios)
    ids_numericos = []
    for valor in dados[1:]:  # Pula o cabeçalho
        if valor and valor.strip():
            try:
                ids_numericos.append(int(valor))
            except ValueError:
                pass
    
    if not ids_numericos:
        return 1
    return max(ids_numericos) + 1


def get_referenciais(tipo=None, ano_serie=None):
    """
    Lista os descritores/habilidades da aba REFERENCIAIS.
    Pode filtrar por tipo (DESCRITOR/HABILIDADE) e ano/série.
    """
    spreadsheet = get_sheet()
    worksheet = spreadsheet.worksheet("REFERENCIAIS")
    
    # Pega todos os dados (a partir da linha 2 para pular cabeçalho)
    dados = worksheet.get_all_records()
    
    # Aplica filtros se fornecidos
    resultados = dados
    if tipo:
        resultados = [r for r in resultados if r.get("Tipo", "").upper() == tipo.upper()]
    if ano_serie:
        resultados = [r for r in resultados if r.get("Ano_Serie", "") == ano_serie]
    
    return resultados


def get_turmas(ano_letivo=None):
    """Lista as turmas da aba TURMAS, opcionalmente filtrando por ano letivo."""
    spreadsheet = get_sheet()
    worksheet = spreadsheet.worksheet("TURMAS")
    dados = worksheet.get_all_records()
    
    if ano_letivo:
        dados = [t for t in dados if str(t.get("Ano_Letivo", "")) == str(ano_letivo)]
    
    return dados


def get_config(chave):
    """Lê um valor específico da aba CONFIG."""
    spreadsheet = get_sheet()
    worksheet = spreadsheet.worksheet("CONFIG")
    dados = worksheet.get_all_records()
    
    for linha in dados:
        if linha.get("Chave", "").strip() == chave:
            return linha.get("Valor", "")
    return None


def criar_avaliacao(nome, tipo, data, id_turma, peso_bimestre, ano_saeb, status="ATIVA"):
    """
    Cria uma nova avaliação na aba AVALIACOES.
    Retorna o ID da avaliação criada.
    """
    spreadsheet = get_sheet()
    worksheet = spreadsheet.worksheet("AVALIACOES")
    
    novo_id = get_proximo_id(spreadsheet, "AVALIACOES")
    
    nova_linha = [
        novo_id,
        nome,
        tipo,
        data,
        id_turma,
        peso_bimestre,
        ano_saeb,
        status
    ]
    
    worksheet.append_row(nova_linha)
    print(f"✅ Avaliação '{nome}' criada com ID {novo_id}")
    return novo_id


def criar_questoes(id_avaliacao, lista_questoes):
    """
    Cria as questões de uma avaliação na aba QUESTOES.
    lista_questoes deve ser uma lista de dicionários com as chaves:
    numero, gabarito, nivel, peso, id_ref
    """
    spreadsheet = get_sheet()
    worksheet = spreadsheet.worksheet("QUESTOES")
    
    proximo_id = get_proximo_id(spreadsheet, "QUESTOES")
    
    linhas_para_adicionar = []
    for questao in lista_questoes:
        linha = [
            proximo_id,
            id_avaliacao,
            questao["numero"],
            questao["gabarito"],
            questao["nivel"],
            questao["peso"],
            questao.get("id_ref", "")  # Pode estar vazio se não tiver descritor
        ]
        linhas_para_adicionar.append(linha)
        proximo_id += 1
    
    if linhas_para_adicionar:
        worksheet.append_rows(linhas_para_adicionar)
        print(f"✅ {len(linhas_para_adicionar)} questões criadas para avaliação {id_avaliacao}")
    
    return True


def validar_modelo_avaliacao(lista_questoes):
    """
    Valida se a prova segue o padrão SAEB:
    3 Básicas, 4 Intermediárias, 3 Avançadas.
    Retorna (valido: bool, mensagem: str)
    """
    contagem = {"Básico": 0, "Intermediário": 0, "Avançado": 0}
    
    for q in lista_questoes:
        nivel = q.get("nivel", "")
        if nivel in contagem:
            contagem[nivel] += 1
    
    esperado = {"Básico": 3, "Intermediário": 4, "Avançado": 3}
    
    if contagem == esperado:
        return True, "Modelo OK: 3 Básicas, 4 Intermediárias, 3 Avançadas"
    else:
        msg = f"Modelo inválido! Encontrado: {contagem}. Esperado: {esperado}"
        return False, msg



# ================================================
# PESOS POR NÍVEL (do saeb.py)
# ================================================
PESOS_SAEB = {
    'BÁSICO': 1.00,
    'BÁSICO': 1.00,  # Aceita com acento
    'INTERMEDIÁRIO': 1.25,
    'INTERMEDIARIO': 1.25,  # Aceita sem acento
    'AVANÇADO': 0.67,
    'AVANCADO': 0.67,  # Aceita sem acento
}

# ================================================
# RÉGUA DE NÍVEIS (do saeb.py)
# ================================================
def calcular_nivel_saeb(nota):
    if nota < 5.00:
        return 'Abaixo do Básico'
    elif nota < 6.50:
        return 'Básico'
    elif nota < 8.50:
        return 'Adequado'
    else:
        return 'Avançado'

# ================================================
# DEVOLUTIVAS POR NÍVEL (do saeb.py)
# ================================================
DEVOLUTIVAS_SAEB = {
    'Abaixo do Básico': 'Dificuldade em localizar informações explícitas e compreender o texto.',
    'Básico': 'Localiza informações, mas apresenta dificuldade com inferências e análises.',
    'Adequado': 'Compreende inferências e interpreta ideias implícitas de forma consistente.',
    'Avançado': 'Leitura crítica, interpreta valores, intenções e contextos históricos.',
}

import math

# ================================================
# PESOS POR NÍVEL (do saeb.py)
# ================================================
PESOS_SAEB = {
    'BÁSICO': 1.00,
    'BÁSICO': 1.00,  # Aceita com acento
    'INTERMEDIÁRIO': 1.25,
    'INTERMEDIARIO': 1.25,  # Aceita sem acento
    'AVANÇADO': 0.67,
    'AVANCADO': 0.67,  # Aceita sem acento
}

# ================================================
# RÉGUA DE NÍVEIS (do saeb.py)
# ================================================
def calcular_nivel_saeb(nota):
    if nota < 5.00:
        return 'Abaixo do Básico'
    elif nota < 6.50:
        return 'Básico'
    elif nota < 8.50:
        return 'Adequado'
    else:
        return 'Avançado'

# ================================================
# DEVOLUTIVAS POR NÍVEL (do saeb.py)
# ================================================
DEVOLUTIVAS_SAEB = {
    'Abaixo do Básico': 'Dificuldade em localizar informações explícitas e compreender o texto.',
    'Básico': 'Localiza informações, mas apresenta dificuldade com inferências e análises.',
    'Adequado': 'Compreende inferências e interpreta ideias implícitas de forma consistente.',
    'Avançado': 'Leitura crítica, interpreta valores, intenções e contextos históricos.',
}

def salvar_correcao_inteligente(dados):
    print("🚨🚨🚨 VERSÃO SAEB INTEGRADA - ARREDONDAMENTO ATIVO 🚨🚨🚨")
    
    spreadsheet = get_sheet()
    turma_nome = dados.get("turma", "")
    nome_aluno = dados.get("nome", "")
    respostas_aluno = dados.get("respostas", [])
    
    if not isinstance(respostas_aluno, list):
        respostas_aluno = []
    while len(respostas_aluno) < 10:
        respostas_aluno.append("")

    # 1. Descobrir o ID da Turma
    turmas_sheet = spreadsheet.worksheet("TURMAS").get_all_records()
    id_turma_alvo = None
    for t in turmas_sheet:
        if str(t.get("Nome", "")).strip().lower() == str(turma_nome).strip().lower():
            id_turma_alvo = str(t.get("ID_Turma", "")).strip()
            break
            
    if not id_turma_alvo:
        return {"sucesso": False, "erro": f"Turma '{turma_nome}' não encontrada."}

    # 2. Achar a Avaliação Ativa
    avaliacoes = spreadsheet.worksheet("AVALIACOES").get_all_records()
    id_avaliacao = None
    for aval in avaliacoes:
        if str(aval.get("ID_Turma", "")).strip() == id_turma_alvo and str(aval.get("Status", "")).upper() == "ATIVA":
            id_avaliacao = aval["ID_Aval"]
            break
            
    if not id_avaliacao:
        return {"sucesso": False, "erro": f"Nenhuma avaliação ATIVA para '{turma_nome}'."}

    # 3. Buscar Questões (agora usamos o NÍVEL para definir o peso, não a coluna Peso)
    questoes = spreadsheet.worksheet("QUESTOES").get_all_records()
    questoes_da_prova = [q for q in questoes if str(q["ID_Aval"]) == str(id_avaliacao)]
    questoes_da_prova.sort(key=lambda x: int(x["Numero"]))
    
    gabarito_oficial = {}
    niveis_questoes = {}
    
    for i, q in enumerate(questoes_da_prova):
        num_q = str(i + 1)
        gabarito_oficial[num_q] = str(q.get("Gabarito", "")).strip().upper()
        niveis_questoes[num_q] = str(q.get("Nivel", "Básico")).strip().upper()

    # 4. Calcular Nota usando os pesos do saeb.py (baseado no NÍVEL)
    nota_ponderada_exata = 0.0
    acertos_totais = 0
    acertos_por_nivel = {'Básico': 0, 'Intermediário': 0, 'Avançado': 0}
    
    for i in range(10): 
        num_q = str(i + 1)
        resp_aluno = str(respostas_aluno[i]).strip().upper()
        gabarito = gabarito_oficial.get(num_q, "A")
        nivel = niveis_questoes.get(num_q, "BÁSICO")
        
        # Pega o peso baseado no NÍVEL (não da coluna Peso)
        peso = PESOS_SAEB.get(nivel, 1.00)
        
        if resp_aluno == gabarito:
            nota_ponderada_exata += peso
            acertos_totais += 1
            
            # Conta acertos por nível
            if 'BÁSICO' in nivel or 'BASICO' in nivel:
                acertos_por_nivel['Básico'] += 1
            elif 'INTERMEDI' in nivel:
                acertos_por_nivel['Intermediário'] += 1
            elif 'AVAN' in nivel:
                acertos_por_nivel['Avançado'] += 1

    # 5. ARREDONDAMENTO ESCOLAR (5.5 vira 6, 5.49 vira 5)
    nota_final_arredondada = int(nota_ponderada_exata + 0.5)
    
    # Garante que a nota não ultrapasse 10
    nota_final_arredondada = min(nota_final_arredondada, 10)

    # 6. Classificação SAEB (usando a régua correta do saeb.py)
    nivel_saeb = calcular_nivel_saeb(nota_final_arredondada)
    devolutiva = DEVOLUTIVAS_SAEB.get(nivel_saeb, '')

    print(f"🧮 CÁLCULO SAEB: Aluno={nome_aluno} | Nota Exata={nota_ponderada_exata:.2f} | Nota Final={nota_final_arredondada} | Nível={nivel_saeb}")

    # 7. Encontrar ID do Aluno
    alunos = spreadsheet.worksheet("ALUNOS").get_all_records()
    id_aluno = None
    for al in alunos:
        if nome_aluno in str(al.get("Nome_Completo", "")):
            id_aluno = al["ID_Aluno"]
            break
            
    if not id_aluno:
        return {"sucesso": False, "erro": f"Aluno '{nome_aluno}' não encontrado."}

    # 8. Salvar Respostas
    worksheet_respostas = spreadsheet.worksheet("RESPOSTAS")
    novo_id_resposta = get_proximo_id(spreadsheet, "RESPOSTAS")
    linha_respostas = [novo_id_resposta, id_avaliacao, id_aluno] + respostas_aluno + ["Corrigido"]
    worksheet_respostas.append_row(linha_respostas)

    # 9. Salvar Resultados (com devolutiva)
    worksheet_resultados = spreadsheet.worksheet("RESULTADOS")
    novo_id_resultado = get_proximo_id(spreadsheet, "RESULTADOS")
    
    linha_resultados = [
        novo_id_resultado,
        id_avaliacao,
        id_aluno,
        acertos_totais,                    # Nota Bruta (acertos)
        nota_final_arredondada,            # Nota Ponderada (arredondada)
        nivel_saeb,                        # Nível SAEB
        acertos_por_nivel['Básico'],
        acertos_por_nivel['Intermediário'],
        acertos_por_nivel['Avançado'],
        devolutiva                         # Devolutiva textual
    ]
    worksheet_resultados.append_row(linha_resultados)
    
    print(f"✅ SUCESSO! Nota {nota_final_arredondada} | Nível {nivel_saeb} salvo na planilha!")

    return {
        "sucesso": True, 
        "nota_final": nota_final_arredondada, # <-- Envia o número puro para o app
        "nivel": nivel_saeb,
        "mensagem": f"Nota Final: {nota_final_arredondada} | Nível: {nivel_saeb}"
    }