import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
from PIL import Image, ImageOps, ImageFilter
import random
import os
import unicodedata
import cv2
import difflib
import time

# ページ設定
st.set_page_config(page_title="歴史クイズ・手書き学習", layout="centered")

# --- 判定ロジックの強化 ---
def normalize_text(text):
    """
    文字の揺れ（全角/半角、大文字/小文字、拗音の大小など）を吸収する関数
    """
    if not text:
        return ""
    # 1. 全角を半角に、大文字を小文字に変換 (NFKC正規化)
    text = unicodedata.normalize('NFKC', text).lower()
    # 2. 判定に影響しやすい文字の置換
    replace_map = {
        'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ',
        'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
        'っ': 'つ', 'ー': '', '-': '', 
    }
    for old, new in replace_map.items():
        text = text.replace(old, new)
    return text.replace(" ", "").strip()

# --- OCRモデルの読み込み ---
@st.cache_resource
def load_ocr():
    # 歴史用に日本語と英語をターゲットにロード
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr()

# --- データ読み込み ---
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        # 歴史専用のExcelファイルを読み込み (ヘッダーなし、1列目:問題, 2列目:解答 を想定)
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        df = df.dropna(subset=['question'])
        return df
    except Exception as e:
        st.error(f"Excelの読み込み中にエラーが発生しました: {e}")
        return None

# ファイル名
file_name = "rekishi_questions.xlsx"
df = load_data(file_name)

# セッション管理
if 'rek_q_index' not in st.session_state:
    st.session_state.rek_q_index = random.randint(0, len(df) - 1) if df is not None and not df.empty else 0
if 'rek_status' not in st.session_state:
    st.session_state.rek_status = None
if 'rek_canvas_key' not in st.session_state:
    st.session_state.rek_canvas_key = 0
if 'show_canvas' not in st.session_state:
    st.session_state.show_canvas = True

# エラー対策：一旦表示を消してから再描画するためのトリガー
if not st.session_state.show_canvas:
    st.session_state.show_canvas = True
    time.sleep(0.1)
    st.rerun()

st.title("📜 歴史クイズ・手書き学習")

if df is not None and not df.empty:
    current_q = df.iloc[st.session_state.rek_q_index]

    st.markdown("---")
    st.subheader("【問題】")
    st.info(current_q['question'])

    st.write("▼ 解答を手書きしてください")
    
    # キャンバスを格納する器を定義（DOM衝突エラー対策）
    canvas_container = st.empty()
    
    canvas_result = None
    if st.session_state.show_canvas:
        with canvas_container.container():
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=7, # 英語アプリの推奨値付近に設定
                stroke_color="#000000",
                background_color="#ffffff",
                height=250,
                width=600,
                drawing_mode="freedraw",
                key=f"rek_canvas_v_{st.session_state.rek_canvas_key}",
                update_streamlit=True,
            )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("採点する", use_container_width=True):
            if canvas_result is not None and canvas_result.image_data is not None:
                with st.spinner('AIが文字を分析中...'):
                    # --- 英語アプリの画像処理ロジックを完全移植 ---
                    # 1. 画像の取得と白背景合成
                    img_rgba = canvas_result.image_data.astype('uint8')
                    img_pil = Image.fromarray(img_rgba)
                    
                    # 透明度がある場合は白背景と合成
                    bg = Image.new("RGB", img_pil.size, (255, 255, 255))
                    if img_pil.mode == 'RGBA':
                        bg.paste(img_pil, mask=img_pil.split()[3])
                    else:
                        bg.paste(img_pil)
                    
                    # 2. OpenCV形式に変換して画像処理
                    open_cv_image = np.array(bg)
                    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
                    
                    # 二値化処理 (文字をはっきりさせる)
                    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
                    
                    # 文字の線を少し太くする（膨張処理）
                    kernel = np.ones((2,2), np.uint8)
                    dilated = cv2.dilate(binary, kernel, iterations=1)
                    
                    # 再度白背景に黒文字に戻す
                    processed_img = cv2.bitwise_not(dilated)
                    
                    # 3. OCR認識
                    # 歴史用なので日本語を含めて認識
                    results = reader.readtext(processed_img, detail=0)
                    recognized_text = "".join(results).replace(" ", "")
                    
                    # 4. 判定ロジック
                    norm_recognized = normalize_text(recognized_text)
                    correct_answer = str(current_q['answer']).strip()
                    norm_correct = normalize_text(correct_answer)
                    
                    # 類似度計算 (英語アプリの手法)
                    similarity = difflib.SequenceMatcher(None, norm_recognized, norm_correct).ratio()
                    
                    if norm_recognized == norm_correct:
                        st.session_state.rek_status = ("success", f"正解！\n(認識結果: {recognized_text})")
                    elif similarity >= 0.8: # 歴史用に閾値を0.8に調整（1文字ミス程度を許容）
                        st.session_state.rek_status = ("success", f"正解！ (少し表記が違いますがOKです)\n(認識: {recognized_text} → 正解: {correct_answer})")
                    else:
                        st.session_state.rek_status = ("error", f"認識結果: {recognized_text}\n正解: {correct_answer}")
                st.rerun()
            else:
                st.warning("何か書いてください。")

    with col2:
        if st.button("書き直す", use_container_width=True):
            canvas_container.empty()
            st.session_state.show_canvas = False
            st.session_state.rek_canvas_key += 1
            st.session_state.rek_status = None
            st.rerun()

    with col3:
        if st.button("次の問題へ ➔", use_container_width=True):
            if len(df) > 1:
                new_idx = st.session_state.rek_q_index
                while new_idx == st.session_state.rek_q_index:
                    new_idx = random.randint(0, len(df) - 1)
                st.session_state.rek_q_index = new_idx
            canvas_container.empty()
            st.session_state.show_canvas = False
            st.session_state.rek_status = None
            st.session_state.rek_canvas_key += 1
            st.rerun()

    if st.session_state.rek_status:
        status, msg = st.session_state.rek_status
        if status == "success":
            st.success(msg)
            st.balloons()
        else:
            st.error(msg)
            if st.checkbox("AIの認識画像を確認"):
                st.image(processed_img, caption="AIが読み取った画像")
else:
    st.warning(f"'{file_name}' が見つからないか、データが空です。")