# services/omr.py
# OMR Sistema 2.0 - Versão com Detecção Dinâmica por 4 Marcadores de Canto

import cv2
import numpy as np
import os
import traceback

def order_points(pts):
    """Ordena pontos: topo-esquerda, topo-direita, baixo-direita, baixo-esquerda"""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def encontrar_marcadores_canto(image, upload_dir):
    """
    Detecta os 4 quadrados pretos nos cantos da área das questões.
    Retorna os 4 pontos ordenados ou None se não encontrar.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Threshold agressivo pra pegar só os pretos bem escuros
        _, thresh = cv2.threshold(blurred, 60, 255, cv2.THRESH_BINARY_INV)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidatos = []
        for c in contours:
            area = cv2.contourArea(c)
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / float(h) if h > 0 else 0
            
            # Marcadores de canto: quadrados pequenos/médios, bem escuros
            if 500 < area < 15000 and 0.7 < aspect < 1.3:
                candidatos.append({
                    'area': area,
                    'box': (x, y, w, h),
                    'center': (x + w/2, y + h/2)
                })
        
        print(f"🔍 Encontrados {len(candidatos)} candidatos a marcador de canto")
        
        if len(candidatos) < 4:
            print("⚠️ Menos de 4 marcadores encontrados — usando fallback")
            return None
        
        # Ordena por área (maiores primeiro) e pega os 4 maiores
        candidatos.sort(key=lambda m: m['area'], reverse=True)
        top_4 = candidatos[:4]
        
        # Extrai os centros
        centers = np.array([m['center'] for m in top_4], dtype="float32")
        
        # Ordena os 4 pontos: TL, TR, BR, BL
        ordered = order_points(centers)
        
        # Debug: desenha os marcadores detectados
        debug_img = image.copy()
        for i, pt in enumerate(ordered):
            cv2.circle(debug_img, (int(pt[0]), int(pt[1])), 10, (0, 0, 255), -1)
            cv2.putText(debug_img, str(i+1), (int(pt[0])+15, int(pt[1])), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        try:
            cv2.imwrite(os.path.join(upload_dir, 'debug_marcadores.jpg'), debug_img)
            print("📸 Debug salvo: debug_marcadores.jpg")
        except:
            pass
        
        return ordered
        
    except Exception as e:
        print(f"⚠️ Erro ao detectar marcadores: {e}")
        return None

def esconder_qr_code(image, upload_dir):
    """
    Detecta o QR Code e pinta de branco — MAS só se a região for
    de tamanho plausível. Retorna True se o QR foi detectado e escondido.
    """
    try:
        detector = cv2.QRCodeDetector()
        bbox = None
        
        data, bbox, _ = detector.detectAndDecode(image)
        if bbox is None:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            data, bbox, _ = detector.detectAndDecode(gray)
        if bbox is None:
            gray2 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
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
            
            x_min = int(max(0, np.min(pts[:, 0]) - 40))
            y_min = int(max(0, np.min(pts[:, 1]) - 40))
            x_max = int(min(w_img, np.max(pts[:, 0]) + 40))
            y_max = int(min(h_img, np.max(pts[:, 1]) + 40))
            
            debug_img = image.copy()
            cv2.rectangle(debug_img, (x_min, y_min), (x_max, y_max), (0, 0, 255), 3)
            try:
                cv2.imwrite(os.path.join(upload_dir, 'debug_qr_antes.jpg'), debug_img)
            except:
                pass
            
            cv2.rectangle(image, (x_min, y_min), (x_max, y_max), (255, 255, 255), -1)
            print(f"✅ QR escondido! Região: ({x_min},{y_min}) até ({x_max},{y_max})")
            return True
        else:
            print("ℹ️ Nenhum QR detectado")
            return False
            
    except Exception as e:
        print(f"⚠️ Erro ao detectar QR: {e}")
        return False

def corrigir_orientacao(caminho_imagem):
    """Corrige a orientação EXIF da foto"""
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

def processar_imagem(caminho_imagem, gabarito_esperado):
    """
    Processa a imagem do gabarito e retorna as respostas detectadas.
    Usa os 4 marcadores de canto para calibrar dinamicamente a grade.
    """
    # Caminho fixo que funciona no Render e localmente
    upload_dir = '/opt/render/project/src/backend/uploads'
    if not os.path.exists(upload_dir):
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    print(f"📁 Pasta de uploads: {upload_dir}")

    try:
        gabarito_esperado = list(gabarito_esperado) + [''] * (10 - len(gabarito_esperado))
        gabarito_esperado = gabarito_esperado[:10]
        print("🚨 OMR.PY - DETECÇÃO DINÂMICA POR 4 MARCADORES 🚨")

        # ETAPA 0: Corrigir orientação
        print("0️⃣ Corrigindo orientação...")
        corrigir_orientacao(caminho_imagem)

        # ETAPA 1: Carregar imagem
        print("1️⃣ Carregando imagem...")
        image = cv2.imread(caminho_imagem)
        if image is None:
            raise Exception("Não conseguiu ler o arquivo de imagem.")

        # ETAPA 2: Esconder QR Code
        print("2️⃣ Procurando QR Code...")
        qr_foi_escondido = esconder_qr_code(image, upload_dir)

        # ETAPA 3: Redimensionar se muito grande
        h_orig, w_orig = image.shape[:2]
        print(f"📐 Tamanho original: {w_orig}x{h_orig}")
        
        MAX_LARGURA = 1200
        if w_orig > MAX_LARGURA:
            escala = MAX_LARGURA / w_orig
            nova_largura = int(w_orig * escala)
            nova_altura = int(h_orig * escala)
            image = cv2.resize(image, (nova_largura, nova_altura))
            print(f"📐 Redimensionado para: {nova_largura}x{nova_altura}")

        # ETAPA 4: Detectar os 4 marcadores de canto
        print("3️⃣ Detectando marcadores de canto...")
        marcadores = encontrar_marcadores_canto(image, upload_dir)
        
        if marcadores is None:
            print("❌ Não foi possível detectar os 4 marcadores — usando coordenadas fixas (fallback)")
            # Fallback: coordenadas fixas (caso os marcadores não sejam encontrados)
            imagem_para_ler = cv2.resize(image, (800, 1000))
            POSICOES_QUESTOES = [
                {'x': 180, 'y': 270, 'w': 460, 'h': 55},
                {'x': 180, 'y': 340, 'w': 460, 'h': 55},
                {'x': 180, 'y': 410, 'w': 460, 'h': 55},
                {'x': 180, 'y': 480, 'w': 460, 'h': 55},
                {'x': 180, 'y': 550, 'w': 460, 'h': 55},
                {'x': 180, 'y': 620, 'w': 460, 'h': 55},
                {'x': 180, 'y': 690, 'w': 460, 'h': 55},
                {'x': 180, 'y': 760, 'w': 460, 'h': 55},
                {'x': 180, 'y': 830, 'w': 460, 'h': 55},
                {'x': 180, 'y': 900, 'w': 460, 'h': 55},
            ]
        else:
            print("✅ 4 marcadores detectados! Calibrando grade dinamicamente...")
            
            # marcadores[0]=TL, [1]=TR, [2]=BR, [3]=BL
            tl, tr, br, bl = marcadores
            
            # Define a área das questões com base nos marcadores
            # Adiciona uma margem interna pra não pegar os próprios marcadores
            margem_x = 30
            margem_y = 20
            
            x_inicio = int(min(tl[0], bl[0])) + margem_x
            x_fim = int(max(tr[0], br[0])) - margem_x
            y_inicio = int(min(tl[1], tr[1])) + margem_y
            y_fim = int(max(bl[1], br[1])) - margem_y
            
            largura_grade = x_fim - x_inicio
            altura_grade = y_fim - y_inicio
            
            print(f"📏 Grade detectada: ({x_inicio},{y_inicio}) até ({x_fim},{y_fim}) = {largura_grade}x{altura_grade}")
            
            # Divide em 10 linhas iguais
            altura_linha = altura_grade / 10
            
            POSICOES_QUESTOES = []
            for i in range(10):
                y = int(y_inicio + i * altura_linha)
                POSICOES_QUESTOES.append({
                    'x': x_inicio,
                    'y': y,
                    'w': largura_grade,
                    'h': int(altura_linha)
                })
            
            # Usa a imagem original (não redimensiona pra 800x1000)
            imagem_para_ler = image

        # ETAPA 5: Leitura das respostas
        print("4️⃣ Lendo respostas...")
        h, w = imagem_para_ler.shape[:2]
        debug_img = imagem_para_ler.copy()
        respostas_detectadas = []
        alternativas_map = ['A', 'B', 'C', 'D']

        for idx_q, pos in enumerate(POSICOES_QUESTOES):
            if idx_q >= len(gabarito_esperado):
                break

            x = max(0, min(w - 10, pos['x']))
            y = max(0, min(h - 10, pos['y']))
            cw = max(10, min(w - x, pos['w']))
            ch = max(10, min(h - y, pos['h']))

            roi_questao = imagem_para_ler[y:y+ch, x:x+cw]
            cv2.rectangle(debug_img, (x, y), (x+cw, y+ch), (0, 255, 0), 2)

            gray_roi = cv2.cvtColor(roi_questao, cv2.COLOR_BGR2GRAY)
            h_roi, w_roi = gray_roi.shape
            largura_alternativa = w_roi // 4
            melhor_opcao_idx = -1
            menor_brilho = 255

            for i in range(4):
                x_inicio = i * largura_alternativa
                x_fim = x_inicio + largura_alternativa
                margem_x = int(largura_alternativa * 0.15)
                margem_y = int(h_roi * 0.15)

                miolo = gray_roi[margem_y:h_roi-margem_y, x_inicio+margem_x:x_fim-margem_x]

                if miolo.size == 0:
                    continue

                brilho = np.mean(miolo)
                if brilho < menor_brilho:
                    menor_brilho = brilho
                    melhor_opcao_idx = i

            if menor_brilho < 235:
                resp = alternativas_map[melhor_opcao_idx]
                respostas_detectadas.append(resp)
                print(f"   ✅ Q{idx_q+1}: '{resp}' (brilho: {round(menor_brilho,1)})")
            else:
                respostas_detectadas.append('')
                print(f"   ⚠️ Q{idx_q+1}: Não detectado (brilho: {round(menor_brilho,1)})")

        cv2.imwrite(os.path.join(upload_dir, 'debug_leitura_final.jpg'), debug_img)

        while len(respostas_detectadas) < len(gabarito_esperado):
            respostas_detectadas.append('')

        return respostas_detectadas[:len(gabarito_esperado)]

    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO:")
        traceback.print_exc()
        return [''] * len(gabarito_esperado)