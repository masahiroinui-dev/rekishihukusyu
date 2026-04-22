import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
from PIL import Image
import random
import os
import unicodedata

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
    return easyocr.Reader(['ja', 'en'], gpu=False)

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
    st.caption("全角半角や文字の大小を柔軟に判定するモードを搭載しました。")

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
    
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=4,
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
                img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA').convert('RGB')
                img_np = np.array(img)
                
                with st.spinner('AIが採点中...'):
                    results = reader.readtext(img_np)
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