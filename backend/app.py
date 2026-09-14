# app.py
# OMR Sistema 2.0 - Backend Híbrido (Supabase + Câmera OMR + Gemini com Rotação Anti-Cota OTIMIZADA)

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from supabase import create_client, Client
import os
import io
import qrcode
import requests as rq_http   # <-- para chamar o Gemini
import json as jsonlib

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
# 🤖 CONFIGURAÇÃO DO GEMINI (MATRIZ ANTI-COTA: chaves × modelos!)
# ==========================================================
def _carregar_chaves_gemini():
    """Lê GEMINI_API_KEYS (separadas por vírgula) ou usa GEMINI_API_KEY."""
    multi = os.environ.get("GEMINI_API_KEYS", "")
    if multi.strip():
        return [c.strip() for c in multi.split(",") if c.strip()]
    unica = os.environ.get("GEMINI_API_KEY", "")
    return [unica] if unica.strip() else []

GEMINI_CHAVES = _carregar_chaves_gemini()
GEMINI_MODELOS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELOS",
    "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-2.0-flash,gemini-2.0-flash-lite"
).split(",") if m.strip()]

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
# 🎯 GERADOR DE GABARITOS PERSONALIZADOS (v3 - CARIMBO NA IMAGEM ORIGINAL)
# ==========================================================
@app.route('/api/gabaritos/turma/<int:id_turma>/prova/<int:id_prova>', methods=['GET'])
def gerar_gabaritos_turma(id_turma, id_prova):
    from PIL import Image, ImageDraw, ImageFont
    import qrcode
    import io

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.join(base_dir, 'gabarito_base.png')
        if not os.path.exists(base_path):
            base_path = os.path.join(base_dir, 'uploads', 'gabarito_base.png')
        if not os.path.exists(base_path):
            return "<h1>❌ Arquivo gabarito_base.png não encontrado!</h1><p>Coloque a imagem do gabarito limpo com o nome gabarito_base.png na pasta do backend.</p>", 404

        base = Image.open(base_path).convert('RGB')

        BASE_W = 1200
        _r = BASE_W / base.width
        base = base.resize((BASE_W, int(base.height * _r)), Image.LANCZOS)

        W, H = base.size

        fonte = None
        for fp in ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                   '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
                   '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
            try:
                fonte = ImageFont.truetype(fp, int(H * 0.032))
                break
            except Exception:
                continue
        if fonte is None:
            fonte = ImageFont.load_default()

        resp_turma = supabase.table("turmas").select("nome").eq("id", id_turma).execute()
        if not resp_turma.data:
            return f"<h1>❌ Turma {id_turma} não encontrada!</h1>", 404
        turma_nome = resp_turma.data[0]['nome']

        resp_av = supabase.table("avaliacoes").select("nome").eq("id", id_prova).execute()
        if not resp_av.data:
            return f"<h1>❌ Avaliação {id_prova} não encontrada!</h1>", 404
        prova_nome = resp_av.data[0]['nome']

        resp_alunos = supabase.table("alunos").select("*").eq("id_turma", id_turma).execute()
        alunos = resp_alunos.data or []
        alunos.sort(key=lambda a: a.get("numero_chamada") or a.get("id") or 0)
        if not alunos:
            return f"<h1>❌ Nenhum aluno na turma {turma_nome}!</h1>", 404

        print(f"🎯 Gerando PDF: {len(alunos)} gabaritos ({turma_nome} / {prova_nome})")

        gabaritos = []
        for aluno in alunos:
            nome = aluno.get("nome") or aluno.get("nome_completo") or "Aluno"
            num = str(aluno.get("numero_chamada") or "")
            img = base.copy()
            draw = ImageDraw.Draw(img)

            draw.text((W * 0.06, H * 0.025),
                      f"Nome: {nome}    N°: {num}    Turma: {turma_nome}",
                      font=fonte, fill=(0, 0, 0))

            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
            qr.add_data(f'OMRALUNO:{id_prova}:{aluno["id"]}')
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
            qr_size = int(H * 0.20)
            qr_img = qr_img.resize((qr_size, qr_size))
            img.paste(qr_img, (int(W * 0.79), int(H * 0.70)))

            gabaritos.append(img)

        DPI = 150
        AW, AH = int(210 / 25.4 * DPI), int(297 / 25.4 * DPI)
        paginas = []
        for i in range(0, len(gabaritos), 3):
            grupo = gabaritos[i:i + 3]
            canvas = Image.new('RGB', (AW, AH), 'white')
            slot_h = AH // 3
            for j, im in enumerate(grupo):
                tw = AW - 30
                ratio = tw / im.width
                th = int(im.height * ratio)
                if th > slot_h - 16:
                    th = slot_h - 16
                    ratio = th / im.height
                    tw = int(im.width * ratio)
                im2 = im.resize((tw, th))
                x = (AW - tw) // 2
                y = j * slot_h + (slot_h - th) // 2
                canvas.paste(im2, (x, y))
            paginas.append(canvas)

        buf = io.BytesIO()
        if len(paginas) == 1:
            paginas[0].save(buf, format='PDF', resolution=150)
        else:
            paginas[0].save(buf, format='PDF', save_all=True, append_images=paginas[1:], resolution=150)
        buf.seek(0)

        return send_file(buf, mimetype='application/pdf', as_attachment=True,
                         download_name=f'gabaritos_{turma_nome}_{prova_nome}.pdf')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1>❌ Erro: {e}</h1>", 500

