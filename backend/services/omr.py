# services/omr.py
# OMR Sistema 2.0 - Versão estável

import cv2
import numpy as np
import os
import traceback

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s    = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff    = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def corrigir_orientacao(caminho_imagem):
    """
    Corrige a orientação EXIF da foto tirada pelo celular.
    """
    try:
        from PIL import Image as PILImage
        pil_img = PILImage.open(caminho_imagem)
        exif    = pil_img._getexif()

        if exif:
            orientation_key = 274
            if orientation_key in exif:
                orientation = exif[orientation_key]
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

def processar_imagem(caminho_imagem, gabarito_esperado):

    if not os.path.exists('uploads'):
        os.makedirs('uploads')

    try:
                # 🔧 Garante que o gabarito tenha sempre 10 posições (evita break prematuro)
        gabarito_esperado = list(gabarito_esperado) + [''] * (10 - len(gabarito_esperado))
        gabarito_esperado = gabarito_esperado[:10]
        print("🚨🚨🚨 OMR.PY - RECORTE CIRÚRGICO NOS CANTOS EXTERNOS 🚨🚨🚨")

        # ── ETAPA 0: Corrigir orientação EXIF ──
        print("0️⃣ Corrigindo orientação da foto...")
        corrigir_orientacao(caminho_imagem)

        # ── ETAPA 1: Carregar imagem ──
        print("1️⃣ Carregando imagem...")
        image = cv2.imread(caminho_imagem)
        if image is None:
            raise Exception("Não conseguiu ler o arquivo de imagem.")

        # ── ETAPA 2: Redimensionar se muito grande ──
        h_orig, w_orig = image.shape[:2]
        print(f"📐 Tamanho original: {w_orig}x{h_orig}")

        MAX_LARGURA = 1200
        if w_orig > MAX_LARGURA:
            escala       = MAX_LARGURA / w_orig
            nova_largura = int(w_orig * escala)
            nova_altura  = int(h_orig * escala)
            image        = cv2.resize(image, (nova_largura, nova_altura))
            print(f"📐 Redimensionado para: {nova_largura}x{nova_altura}")

        # ── ETAPA 3: Achar marcadores ──
        print("2️⃣ Processando para achar marcadores...")
        gray    = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(
            blurred, 0, 255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        contours, _ = cv2.findContours(
            thresh,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        possible_markers = []
        for c in contours:
            area       = cv2.contourArea(c)
            x, y, w, h = cv2.boundingRect(c)
            aspect     = w / float(h)

            if 200 < area < 50000 and 0.5 < aspect < 1.5:
                possible_markers.append({
                    'area': area,
                    'box':  (x, y, w, h)
                })

        print(f"🔎 Encontrados {len(possible_markers)} possíveis marcadores.")

        imagem_para_ler = image

        # ── ETAPA 4: Planificação ──
        if len(possible_markers) >= 4:
            print("3️⃣ Selecionando os 4 maiores marcadores...")
            possible_markers.sort(key=lambda m: m['area'], reverse=True)
            top_4 = possible_markers[:4]

            centers = []
            for m in top_4:
                x, y, w, h = m['box']
                centers.append([x + w / 2, y + h / 2])

            pts  = np.array(centers, dtype="float32")
            rect = order_points(pts)

            ordered_boxes = []
            for pt in rect:
                min_dist = float('inf')
                best_box = None
                for m in top_4:
                    cx   = m['box'][0] + m['box'][2] / 2
                    cy   = m['box'][1] + m['box'][3] / 2
                    dist = np.sqrt(
                        (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2
                    )
                    if dist < min_dist:
                        min_dist = dist
                        best_box = m['box']
                ordered_boxes.append(best_box)

            tl_x, tl_y, tl_w, tl_h = ordered_boxes[0]
            tr_x, tr_y, tr_w, tr_h = ordered_boxes[1]
            br_x, br_y, br_w, br_h = ordered_boxes[2]
            bl_x, bl_y, bl_w, bl_h = ordered_boxes[3]

            pts_crop = np.array([
                [tl_x,        tl_y        ],
                [tr_x + tr_w, tr_y        ],
                [br_x + br_w, br_y + br_h ],
                [bl_x,        bl_y + bl_h ]
            ], dtype="float32")

            widthA   = np.sqrt(
                ((br_x + br_w - bl_x) ** 2) +
                ((br_y + br_h - bl_y) ** 2)
            )
            widthB   = np.sqrt(
                ((tr_x + tr_w - tl_x) ** 2) +
                ((tr_y - tl_y) ** 2)
            )
            maxWidth = int(max(widthA, widthB))

            heightA   = np.sqrt(
                ((tr_x + tr_w - br_x + br_w) ** 2) +
                ((tr_y - br_y + br_h) ** 2)
            )
            heightB   = np.sqrt(
                ((tl_x - bl_x) ** 2) +
                ((tl_y - bl_y + bl_h) ** 2)
            )
            maxHeight = int(max(heightA, heightB))

            dst = np.array([
                [0,            0            ],
                [maxWidth - 1, 0            ],
                [maxWidth - 1, maxHeight - 1],
                [0,            maxHeight - 1]
            ], dtype="float32")

            print("5️⃣ Aplicando transformação...")
            M      = cv2.getPerspectiveTransform(pts_crop, dst)
            warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

            print("6️⃣ Padronizando tamanho para 800x1000...")
            imagem_para_ler = cv2.resize(warped, (800, 1000))

            cv2.imwrite('uploads/debug_planificada.jpg', imagem_para_ler)
            print("✅ SUCESSO! Imagem planificada e salva!")

        else:
            print(f"⚠️ Apenas {len(possible_markers)} marcadores.")
            print("⚠️ Pulando planificação.")
            print("📐 Redimensionando para 800x1000 mesmo sem planificação...")
            imagem_para_ler = cv2.resize(imagem_para_ler, (800, 1000))
            cv2.imwrite('uploads/debug_planificada.jpg', imagem_para_ler)

        # ── ETAPA 5: Posições das questões ──
        POSICOES_QUESTOES = [
            {'x': 173, 'y':  28, 'w': 468, 'h': 70},  # Q1
            {'x': 170, 'y': 123, 'w': 486, 'h': 67},  # Q2
            {'x': 158, 'y': 231, 'w': 498, 'h': 59},  # Q3
            {'x': 161, 'y': 328, 'w': 500, 'h': 62},  # Q4
            {'x': 170, 'y': 426, 'w': 483, 'h': 64},  # Q5
            {'x': 166, 'y': 531, 'w': 495, 'h': 62},  # Q6
            {'x': 165, 'y': 631, 'w': 496, 'h': 59},  # Q7
            {'x': 165, 'y': 736, 'w': 493, 'h': 65},  # Q8
            {'x': 170, 'y': 831, 'w': 483, 'h': 59},  # Q9
            {'x': 153, 'y': 931, 'w': 500, 'h': 62},  # Q10
        ]

        # ── ETAPA 6: Leitura das respostas ──
        print("7️⃣ Iniciando leitura das respostas...")
        h, w                 = imagem_para_ler.shape[:2]
        debug_img            = imagem_para_ler.copy()
        respostas_detectadas = []
        alternativas_map     = ['A', 'B', 'C', 'D']

        for idx_q, pos in enumerate(POSICOES_QUESTOES):
            if idx_q >= len(gabarito_esperado):
                break

            x  = max(0, min(w - 10, pos['x']))
            y  = max(0, min(h - 10, pos['y']))
            cw = max(10, min(w - x,  pos['w']))
            ch = max(10, min(h - y,  pos['h']))

            roi_questao = imagem_para_ler[y: y + ch, x: x + cw]
            cv2.rectangle(
                debug_img, (x, y), (x + cw, y + ch), (0, 255, 0), 2
            )

            gray_roi            = cv2.cvtColor(roi_questao, cv2.COLOR_BGR2GRAY)
            h_roi, w_roi        = gray_roi.shape
            largura_alternativa = w_roi // 4
            melhor_opcao_idx    = -1
            menor_brilho        = 255

            for i in range(4):
                x_inicio = i * largura_alternativa
                x_fim    = x_inicio + largura_alternativa
                margem_x = int(largura_alternativa * 0.15)
                margem_y = int(h_roi * 0.15)

                miolo = gray_roi[
                    margem_y: h_roi - margem_y,
                    x_inicio + margem_x: x_fim - margem_x
                ]

                if miolo.size == 0:
                    continue

                brilho = np.mean(miolo)
                if brilho < menor_brilho:
                    menor_brilho     = brilho
                    melhor_opcao_idx = i

            # Limiar original que funcionava bem
            if menor_brilho < 215:
                resp = alternativas_map[melhor_opcao_idx]
                respostas_detectadas.append(resp)
                print(f"   ✅ Q{idx_q+1}: '{resp}' (brilho: {round(menor_brilho,1)})")
            else:
                respostas_detectadas.append('')
                print(f"   ⚠️ Q{idx_q+1}: Não detectado (brilho: {round(menor_brilho,1)})")

        cv2.imwrite('uploads/debug_leitura_final.jpg', debug_img)

        # Garante 10 respostas
        while len(respostas_detectadas) < len(gabarito_esperado):
            respostas_detectadas.append('')

        return respostas_detectadas[:len(gabarito_esperado)]

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO NA EXECUÇÃO:")
        traceback.print_exc()
        return [''] * len(gabarito_esperado)