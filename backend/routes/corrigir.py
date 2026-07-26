# routes/corrigir.py
# Versão 2.1 - Aceita 'image'/'foto' + Gabarito Dinâmico vindo do Celular

import os
import base64
import tempfile
import json
from flask import Blueprint, request, jsonify
from services.omr import processar_imagem

corrigir_bp = Blueprint('corrigir', __name__)

@corrigir_bp.route('/corrigir', methods=['POST'])
def corrigir():
    print("\n--- 📷 [corrigir.py] RECEBENDO FOTO DO CELULAR PARA LEITURA OMR ---")
    
    foto_path = None
    dados_aluno = {}

    try:
        # 🔹 1. Aceita JSON com Base64
        if request.is_json:
            payload = request.get_json()
            base64_str = payload.get('fotoBase64', '')
            if not base64_str:
                return jsonify({'erro': 'Base64 da foto não enviado.'}), 400
            
            img_data = base64.b64decode(base64_str)
            temp_fd, foto_path = tempfile.mkstemp(suffix='.jpg')
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(img_data)
            print("✅ Foto recebida via Base64.")

        # 🔹 2. Aceita tanto 'foto' quanto 'image' (Compatibilidade total com o Flutter!)
        elif 'foto' in request.files or 'image' in request.files:
            foto = request.files.get('foto') or request.files.get('image')
            if foto.filename == '':
                return jsonify({'erro': 'Nenhum arquivo enviado.'}), 400
            
            temp_fd, foto_path = tempfile.mkstemp(suffix='.jpg')
            foto.save(foto_path)
            print("✅ Foto do gabarito recebida com sucesso via FormData!")
        else:
            return jsonify({'erro': 'Nenhum arquivo de foto recebido.'}), 400

        # 🔹 3. Pega o Gabarito Oficial que o Celular enviou!
        gabarito_recebido = ['A', 'B', 'C', 'D', 'A', 'B', 'C', 'D', 'A', 'B'] # Fallback
        if 'gabarito' in request.form:
            try:
                gabarito_recebido = json.loads(request.form.get('gabarito'))
                print(f"🎯 Gabarito Dinâmico recebido do celular ({len(gabarito_recebido)} questões): {gabarito_recebido}")
            except Exception as e_gab:
                print(f"⚠️ Erro ao ler gabarito dinâmico, usando padrão: {e_gab}")

        # 🔹 4. Processa a imagem no OpenCV com o gabarito real da prova!
        respostas_omr = processar_imagem(foto_path, gabarito_recebido)
        print(f"👁️ Bolinhas lidas pelo OMR.PY: {respostas_omr}")

        # Monta estrutura exata para o celular
        questoes_config = []
        detalhes = []
        for i, resp in enumerate(respostas_omr):
            gab_certo = gabarito_recebido[i] if i < len(gabarito_recebido) else 'A'
            questoes_config.append({"questao": i+1, "gabarito": gab_certo})
            detalhes.append({
                "questao": i+1,
                "correta": (resp == gab_certo) if resp else False,
                "descritor": "",
                "resposta_aluno": resp
            })

        resultado_formatado = {
            "respostas": respostas_omr,
            "questoesConfig": questoes_config,
            "detalhes": detalhes,
            "nota": 0.0,
            "nivel": "Em análise"
        }

        return jsonify({'sucesso': True, 'resultado': resultado_formatado}), 200

    except Exception as e:
        print(f"❌ Erro na correção do OMR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'erro': str(e)}), 500
    finally:
        if foto_path and os.path.exists(foto_path):
            try:
                os.remove(foto_path)
            except Exception:
                pass