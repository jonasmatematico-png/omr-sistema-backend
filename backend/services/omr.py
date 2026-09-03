# services/omr.py
# OMR Sistema 3.0 - Gabarito oficial 26 questões (4 colunas 7/7/7/5)
# Detecção pelos 4 marcadores de canto + perspectiva normalizada

import cv2
import numpy as np
import os
import traceback

# Tamanho do espaço normalizado (entre os 4 marcadores)
TAM_NORM = (1000, 470)

# ── CALIBRAÇÃO (no espaço normalizado 1000x470) ──
COLUNAS_X = [76, 337, 599, 833]   # centro da bolinha A de cada coluna
DX_BOLINHA = 37                   # distância entre centros A-B-C-D
Y0 = 90                           # centro da 1ª linha
DY_LINHA = 47.6                   # distância entre linhas
QUESTOES_POR_COLUNA = [7, 7, 7, 5]

JANELA = 14           # meia-janela de leitura (miolo da bolinha)
LIMIAR_BRILHO = 200   # abaixo disso = bolinha pintada

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
    """Detecta o QR e pinta de branco (com proteção anti-alucinação)."""
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
            contrast = clahe.apply(gray2)
            data, bbox, _ = detector.detectAndDecode(contrast)

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
            print(f"✅ QR escondido! Região: ({x_min},{y_min}) até ({x_max},{y_max})")
            return True
        else:
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
            orientation = exif[274]
            print(f"📷 Orientação EXIF: {orientation}")
            if orientation == 3:
                pil_img = pil_img.rotate(180, expand=True)
            elif orientation == 6:
                pil_img = pil_img.rotate(270, expand=True)
            elif orientation == 8:
                pil_img = pil_img.rotate(90, expand=True)
            pil_img.save(caminho_imagem)
            print("✅ Orientação corrigida!")
    except Exception as e:
        print(f"⚠️ Não foi possível corrigir orientação: {e}")

def detectar_marcadores(image):
    """Acha os 4 quadrados pretos dos cantos."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 60, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidatos = []
    for c in contours:
        area = cv2.contourArea(c)
        x, y, w, h = cv2.boundingRect(c)
        aspect = w / float(h) if h > 0 else 0
        solidez = area / (w * h) if w * h > 0 else 0

        # quadrado sólido, bem preto, tamanho plausível
        if 150 < area < 8000 and 0.6 < aspect < 1.4 and solidez > 0.8:
            candidatos.append((area, (x + w / 2, y + h / 2)))

    print(f"⬛ Candidatos a marcador: {len(candidatos)}")

    if len(candidatos) < 4:
        return None

    candidatos.sort(key=lambda c: c[0], reverse=True)
    pts = np.array([c[1] for c in candidatos[:4]], dtype="float32")
    return ordem_pontos(pts)

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
        print(f"🚨 OMR 3.0 — GABARITO 26 QUESTÕES (4 COLUNAS) — lendo {n_q} 🚨")

        # ETAPA 0: orientação
        corrigir_orientacao(caminho_imagem)

        # ETAPA 1: carregar
        image = cv2.imread(caminho_imagem)
        if image is None:
            raise Exception("Não conseguiu ler o arquivo de imagem.")

        # ETAPA 2: esconder QR
        esconder_qr_code(image, upload_dir)

        # ETAPA 3: limitar tamanho
        h_orig, w_orig = image.shape[:2]
        print(f"📐 Tamanho original: {w_orig}x{h_orig}")
        MAX_LARGURA = 1600
        if w_orig > MAX_LARGURA:
            escala = MAX_LARGURA / w_orig
            image = cv2.resize(image, (int(w_orig * escala), int(h_orig * escala)))
            print(f"📐 Redimensionado para: {image.shape[1]}x{image.shape[0]}")

        # ETAPA 4: marcadores de canto
        marcadores = detectar_marcadores(image)
        if marcadores is None:
            print("❌ Não achou os 4 marcadores de canto!")
            return [''] * len(gabarito_esperado)

        print("✅ 4 marcadores encontrados! Normalizando...")

        dst = np.array([
            [0, 0],
            [TAM_NORM[0] - 1, 0],
            [TAM_NORM[0] - 1, TAM_NORM[1] - 1],
            [0, TAM_NORM[1] - 1]
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(marcadores, dst)
        norm = cv2.warpPerspective(image, M, TAM_NORM)

        cv2.imwrite(os.path.join(upload_dir, 'debug_planificada.jpg'), norm)
        print("📸 debug_planificada.jpg salva")

        # ETAPA 5: posições das 26 questões (na ordem 1..26)
        posicoes = []
        for xa, nq_col in zip(COLUNAS_X, QUESTOES_POR_COLUNA):
            for r in range(nq_col):
                posicoes.append((xa, Y0 + r * DY_LINHA))

        # ETAPA 6: leitura
        gray_norm = cv2.cvtColor(norm, cv2.COLOR_BGR2GRAY)
        debug_img = norm.copy()
        respostas = []
        alternativas_map = ['A', 'B', 'C', 'D']

        for q in range(n_q):
            cx, cy = posicoes[q]
            brilhos = []
            for i in range(4):
                bx = int(cx + i * DX_BOLINHA)
                by = int(cy)
                miolo = gray_norm[by - JANELA: by + JANELA, bx - JANELA: bx + JANELA]
                brilho = float(np.mean(miolo)) if miolo.size > 0 else 255.0
                brilhos.append(brilho)
                cv2.circle(debug_img, (bx, by), JANELA, (255, 0, 0), 1)

            melhor = int(np.argmin(brilhos))
            menor_brilho = brilhos[melhor]

            if menor_brilho < LIMIAR_BRILHO:
                resp = alternativas_map[melhor]
                respostas.append(resp)
                cv2.circle(debug_img, (int(cx + melhor * DX_BOLINHA), int(cy)), JANELA, (0, 255, 0), 2)
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