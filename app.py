import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
from PIL import Image
import random
import os

# --- OCRモデルの読み込み (キャッシュ化して高速化) ---
@st.cache_resource
def load_ocr():
    # サーバー負荷を抑えるためGPUをオフに設定
    return easyocr.Reader(['ja', 'en'], gpu=False)

# --- Data Loading ---
@st.cache_data
def load_data(file_path):
    """
    Excelファイルを読み込む関数
    A列: 問題, B列: 解答 (ヘッダーなし)
    """
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
    st.caption("AIがあなたの手書き解答を読み取って採点します。")

    # OCRとデータの準備
    reader = load_ocr()
    file_name = "questions.xlsx"
    df = load_data(file_name)

    if df is None or df.empty:
        st.warning(f"'{file_name}' が見つかりません。")
        return

    # セッション状態の初期化
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
                # 画像処理
                img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA').convert('RGB')
                img_np = np.array(img)
                
                with st.spinner('AIが採点中...'):
                    results = reader.readtext(img_np)
                    # 認識した文字を結合
                    recognized_text = "".join([res[1] for res in results]).replace(" ", "").strip()
                    correct_answer = str(current_q['answer']).strip()
                    
                    if recognized_text == correct_answer:
                        st.session_state.answer_status = ("success", f"正解です！ (認識結果: {recognized_text})")
                    else:
                        st.session_state.answer_status = ("error", f"不正解... (認識結果: {recognized_text} / 正解: {correct_answer})")
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

    # 採点結果の表示
    if st.session_state.answer_status:
        status, msg = st.session_state.answer_status
        if status == "success":
            st.success(msg)
            st.balloons()
        else:
            st.error(msg)

if __name__ == "__main__":
    main()