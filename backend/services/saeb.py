# services/saeb.py
# Cérebro do sistema SAEB
# Calcula nota, nível e devolutiva

# ================================================
# PESOS POR NÍVEL (definidos pela escola)
# ================================================
PESOS = {
    'BASICO':        1.00,
    'INTERMEDIARIO': 1.25,
    'AVANCADO':      0.67,
}

# ================================================
# RÉGUA DE NÍVEIS (definida pela escola)
# ================================================
# 🔴 Abaixo do Básico: 0,00 até 4,99
# 🟡 Básico:           5,00 até 6,49
# 🔵 Adequado:         6,50 até 8,49
# 🟢 Avançado:         8,50 até 10,00

def calcular_nivel(nota):
    if nota < 5.00:
        return 'Abaixo do Básico'
    elif nota < 6.50:
        return 'Básico'
    elif nota < 8.50:
        return 'Adequado'
    else:
        return 'Avançado'

# ================================================
# DEVOLUTIVAS POR NÍVEL
# ================================================
DEVOLUTIVAS = {
    'Abaixo do Básico': 'Dificuldade em localizar informações explícitas e compreender o texto.',
    'Básico':           'Localiza informações, mas apresenta dificuldade com inferências e análises.',
    'Adequado':         'Compreende inferências e interpreta ideias implícitas de forma consistente.',
    'Avançado':         'Leitura crítica, interpreta valores, intenções e contextos históricos.',
}

def calcular_devolutiva(nivel):
    return DEVOLUTIVAS.get(nivel, '')

# ================================================
# CÁLCULO DA NOTA SAEB COM PESOS
# ================================================
def calcular_nota_saeb(questoes_config, respostas_aluno):
    """
    questoes_config: lista de dicionários com:
        - gabarito: letra correta (ex: 'A')
        - nivel: nível da questão (ex: 'BASICO')
    
    respostas_aluno: lista de letras detectadas pelo OMR
        (ex: ['A', 'B', 'C', 'D', ...])
    
    Retorna dicionário com:
        - nota: nota final (0 a 10)
        - nivel: nível SAEB
        - devolutiva: texto de devolutiva
        - acertos_basico: quantidade de acertos básicos
        - total_basico: total de questões básicas
        - acertos_inter: quantidade de acertos intermediários
        - total_inter: total de questões intermediárias
        - acertos_avanc: quantidade de acertos avançados
        - total_avanc: total de questões avançadas
        - detalhes: lista com resultado de cada questão
    """
    nota        = 0.0
    detalhes    = []

    acertos_basico = 0
    acertos_inter  = 0
    acertos_avanc  = 0
    total_basico   = 0
    total_inter    = 0
    total_avanc    = 0

    for i, q in enumerate(questoes_config):
        gabarito = str(q.get('gabarito', '')).strip().upper()
        nivel    = str(q.get('nivel', 'BASICO')).strip().upper()

        # Normaliza o nível
        if nivel.startswith('B'):
            nivel_normalizado = 'BASICO'
            total_basico += 1
        elif nivel.startswith('I'):
            nivel_normalizado = 'INTERMEDIARIO'
            total_inter += 1
        else:
            nivel_normalizado = 'AVANCADO'
            total_avanc += 1

        peso = PESOS.get(nivel_normalizado, 1.00)

        # Resposta do aluno
        if i < len(respostas_aluno):
            resp_aluno = str(respostas_aluno[i]).strip().upper()
        else:
            resp_aluno = ''

        correta = (resp_aluno == gabarito)

        if correta:
            nota += peso
            if nivel_normalizado == 'BASICO':
                acertos_basico += 1
            elif nivel_normalizado == 'INTERMEDIARIO':
                acertos_inter += 1
            else:
                acertos_avanc += 1

        detalhes.append({
            'questao':        i + 1,
            'gabarito':       gabarito,
            'resposta_aluno': resp_aluno,
            'nivel':          nivel_normalizado,
            'peso':           peso,
            'correta':        correta,
        })

    # Garante que a nota não ultrapasse 10
    nota = round(min(nota, 10.0), 2)

    nivel     = calcular_nivel(nota)
    devolutiva = calcular_devolutiva(nivel)

    return {
        'nota':           nota,
        'nivel':          nivel,
        'devolutiva':     devolutiva,
        'acertos_basico': acertos_basico,
        'total_basico':   total_basico,
        'acertos_inter':  acertos_inter,
        'total_inter':    total_inter,
        'acertos_avanc':  acertos_avanc,
        'total_avanc':    total_avanc,
        'detalhes':       detalhes,
    }

# ================================================
# CÁLCULO DA NOTA COMUM (1 ponto por questão)
# ================================================
def calcular_nota_comum(questoes_config, respostas_aluno):
    """
    Para o modelo COMUM_10:
    Cada questão vale 1 ponto.
    Nota máxima = 10.
    Não usa níveis nem pesos.
    """
    acertos  = 0
    detalhes = []

    for i, q in enumerate(questoes_config):
        # Aceita tanto 'gabarito' quanto 'g'
        gabarito = str(
            q.get('gabarito', q.get('g', ''))
        ).strip().upper()

        if i < len(respostas_aluno):
            resp_aluno = str(
                respostas_aluno[i]
            ).strip().upper()
        else:
            resp_aluno = ''

        correta = (resp_aluno == gabarito)
        if correta:
            acertos += 1

        detalhes.append({
            'questao':        i + 1,
            'gabarito':       gabarito,
            'resposta_aluno': resp_aluno,
            'correta':        correta,
        })

    nota       = round(float(acertos), 2)
    nivel      = calcular_nivel(nota)
    devolutiva = calcular_devolutiva(nivel)

    return {
        'nota':           nota,
        'nivel':          nivel,
        'devolutiva':     devolutiva,
        'acertos_basico': acertos,
        'total_basico':   len(questoes_config),
        'acertos_inter':  0,
        'total_inter':    0,
        'acertos_avanc':  0,
        'total_avanc':    0,
        'detalhes':       detalhes,
    }