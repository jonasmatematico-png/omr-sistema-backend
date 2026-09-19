# app.py
# OMR Sistema 2.0 - Backend Completo (Supabase + Câmera OMR + Gemini + Relatórios PDF)

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from supabase import create_client, Client
import os
import io
import qrcode
import requests as rq_http
import json as jsonlib
from datetime import datetime

# ==========================================================
# 📄 RELATÓRIOS PDF (Etapa 2!)
# ==========================================================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    PDF_OK = True
    print("✅ ReportLab carregado — Relatórios PDF ativos!")
except ImportError:
    PDF_OK = False
    print("⚠️ ReportLab NÃO instalado — Relatórios PDF desativados")

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

        supabase.table("questoes").delete().eq("id_avaliacao", id_avaliacao).execute()

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

        if dados_para_inserir:
            response = supabase.table("questoes").insert(dados_para_inserir).execute()
            return jsonify({"sucesso": True, "mensagem": "Gabarito salvo!"}), 201
        else:
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
# 📱 QR CODES
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
    return send_file(buf, mimetype='image/png')

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
# 🎯 GERADOR DE GABARITOS PERSONALIZADOS (v3)
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
            return "<h1>❌ Arquivo gabarito_base.png não encontrado!</h1>", 404

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
# 📥 PÁGINA PARA BAIXAR GABARITOS
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
# 📄 PÁGINA DE RELATÓRIOS (acesso quando quiser!)
# ==========================================================
@app.route('/relatorios', methods=['GET'])
def pagina_relatorios():
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
<title>📄 Relatórios</title>
<style>
  body {{ font-family: Arial; background:#f2f4ff; display:flex; justify-content:center; padding:20px; }}
  .card {{ background:#fff; border-radius:16px; box-shadow:0 4px 20px rgba(0,0,0,.12); padding:28px; max-width:420px; width:100%; }}
  h1 {{ font-size:20px; text-align:center; color:#4A148C; }}
  label {{ font-weight:bold; display:block; margin:14px 0 6px; color:#333; }}
  select {{ width:100%; padding:12px; border-radius:8px; border:1px solid #bbb; font-size:15px; }}
  button {{ width:100%; margin-top:14px; padding:14px; border:none; border-radius:10px; font-size:15px; font-weight:bold; color:#fff; cursor:pointer; }}
  .btn-turma {{ background:#4A148C; }}
  .btn-aluno {{ background:#FF6F00; }}
  button:active {{ opacity:.8; }}
  p.dica {{ font-size:12px; color:#777; text-align:center; margin-top:14px; }}
</style>
</head>
<body>
<div class="card">
  <h1>📄 Relatórios (quando quiser!)</h1>
  <label>1️⃣ Turma:</label>
  <select id="turma" onchange="carregarAlunos()">{opts_t}</select>
  <label>2️⃣ Avaliação (prova):</label>
  <select id="prova">{opts_a}</select>
  <label>3️⃣ Aluno (só pro PDF individual):</label>
  <select id="aluno"><option value="">-- Escolha a turma primeiro --</option></select>
  <button class="btn-turma" onclick="pdfTurma()">📊 PDF DA TURMA (completo)</button>
  <button class="btn-aluno" onclick="pdfAluno()">📝 PDF DO ALUNO (individual)</button>
  <p class="dica">Os relatórios usam os dados salvos no banco — podem ser gerados a qualquer momento!</p>
</div>
<script>
  async function carregarAlunos() {{
    const t = document.getElementById('turma').value;
    const sel = document.getElementById('aluno');
    sel.innerHTML = '<option value="">Carregando...</option>';
    try {{
      const r = await fetch('/api/turmas/' + t + '/alunos');
      const j = await r.json();
      sel.innerHTML = '<option value="">-- Escolha o aluno --</option>';
      (j.alunos || []).forEach(a => {{
        sel.innerHTML += '<option value="' + a.id + '">' + a.nome + '</option>';
      }});
    }} catch (e) {{
      sel.innerHTML = '<option value="">Erro ao carregar</option>';
    }}
  }}
  function pdfTurma() {{
    const t = document.getElementById('turma').value;
    const p = document.getElementById('prova').value;
    window.open('/api/relatorio/turma/' + t + '/' + p, '_blank');
  }}
  function pdfAluno() {{
    const a = document.getElementById('aluno').value;
    const p = document.getElementById('prova').value;
    if (!a) {{ alert('Escolha o aluno primeiro!'); return; }}
    window.open('/api/relatorio/aluno/' + a + '/' + p, '_blank');
  }}
</script>
</body>
</html>'''
        return html
    except Exception as e:
        return f"<h1>Erro: {e}</h1>", 500

# ==========================================================
# 🏓 ROTA PING (UptimeRobot)
# ==========================================================
@app.route('/api/ping', methods=['GET'])
def ping():
    return jsonify({
        "sucesso": True,
        "pong": "servidor acordado!",
        "chaves": len(GEMINI_CHAVES),
        "modelos": GEMINI_MODELOS,
        "pdf_ativo": PDF_OK
    }), 200

# ==========================================================
# 🤖 CORREÇÃO DISSERTATIVA (matriz anti-cota)
# ==========================================================
@app.route('/api/teste_gemini', methods=['GET'])
def teste_gemini():
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
    """Matriz anti-cota: para cada modelo, tenta todas as chaves."""
    try:
        if not GEMINI_CHAVES:
            return jsonify({"sucesso": False, "erro": "Nenhuma chave Gemini configurada"}), 500

        dados = request.get_json() or {}
        prompt = (dados.get('prompt') or '').strip()
        imagens = dados.get('imagens') or []

        if not prompt:
            return jsonify({"sucesso": False, "erro": "Envie 'prompt'"}), 400
        if not imagens:
            return jsonify({"sucesso": False, "erro": "Envie 'imagens' (lista)"}), 400

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

        print(f"🤖 [GEMINI v5] {len(imagens)} imagem(ns) | {len(GEMINI_CHAVES)} chave(s) × {len(GEMINI_MODELOS)} modelo(s)")

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
                    ultimo_erro = f"Chave {i+1}/{modelo}: erro {resp.status_code}"
                    continue

                saida = resp.json()
                texto = saida["candidates"][0]["content"]["parts"][0]["text"]
                print(f"✅ [GEMINI] Correção concluída com chave {i+1} + modelo {modelo}!")
                return jsonify({
                    "sucesso": True,
                    "texto": texto,
                    "modelo": modelo,
                    "chave_usada": i + 1
                })

        return jsonify({
            "sucesso": False,
            "erro": f"Todas as chaves × modelos sem cota. Último: {ultimo_erro}"
        }), 429

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/corrigir_lote', methods=['POST'])
def corrigir_lote():
    """Recebe array de provas e corrige em paralelo (4 threads)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    try:
        if not GEMINI_CHAVES:
            return jsonify({"sucesso": False, "erro": "Nenhuma chave configurada"}), 500

        dados = request.get_json() or {}
        provas = dados.get('provas') or []
        
        if not provas:
            return jsonify({"sucesso": False, "erro": "Envie 'provas' (lista)"}), 400
        
        print(f"📦 [LOTE] Recebidas {len(provas)} prova(s) para correção em paralelo")
        
        def corrigir_uma_prova(prova):
            id_aluno = prova.get('id_aluno')
            nome_aluno = prova.get('nome_aluno', 'Sem nome')
            prompt = (prova.get('prompt') or '').strip()
            imagens = prova.get('imagens') or []
            
            if not prompt or not imagens:
                return {
                    "id_aluno": id_aluno,
                    "nome_aluno": nome_aluno,
                    "sucesso": False,
                    "erro": "Prompt ou imagens faltando"
                }
            
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
            
            for modelo in GEMINI_MODELOS:
                for i, chave in enumerate(GEMINI_CHAVES):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={chave}"
                    try:
                        resp = rq_http.post(url, json=payload, timeout=180)
                    except Exception:
                        continue
                    
                    if resp.status_code == 429 or resp.status_code != 200:
                        continue
                    
                    saida = resp.json()
                    texto = saida["candidates"][0]["content"]["parts"][0]["text"]
                    return {
                        "id_aluno": id_aluno,
                        "nome_aluno": nome_aluno,
                        "sucesso": True,
                        "texto": texto,
                        "modelo": modelo,
                        "chave_usada": i + 1
                    }
            
            return {
                "id_aluno": id_aluno,
                "nome_aluno": nome_aluno,
                "sucesso": False,
                "erro": "Todas as chaves/modelos sem cota"
            }
        
        resultados = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(corrigir_uma_prova, prova): prova for prova in provas}
            for future in as_completed(futures):
                resultado = future.result()
                resultados.append(resultado)
                status = "✅" if resultado.get('sucesso') else "❌"
                print(f"{status} [LOTE] {resultado.get('nome_aluno')}")
        
        resultados.sort(key=lambda r: r.get('id_aluno') or 0)
        
        sucessos = sum(1 for r in resultados if r.get('sucesso'))
        falhas = len(resultados) - sucessos
        
        print(f"📦 [LOTE] Concluído: {sucessos} sucesso(s), {falhas} falha(s)")
        
        return jsonify({
            "sucesso": True,
            "total": len(resultados),
            "sucessos": sucessos,
            "falhas": falhas,
            "resultados": resultados
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================================
# 💾 NOVA: SALVAR CORREÇÃO DISSERTATIVA DETALHADA (Etapa 1!)
# ==========================================================
@app.route('/api/salvar_correcao_detalhada', methods=['POST'])
def salvar_correcao_detalhada():
    """
    Salva os detalhes da correção dissertativa (transcrição, justificativa, notas)
    na tabela correcoes_dissertativas_detalhadas.
    """
    try:
        dados = request.get_json() or {}
        id_aluno = dados.get('id_aluno')
        id_avaliacao = dados.get('id_avaliacao')
        modelo_usado = dados.get('modelo_usado', '')
        questoes = dados.get('questoes') or []
        
        if not id_aluno or not id_avaliacao:
            return jsonify({"sucesso": False, "erro": "Envie id_aluno e id_avaliacao"}), 400
        
        if not questoes:
            return jsonify({"sucesso": False, "erro": "Envie 'questoes' (lista)"}), 400
        
        # Deleta registros anteriores (pra evitar duplicatas)
        supabase.table("correcoes_dissertativas_detalhadas").delete() \
            .eq("id_aluno", id_aluno) \
            .eq("id_avaliacao", id_avaliacao) \
            .execute()
        
        # Insere os novos registros
        registros = []
        for q in questoes:
            registros.append({
                "id_aluno": id_aluno,
                "id_avaliacao": id_avaliacao,
                "numero_questao": q.get('numero'),
                "enunciado": q.get('enunciado', ''),
                "transcricao": q.get('transcricao', ''),
                "nota_sugerida_ia": q.get('nota_sugerida_ia'),
                "nota_final": q.get('nota_final'),
                "valor_questao": q.get('valor_questao'),
                "justificativa": q.get('justificativa', ''),
                "revisar": q.get('revisar', False),
                "modelo_usado": modelo_usado
            })
        
        supabase.table("correcoes_dissertativas_detalhadas").insert(registros).execute()
        
        print(f"💾 [DETALHE] {len(registros)} questões salvas (aluno {id_aluno}, prova {id_avaliacao})")
        
        return jsonify({
            "sucesso": True,
            "mensagem": f"{len(registros)} questões salvas com detalhes!",
            "total": len(registros)
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================================
# 📊 NOVA: SALVAR ESTATÍSTICAS DE PRECISÃO (Etapa 3!)
# ==========================================================
@app.route('/api/estatisticas/salvar', methods=['POST'])
def salvar_estatisticas():
    """Salva estatísticas de precisão de uma sessão de correção."""
    try:
        dados = request.get_json() or {}
        registro = {
            "id_avaliacao": dados.get('id_avaliacao'),
            "total_provas": dados.get('total_provas', 0),
            "concordancias": dados.get('concordancias', 0),
            "ajustes_pequenos": dados.get('ajustes_pequenos', 0),
            "ajustes_grandes": dados.get('ajustes_grandes', 0),
            "falhas_ia": dados.get('falhas_ia', 0),
            "tempo_total_minutos": dados.get('tempo_total_minutos', 0)
        }
        
        supabase.table("estatisticas_precisao").insert(registro).execute()
        
        return jsonify({
            "sucesso": True,
            "mensagem": "Estatísticas salvas!"
        })
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/estatisticas/<int:id_avaliacao>', methods=['GET'])
def get_estatisticas(id_avaliacao):
    """Retorna estatísticas de precisão de uma avaliação."""
    try:
        resp = supabase.table("estatisticas_precisao") \
            .select("*") \
            .eq("id_avaliacao", id_avaliacao) \
            .execute()
        return jsonify({"sucesso": True, "estatisticas": resp.data or []})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================================
# 📄 NOVA: RELATÓRIO PDF DO ALUNO (Etapa 2!)
# ==========================================================
@app.route('/api/relatorio/aluno/<int:id_aluno>/<int:id_avaliacao>', methods=['GET'])
def gerar_relatorio_aluno(id_aluno, id_avaliacao):
    """Gera PDF com o feedback detalhado da correção de um aluno."""
    if not PDF_OK:
        return jsonify({"sucesso": False, "erro": "ReportLab não instalado"}), 500
    
    try:
        # Busca os dados do aluno
        r_aluno = supabase.table("alunos").select("*").eq("id", id_aluno).maybe_single().execute()
        if not r_aluno.data:
            return f"<h1>❌ Aluno {id_aluno} não encontrado!</h1>", 404
        aluno = r_aluno.data
        
        # Busca os dados da avaliação
        r_av = supabase.table("avaliacoes").select("*").eq("id", id_avaliacao).maybe_single().execute()
        avaliacao = r_av.data or {"nome": "Avaliação"}
        
        # Busca os detalhes da correção
        r_det = supabase.table("correcoes_dissertativas_detalhadas") \
            .select("*") \
            .eq("id_aluno", id_aluno) \
            .eq("id_avaliacao", id_avaliacao) \
            .order("numero_questao") \
            .execute()
        
        detalhes = r_det.data or []
        
        if not detalhes:
            # Fallback: relatório simples com a nota salva em "resultados"
            r_res = supabase.table("resultados").select("*") \
                .eq("id_aluno", id_aluno) \
                .eq("id_avaliacao", id_avaliacao) \
                .maybe_single().execute()
            if not r_res.data:
                return f"<h1>❌ Nenhuma correção salva para {aluno.get('nome_completo', 'Aluno')}!</h1>", 404
            res = r_res.data
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                                    topMargin=1.5*cm, bottomMargin=1.5*cm)
            styles = getSampleStyleSheet()
            elementos = [
                Paragraph("📝 RELATÓRIO DE DESEMPENHO", styles['Title']),
                Paragraph(f"<b>Aluno(a):</b> {aluno.get('nome_completo', 'Sem nome')}", styles['Normal']),
                Paragraph(f"<b>Avaliação:</b> {avaliacao.get('nome', 'Avaliação')}", styles['Normal']),
                Paragraph(f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M')}", styles['Normal']),
                Spacer(1, 16),
                Paragraph(f"<b>Nota:</b> {float(res.get('nota_bruta') or 0):.1f} de 10,0", styles['Heading3']),
                Paragraph(f"<b>Nível:</b> {res.get('nivel_saeb', '-')}", styles['Normal']),
                Paragraph(f"<b>Devolutiva:</b> {res.get('devolutiva', '-')}", styles['Normal']),
                Spacer(1, 16),
                Paragraph("<i>Observação: esta correção foi salva antes do registro detalhado por questão, "
                          "por isso não há transcrições e justificativas nesta prova.</i>", styles['Normal']),
            ]
            doc.build(elementos)
            buf.seek(0)
            nome_aluno_seguro = ''.join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in aluno.get('nome_completo', 'aluno'))
            timestamp = datetime.now().strftime('%d%m_%H%M')
            resposta = send_file(buf, mimetype='application/pdf', as_attachment=True,
                                 download_name=f'relatorio_{nome_aluno_seguro}_prova{id_avaliacao}_{timestamp}.pdf')
            resposta.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            return resposta
        
        # Monta o PDF
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )
        
        styles = getSampleStyleSheet()
        
        # Estilos customizados
        titulo_style = ParagraphStyle(
            'TituloCustom',
            parent=styles['Title'],
            fontSize=20,
            textColor=HexColor('#4A148C'),
            spaceAfter=12
        )
        
        cabecalho_style = ParagraphStyle(
            'CabecalhoCustom',
            parent=styles['Normal'],
            fontSize=11,
            textColor=HexColor('#333333'),
            spaceAfter=6
        )
        
        questao_style = ParagraphStyle(
            'QuestaoCustom',
            parent=styles['Heading3'],
            fontSize=13,
            textColor=HexColor('#FF6F00'),
            spaceBefore=12,
            spaceAfter=6
        )
        
        corpo_style = ParagraphStyle(
            'CorpoCustom',
            parent=styles['Normal'],
            fontSize=10,
            textColor=black,
            spaceAfter=4,
            leading=14
        )
        
        transcri_style = ParagraphStyle(
            'TranscriCustom',
            parent=styles['Normal'],
            fontSize=10,
            textColor=HexColor('#1A237E'),
            fontStyle='italic',
            spaceAfter=4,
            leading=13
        )
        
        justif_style = ParagraphStyle(
            'JustifCustom',
            parent=styles['Normal'],
            fontSize=10,
            textColor=HexColor('#555555'),
            spaceAfter=8,
            leading=13
        )
        
        elementos = []
        
        # CABEÇALHO
        elementos.append(Paragraph("📝 RELATÓRIO DE CORREÇÃO DISSERTATIVA", titulo_style))
        elementos.append(Paragraph(
            f"<b>Aluno(a):</b> {aluno.get('nome_completo', 'Sem nome')}",
            cabecalho_style
        ))
        elementos.append(Paragraph(
            f"<b>Avaliação:</b> {avaliacao.get('nome', 'Avaliação')}",
            cabecalho_style
        ))
        data_av = avaliacao.get('data_prova', '')
        if data_av:
            elementos.append(Paragraph(f"<b>Data da prova:</b> {data_av}", cabecalho_style))
        elementos.append(Paragraph(
            f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
            cabecalho_style
        ))
        elementos.append(Spacer(1, 12))
        
        # RESUMO DA NOTA
        soma_final = sum(float(d.get('nota_final') or 0) for d in detalhes)
        soma_valor = sum(float(d.get('valor_questao') or 0) for d in detalhes)
        nota_10 = (soma_final * 10 / soma_valor) if soma_valor > 0 else 0
        
        resumo_data = [
            ['📊 RESUMO DA CORREÇÃO', ''],
            ['Total de questões:', str(len(detalhes))],
            ['Nota obtida:', f'{soma_final:.1f} de {soma_valor:.1f}'],
            ['Nota (escala 0-10):', f'{nota_10:.1f}'],
            ['Modelo de IA utilizado:', detalhes[0].get('modelo_usado', '-')],
        ]
        
        tabela_resumo = Table(resumo_data, colWidths=[8*cm, 8*cm])
        tabela_resumo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4A148C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F3E5F5')),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#9C27B0')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elementos.append(tabela_resumo)
        elementos.append(Spacer(1, 20))
        
        # DETALHES POR QUESTÃO
        elementos.append(Paragraph("📋 DETALHES POR QUESTÃO", titulo_style))
        
        for det in detalhes:
            num = det.get('numero_questao', '?')
            nota_s = det.get('nota_sugerida_ia', 0)
            nota_f = det.get('nota_final', 0)
            valor = det.get('valor_questao', 0)
            revisar = det.get('revisar', False)
            
            badge = " ⚠️ (professor ajustou)" if (nota_s != nota_f) else ""
            
            elementos.append(Paragraph(
                f"Questão {num} — Nota: {nota_f}/{valor}{badge}",
                questao_style
            ))
            
            enunciado = det.get('enunciado', '')
            if enunciado:
                elementos.append(Paragraph(f"<b>Enunciado:</b> {enunciado}", corpo_style))
            
            transcri = det.get('transcricao', '')
            if transcri:
                elementos.append(Paragraph(
                    f"<b>✍️ O que o aluno escreveu:</b><br/><i>\"{transcri}\"</i>",
                    transcri_style
                ))
            
            justif = det.get('justificativa', '')
            if justif:
                elementos.append(Paragraph(
                    f"<b>💡 Avaliação:</b> {justif}",
                    justif_style
                ))
            
            if revisar:
                elementos.append(Paragraph(
                    "<b>⚠️ Observação:</b> Raciocínio diferente — professor revisou.",
                    corpo_style
                ))
            
            elementos.append(Spacer(1, 8))
        
        # RODAPÉ
        elementos.append(Spacer(1, 20))
        elementos.append(Paragraph(
            "<i>Este relatório foi gerado automaticamente pelo OMR Sistema 2.0 com apoio de Inteligência Artificial (Gemini) e revisão do professor.</i>",
            ParagraphStyle('Rodape', parent=styles['Normal'], fontSize=9, textColor=HexColor('#777777'), alignment=TA_CENTER)
        ))
        
        doc.build(elementos)
        buf.seek(0)
        
        nome_aluno_seguro = ''.join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in aluno.get('nome_completo', 'aluno'))
        
        timestamp = datetime.now().strftime('%d%m_%H%M')
        nome_arquivo = f'relatorio_{nome_aluno_seguro}_prova{id_avaliacao}_{timestamp}.pdf'
        
        resposta = send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nome_arquivo
        )
        resposta.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resposta.headers['Pragma'] = 'no-cache'
        resposta.headers['Expires'] = '0'
        return resposta
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1>❌ Erro ao gerar relatório: {e}</h1>", 500

# ==========================================================
# 📄 RELATÓRIO PDF DA TURMA (v2 — COMPLETO E PERFEITO!)
# ==========================================================
@app.route('/api/relatorio/turma/<int:id_turma>/<int:id_avaliacao>', methods=['GET'])
def gerar_relatorio_turma(id_turma, id_avaliacao):
    """Gera PDF completo com estatísticas, top 3 e alunos que precisam de atenção."""
    if not PDF_OK:
        return jsonify({"sucesso": False, "erro": "ReportLab não instalado"}), 500
    
    try:
        r_turma = supabase.table("turmas").select("*").eq("id", id_turma).maybe_single().execute()
        if not r_turma.data:
            return f"<h1>❌ Turma {id_turma} não encontrada!</h1>", 404
        turma = r_turma.data
        
        r_av = supabase.table("avaliacoes").select("*").eq("id", id_avaliacao).maybe_single().execute()
        avaliacao = r_av.data or {"nome": "Avaliação"}
        
        r_alunos = supabase.table("alunos").select("*").eq("id_turma", id_turma).order("numero_chamada").execute()
        alunos = r_alunos.data or []
        
        r_res = supabase.table("resultados").select("*").eq("id_avaliacao", id_avaliacao).execute()
        ids_alunos_turma = {a['id'] for a in alunos}
        resultados = {r['id_aluno']: r for r in (r_res.data or []) if r['id_aluno'] in ids_alunos_turma}
        
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
        
        styles = getSampleStyleSheet()
        titulo_style = ParagraphStyle(
            'TituloCustom', parent=styles['Title'],
            fontSize=18, textColor=HexColor('#4A148C'), spaceAfter=12
        )
        subtitulo_style = ParagraphStyle(
            'SubtituloCustom', parent=styles['Heading2'],
            fontSize=14, textColor=HexColor('#FF6F00'),
            spaceBefore=16, spaceAfter=8
        )
        
        elementos = []
        
        # ========== CABEÇALHO ==========
        elementos.append(Paragraph("📊 RELATÓRIO DE DESEMPENHO DA TURMA", titulo_style))
        elementos.append(Paragraph(
            f"<b>Turma:</b> {turma.get('nome')} | <b>Avaliação:</b> {avaliacao.get('nome')}",
            styles['Normal']
        ))
        elementos.append(Paragraph(
            f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
            styles['Normal']
        ))
        elementos.append(Spacer(1, 16))
        
        # ========== LISTA DE ALUNOS ==========
        elementos.append(Paragraph("📋 LISTA DE ALUNOS", subtitulo_style))
        
        dados_tabela = [['Nº', 'Aluno', 'Nota', 'Nível']]
        
        for aluno in alunos:
            res = resultados.get(aluno['id'])
            nota = res.get('nota_bruta', '-') if res else '-'
            nivel = res.get('nivel_saeb', '-') if res else '-'
            
            if isinstance(nota, (int, float)):
                nota = f'{nota:.1f}'
            
            dados_tabela.append([
                str(aluno.get('numero_chamada', '-')),
                aluno.get('nome_completo', 'Sem nome'),
                str(nota),
                str(nivel)
            ])
        
        tabela = Table(dados_tabela, colWidths=[1.5*cm, 10*cm, 2.5*cm, 4*cm])
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4A148C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (3, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#9C27B0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F3E5F5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elementos.append(tabela)
        elementos.append(Spacer(1, 16))
        
        # ========== ESTATÍSTICAS GERAIS ==========
        total_alunos_turma = len(alunos)
        notas = [r.get('nota_bruta', 0) for r in resultados.values() if r.get('nota_bruta') is not None]
        alunos_que_fizeram = len(notas)
        alunos_que_faltaram = total_alunos_turma - alunos_que_fizeram
        percentual_participacao = (alunos_que_fizeram / total_alunos_turma * 100) if total_alunos_turma > 0 else 0
        
        elementos.append(Paragraph("📈 ESTATÍSTICAS GERAIS", subtitulo_style))
        
        stats_data = [
            ['Total de alunos na turma:', str(total_alunos_turma)],
            ['✅ Alunos que FIZERAM a prova:', str(alunos_que_fizeram)],
            ['❌ Alunos que NÃO fizeram:', str(alunos_que_faltaram)],
            ['📊 Percentual de participação:', f'{percentual_participacao:.1f}%'],
        ]
        
        if notas:
            media = sum(notas) / len(notas)
            maior = max(notas)
            menor = min(notas)
            stats_data.extend([
                ['Média da turma:', f'{media:.2f}'],
                ['Maior nota:', f'{maior:.2f}'],
                ['Menor nota:', f'{menor:.2f}'],
            ])
        
        tabela_stats = Table(stats_data, colWidths=[8*cm, 5*cm])
        tabela_stats.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFF3E0')),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#FF6F00')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elementos.append(tabela_stats)
        
        if notas:
            # ========== DISTRIBUIÇÃO DE NOTAS (GRÁFICO VISUAL) ==========
            elementos.append(Spacer(1, 16))
            elementos.append(Paragraph("📊 DISTRIBUIÇÃO DE NOTAS", subtitulo_style))
            
            # Classifica cada aluno numa faixa
            avancado = [n for n in notas if n >= 8]
            adequado = [n for n in notas if 6 <= n < 8]
            basico = [n for n in notas if 4 <= n < 6]
            abaixo = [n for n in notas if n < 4]
            
            max_count = max(len(avancado), len(adequado), len(basico), len(abaixo)) or 1
            
            def barra(count, cor):
                """Gera uma 'barra' visual com blocos coloridos."""
                bloco_count = int((count / max_count) * 15) or (1 if count > 0 else 0)
                return Paragraph(
                    f'<font color="{cor}">{"█" * bloco_count}</font> {count}',
                    ParagraphStyle('Barra', parent=styles['Normal'], fontSize=12)
                )
            
            dist_data = [
                ['Faixa de nota', 'Nível', 'Alunos', 'Distribuição'],
                ['8 a 10', 'Avançado', str(len(avancado)), barra(len(avancado), '#2E7D32')],
                ['6 a 8', 'Adequado', str(len(adequado)), barra(len(adequado), '#388E3C')],
                ['4 a 6', 'Básico', str(len(basico)), barra(len(basico), '#F57C00')],
                ['0 a 4', 'Abaixo do Básico', str(len(abaixo)), barra(len(abaixo), '#C62828')],
            ]
            
            tabela_dist = Table(dist_data, colWidths=[3*cm, 4*cm, 2*cm, 8*cm])
            tabela_dist.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4A148C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (2, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#9C27B0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F3E5F5')]),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elementos.append(tabela_dist)
            
            # ========== TOP 3 MELHORES ALUNOS ==========
            elementos.append(Spacer(1, 16))
            elementos.append(Paragraph("🏆 TOP 3 MELHORES NOTAS", subtitulo_style))
            
            # Ordena resultados por nota (decrescente)
            ranking = []
            for aluno in alunos:
                res = resultados.get(aluno['id'])
                if res and res.get('nota_bruta') is not None:
                    ranking.append({
                        'nome': aluno.get('nome_completo', 'Aluno'),
                        'nota': float(res.get('nota_bruta', 0)),
                        'num': aluno.get('numero_chamada', '-')
                    })
            ranking.sort(key=lambda x: x['nota'], reverse=True)
            top3 = ranking[:3]
            
            medalhas = ['🥇', '🥈', '🥉']
            top_data = [['Posição', 'Aluno', 'Nota']]
            for i, aluno in enumerate(top3):
                top_data.append([
                    f'{medalhas[i]} {i+1}º lugar',
                    aluno['nome'],
                    f'{aluno["nota"]:.2f}'
                ])
            
            tabela_top = Table(top_data, colWidths=[3.5*cm, 10.5*cm, 3*cm])
            tabela_top.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#FFD700')),
                ('TEXTCOLOR', (0, 0), (-1, 0), black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#FFA000')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFF9C4'), white]),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elementos.append(tabela_top)
            
            # ========== ALUNOS QUE PRECISAM DE ATENÇÃO ==========
            alunos_atencao = []
            for aluno in alunos:
                res = resultados.get(aluno['id'])
                if res and res.get('nota_bruta') is not None:
                    nota = float(res.get('nota_bruta', 0))
                    if nota < 4:
                        alunos_atencao.append({
                            'nome': aluno.get('nome_completo', 'Aluno'),
                            'nota': nota,
                            'nivel': res.get('nivel_saeb', 'Abaixo do Básico')
                        })
            
            if alunos_atencao:
                alunos_atencao.sort(key=lambda x: x['nota'])
                
                elementos.append(Spacer(1, 16))
                elementos.append(Paragraph(
                    f"⚠️ ALUNOS QUE PRECISAM DE ATENÇÃO ({len(alunos_atencao)})",
                    subtitulo_style
                ))
                
                atencao_data = [['Aluno', 'Nota', 'Nível']]
                for a in alunos_atencao:
                    atencao_data.append([
                        a['nome'],
                        f'{a["nota"]:.2f}',
                        a['nivel']
                    ])
                
                tabela_atencao = Table(atencao_data, colWidths=[10*cm, 3*cm, 4*cm])
                tabela_atencao.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#C62828')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('ALIGN', (1, 0), (2, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#EF5350')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFEBEE'), white]),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                elementos.append(tabela_atencao)
                
                elementos.append(Spacer(1, 8))
                elementos.append(Paragraph(
                    "<i>💡 Sugestão: Agendar atendimento individualizado e reforço específico para estes alunos.</i>",
                    ParagraphStyle('Sugestao', parent=styles['Normal'], fontSize=9,
                                   textColor=HexColor('#555555'), alignment=TA_LEFT)
                ))
        
        # ========== RODAPÉ ==========
        elementos.append(Spacer(1, 20))
        elementos.append(Paragraph(
            "<i>Este relatório foi gerado automaticamente pelo OMR Sistema 2.0.</i>",
            ParagraphStyle('Rodape', parent=styles['Normal'], fontSize=9,
                           textColor=HexColor('#777777'), alignment=TA_CENTER)
        ))
        
        doc.build(elementos)
        buf.seek(0)
        
        nome_turma_seguro = ''.join(
            c if c.isalnum() or c in (' ', '_', '-') else '_'
            for c in turma.get('nome', 'turma')
        )
        
        timestamp = datetime.now().strftime('%d%m_%H%M')
        nome_arquivo = f'relatorio_turma_{nome_turma_seguro}_prova{id_avaliacao}_{timestamp}.pdf'
        
        resposta = send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nome_arquivo
        )
        resposta.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resposta.headers['Pragma'] = 'no-cache'
        resposta.headers['Expires'] = '0'
        return resposta
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"<h1>❌ Erro ao gerar relatório: {e}</h1>", 500

# ==========================================================
# 🧠 SITUAÇÃO 1: GERAR QUESTÕES E IDENTIFICAR HABILIDADES
# ==========================================================
def _gemini_chamar(payload):
    """Chama o Gemini com a matriz anti-cota. Retorna (texto, modelo, chave) ou (None, erro)."""
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
                ultimo_erro = f"Chave {i+1}/{modelo}: 429"
                continue
            if resp.status_code != 200:
                ultimo_erro = f"Chave {i+1}/{modelo}: {resp.status_code}"
                continue
            saida = resp.json()
            texto = saida["candidates"][0]["content"]["parts"][0]["text"]
            return texto, modelo, i + 1
    return None, ultimo_erro


def _extrair_json_array(texto):
    """Extrai um array JSON mesmo se a IA vier com texto extra."""
    t = (texto or '').strip()
    i = t.find('[')
    f = t.rfind(']')
    if i == -1 or f == -1 or f <= i:
        return []
    try:
        arr = jsonlib.loads(t[i:f + 1])
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


@app.route('/api/matriz', methods=['GET'])
def listar_matriz():
    """Lista habilidades/descritores pra preencher os menus do app."""
    fonte = request.args.get('fonte', 'CP')
    componente = request.args.get('componente', 'Matemática')
    ano = request.args.get('ano', type=int)
    try:
        q = supabase.table("matriz_curricular").select("*") \
            .eq("fonte", fonte).eq("componente", componente)
        if ano:
            q = q.eq("ano", ano)
        resp = q.order("codigo").execute()
        return jsonify({"sucesso": True, "itens": resp.data or []})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/gerar_questoes', methods=['POST'])
def gerar_questoes():
    """✨ IA cria questões dissertativas alinhadas à habilidade/descritor escolhido."""
    try:
        dados = request.get_json() or {}
        codigos = dados.get('codigos') or []
        fonte = dados.get('fonte', 'CP')
        componente = dados.get('componente', 'Matemática')
        ano = dados.get('ano', 6)
        quantidade = max(1, min(5, int(dados.get('quantidade', 1))))
        dificuldade = dados.get('dificuldade', 'média')
        contexto = (dados.get('contexto') or '').strip()
        valor_padrao = float(dados.get('valor_padrao', 2.0))

        if not codigos:
            return jsonify({"sucesso": False, "erro": "Escolha ao menos uma habilidade/descritor"}), 400

        # Busca as descrições oficiais na matriz
        resp = supabase.table("matriz_curricular").select("*") \
            .in_("codigo", codigos).eq("fonte", fonte).execute()
        itens = resp.data or []
        if not itens:
            return jsonify({"sucesso": False, "erro": "Códigos não encontrados na matriz"}), 404

        lista = "\n".join(f"- {it['codigo']} ({it['tema']}): {it['descricao']}" for it in itens)

        ctx = f"\nContexto pedido pelo professor: {contexto}" if contexto else ""
        prompt = (
            f"Você é um professor especialista em {componente} do {ano}º ano do Ensino Fundamental, "
            f"alinhado ao Currículo Paulista e às matrizes de referência do SAEB.\n"
            f"Crie {quantidade} questão(ões) dissertativa(s) INÉDITA(s) e contextualizadas para CADA habilidade/descritor da lista abaixo.\n"
            f"Dificuldade: {dificuldade}.{ctx}\n"
            f"Regras obrigatórias:\n"
            f"- Enunciado claro, com todos os dados necessários e uma demanda principal única.\n"
            f"- Linguagem adequada a estudantes do {ano}º ano.\n"
            f"- Resposta esperada completa, mostrando o raciocínio/cálculos.\n"
            f"- Critérios de correção explicando o que vale nota parcial.\n"
            f"HABILIDADES/DESCRITORES:\n{lista}\n\n"
            f"Responda SOMENTE um array JSON válido no formato:\n"
            f'[{{"codigo":"...","enunciado":"...","resposta_esperada":"...","criterios":"...","valor":{valor_padrao}}}]'
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json"},
        }
        texto, modelo, chave = _gemini_chamar(payload)
        if texto is None:
            return jsonify({"sucesso": False, "erro": f"Sem cota em todas as chaves: {chave}"}), 429

        questoes = _extrair_json_array(texto)
        if not questoes:
            return jsonify({"sucesso": False, "erro": "A IA não retornou questões válidas"}), 502

        print(f"✨ [GERAR] {len(questoes)} questão(ões) criadas com {modelo} (chave {chave})")
        return jsonify({
            "sucesso": True,
            "questoes": questoes,
            "modelo": modelo,
            "chave_usada": chave,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500


@app.route('/api/identificar_habilidade', methods=['POST'])
def identificar_habilidade():
    """🔍 IA diz qual habilidade/descritor uma questão existente avalia."""
    try:
        dados = request.get_json() or {}
        texto = (dados.get('texto') or '').strip()
        fonte = dados.get('fonte', 'CP')
        componente = dados.get('componente', 'Matemática')
        ano = dados.get('ano', 6)

        if not texto:
            return jsonify({"sucesso": False, "erro": "Cole o texto da questão"}), 400

        resp = supabase.table("matriz_curricular").select("*") \
            .eq("fonte", fonte).eq("componente", componente).eq("ano", ano) \
            .order("codigo").execute()
        itens = resp.data or []
        if not itens:
            return jsonify({"sucesso": False, "erro": "Matriz vazia para essa fonte/ano"}), 404

        lista = "\n".join(f"{it['codigo']}) {it['descricao']}" for it in itens)
        prompt = (
            f"Você é um especialista em avaliação educacional ({componente}, {ano}º ano, matriz {fonte}).\n"
            f"Leia a QUESTÃO do professor e indique os até 3 códigos da matriz que MELHOR correspondem ao que ela exige, "
            f"do mais aderente para o menos aderente.\n"
            f"MATRIZ:\n{lista}\n\nQUESTÃO:\n{texto}\n\n"
            f'Responda SOMENTE um array JSON válido no formato:\n'
            f'[{{"codigo":"...","aderencia":95,"justificativa":"..."}}]'
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        texto_resp, modelo, chave = _gemini_chamar(payload)
        if texto_resp is None:
            return jsonify({"sucesso": False, "erro": f"Sem cota em todas as chaves: {chave}"}), 429

        resultados = _extrair_json_array(texto_resp)
        if not resultados:
            return jsonify({"sucesso": False, "erro": "A IA não retornou análise válida"}), 502

        print(f"🔍 [IDENTIFICAR] análise concluída com {modelo} (chave {chave})")
        return jsonify({"sucesso": True, "resultados": resultados, "modelo": modelo})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

# ==========================================================
# 🏁 INICIALIZAÇÃO DO SERVIDOR
# ==========================================================
if __name__ == '__main__':
    print("🚨🚨🚨 OMR SISTEMA 2.0 - BACKEND COMPLETO 🚨🚨🚨")
    print(f"🔗 Supabase URL: {SUPABASE_URL}")
    print(f"🔑 Gemini chaves: {len(GEMINI_CHAVES)} configurada(s)")
    print(f"🤖 Gemini modelos: {GEMINI_MODELOS}")
    print(f"📄 Relatórios PDF: {'✅ ATIVOS' if PDF_OK else '❌ INATIVOS (instalar reportlab)'}")
    port = int(os.environ.get("PORT", 10000))
    print(f"📡 Servidor rodando na porta: {port}")
    app.run(host='0.0.0.0', port=port, debug=False)