import csv
from supabase import create_client, Client

# 🔑 Configuração do Supabase
SUPABASE_URL = "https://mkqnaiuplkqiitwxltli.supabase.co"
SUPABASE_KEY = "sb_publishable_r-Tqilnqa8Q6iDURFV14rQ_W2wFuZoK"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

cache_turmas = {}

def get_or_create_turma(nome_turma):
    nome_turma = nome_turma.strip()
    if nome_turma in cache_turmas:
        return cache_turmas[nome_turma]

    response = supabase.table("turmas").select("id").eq("nome", nome_turma).execute()
    
    if response.data:
        turma_id = response.data[0]['id']
    else:
        response = supabase.table("turmas").insert({"nome": nome_turma}).execute()
        turma_id = response.data[0]['id']
        print(f"    🏫 Nova turma criada: {nome_turma} (ID: {turma_id})")

    cache_turmas[nome_turma] = turma_id
    return turma_id

def migrar():
    print("🚀 Iniciando migração dos alunos reais do CSV...")
    print(" Lendo arquivo alunos.csv...\n")
    
    with open('alunos.csv', mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        count = 0
        erros = 0
        
        for row in reader:
            nome_turma = row.get('Turma') or row.get('turma') or row.get('TURMA')
            nome_aluno = row.get('Nome') or row.get('nome') or row.get('NOME')

            if not nome_turma or not nome_aluno:
                continue

            nome_aluno = nome_aluno.strip()
            turma_id = get_or_create_turma(nome_turma)

            try:
                supabase.table("alunos").insert({
                    "id_turma": turma_id,
                    "nome_completo": nome_aluno
                }).execute()
                count += 1
                print(f"✅ {nome_aluno} -> {nome_turma}")
            except Exception:
                erros += 1
                
    print(f"\n🎉 MIGRAÇÃO CONCLUÍDA!")
    print(f"📊 Total de alunos processados: {count}")
    if erros > 0:
        print(f"️ Alunos ignorados (provavelmente já existiam): {erros}")

if __name__ == '__main__':
    migrar()