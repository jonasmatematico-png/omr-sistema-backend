import google.generativeai as genai
import warnings

# Suprime o warning de descontinuação (não é erro, é só aviso)
warnings.filterwarnings("ignore", category=FutureWarning)

# 🔑 SUAS 10 CHAVES (já estão corretas!)
CHAVES_PARA_TESTAR = [
    "AQ.Ab8RN6IPSl8XwoidxZavojf9OV9MpfGaT5Gc4T7rcCW3-4o7Bw",
    "AQ.Ab8RN6JWZx9y0HosgZ0p-nRsZ8CWrPjL4A1e6w5tm6Ndumwp2g",
    "AQ.Ab8RN6JWZx9y0HosgZ0p-nRsZ8CWrPjL4A1e6w5tm6Ndumwp2g",
    "AQ.Ab8RN6IPSl8XwoidxZavojf9OV9MpfGaT5Gc4T7rcCW3-4o7Bw",
    "AQ.Ab8RN6KmTI5OrZTv2tBqZUQMFx8k6-Y6kaMOCdDzInsvlOfBlA",
    "AQ.Ab8RN6JaF2h7RsteZsHbFyqdfkU1oG04aHQq_3DGdteSoDSvoA",
    "AQ.Ab8RN6Kpp2CvKLiLkVmV2iMWIENVgdJL8_Z1DOjUbcs6ICYKVA",
    "AQ.Ab8RN6JEqDV5pZEjFAEb2c4PQPDBXuqK3tIY9O-0ly8TslGxmQ",
    "AQ.Ab8RN6KYdJSvLmLZl-xSPTJJ90e4lunJhRhAM0j9cizUa7qQUQ",
    "AQ.Ab8RN6J17Pjwj8uw9mIxqUgpWxkY86XEAAH1iksul6q7Eacm1Q",
]

# Modelos atuais do Gemini (2026) - testamos todos
MODELOS_PARA_TESTAR = [
    "gemini-2.5-flash",   # Mais novo e rápido
    "gemini-2.0-flash",   # Modelo estável
    "gemini-1.5-flash",   # Antigo (pode não existir)
]

print("🚀 INICIANDO TESTE DAS 10 CHAVES GEMINI (Versão 2026)...\n")
print("=" * 70)

chaves_validas = []
chaves_com_cota = []

for i, chave in enumerate(CHAVES_PARA_TESTAR, 1):
    print(f"\n🔑 Testando chave {i}/10: {chave[:15]}...")
    
    modelo_funcionou = None
    
    for modelo_nome in MODELOS_PARA_TESTAR:
        try:
            genai.configure(api_key=chave)
            model = genai.GenerativeModel(modelo_nome)
            
            # Faz uma requisição mínima
            resposta = model.generate_content("Responda apenas: OK")
            
            if "OK" in resposta.text:
                print(f"   ✅ ATIVA com modelo: {modelo_nome}")
                modelo_funcionou = modelo_nome
                chaves_validas.append(chave)
                chaves_com_cota.append(chave)
                break
                
        except Exception as e:
            erro_str = str(e).lower()
            if '404' in erro_str or 'not found' in erro_str:
                continue  # Modelo não existe, tenta o próximo
            elif '429' in erro_str or 'quota' in erro_str or 'exhausted' in erro_str:
                print(f"   ⏰ ATIVA, mas COTA EXCEDIDA hoje (modelo {modelo_nome})")
                chaves_validas.append(chave)
                break
            elif '403' in erro_str or 'permission' in erro_str:
                print(f"   ❌ PERMISSÃO NEGADA (chave inválida)")
                break
            else:
                print(f"   ⚠️ Erro: {str(e)[:80]}")
                continue
    
    if not modelo_funcionou and chave not in chaves_validas:
        print(f"   ❌ Nenhum modelo funcionou com esta chave")

# ========================================================================
# 📊 RELATÓRIO FINAL
# ========================================================================
print("\n" + "=" * 70)
print("📊 RELATÓRIO FINAL")
print("=" * 70)
print(f"✅ Chaves VÁLIDAS e com cota: {len(chaves_com_cota)}/10")
print(f"⚠️  Chaves VÁLIDAS (cota excedida): {len(chaves_validas) - len(chaves_com_cota)}/10")
print(f"❌ Chaves INVÁLIDAS: {10 - len(chaves_validas)}/10")

if chaves_com_cota:
    print("\n🎯 CHAVES PRONTAS PARA USO NO RENDER:")
    for i, chave in enumerate(chaves_com_cota, 1):
        print(f"   GEMINI_API_KEY_{i} = {chave}")