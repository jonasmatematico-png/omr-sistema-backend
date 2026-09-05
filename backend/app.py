# app.py
# OMR Sistema 2.0 - Backend Híbrido (Supabase + Câmera OMR)

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from supabase import create_client, Client
import os
import io
import qrcode

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
# 🚨 CARREGAMENTO E REGISTRO DO BLUEPRINT DE CORREÇÃO
# ==========================================================

from routes.corrigir import corrigir_bp
print("DEBUG: Blueprint 'corrigir_bp' importado com sucesso.")
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
    id_aluno = dados.get('id_aluno')
    id_avaliacao = dados.get('id_avaliacao', 1)
    nome_aluno = dados.get('nome', '')
    turma_nome = dados.get('turma', '')
    nota_final = float(dados.get('nota_final', 0.0))
    detalhes_respostas = dados.get('detalhes_respostas', [])

    try:
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
        elif nota_final >= 4: nivel = "Básico"

        supabase.table("resultados").insert({
            "id_aluno": id_aluno,
            "id_avaliacao": id_avaliacao,
            "nota_bruta": nota_final,
            "nota_final": round(nota_final),
            "nivel_saeb": nivel,
            "devolutiva": f"O aluno acertou questões totalizando nota {nota_final}."
        }).execute()

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
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/debug/<filename>', methods=['GET'])
def get_debug_image(filename):
    filepath = os.path.join('uploads', filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='image/jpeg')
    return jsonify({"erro": f"Arquivo {filename} não encontrado"}), 404

@app.route('/debug/lista', methods=['GET'])
def list_debug_images():
    if not os.path.exists('uploads'):
        return jsonify({"arquivos": []})
    arquivos = [f for f in os.listdir('uploads') if f.endswith('.jpg')]
    arquivos.sort(reverse=True)
    return jsonify({"arquivos": arquivos})

# ==========================================================
# 📱 QR CODE DA AVALIAÇÃO
# ==========================================================
@app.route('/api/qr/<int:id_avaliacao>', methods=['GET'])
def gerar_qr_avaliacao(id_avaliacao):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(f'OMRPROVA:{id_avaliacao}')
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    print(f"📱 QR gerado para avaliação {id_avaliacao}")
    return send_file(buf, mimetype='image/png')