# ==========================================================
# 📥 PÁGINA PARA BAIXAR GABARITOS (sem decorar URL!)
# ==========================================================
@app.route('/baixar_gabaritos', methods=['GET'])
def pagina_baixar_gabaritos():
    try:
        resp_turmas = supabase.table("turmas").select("id, nome").order("id").execute()
        turmas = resp_turmas.data or []
        resp_avs = supabase.table("avaliacoes").select("id, nome").order("id").execute()
        avs = resp_avs.data or []

        opts_t = "".join(f'<option value="{t["id"]}">{t["nome"]}</option>' for t in turmas)
        opts_a = "".join(f'<option value="{a["id"]}">{a["nome"]}</option>' for a in avs)

        html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>📥 Baixar Gabaritos Personalizados</title>
<style>
  body {{ font-family: Arial; background:#f2f4ff; display:flex; justify-content:center; padding:20px; }}
  .card {{ background:#fff; border-radius:16px; box-shadow:0 4px 20px rgba(0,0,0,.12); padding:28px; max-width:420px; width:100%; }}
  h1 {{ font-size:20px; text-align:center; color:#3f51b5; }}
  label {{ font-weight:bold; display:block; margin:14px 0 6px; color:#333; }}
  select {{ width:100%; padding:12px; border-radius:8px; border:1px solid #bbb; font-size:15px; }}
  button {{ width:100%; margin-top:18px; padding:14px; border:none; border-radius:10px; font-size:16px; font-weight:bold; color:#fff; cursor:pointer; }}
  .btn-pdf {{ background:#3f51b5; }}
  .btn-etq {{ background:#009688; }}
  button:active {{ opacity:.8; }}
  p.dica {{ font-size:12px; color:#777; text-align:center; margin-top:14px; }}
</style>
</head>
<body>
<div class="card">
  <h1>📥 Gabaritos Personalizados</h1>
  <label>1️⃣ Turma:</label>
  <select id="turma">{opts_t}</select>
  <label>2️⃣ Avaliação (prova):</label>
  <select id="prova">{opts_a}</select>
  <button class="btn-pdf" onclick="baixarPDF()">📄 BAIXAR PDF DOS GABARITOS</button>
  <button class="btn-etq" onclick="baixarEtiquetas()">🏷️ BAIXAR ETIQUETAS QR DA TURMA</button>
  <p class="dica">O PDF sai com 3 gabaritos por folha, cada um com o nome do aluno e o QR combo.</p>
</div>
<script>
  function baixarPDF() {{
    const t = document.getElementById('turma').value;
    const p = document.getElementById('prova').value;
    window.open('/api/gabaritos/turma/' + t + '/prova/' + p, '_blank');
  }}
  function baixarEtiquetas() {{
    const t = document.getElementById('turma').value;
    window.open('/api/etiquetas/' + t, '_blank');
  }}
</script>
</body>
</html>'''
        return html
    except Exception as e:
        return f"<h1>Erro: {e}</h1>", 500

# ==========================================================
# 🏓 ROTA PING (pro UptimeRobot manter servidor acordado!)
# ==========================================================
@app.route('/api/ping', methods=['GET'])
def ping():
    """Rota leve pro UptimeRobot manter o servidor acordado 24/7."""
    return jsonify({
        "sucesso": True,
        "pong": "servidor acordado!",
        "chaves": len(GEMINI_CHAVES),
        "modelos": GEMINI_MODELOS
    }), 200

# ==========================================================
# 🤖 CORREÇÃO DISSERTATIVA (v5 — MATRIZ OTIMIZADA: modelo → chave!)
# ==========================================================
@app.route('/api/teste_gemini', methods=['GET'])
def teste_gemini():
    """Teste rápido: verifica a matriz de chaves e modelos."""
    if not GEMINI_CHAVES:
        return jsonify({"sucesso": False, "erro": "Nenhuma chave configurada"}), 500
    
    resultados = []
    for i, chave in enumerate(GEMINI_CHAVES):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODELOS[0]}:generateContent?key={chave}"
        try:
            resp = rq_http.post(url, json={"contents": [{"parts": [{"text": "OK"}]}]}, timeout=30)
            status = "✅ OK" if resp.status_code == 200 else f"⚠️ {resp.status_code}"
        except Exception as e:
            status = f"❌ {e}"
        resultados.append({"chave": i + 1, "status": status})
    
    return jsonify({
        "sucesso": True,
        "total_chaves": len(GEMINI_CHAVES),
        "modelos": GEMINI_MODELOS,
        "resultados": resultados
    })

@app.route('/api/corrigir_dissertativa', methods=['POST'])
def corrigir_dissertativa():
    """
    Matriz anti-cota OTIMIZADA: para cada modelo, tenta todas as chaves.
    Assim usa as 9 chaves no modelo principal antes de cair pro secundário.
    """
    try:
        if not GEMINI_CHAVES:
            return jsonify({"sucesso": False, "erro": "Nenhuma chave Gemini configurada no servidor"}), 500

        dados = request.get_json() or {}
        prompt = (dados.get('prompt') or '').strip()
        imagens = dados.get('imagens') or []

        if not prompt:
            return jsonify({"sucesso": False, "erro": "Envie 'prompt'"}), 400
        if not imagens:
            return jsonify({"sucesso": False, "erro": "Envie 'imagens' (lista)"}), 400

        # Monta as partes: prompt + todas as imagens
        parts = [{"text": prompt}]
        for img in imagens:
            mime = img.get('mime') or 'image/jpeg'
            data = img.get('data') or ''
            if data.startswith('data:'):
                data = data.split(',', 1)[1] if ',' in data else ''
            parts.append({"inline_data": {"mime_type": mime, "data": data}})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        print(f"🤖 [GEMINI v5 OTIMIZADO] {len(imagens)} imagem(ns) | {len(GEMINI_CHAVES)} chave(s) × {len(GEMINI_MODELOS)} modelo(s)")

        # MATRIZ OTIMIZADA: para cada MODELO, tenta todas as CHAVES
        # Assim usa as 9 chaves no modelo principal antes de cair pro secundário
        ultimo_erro = None
        for modelo in GEMINI_MODELOS:
            for i, chave in enumerate(GEMINI_CHAVES):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={chave}"
                try:
                    resp = rq_http.post(url, json=payload, timeout=180)
                except Exception as e:
                    ultimo_erro = f"Chave {i+1}/{modelo}: rede ({e})"
                    continue

                if resp.status_code == 429:
                    print(f"🔑 [GEMINI] Chave {i+1} + {modelo} sem cota (429) — pulando...")
                    ultimo_erro = f"Chave {i+1}/{modelo}: 429"
                    continue

                if resp.status_code != 200:
                    print(f"❌ [GEMINI] Chave {i+1}/{modelo} erro {resp.status_code}: {resp.text[:200]}")
                    ultimo_erro = f"Chave {i+1}/{modelo}: erro {resp.status_code}"
                    continue

                # SUCESSO!
                saida = resp.json()
                texto = saida["candidates"][0]["content"]["parts"][0]["text"]
                print(f"✅ [GEMINI] Correção concluída com chave {i+1} + modelo {modelo}!")
                return jsonify({
                    "sucesso": True,
                    "texto": texto,
                    "modelo": modelo,
                    "chave_usada": i + 1
                })

        # Todas falharam
        print(f"❌ [GEMINI] Toda a matriz falhou. Último: {ultimo_erro}")
        return jsonify({
            "sucesso": False,
            "erro": f"Todas as {len(GEMINI_CHAVES)} chave(s) × {len(GEMINI_MODELOS)} modelo(s) sem cota. Último erro: {ultimo_erro}"
        }), 429

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================================
# 🏁 INICIALIZAÇÃO DO SERVIDOR
# ==========================================================
if __name__ == '__main__':
    print("🚨🚨🚨 OMR SISTEMA 2.0 - MATRIZ ANTI-COTA OTIMIZADA 🚨🚨🚨")
    print(f"🔗 Supabase URL: {SUPABASE_URL}")
    print(f"🔑 Gemini chaves: {len(GEMINI_CHAVES)} configurada(s)")
    print(f"🤖 Gemini modelos: {GEMINI_MODELOS}")
    port = int(os.environ.get("PORT", 10000))
    print(f"📡 Servidor rodando na porta: {port} (host: 0.0.0.0)")
    print(f"   Acessível em: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)