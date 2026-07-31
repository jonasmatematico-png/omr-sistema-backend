# routes/corrigir.py
# Versão 2.2 - Agora SALVA no Supabase (respostas + resultados)

import os
import base64
import tempfile
import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from services.omr import processar_imagem

corrigir_bp = Blueprint('corrigir', __name__)

@corrigir_bp.route('/corrigir', methods=['POST'])
def corrigir():
    # 🔹 IMPORTAÇÃO LOCAL PARA EVITAR ERRO CIRCULAR
    from app import supabase 
    print("🚨🚨🚨 VERSÃO UPSERT CARREGADA COM SUCESSO NO RENDER 🚨🚨🚨")
    print("\n--- 📷 [corrigir.py] RECEBENDO FOTO DO CELULAR PARA LEITURA OMR ---")
    
    foto_path = None
    id_aluno = None
    id_avaliacao = None

    try:
        #  1. Aceita JSON com Base64
        if request.is_json:
            payload = request.get_json()
            base64_str = payload.get('fotoBase64', '')
            if not base64_str:
                return jsonify({'erro': 'Base64 da foto não enviado.'}), 400
            
            # Pega IDs do aluno e avaliação
            id_aluno = payload.get('id_aluno')
            id_avaliacao = payload.get('id_avaliacao')
            
            img_data = base64.b64decode(base64_str)
            temp_fd, foto_path = tempfile.mkstemp(suffix='.jpg')
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(img_data)
            print("✅ Foto recebida via Base64.")

        # 🔹 2. Aceita tanto 'foto' quanto 'image'
        elif 'foto' in request.files or 'image' in request.files:
            foto = request.files.get('foto') or request.files.get('image')
            if foto.filename == '':
                return jsonify({'erro': 'Nenhum arquivo enviado.'}), 400
            
            # Pega IDs do aluno e avaliação
            id_aluno = request.form.get('id_aluno')
            id_avaliacao = request.form.get('id_avaliacao')
            
            temp_fd, foto_path = tempfile.mkstemp(suffix='.jpg')
            foto.save(foto_path)
            print("✅ Foto do gabarito recebida com sucesso via FormData!")
        else:
            return jsonify({'erro': 'Nenhum arquivo de foto recebido.'}), 400

        # 🔹 3. Pega o Gabarito Oficial
        gabarito_recebido = ['A', 'B', 'C', 'D', 'A', 'B', 'C', 'D', 'A', 'B']
        if 'gabarito' in request.form:
            try:
                gabarito_recebido = json.loads(request.form.get('gabarito'))
                print(f"🎯 Gabarito Dinâmico recebido ({len(gabarito_recebido)} questões)")
            except Exception as e_gab:
                print(f"⚠️ Erro ao ler gabarito dinâmico: {e_gab}")

        # 🔹 4. Processa a imagem
        respostas_omr = processar_imagem(foto_path, gabarito_recebido)
        print(f"👁️ Bolinhas lidas pelo OMR.PY: {respostas_omr}")

        # 🔹 5. CALCULA ESTATÍSTICAS
        total_questoes = len(respostas_omr)
        acertos = sum(1 for i, resp in enumerate(respostas_omr) if i < len(gabarito_recebido) and resp == gabarito_recebido[i])
        nota_bruta = acertos
        nota_final = (acertos / total_questoes * 10) if total_questoes > 0 else 0
        
        # Conta por nível (SAEB)
        acertos_basico = 0  # Aqui você ajusta conforme seus descritores
        acertos_intermediarios = 0
        acertos_avancados = 0
        
        # Determina nível SAEB
        if nota_final >= 7:
            nivel_saeb = "Avançado"
        elif nota_final >= 5:
            nivel_saeb = "Adequado"
        else:
            nivel_saeb = "Básico"
        
        porcentual_acertos = (acertos / total_questoes * 100) if total_questoes > 0 else 0

        # 🔹 6. SALVA CADA RESPOSTA NA TABELA 'respostas' (USANDO UPSERT PARA EVITAR DUPLICIDADE)
        print(f"💾 Salvando ou atualizando {total_questoes} respostas na tabela 'respostas'...")
        for i, resp in enumerate(respostas_omr):
            gab_certo = gabarito_recebido[i] if i < len(gabarito_recebido) else 'A'
            
            supabase.table('respostas').upsert({
                'id_avaliacao': id_avaliacao,
                'id_aluno': id_aluno,
                'id_questao': i + 1,
                'resposta_aluno': resp if resp else '',
                'correta': (resp == gab_certo) if resp else False
            }, on_conflict="id_avaliacao,id_aluno,id_questao").execute()
            
        print("✅ Respostas salvas/atualizadas com sucesso!")
        
        # 🔹 7. SALVA RESULTADO FINAL NA TABELA 'resultados'
        print("💾 Salvando resultado final na tabela 'resultados'...")
        supabase.table('resultados').insert({
            'id_avaliacao': id_avaliacao,
            'id_aluno': id_aluno,
            'nota_bruta': nota_bruta,
            'nota_final': round(nota_final, 2),
            'nivel_saeb': nivel_saeb,
            'devolutiva': f"Acertou {acertos} de {total_questoes} questões",
            'acertos_basico': acertos_basico,
            'acertos_intermediarios': acertos_intermediarios,
            'acertos_avancados': acertos_avancados,
            'porcentual_acertos': round(porcentual_acertos, 2),
            'data_correcao': datetime.now().isoformat()
        }).execute()
        print("✅ Resultado final salvo com sucesso!")

        # 🔹 8. Monta resposta para o celular
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
            "nota": round(nota_final, 2),
            "nivel": nivel_saeb,
            "acertos": acertos,
            "total": total_questoes
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