import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
from PIL import Image
import random
import difflib
import cv2

# ページ設定
st.set_page_config(page_title="英単語手書き採点アプリ", layout="centered")

# OCRモデルの読み込み（英語を指定）
@st.cache_resource
def load_ocr():
    # アルファベットのみをターゲットにロード
    return easyocr.Reader(['en'], gpu=False)

reader = load_ocr()

# エクセルデータの読み込み
@st.cache_data
def load_data():
    try:
        df = pd.read_excel("questions.xlsx")
        df.columns = df.columns.str.strip()
        df = df.dropna(subset=["word", "meaning"])
        return df
    except Exception as e:
        st.error(f"エラー: {e}")
        return pd.DataFrame(columns=["word", "meaning"])

df = load_data()

# 画面収まりを良くするためのカスタムCSS
st.markdown("""
<style>
    /* 全体の余白を詰める */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
    }
    /* 意味を表示するボックスの調整 */
    .meaning-box {
        background-color: #f0f2f6;
        padding: 10px 15px;
        border-radius: 8px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    .meaning-text {
        margin: 0;
        color: #31333f;
        font-size: 1.5rem;
        text-align: center;
        font-weight: bold;
    }
    /* 削除/クリアボタンのスタイル */
    div[data-testid="stButton"] > button:contains("書き直す"),
    div[data-testid="stButton"] > button:contains("最初から") {
        border: 1px solid #ff4b4b !important;
        color: #ff4b4b !important;
        background-color: white !important;
    }
    /* 戻るボタンのスタイル */
    div[data-testid="stButton"] > button:contains("前へ") {
        border: 1px solid #0068c9 !important;
        color: #0068c9 !important;
        background-color: white !important;
    }
    /* 次へ/採点ボタンのスタイル */
    div[data-testid="stButton"] > button:contains("採点"),
    div[data-testid="stButton"] > button:contains("次へ") {
        background-color: #0068c9 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# セッション状態の初期化
if 'question_pool' not in st.session_state:
    if not df.empty:
        indices = list(range(len(df)))
        random.shuffle(indices)
        st.session_state.question_pool = indices
        st.session_state.pool_ptr = 0
        st.session_state.q_index = st.session_state.question_pool[0]
        st.session_state.history = []
        st.session_state.canvas_key = 0 # キャンバスリセット用
    else:
        st.session_state.question_pool = []
        st.session_state.q_index = 0
        st.session_state.canvas_key = 0

if 'answer_status' not in st.session_state:
    st.session_state.answer_status = None

st.title("📝 英単語手書きテスト")

# サイドバー設定
st.sidebar.title("🖌️ 設定")
stroke_width = st.sidebar.slider("ペンの太さ", 1, 15, 7)
st.sidebar.info("aとoを区別するため、aは丸をしっかり閉じ、oは少し縦長に書くと認識しやすくなります。")

if not df.empty:
    current_question = df.iloc[st.session_state.q_index]
    q_meaning = str(current_question['meaning'])
    q_word = str(current_question['word'])
    
    # 意味をコンパクトに表示
    st.markdown(f"""
    <div class="meaning-box">
        <p class="meaning-text">{q_meaning}</p>
    </div>
    """, unsafe_allow_html=True)

    # キャンバス
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=180,
        width=600,
        drawing_mode="freedraw",
        key=f"canvas_{st.session_state.q_index}_{st.session_state.canvas_key}",
    )

    # ボタンレイアウト
    col_clear, col_judge, col_prev, col_next = st.columns([1, 1, 1, 1])

    with col_clear:
        if st.button("書き直す", use_container_width=True):
            st.session_state.canvas_key += 1
            st.session_state.answer_status = None
            st.rerun()

    with col_judge:
        if st.button("採点する ✅", use_container_width=True):
            if canvas_result.image_data is not None:
                img_rgba = canvas_result.image_data.astype('uint8')
                img_pil = Image.fromarray(img_rgba)
                bg = Image.new("RGB", img_pil.size, (255, 255, 255))
                bg.paste(img_pil, mask=img_pil.split()[3])
                
                open_cv_image = np.array(bg)
                gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
                _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
                
                # 線の太らせすぎを防ぐため、kernelサイズを調整
                kernel = np.ones((2,2), np.uint8)
                dilated = cv2.dilate(binary, kernel, iterations=1)
                processed_img = cv2.bitwise_not(dilated)
                
                with st.spinner('AIが判定中...'):
                    results = reader.readtext(
                        processed_img, 
                        detail=0, 
                        allowlist='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
                        mag_ratio=1.5
                    )
                    recognized_text = "".join(results).replace(" ", "").lower()
                    correct_word = q_word.strip().lower()
                    
                    # 類似度の計算
                    similarity = difflib.SequenceMatcher(None, recognized_text, correct_word).ratio()
                    
                    # 判定の厳格化
                    # 1. 文字数が全く違う（2文字以上差がある）場合は推測とみなして弾く
                    len_diff = abs(len(recognized_text) - len(correct_word))
                    
                    if recognized_text == correct_word:
                        st.session_state.answer_status = ("success", f"正解: {correct_word}")
                    elif len_diff <= 1 and similarity >= 0.8:
                        # 文字数の差が少なく、かつ8割以上一致している場合のみ推測を許容
                        st.session_state.answer_status = ("success", f"正解！ (推測判定: {correct_word})")
                    else:
                        # 認識された文字が少なすぎたり多すぎたりする場合は不正解
                        st.session_state.answer_status = ("error", f"認識: {recognized_text if recognized_text else '判定不能'} / 正解: {correct_word}")
            else:
                st.warning("何か書いてください。")

    with col_prev:
        if st.button("⬅️ 前へ", use_container_width=True):
            if len(st.session_state.history) > 0:
                st.session_state.q_index = st.session_state.history.pop()
                st.session_state.pool_ptr = max(0, st.session_state.pool_ptr - 1)
                st.session_state.answer_status = None
                st.rerun()

    with col_next:
        if st.button("次へ ➡️", use_container_width=True):
            st.session_state.history.append(st.session_state.q_index)
            st.session_state.pool_ptr += 1
            if st.session_state.pool_ptr >= len(st.session_state.question_pool):
                random.shuffle(st.session_state.question_pool)
                st.session_state.pool_ptr = 0
            st.session_state.q_index = st.session_state.question_pool[st.session_state.pool_ptr]
            st.session_state.answer_status = None
            st.rerun()

    if st.session_state.answer_status:
        status, msg = st.session_state.answer_status
        if status == "success":
            st.success(msg)
            st.balloons()
        else:
            st.error(msg)
            if st.checkbox("AIがどう見たか確認"):
                st.image(processed_img, caption="AI解析用画像")
else:
    st.warning("問題データがありません。")

# サイドバー：学習メニュー
st.sidebar.divider()
if not df.empty:
    st.sidebar.write(f"進捗: {st.session_state.pool_ptr + 1} / {len(df)}")
    if st.sidebar.button("最初からやり直す 🔄"):
        indices = list(range(len(df)))
        random.shuffle(indices)
        st.session_state.question_pool = indices
        st.session_state.pool_ptr = 0
        st.session_state.q_index = st.session_state.question_pool[0]
        st.session_state.history = []
        st.session_state.answer_status = None
        st.rerun()