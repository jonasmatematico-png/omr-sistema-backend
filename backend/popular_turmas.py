import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "credentials.json"

def popular_alunos():
    print("🔌 Conectando ao Google Sheets...")
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        client = gspread.authorize(creds)
        spreadsheet = client.open("OMR Sistema 2.0")
        worksheet = spreadsheet.worksheet("ALUNOS")
    except Exception as e:
        print(f"❌ ERRO: {e}")
        return

    # ⚠️ ATENÇÃO: O número "3" na terceira coluna é o ID_Turma do "6º Ano A" 
    # que criamos no script popular_turmas.py anteriormente!
    dados_para_inserir = [
        ["1", "01 - Ana Clara Silva", "3", "1"],
        ["2", "02 - Bruno Souza Barbosa", "3", "2"],
        ["3", "03 - Carlos Eduardo Santos", "3", "3"],
        ["4", "04 - Daniela Ferreira Alves", "3", "4"],
        ["5", "05 - Elena Gomes Pereira", "3", "5"],
        ["6", "06 - Felipe Oliveira Costa", "3", "6"],
        ["7", "07 - Gabriela Mendes Rocha", "3", "7"],
    ]

    print("📝 Inserindo alunos na aba ALUNOS...")
    worksheet.insert_rows(dados_para_inserir, 2)
    
    print("✅ SUCESSO! 7 alunos foram adicionados à turma 6º Ano A (ID 3).")

if __name__ == "__main__":
    popular_alunos()