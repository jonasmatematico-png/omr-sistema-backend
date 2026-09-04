# app.py
# OMR Sistema 2.0 - Backend Híbrido (Supabase + Câmera OMR)

from flask import Flask, jsonify, request
from flask_cors import CORS
from supabase import create_client, Client
import os

# ==========================================================
# 🔑 CRIAÇÃO DO OBJETO FLASK E CONFIGURAÇÃO INICIAL
# ==========================================================

app = Flask(__name__)
CORS(app)

# ==========================================================
# 🔑 CONFIGURAÇÃO DO SUPABASE
# ==========================================================
SUPABASE_URL = "https://mkqnaiuplkqiitwxltli.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1rcW5haXVwbGtxaWl0d3hsdGxpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQzOTg5MzMsImV4cCI6MjA5OTk3NDkzM30.65MoDC1gMNpNs6bCKZlCTyCn2ijaaA6y9DOnQgNxacA"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================================
# 🚨 CARREGAMENTO E REGISTRO DO BLUEPRINT DE CORREÇÃO (DEVE VIR DEPOIS DA CRIAÇÃO DO APP)
# ==========================================================

# Importa o blueprint *depois* que 'app' e 'supabase' são definidos
# A importação é feita aqui para garantir que 'app' já exista quando 'corrigir_bp' for registrado.
# O 'print' de debug é opcional, mas ajuda a confirmar o carregamento.
from routes.corrigir import corrigir_bp
print("DEBUG: Blueprint 'corrigir_bp' importado com sucesso.")

# Registra o blueprint *depois* que 'app' foi criado e configurado.
app.register_blueprint(corrigir_bp)
print("DEBUG: Blueprint 'corrigir_bp' registrado com sucesso.")

# ===========================================================
# 🚀 ROTAS DA API
# ===========================================================

@app.route('/api/config/IP_Servidor', methods=['GET'])
def get_ip_servidor():
    return jsonify({"ip": "192.168.3.20", "status": "online", "sucesso": True})

@app.route('/api/avaliacoes/tipos', methods=['GET'])
def get_tipos_avaliacao():
    try:
        response = supabase.table("tipos_avaliacao").select("*").execute()
        return jsonify({"sucesso": True, "tipos": response.data})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/turmas', methods=['GET'])
def get_turmas():
    try:
        response = supabase.table("turmas").select("*").execute()
        return jsonify({'sucesso': True, 'turmas': response.data})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/turmas/<int:turma_id>/alunos', methods=['GET'])
def get_alunos_turma(turma_id):
    try:
        response = supabase.table("alunos").select("*").eq("id_turma", turma_id).execute()
        alunos_formatados = []
        for aluno in response.data:
            alunos_formatados.append({
                "id": aluno["id"],
                "nome": aluno.get("nome") or aluno.get("nome_completo") or "Sem nome",
                "id_turma": aluno.get("id_turma"),
                "status": aluno.get("status", "Pendente")
            })
        return jsonify({"sucesso": True, "alunos": alunos_formatados})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/avaliacoes/lista', methods=['GET'])
def get_avaliacoes_lista():
    try:
        response = supabase.table("avaliacoes").select("id, nome").execute()
        if response.data:
            return jsonify(response.data)
        return jsonify([{"id": 1, "nome": "Simulado SAEB - 1º Bimestre"}])
    except Exception:
        return jsonify([{"id": 1, "nome": "Avaliação Padrão"}])

@app.route('/api/avaliacoes/<int:avaliacao_id>/gabarito', methods=['GET'])
def get_gabarito_avaliacao(avaliacao_id):
    try:
        response = supabase.table("questoes").select("gabarito, peso, nivel, descritor").eq("id_avaliacao", avaliacao_id).order("numero").execute()
        if response.data:
            return jsonify({
                "gabarito": [q["gabarito"] for q in response.data],
                "pesos": [float(q["peso"]) for q in response.data],
                "niveis": [q.get("nivel", "Básico") for q in response.data],
                "descritores": [q.get("descritor", "") for q in response.data]
            })
        return jsonify({"gabarito": [], "pesos": [], "niveis": [], "descritores": []})
    except Exception as e:
        print(f"Erro ao buscar gabarito: {e}")
        return jsonify({"gabarito": [], "pesos": [], "niveis": [], "descritores": []})

