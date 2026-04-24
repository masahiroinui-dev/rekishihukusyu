import streamlit as st
from streamlit_drawable_canvas import st_canvas
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import random

# --- 設定 ---
st.set_page_config(page_title="歴史・手書き自動採点アプリ", layout="centered")

# Gemini APIのセットアップ
# StreamlitのSecretsまたは環境変数からAPIキーを取得することを想定
api_key = st.sidebar.text_input("Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.warning("左側のサイドバーに Gemini APIキーを入力してください。")

# --- データ読み込み ---
@st.cache_data
def load_data():
    try:
        # アップロードされたファイルを読み込む
        # ファイル名が異なる場合はここを修正してください
        df = pd.read_csv("rekishi_questions.xlsx - Sheet1.csv", header=None, names=["question", "answer"])
        return df
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=["question", "answer"])

df = load_data()

# --- セッション状態の初期化 ---
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = random.randint(0, len(df) - 1) if not df.empty else 0
if "result" not in st.session_state:
    st.session_state.result = None
if "recognized_text" not in st.session_state:
    st.session_state.recognized_text = ""

# --- UI ---
st.title("📝 歴史 手書き自動採点")
st.write("問題に対して、下のキャンバスに手書きで答えてください。")

if not df.empty:
    question = df.iloc[st.session_state.current_q_idx]["question"]
    correct_answer = df.iloc[st.session_state.current_q_idx]["answer"]

    st.info(f"**問題:** {question}")

    # キャンバスの設定
    col1, col2 = st.columns([1, 4])
    with col1:
        stroke_width = st.slider("線の太さ", 1, 10, 3)
        if st.button("次の問題へ"):
            st.session_state.current_q_idx = random.randint(0, len(df) - 1)
            st.session_state.result = None
            st.session_state.recognized_text = ""
            st.rerun()

    # 手書きキャンバス
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=250,
        width=500,
        drawing_mode="freedraw",
        key="canvas",
    )

    if st.button("採点する"):
        if canvas_result.image_data is not None and api_key:
            with st.spinner("AIが文字を読み取っています..."):
                # キャンバス画像をPIL Imageに変換
                img = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA').convert('RGB')
                
                # Gemini 1.5 Flash を使用してOCR
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                prompt = "この画像に書かれている日本語（歴史用語）をテキストで抽出してください。回答が1つの単語であればその単語のみを、複数行ある場合は繋げて返してください。解説は不要です。"
                
                try:
                    response = model.generate_content([prompt, img])
                    recognized = response.text.strip().replace(" ", "").replace("　", "")
                    st.session_state.recognized_text = recognized
                    
                    # 採点ロジック（簡易一致確認）
                    if recognized == str(correct_answer).strip():
                        st.session_state.result = "正解"
                    else:
                        st.session_state.result = "不正解"
                except Exception as e:
                    st.error(f"APIエラーが発生しました: {e}")

    # 結果表示
    if st.session_state.result:
        if st.session_state.result == "正解":
            st.success(f"⭕️ 正解！ (認識結果: {st.session_state.recognized_text})")
        else:
            st.error(f"❌ 残念！ (認識結果: {st.session_state.recognized_text})")
            st.write(f"正しい答え: **{correct_answer}**")
else:
    st.error("問題データが見つかりません。")

# --- 使い方のヒント ---
with st.expander("使い方ガイド"):
    st.write("""
    1. サイドバーにGoogle AI Studioで取得したAPIキーを入力します。
    2. 白い枠の中にマウスやタッチペンで答えを書きます。
    3. 「採点する」ボタンを押すと、AIが文字を読み取って正誤判定します。
    """)