# ==========================================================
# 📱 QR DO ALUNO (sticker/cartão permanente)
# ==========================================================
@app.route('/api/qr/aluno/<int:id_aluno>', methods=['GET'])
def gerar_qr_aluno(id_aluno):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(f'OMRCARD:{id_aluno}')
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# ==========================================================
# 📱 QR COMBO (prova + aluno)
# ==========================================================
@app.route('/api/qr/combo/<int:id_prova>/<int:id_aluno>', methods=['GET'])
def gerar_qr_combo(id_prova, id_aluno):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(f'OMRALUNO:{id_prova}:{id_aluno}')
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# ==========================================================
# 🎯 GERADOR DE GABARITOS PERSONALIZADOS POR TURMA (v2 - CORRIGIDA)
# ==========================================================
@app.route('/api/gabaritos/turma/<int:id_turma>/prova/<int:id_prova>', methods=['GET'])
def gerar_gabaritos_turma(id_turma, id_prova):
    try:
        print(f"🎯 Gerando gabaritos: turma={id_turma}, prova={id_prova}")

        # Busca turma (com tratamento robusto)
        resp_turma = supabase.table("turmas").select("nome").eq("id", id_turma).execute()
        if not resp_turma.data or len(resp_turma.data) == 0:
            return f"<h1>❌ Turma ID {id_turma} não encontrada!</h1><p>Verifique em <a href='/api/turmas'>/api/turmas</a></p>", 404
        turma_nome = resp_turma.data[0]['nome']

        # Busca avaliação (com tratamento robusto)
        resp_av = supabase.table("avaliacoes").select("nome").eq("id", id_prova).execute()
        if not resp_av.data or len(resp_av.data) == 0:
            return f"<h1>❌ Avaliação ID {id_prova} não encontrada!</h1><p>Verifique em <a href='/api/avaliacoes/lista'>/api/avaliacoes/lista</a></p>", 404
        prova_nome = resp_av.data[0]['nome']

        # Busca alunos
        resp_alunos = supabase.table("alunos").select("*").eq("id_turma", id_turma).execute()
        alunos = resp_alunos.data or []
        alunos.sort(key=lambda a: a.get("numero_chamada") or a.get("id") or 0)

        if not alunos:
            return f"<h1>❌ Nenhum aluno encontrado na turma {turma_nome}!</h1>", 404

        print(f"✅ Turma: {turma_nome} | Prova: {prova_nome} | Alunos: {len(alunos)}")

        # Função para gerar um gabarito (4 colunas: 7+7+7+5 = 26)
        def gerar_gabarito_aluno(aluno):
            nome = aluno.get("nome") or aluno.get("nome_completo") or "Aluno"
            num = str(aluno.get("numero_chamada") or "")
            id_aluno = aluno['id']
            qr_url = f"/api/qr/combo/{id_prova}/{id_aluno}"

            # Gera colunas: 7, 7, 7, 5 questões
            cols_config = [
                (1, 7),    # coluna 1: questões 1-7
                (8, 14),   # coluna 2: questões 8-14
                (15, 21),  # coluna 3: questões 15-21
                (22, 26),  # coluna 4: questões 22-26
            ]

            colunas_html = ""
            for ini, fim in cols_config:
                questoes_html = ""
                for n in range(ini, fim + 1):
                    questoes_html += f'''
                    <div class="questao">
                        <span class="q-numero">{n:02d}</span>
                        <div class="bolinha"></div>
                        <div class="bolinha"></div>
                        <div class="bolinha"></div>
                        <div class="bolinha"></div>
                    </div>'''
                colunas_html += f'''
                <div class="coluna">
                    <div class="coluna-header">
                        <span></span><span>A</span><span>B</span><span>C</span><span>D</span>
                    </div>
                    {questoes_html}
                </div>'''

            return f'''
            <div class="gabarito">
                <div class="marcador tl"></div>
                <div class="marcador tr"></div>
                <div class="marcador bl"></div>
                <div class="marcador br"></div>

                <div class="cabecalho">
                    <div class="campos">
                        <div class="campo campo-full">
                            <label>Nome:</label>
                            <span class="nome-impresso">{nome}</span>
                        </div>
                        <div class="campo">
                            <label>N°:</label>
                            <span class="valor">{num}</span>
                        </div>
                        <div class="campo">
                            <label>Turma:</label>
                            <span class="valor">{turma_nome}</span>
                        </div>
                        <div class="campo campo-full">
                            <label>Avaliação:</label>
                            <span class="valor">{prova_nome}</span>
                        </div>
                    </div>
                </div>

                <div class="grade">{colunas_html}</div>

                <div class="qr-container">
                    <img class="qr-img" src="{qr_url}" alt="QR">
                </div>
            </div>
            '''

        # Gera todos os gabaritos
        gabaritos = [gerar_gabarito_aluno(a) for a in alunos]

        # Monta páginas (3 por folha A4)
        paginas = ""
        for i in range(0, len(gabaritos), 3):
            grupo = gabaritos[i:i+3]
            quebras = ""
            for j, gab in enumerate(grupo):
                quebras += gab
                if j < len(grupo) - 1:
                    quebras += '<div class="linha-corte">✂ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─</div>'
            paginas += f'<div class="folha">{quebras}</div>'
            if i + 3 < len(gabaritos):
                paginas += '<div style="page-break-after: always;"></div>'

        html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Gabaritos - {turma_nome} - {prova_nome}</title>