@app.route('/api/salvar_correcao_omr', methods=['POST'])
def salvar_correcao_omr():
    if not request.is_json:
        return jsonify({'erro': 'Formato inválido. Envie JSON.'}), 400

    dados = request.get_json()

    # Tenta pegar os IDs direto (o ideal), senão usa os nomes (fallback)
    id_aluno = dados.get('id_aluno')
    id_avaliacao = dados.get('id_avaliacao', 1) # Se não enviar, usa 1 como padrão
    nome_aluno = dados.get('nome', '')
    turma_nome = dados.get('turma', '')
    nota_final = float(dados.get('nota_final', 0.0))

    # NOVO: Lista de respostas detalhadas que o celular deve enviar
    detalhes_respostas = dados.get('detalhes_respostas', [])

    try:
        # Se o ID do aluno não veio direto, busca pelo nome (para não quebrar seu app atual)
        if not id_aluno:
            resp_turma = supabase.table("turmas").select("id").eq("nome", turma_nome).execute()
            if not resp_turma.data:
                return jsonify({"sucesso": False, "erro": f"Turma '{turma_nome}' não encontrada"}), 404
            id_turma = resp_turma.data[0]['id']

            resp_aluno = supabase.table("alunos").select("id").eq("nome", nome_aluno).eq("id_turma", id_turma).execute()
            if not resp_aluno.data:
                return jsonify({"sucesso": False, "erro": f"Aluno '{nome_aluno}' não encontrado"}), 404
            id_aluno = resp_aluno.data[0]['id']

        nivel = "Abaixo do Básico"
        if nota_final >= 8: nivel = "Avançado"
        elif nota_final >= 6: nivel = "Adequado"
        elif nota_final >= 4: nivel = "Básico" # Corrigido typo: "Bás" para "Básico"

        # 1. SALVAR RESULTADO FINAL (Já fazia isso)
        supabase.table("resultados").insert({
            "id_aluno": id_aluno,
            "id_avaliacao": id_avaliacao,
            "nota_bruta": nota_final,
            "nota_final": round(nota_final),
            "nivel_saeb": nivel,
            "devolutiva": f"O aluno acertou questões totalizando nota {nota_final}."
        }).execute()

        # 2. 🚨 NOVO: SALVAR CADA RESPOSTA NA TABELA 'respostas'
        if detalhes_respostas:
            print(f"💾 Salvando {len(detalhes_respostas)} respostas detalhadas no banco...")
            for item in detalhes_respostas:
                supabase.table("respostas").insert({
                    "id_avaliacao": id_avaliacao,
                    "id_aluno": id_aluno,
                    "id_questao": item.get('questao'),
                    "resposta_aluno": item.get('resposta', ''),
                    "correta": item.get('correta', False)
                }).execute()
            print("✅ Respostas detalhadas salvas com sucesso!")

        return jsonify({'sucesso': True, 'mensagem': f'Nota {round(nota_final)} e respostas gravadas com sucesso!'}), 200

    except Exception as e:
        print(f"❌ ERRO AO SALVAR: {e}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

@app.route('/api/avaliacoes/criar', methods=['POST'])
def criar_avaliacao():
    try:
        dados = request.json
        response = supabase.table("avaliacoes").insert({
            "id_turma": dados.get("id_turma"),
            "id_tipo": dados.get("id_tipo"),
            "nome": dados.get("nome"),
            "data_prova": dados.get("data_prova"),
            "status": "ativa"
        }).execute()

        if response.data:
            return jsonify({"sucesso": True, "mensagem": "Avaliação criada!"}), 201
        return jsonify({"sucesso": False, "erro": "Falha ao inserir"}), 500
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ========================================================================
# 🚨 AQUI ESTÁ A ROTA DO GABARITO (NO NÍVEL CORRETO, SEM INDENTAÇÃO ERRADA)
# ========================================================================
@app.route('/api/avaliacoes/gabarito/salvar', methods=['POST'])
def salvar_gabarito():
    try:
        print("🟢 [PYTHON] Rota /api/avaliacoes/gabarito/salvar chamada!")
        dados = request.json
        id_avaliacao = dados.get('id_avaliacao')
        questoes = dados.get('questoes', [])
        print(f"🟢 [PYTHON] Recebido gabarito para avaliação {id_avaliacao}: {len(questoes)} questões")

        print("🟡 [PYTHON] Passo 1: Deletando questões antigas...")
        supabase.table("questoes").delete().eq("id_avaliacao", id_avaliacao).execute()
        print("🟢 [PYTHON] Passo 1 concluído.")

        print("🟡 [PYTHON] Passo 2: Preparando dados para inserção...")
        dados_para_inserir = []
        for q in questoes:
            dados_para_inserir.append({
                "id_avaliacao": id_avaliacao,
                "numero": q.get('numero'),
                "gabarito": q.get('resposta').upper(),
                "peso": float(q.get('peso', 1.0)),
                "nivel": q.get('nivel', 'Básico'),
                "descritor": q.get('descritor', '')
            })
        print(f"🟢 [PYTHON] Passo 2 concluído. {len(dados_para_inserir)} itens preparados.")

        print("🟡 [PYTHON] Passo 3: Inserindo no Supabase...")
        if dados_para_inserir:
            response = supabase.table("questoes").insert(dados_para_inserir).execute()
            print(f"🟢 [PYTHON] Passo 3 concluído! {len(response.data)} questões salvas.")
            return jsonify({"sucesso": True, "mensagem": "Gabarito salvo!"}), 201
        else:
            print("🔴 [PYTHON] Nenhuma questão para salvar.")
            return jsonify({"sucesso": False, "erro": "Nenhuma questão para salvar"}), 400

    except Exception as e:
        print(f"🔴 [PYTHON] ERRO CRÍTICO ao salvar gabarito: {e}")
        import traceback
        traceback.print_exc() # Isso vai mostrar a linha exata do erro no terminal
        return jsonify({"sucesso": False, "erro": str(e)}), 500

    # ==========================================================
# 📸 ROTA PARA BAIXAR FOTOS DE DEBUG
# ==========================================================
@app.route('/debug/<filename>', methods=['GET'])
def get_debug_image(filename):
    import os
    filepath = os.path.join('uploads', filename)
    if os.path.exists(filepath):
        from flask import send_file
        return send_file(filepath, mimetype='image/jpeg')
    return jsonify({"erro": f"Arquivo {filename} não encontrado"}), 404

@app.route('/debug/lista', methods=['GET'])
def list_debug_images():
    import os
    if not os.path.exists('uploads'):
        return jsonify({"arquivos": []})
    arquivos = [f for f in os.listdir('uploads') if f.endswith('.jpg')]
    arquivos.sort(reverse=True)
    return jsonify({"arquivos": arquivos})

    # ==========================================================
# 📱 ROTA PARA GERAR QR CODE DA AVALIAÇÃO
# ==========================================================
@app.route('/api/qr/<int:id_avaliacao>', methods=['GET'])
def gerar_qr_avaliacao(id_avaliacao):
    import qrcode
    import io
    from flask import send_file

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(f'OMRAV{id_avaliacao}')
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    print(f"📱 QR gerado para avaliação {id_avaliacao}")
    return send_file(buf, mimetype='image/png')

# ==========================================================
# 🏁 INICIALIZAÇÃO DO SERVIDOR (DEVE SER A ÚLTIMA COISA NO ARQUIVO)
# ==========================================================
if __name__ == '__main__':
    print("🚨🚨🚨 OMR SISTEMA 2.0 - HÍBRIDO (SUPABASE + CÂMERA) 🚨🚨🚨")
    print(f"🔗 Supabase URL: {SUPABASE_URL}")

    # 🚨 AJUSTE PARA RENDER: Sempre use a porta fornecida pelo ambiente
    # O Render define automaticamente a variável PORT.
    # O valor padrão é 10000, mas é melhor deixar o ambiente definir.
    # Não defina host='127.0.0.1', use '0.0.0.0' como exigido.
    port = int(os.environ.get("PORT", 10000))
    print(f"📡 Servidor rodando na porta: {port} (host: 0.0.0.0)")
    print(f"   Acessível em: http://0.0.0.0:{port}")

    # Obrigatório para o Render: Bind em 0.0.0.0
    app.run(host='0.0.0.0', port=port, debug=False)
