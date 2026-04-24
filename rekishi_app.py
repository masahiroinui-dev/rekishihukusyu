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
import difflib
import time

# --- ページ設定 ---
st.set_page_config(page_title="歴史クイズ・手書き学習", layout="centered")

# --- 文字正規化関数 (判定の揺れを吸収) ---
def normalize_text(text):
    if not text:
        return ""
    # 全角を半角に、大文字を小文字に変換
    text = unicodedata.normalize('NFKC', text).lower()
    # 拗音や記号の揺れを置換
    replace_map = {
        'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ',
        'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
        'っ': 'つ', 'ー': '', '-': '', 
    }
    for old, new in replace_map.items():
        text = text.replace(old, new)
    return text.replace(" ", "").strip()

# --- OCRモデルの読み込み (キャッシュ利用) ---
@st.cache_resource
def load_ocr():
    # 日本語と英語をターゲットにロード
    return easyocr.Reader(['ja', 'en'], gpu=False)

# --- データ読み込み ---
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        # 歴史専用のExcelファイルを読み込み (1列目: 問題, 2列目: 解答)
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        df = df.dropna(subset=['question'])
        return df
    except Exception as e:
        st.error(f"Excelの読み込み中にエラーが発生しました: {e}")
        return None

def main():
    st.title("📜 歴史クイズ・手書き学習")
    st.caption("手書きで歴史の解答を記入し、AIが自動で採点します。")

    reader = load_ocr()
    file_name = "rekishi_questions.xlsx"
    df = load_data(file_name)

    if df is None or df.empty:
        st.warning(f"'{file_name}' が見つかりません。GitHubリポジトリにExcelファイルを配置してください。")
        return

    # --- セッション管理 ---
    if 'rek_q_index' not in st.session_state:
        st.session_state.rek_q_index = random.randint(0, len(df) - 1)
    if 'rek_status' not in st.session_state:
        st.session_state.rek_status = None
    if 'rek_canvas_key' not in st.session_state:
        st.session_state.rek_canvas_key = 0
    if 'show_canvas' not in st.session_state:
        st.session_state.show_canvas = True

    # --- DOM衝突回避ロジック ---
    if not st.session_state.show_canvas:
        st.session_state.show_canvas = True
        time.sleep(0.2) # ブラウザのクリーンアップ時間を確保
        st.rerun()

    current_q = df.iloc[st.session_state.rek_q_index]

    st.markdown("---")
    st.subheader("【問題】")
    st.info(current_q['question'])
    st.write("▼ 解答を手書きしてください")
    
    # キャンバス配置用のプレースホルダー
    canvas_placeholder = st.empty()
    
    canvas_result = None
    if st.session_state.show_canvas:
        with canvas_placeholder.container():
            # keyを動的に変更することで、再描画時のエラーを回避
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=7,
                stroke_color="#000000",
                background_color="#ffffff",
                height=250,
                width=600,
                drawing_mode="freedraw",
                key=f"rek_canvas_v{st.session_state.rek_canvas_key}",
                update_streamlit=True,
            )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("採点する", use_container_width=True):
            if canvas_result is not None and canvas_result.image_data is not None:
                with st.spinner('AIが文字を分析中...'):
                    # 画像処理 (白背景合成 + 二値化 + 膨張)
                    img_rgba = canvas_result.image_data.astype('uint8')
                    img_pil = Image.fromarray(img_rgba)
                    bg = Image.new("RGB", img_pil.size, (255, 255, 255))
                    if img_pil.mode == 'RGBA':
                        bg.paste(img_pil, mask=img_pil.split()[3])
                    else:
                        bg.paste(img_pil)
                    
                    open_cv_image = np.array(bg)
                    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
                    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
                    kernel = np.ones((2,2), np.uint8)
                    dilated = cv2.dilate(binary, kernel, iterations=1)
                    processed_img = cv2.bitwise_not(dilated)
                    
                    # OCR認識
                    results = reader.readtext(processed_img, detail=0)
                    recognized_text = "".join(results).replace(" ", "")
                    
                    # 判定
                    norm_recognized = normalize_text(recognized_text)
                    correct_answer = str(current_q['answer']).strip()
                    norm_correct = normalize_text(correct_answer)
                    
                    # 類似度計算 (多少の誤字を許容)
                    similarity = difflib.SequenceMatcher(None, norm_recognized, norm_correct).ratio()
                    
                    if norm_recognized == norm_correct:
                        st.session_state.rek_status = ("success", f"正解！\n(認識結果: {recognized_text})")
                    elif similarity >= 0.8:
                        st.session_state.rek_status = ("success", f"正解！ (許容範囲内)\n(認識: {recognized_text} → 正解: {correct_answer})")
                    else:
                        st.session_state.rek_status = ("error", f"不正解...\n認識結果: {recognized_text}\n正解: {correct_answer}")
                st.rerun()

    with col2:
        if st.button("書き直す", use_container_width=True):
            canvas_placeholder.empty()
            st.session_state.show_canvas = False
            st.session_state.rek_canvas_key += 1
            st.session_state.rek_status = None
            st.rerun()

    with col3:
        if st.button("次の問題へ ➔", use_container_width=True):
            canvas_placeholder.empty()
            if len(df) > 1:
                new_idx = st.session_state.rek_q_index
                while new_idx == st.session_state.rek_q_index:
                    new_idx = random.randint(0, len(df) - 1)
                st.session_state.rek_q_index = new_idx
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
                st.image(processed_img)

if __name__ == "__main__":
    main()