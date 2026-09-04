# services/omr.py
# OMR 4.5 - RAIO-X: log com coordenadas de cada bolinha + proteção anti-travamento

import cv2
import numpy as np
import os
import traceback
import itertools

TAM_NORM = (1000, 470)

COLUNAS_X = [76, 337, 570, 833]
DX_APROX = 37
Y0 = 90
DY = 47.7
N_COLS = [7, 7, 7, 5]

MEIA_ALTURA = 16
JANELA = 10
LIMIAR_BRILHO = 200

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
            print(f"🔍 QR detectado! Tamanho: {w_qr}x{h_qr} | Conteúdo: '{data}'")
            x_min = int(max(0, np.min(pts[:, 0]) - 30))
            y_min = int(max(0, np.min(pts[:, 1]) - 30))
            x_max = int(min(w_img, np.max(pts[:, 0]) + 30))
            y_max = int(min(h_img, np.max(pts[:, 1]) + 30))
            cv2.rectangle(image, (x_min, y_min), (x_max, y_max), (255, 255, 255), -1)
            print("✅ QR escondido!")
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

    # 🛡️ ANTI-QR: escolhe os 4 candidatos que formam o MAIOR quadrilátero
    # (os marcadores verdadeiros estão nos cantos extremos da folha;
    #  qualquer pedaço de QR que escapar forma um quadrilátero menor)
    candidatos.sort(key=lambda c: c[0], reverse=True)
    top = candidatos[:8]
    melhor_combo = None
    melhor_area = -1
    for combo in itertools.combinations(top, 4):
        pts = np.array([c[1] for c in combo], dtype="float32")
        ord_pts = ordem_pontos(pts)
        area = cv2.contourArea(ord_pts.astype(np.int32))
        if area > melhor_area:
            melhor_area = area
            melhor_combo = ord_pts
    ordered = melhor_combo

    for i, pt in enumerate(ordered):
        cv2.circle(debug_img, (int(pt[0]), int(pt[1])), 14, (0, 255, 0), 3)
        cv2.putText(debug_img, str(i + 1), (int(pt[0]) + 18, int(pt[1]) + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imwrite(os.path.join(upload_dir, 'debug_marcadores.jpg'), debug_img)
    return ordered

def ler_linha(gray, col_x, y, debug_img, qnum):
    """RAIO-X: nunca trava; imprime no log tudo o que encontra."""
    try:
        h, w = gray.shape
        x0 = max(0, int(col_x - 30))
        x1 = min(w, int(col_x + 3 * DX_APROX + 30))
        y0 = max(0, int(y - MEIA_ALTURA))
        y1 = min(h, int(y + MEIA_ALTURA))
        strip = gray[y0:y1, x0:x1]

        blurred = cv2.GaussianBlur(strip, (3, 3), 0)
        _, th = cv2.threshold(blurred, 140, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bolhas = []
        for c in contours:
            x, yb, bw, bh = cv2.boundingRect(c)
            if 10 <= bw <= 30 and 10 <= bh <= 26 and 0.6 <= bw / float(bh) <= 1.4:
                cx = x + bw / 2 + x0   # coordenada ABSOLUTA na imagem
                interior = strip[yb + bh // 4: yb + 3 * bh // 4,
                                 x + bw // 4: x + 3 * bw // 4]
                m = float(np.mean(interior)) if interior.size else 255.0
                bolhas.append([cx, m])

        bolhas.sort(key=lambda b: b[0])

        clusters = []
        for cx, m in bolhas:
            if clusters and abs(cx - clusters[-1][0]) < 12:
                clusters[-1][0] = (clusters[-1][0] + cx) / 2
                clusters[-1][1] = min(clusters[-1][1], m)
            else:
                clusters.append([cx, m])

        for cx, m in clusters:
            cv2.circle(debug_img, (int(cx), int(y)), 12, (0, 255, 255), 1)

        #  RAIO-X no log: onde achou bolinhas e quão escuras são
        print(f"   🔬 Q{qnum}: {len(clusters)} bolinhas em x={[int(c[0]) for c in clusters]} brilhos={[round(c[1]) for c in clusters]}")

        if len(clusters) == 4:
            melhor = min(range(4), key=lambda i: clusters[i][1])
            menor = clusters[melhor][1]
            pos_x = clusters[melhor][0]
            if menor < LIMIAR_BRILHO:
                return ['A', 'B', 'C', 'D'][melhor], pos_x, menor, len(clusters)
            return '', pos_x, menor, len(clusters)

        # fallback: janelas fixas
        brilhos = []
        for i in range(4):
            bx = int(col_x + i * DX_APROX)
            win = gray[int(y) - JANELA: int(y) + JANELA, bx - JANELA: bx + JANELA]
            brilhos.append(float(np.mean(win)) if win.size else 255.0)
        print(f"   🔬 Q{qnum} fallback brilhos={[round(b) for b in brilhos]}")
        melhor = int(np.argmin(brilhos))
        menor = brilhos[melhor]
        pos_x = col_x + melhor * DX_APROX
        if menor < LIMIAR_BRILHO:
            return ['A', 'B', 'C', 'D'][melhor], pos_x, menor, len(clusters)
        return '', pos_x, menor, len(clusters)

    except Exception as e:
        print(f"   ⚠️ Q{qnum}: erro interno na leitura: {e}")
        return '', col_x, 255.0, 0

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
        print(f"🚨 OMR 4.5 — MODO RAIO-X — lendo {n_q} 🚨🚨")

        corrigir_orientacao(caminho_imagem)

        image = cv2.imread(caminho_imagem)
        if image is None:
            raise Exception("Não conseguiu ler o arquivo de imagem.")

        esconder_qr_code(image, upload_dir)

        h_orig, w_orig = image.shape[:2]
        print(f"📐 Tamanho original: {w_orig}x{h_orig}")

        if w_orig < 1200:
            print("⚠️ FOTO PEQUENA DEMAIS! Aproxime o celular da folha.")

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
        for xa, n in zip(COLUNAS_X, N_COLS):
            for r in range(n):
                posicoes.append((xa, Y0 + r * DY))

        gray_norm = cv2.cvtColor(norm, cv2.COLOR_BGR2GRAY)
        debug_img = norm.copy()
        respostas = []

        for q in range(n_q):
            cx, cy = posicoes[q]
            resp, pos_x, brilho, n_bolhas = ler_linha(gray_norm, cx, cy, debug_img, q + 1)
            respostas.append(resp)

            if resp:
                cv2.circle(debug_img, (int(pos_x), int(cy)), JANELA + 2, (0, 255, 0), 2)
                print(f"   ✅ Q{q+1}: '{resp}' (brilho: {round(brilho,1)})")
            else:
                print(f"   ⚠️ Q{q+1}: Não detectado (brilho: {round(brilho,1)})")

        cv2.imwrite(os.path.join(upload_dir, 'debug_leitura_final.jpg'), debug_img)
        print("📸 debug_leitura_final.jpg salva")

        while len(respostas) < len(gabarito_esperado):
            respostas.append('')
        return respostas[:len(gabarito_esperado)]

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO:")
        traceback.print_exc()
        return [''] * len(gabarito_esperado)