<style>
    @page {{ size: A4 portrait; margin: 5mm; }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: Arial, Helvetica, sans-serif; background: #fff; padding: 10px; }}
    h1 {{ text-align: center; font-size: 14px; margin-bottom: 4mm; color: #333; }}

    .folha {{ width: 200mm; min-height: 286mm; margin: 0 auto; padding: 0.5mm 2mm; display: flex; flex-direction: column; justify-content: space-between; }}
    .gabarito {{ position: relative; height: 91.5mm; border: 0.5mm solid #333; padding: 1.5mm 4mm 1mm 4mm; overflow: hidden; }}

    .marcador {{ position: absolute; width: 5mm; height: 5mm; background: #000; }}
    .marcador.tl {{ top: 0; left: 0; }} .marcador.tr {{ top: 0; right: 0; }}
    .marcador.bl {{ bottom: 0; left: 0; }} .marcador.br {{ bottom: 0; right: 0; }}

    .cabecalho {{ margin-bottom: 1.5mm; padding-bottom: 1mm; border-bottom: 0.3mm dashed #999; }}
    .campos {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1mm 4mm; font-size: 8.5px; }}
    .campo {{ display: flex; align-items: baseline; gap: 1.5mm; }}
    .campo label {{ font-weight: bold; white-space: nowrap; }}
    .campo .nome-impresso {{ flex: 1; border-bottom: 0.3mm solid #333; font-weight: bold; font-size: 10px; padding-left: 2mm; }}
    .campo .valor {{ flex: 1; border-bottom: 0.3mm solid #333; font-weight: bold; padding-left: 2mm; }}
    .campo-full {{ grid-column: 1 / -1; }}

    .grade {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 0 3mm; }}
    .coluna-header {{ display: grid; grid-template-columns: 5mm 1fr 1fr 1fr 1fr; font-size: 7px; font-weight: bold; text-align: center; height: 3mm; color: #333; }}
    .questao {{ display: grid; grid-template-columns: 5mm 1fr 1fr 1fr 1fr; align-items: center; height: 4.2mm; border-bottom: 0.2mm dotted #ccc; }}
    .q-numero {{ font-size: 7.5px; font-weight: bold; text-align: center; color: #333; }}
    .bolinha {{ width: 3.5mm; height: 3.5mm; border: 0.4mm solid #333; border-radius: 50%; margin: 0 auto; }}

    .qr-container {{ position: absolute; bottom: 2mm; right: 3mm; }}
    .qr-img {{ width: 16mm; height: 16mm; }}

    .linha-corte {{ text-align: center; font-size: 7px; color: #999; height: 3mm; line-height: 3mm; }}

    @media print {{
        body {{ padding: 0; background: white; }}
        .folha {{ padding: 0; }}
    }}
</style>
</head>
<body>
<h1>📋 GABARITOS PERSONALIZADOS — {turma_nome} — {prova_nome} ({len(alunos)} alunos)</h1>
{paginas}
</body>
</html>'''
        return html

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1>❌ Erro ao gerar gabaritos: {e}</h1>", 500

# ==========================================================
# 🏷️ FOLHA DE ETIQUETAS QR DA TURMA
# ==========================================================
@app.route('/api/etiquetas/<int:id_turma>', methods=['GET'])
def etiquetas_turma(id_turma):
    try:
        resp = supabase.table("alunos").select("*").eq("id_turma", id_turma).execute()
        alunos = resp.data or []
        alunos.sort(key=lambda a: a.get("numero_chamada") or a.get("id") or 0)

        cards = ""
        for a in alunos:
            nome = a.get("nome") or a.get("nome_completo") or "Aluno"
            num = a.get("numero_chamada") or ""
            cards += f'''
            <div class="etiqueta">
                <img src="/api/qr/aluno/{a['id']}">
                <div class="nome">{num}. {nome}</div>
            </div>'''

        html = f'''<!DOCTYPE html>
        <html lang="pt-BR"><head><meta charset="UTF-8">
        <title>Etiquetas QR - Turma {id_turma}</title>
        <style>
            @page {{ size: A4 portrait; margin: 8mm; }}
            body {{ font-family: Arial; }}
            .grade {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 4mm; }}
            .etiqueta {{ border: 1px dashed #999; padding: 3mm; text-align: center; page-break-inside: avoid; }}
            .etiqueta img {{ width: 30mm; height: 30mm; }}
            .nome {{ font-size: 9px; font-weight: bold; margin-top: 1mm; }}
            h1 {{ font-size: 12px; text-align: center; }}
        </style></head><body>
        <h1>ETIQUETAS QR DOS ALUNOS — recorte e cole no gabarito (ou lamine como cartão)</h1>
        <div class="grade">{cards}</div>
        </body></html>'''
        return html
    except Exception as e:
        return f"<h1>Erro: {e}</h1>", 500

# ==========================================================
# 🏁 INICIALIZAÇÃO DO SERVIDOR
# ==========================================================
if __name__ == '__main__':
    print("🚨🚨🚨 OMR SISTEMA 2.0 - HÍBRIDO (SUPABASE + CÂMERA) 🚨🚨🚨")
    print(f"🔗 Supabase URL: {SUPABASE_URL}")
    port = int(os.environ.get("PORT", 10000))
    print(f"📡 Servidor rodando na porta: {port} (host: 0.0.0.0)")
    print(f"   Acessível em: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)