import streamlit as st
from streamlit_drawable_canvas import st_canvas
import pandas as pd
from PIL import Image
import pytesseract
import random
import numpy as np

# --- 設定 ---
st.set_page_config(page_title="歴史・手書き自動採点アプリ", layout="centered")

# --- データ読み込み ---
@st.cache_data
def load_data():
    try:
        # アップロードされたCSVを読み込み
        df = pd.read_csv("rekishi_questions.xlsx - Sheet1.csv", header=None, names=["question", "answer"])
        return df
    except Exception as e:
        st.error(f"問題データの読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=["question", "answer"])

df = load_data()

# --- セッション状態の初期化 ---
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = random.randint(0, len(df) - 1) if not df.empty else 0
if "result" not in st.session_state:
    st.session_state.result = None
if "recognized_text" not in st.session_state:
    st.session_state.recognized_text = ""
if "canvas_key_id" not in st.session_state:
    st.session_state.canvas_key_id = 0

# --- メインコンテンツ ---
st.title("📝 歴史 手書き自動採点")
st.write("APIキー不要・オフラインライブラリによる文字認識")

if not df.empty:
    question = df.iloc[st.session_state.current_q_idx]["question"]
    correct_answer = df.iloc[st.session_state.current_q_idx]["answer"]

    st.markdown(f"### 問題: {question}")

    # キャンバス操作用カラム
    col_ctrl, col_canvas = st.columns([1, 3])
    
    with col_ctrl:
        stroke_width = st.slider("ペンの太さ", 1, 10, 5)
        if st.button("🔄 次の問題へ"):
            st.session_state.current_q_idx = random.randint(0, len(df) - 1)
            st.session_state.result = None
            st.session_state.recognized_text = ""
            st.session_state.canvas_key_id += 1 
            st.rerun()

    with col_canvas:
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=stroke_width,
            stroke_color="#000000",
            background_color="#ffffff",
            height=250,
            width=500,
            drawing_mode="freedraw",
            key=f"canvas_q_{st.session_state.canvas_key_id}",
            update_streamlit=True,
        )

    if st.button("✅ 採点する", use_container_width=True):
        if canvas_result.image_data is not None:
            with st.spinner("ローカルライブラリで判定中..."):
                # 画像処理
                img_data = canvas_result.image_data.astype('uint8')
                img = Image.fromarray(img_data).convert('L') # グレースケール変換
                
                # OCR実行 (日本語と英語をターゲットに設定)
                try:
                    # configは1文字、または単語として認識する設定
                    recognized = pytesseract.image_to_string(img, lang='jpn', config='--psm 7')
                    recognized = recognized.strip().replace(" ", "").replace("　", "").replace("\n", "")
                    st.session_state.recognized_text = recognized
                    
                    # 採点
                    if recognized == str(correct_answer).strip():
                        st.session_state.result = "正解"
                    else:
                        st.session_state.result = "不正解"
                except Exception as e:
                    st.error("OCRエンジンが見つかりません。packages.txtの設定を確認してください。")

    # 結果表示
    if st.session_state.result:
        st.divider()
        if st.session_state.result == "正解":
            st.balloons()
            st.success(f"🎊 **正解です！** (認識: {st.session_state.recognized_text})")
        else:
            st.error(f"😭 **不正解...** (認識: {st.session_state.recognized_text})")
            st.info(f"正解は **{correct_answer}** です。")
else:
    st.error("問題データが空です。")

st.caption("Powered by Streamlit & Tesseract OCR")