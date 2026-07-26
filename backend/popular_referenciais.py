import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DE ACESSO ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "credentials.json"

def popular_referenciais():
    print("🔌 Conectando ao Google Sheets...")
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        client = gspread.authorize(creds)
        spreadsheet = client.open("OMR Sistema 2.0")
        worksheet = spreadsheet.worksheet("REFERENCIAIS")
    except Exception as e:
        print(f"❌ ERRO: {e}")
        return

    # Dados reais de Descritores de Matemática (SAEB - 9º Ano) e Habilidades (BNCC)
    dados_para_inserir = [
        ["1", "DESCRITOR", "D1", "Identificar localização/movimentação de objeto em mapas e croquis.", "9º ano", "Matemática"],
        ["2", "DESCRITOR", "D2", "Identificar propriedades de poliedros e corpos redondos (planificações).", "9º ano", "Matemática"],
        ["3", "DESCRITOR", "D3", "Identificar propriedades de triângulos pela comparação de lados e ângulos.", "9º ano", "Matemática"],
        ["4", "DESCRITOR", "D19", "Resolver problema com números naturais, envolvendo diferentes significados das operações.", "9º ano", "Matemática"],
        ["5", "DESCRITOR", "D24", "Reconhecer as representações decimais dos números racionais como uma extensão do sistema de numeração decimal.", "9º ano", "Matemática"],
        ["6", "HABILIDADE", "EF09MA01", "Reconhecer que, fixada uma unidade, alguns comprimentos são expressos por números irracionais.", "9º ano", "Matemática"],
        ["7", "HABILIDADE", "EF09MA03", "Efetuar cálculos com números reais, inclusive potências com expoentes fracionários.", "9º ano", "Matemática"],
    ]

    print("📝 Inserindo descritores e habilidades na aba REFERENCIAIS...")
    
    # Insere os dados logo após o cabeçalho (linha 2)
    worksheet.insert_rows(dados_para_inserir, 2)
    
    print("✅ SUCESSO! 7 referenciais foram adicionados à sua planilha.")
    print("👉 Abra o Google Sheets e confira a aba 'REFERENCIAIS'!")

if __name__ == "__main__":
    popular_referenciais()