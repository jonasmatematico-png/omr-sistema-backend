# services/omr.py
# OMR Sistema 4.0 - Calibrado para gabarito de 26 questões (7/7/7/5)
# Usa a MESMA régua em mm do seu gabarito impresso

import cv2
import numpy as np
import os
import traceback

TAM_NORM = (1000, 470)

# ══ CALIBRAÇÃO PARA O SEU GABARITO (26 questões, 7/7/7/5) ══
KX = 1000 / 193.0
KY = 470 / 86.5
X0_COLS = [8, 56, 104, 152]
N_COLS  = [7, 7, 7, 5]          # ← 7+7+7+5 = 26 questões!
OFF_MM  = [8, 17, 26, 35]
ROW0_MM, ROWH_MM = 16, 9        # altura da linha ajustada

COLUNAS = [{'x': (x0 + 8) * KX, 'dx': 9 * KX, 'n': n} for x0, n in zip(X0_COLS, N_COLS)]
Y0 = ROW0_MM * KY
DY = ROWH_MM * KY

JANELA = 10
LIMIAR_BRILHO = 200
TOLERANCIA = [-6, -3, 0, 3, 6]

def ordem_pontos(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def esconder_qr_code(image, upload_dir):
    try:
        detector = cv2.QRCodeDetector()
        bbox = None
        data, bbox, _ = detector.detectAndDecode(image)
        if bbox is None:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            data, bbox, _ = detector.detectAndDecode(gray)
        if bbox is None:
            gray2 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            data, bbox, _ = detector.detectAndDecode(clahe.apply(gray2))

        if bbox is not None and len(bbox) > 0:
            pts = bbox.astype(np.int32)
            h_img, w_img = image.shape[:2]
            w_qr = np.max(pts[:, 0]) - np.min(pts[:, 0])
            h_qr = np.max(pts[:, 1]) - np.min(pts[:, 1])
            if w_qr > w_img * 0.25 or h_qr > h_img * 0.35:
                print(f"⚠️ QR GRANDE DEMAIS ({w_qr}x{h_qr}) — ignorando")
                return False
            print(f"🔍 QR detectado! Tamanho: {w_qr}x{h_qr}")
            x_min = int(max(0, np.min(pts[:, 0]) - 30))
            y_min = int(max(0, np.min(pts[:, 1]) - 30))
            x_max = int(min(w_img, np.max(pts[:, 0]) + 30))
            y_max = int(min(h_img, np.max(pts[:, 1]) + 30))
            cv2.rectangle(image, (x_min, y_min), (x_max, y_max), (255, 255, 255), -1)
            print(f"✅ QR escondido!")
            return True
        print("ℹ️ Nenhum QR detectado (seguindo sem esconder)")
        return False
    except Exception as e:
        print(f"⚠️ Erro ao detectar QR: {e}")
        return False

def corrigir_orientacao(caminho_imagem):
    try:
        from PIL import Image as PILImage
        pil_img = PILImage.open(caminho_imagem)
        exif = pil_img._getexif()
        if exif and 274 in exif:
            o = exif[274]
            print(f"📷 Orientação EXIF: {o}")
            if o == 3: pil_img = pil_img.rotate(180, expand=True)
            elif o == 6: pil_img = pil_img.rotate(270, expand=True)
            elif o == 8: pil_img = pil_img.rotate(90, expand=True)
            pil_img.save(caminho_imagem)
            print("✅ Orientação corrigida!")
    except Exception as e:
        print(f"⚠️ Não foi possível corrigir orientação: {e}")

def detectar_marcadores(image, upload_dir):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 80, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidatos = []
    for c in contours:
        area = cv2.contourArea(c)
        x, y, w, h = cv2.boundingRect(c)
        aspect = w / float(h) if h > 0 else 0
        solidez = area / (w * h) if w * h > 0 else 0
        if 100 < area < 12000 and 0.6 < aspect < 1.4 and solidez > 0.7:
            candidatos.append((area, (x + w / 2, y + h / 2)))

    print(f"⬛ Candidatos a marcador: {len(candidatos)}")

    debug_img = image.copy()
    for area, (cx, cy) in candidatos:
        cv2.circle(debug_img, (int(cx), int(cy)), 14, (0, 0, 255), 2)

    if len(candidatos) < 4:
        cv2.imwrite(os.path.join(upload_dir, 'debug_marcadores.jpg'), debug_img)
        return None

    candidatos.sort(key=lambda c: c[0], reverse=True)
    ordered = ordem_pontos(np.array([c[1] for c in candidatos[:4]], dtype="float32"))

    for i, pt in enumerate(ordered):
        cv2.circle(debug_img, (int(pt[0]), int(pt[1])), 14, (0, 255, 0), 3)
        cv2.putText(debug_img, str(i + 1), (int(pt[0]) + 18, int(pt[1]) + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imwrite(os.path.join(upload_dir, 'debug_marcadores.jpg'), debug_img)
    return ordered

def processar_imagem(caminho_imagem, gabarito_esperado):

    upload_dir = '/opt/render/project/src/backend/uploads'
    if not os.path.exists(upload_dir):
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    print(f"📁 Pasta de uploads: {upload_dir}")

    try:
        gabarito_esperado = list(gabarito_esperado)
        n_q = min(len(gabarito_esperado), 26)
        print(f"🚨 OMR 4.0 — GABARITO 26 QUESTÕES (7/7/7/5) — lendo {n_q} 🚨")

        corrigir_orientacao(caminho_imagem)

        image = cv2.imread(caminho_imagem)
        if image is None:
            raise Exception("Não conseguiu ler o arquivo de imagem.")

        esconder_qr_code(image, upload_dir)

        h_orig, w_orig = image.shape[:2]
        print(f"📐 Tamanho original: {w_orig}x{h_orig}")

        if w_orig < 1200:
            print("⚠️ FOTO PEQUENA DEMAIS! Peça pro aluno aproximar o celular.")

        MAX_LARGURA = 1600
        if w_orig > MAX_LARGURA:
            escala = MAX_LARGURA / w_orig
            image = cv2.resize(image, (int(w_orig * escala), int(h_orig * escala)))
            print(f"📐 Redimensionado para: {image.shape[1]}x{image.shape[0]}")

        marcadores = detectar_marcadores(image, upload_dir)
        if marcadores is None:
            print("❌ Não achou os 4 marcadores de canto!")
            cv2.imwrite(os.path.join(upload_dir, 'debug_leitura_final.jpg'), image)
            return [''] * len(gabarito_esperado)

        print("✅ 4 marcadores encontrados! Normalizando...")

        dst = np.array([[0, 0], [999, 0], [999, 469], [0, 469]], dtype="float32")
        M = cv2.getPerspectiveTransform(marcadores, dst)
        norm = cv2.warpPerspective(image, M, TAM_NORM)
        cv2.imwrite(os.path.join(upload_dir, 'debug_planificada.jpg'), norm)

        posicoes = []
        for col in COLUNAS:
            for r in range(col['n']):
                posicoes.append((col['x'], col['dx'], Y0 + r * DY))

        gray_norm = cv2.cvtColor(norm, cv2.COLOR_BGR2GRAY)
        debug_img = norm.copy()
        respostas = []
        alternativas_map = ['A', 'B', 'C', 'D']

        for q in range(n_q):
            cx, dx, cy = posicoes[q]
            brilhos = []
            for i in range(4):
                base_x = cx + i * dx
                melhor_b = 255.0
                for sh in TOLERANCIA:
                    bx, by = int(base_x + sh), int(cy)
                    miolo = gray_norm[by - JANELA: by + JANELA, bx - JANELA: bx + JANELA]
                    if miolo.size > 0:
                        melhor_b = min(melhor_b, float(np.mean(miolo)))
                brilhos.append(melhor_b)
                cv2.circle(debug_img, (int(base_x), int(cy)), JANELA, (255, 0, 0), 1)

            melhor = int(np.argmin(brilhos))
            menor_brilho = brilhos[melhor]

            if menor_brilho < LIMIAR_BRILHO:
                resp = alternativas_map[melhor]
                respostas.append(resp)
                cv2.circle(debug_img, (int(cx + melhor * dx), int(cy)), JANELA + 2, (0, 255, 0), 2)
                print(f"   ✅ Q{q+1}: '{resp}' (brilho: {round(menor_brilho,1)})")
            else:
                respostas.append('')
                print(f"   ⚠️ Q{q+1}: Não detectado (brilho: {round(menor_brilho,1)})")

        cv2.imwrite(os.path.join(upload_dir, 'debug_leitura_final.jpg'), debug_img)
        print("📸 debug_leitura_final.jpg salva")

        while len(respostas) < len(gabarito_esperado):
            respostas.append('')
        return respostas[:len(gabarito_esperado)]

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO:")
        traceback.print_exc()
        return [''] * len(gabarito_esperado)