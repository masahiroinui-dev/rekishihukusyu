import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
from PIL import Image, ImageOps
import random
import os
import unicodedata
import cv2

# --- 判定ロジックの強化 ---
def normalize_text(text):
    """
    文字の揺れ（全角/半角、大文字/小文字、拗音の大小など）を吸収する関数
    """
    if not text:
        return ""
    
    # 1. 全角を半角に、大文字を小文字に変換 (NFKC正規化)
    text = unicodedata.normalize('NFKC', text).lower()
    
    # 2. 判定に影響しやすい文字の置換（大小を区別しない設定）
    replace_map = {
        'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ',
        'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
        'っ': 'つ',
        'ー': '', '-': '',  # 長音やハイフンを無視する場合
    }
    for old, new in replace_map.items():
        text = text.replace(old, new)
        
    # 3. 空白の除去
    return text.replace(" ", "").strip()

# --- OCRモデルの読み込み ---
@st.cache_resource
def load_ocr():
    # サーバー負荷を抑えるためGPUをオフに設定
    return easyocr.Reader(['ja', 'en'], gpu=False)

# --- 画像の前処理 (精度大幅向上用) ---
def preprocess_image(image_data):
    """
    エッジ強調と適応的二値化でOCR精度を最大化する処理
    """
    # RGBAからRGBに変換し、NumPy配列(OpenCV形式)にする
    img = Image.fromarray(image_data.astype('uint8'), 'RGBA').convert('RGB')
    img_np = np.array(img)
    
    # 1. グレースケール化
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # 2. ノイズ除去 (中値フィルタ)
    # 手書きの小さなゴミを除去
    gray = cv2.medianBlur(gray, 3)
    
    # 3. エッジ強調 (アンシャープマスキング)
    # ぼかした画像との差分を利用して輪郭を強調
    gaussian_3 = cv2.GaussianBlur(gray, (0, 0), 2.0)
    unsharp_image = cv2.addWeighted(gray, 2.0, gaussian_3, -1.0, 0)
    
    # 4. 適応的二値化 (Adaptive Thresholding)
    # 画像の局所的な明るさに合わせて閾値を調整するため、かすれた文字に強い
    binary = cv2.adaptiveThreshold(
        unsharp_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 11, 2
    )
    
    # 5. モルフォロジー変換 (膨張・収縮)
    # 文字の線を少し太らせて連結を強める
    kernel = np.ones((2,2), np.uint8)
    processed_img = cv2.erode(binary, kernel, iterations=1) 
    
    return processed_img

# --- Data Loading ---
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        df = df.dropna(subset=['question'])
        return df
    except Exception as e:
        st.error(f"Excelの読み込み中にエラーが発生しました: {e}")
        return None

def main():
    st.set_page_config(page_title="手書き自動採点アプリ", layout="centered")

    st.title("📝 手書き自動採点アプリ")
    st.caption("エッジ強調と適応的二値化により、認識精度をさらに強化しました。")

    reader = load_ocr()
    file_name = "questions.xlsx"
    df = load_data(file_name)

    if df is None or df.empty:
        st.warning(f"'{file_name}' が見つかりません。")
        return

    if 'q_index' not in st.session_state:
        st.session_state.q_index = random.randint(0, len(df) - 1)
    if 'answer_status' not in st.session_state:
        st.session_state.answer_status = None
    if 'canvas_key' not in st.session_state:
        st.session_state.canvas_key = 0

    current_q = df.iloc[st.session_state.q_index]

    st.markdown("---")
    st.subheader("【問題】")
    st.info(current_q['question'])

    st.write("▼ 下の枠に解答を書いてください")
    
    # ペンの太さを少し太く設定（認識率向上のため）
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=6,
        stroke_color="#000000",
        background_color="#ffffff",
        height=250,
        width=600,
        drawing_mode="freedraw",
        key=f"canvas_{st.session_state.canvas_key}",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("採点する", use_container_width=True):
            if canvas_result.image_data is not None:
                with st.spinner('AIが画像を解析中...'):
                    # 画像の前処理を実行 (エッジ強調・適応二値化)
                    processed_img = preprocess_image(canvas_result.image_data)
                    
                    # OCR実行
                    results = reader.readtext(processed_img)
                    raw_recognized = "".join([res[1] for res in results])
                    
                    # 判定用の正規化
                    norm_recognized = normalize_text(raw_recognized)
                    norm_correct = normalize_text(str(current_q['answer']))
                    
                    if norm_recognized == norm_correct:
                        st.session_state.answer_status = ("success", f"正解です！\n(認識: {raw_recognized})")
                    else:
                        st.session_state.answer_status = ("error", f"不正解...\n認識結果: {raw_recognized}\n正解: {current_q['answer']}")
                st.rerun()

    with col2:
        if st.button("書き直す", use_container_width=True):
            st.session_state.canvas_key += 1
            st.session_state.answer_status = None
            st.rerun()

    with col3:
        if st.button("次の問題へ ➔", use_container_width=True):
            st.session_state.q_index = random.randint(0, len(df) - 1)
            st.session_state.answer_status = None
            st.session_state.canvas_key += 1
            st.rerun()

    if st.session_state.answer_status:
        status, msg = st.session_state.answer_status
        if status == "success":
            st.success(msg)
            st.balloons()
        else:
            st.error(msg)

if __name__ == "__main__":
    main()