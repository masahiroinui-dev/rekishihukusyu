import streamlit as st
from streamlit_drawable_canvas import st_canvas
import pandas as pd
from PIL import Image, ImageOps
import random
import numpy as np
import re

# ライブラリのインポートチェック
try:
    import easyocr
    import jaconv
except ModuleNotFoundError:
    st.error("必要なライブラリ（easyocr または jaconv）が見つかりません。requirements.txt が正しく配置されているか確認してください。")
    st.stop()

# --- 設定 ---
st.set_page_config(page_title="歴史・手書き自動採点アプリ", layout="centered")

# ダークモードでもキャンバスのアイコン（消去、戻る等）を見やすくするためのCSS
st.markdown("""
    <style>
    /* キャンバスのツールバーアイコンをダークモードでも白っぽく強調 */
    [data-testid="stCanvas"] button {
        background-color: #f0f2f6 !important;
        color: #31333F !important;
        border-radius: 4px;
        margin: 2px;
    }
    /* キャンバス自体に外枠をつけて境界をわかりやすくする */
    .stCanvasContainer {
        border: 2px solid #4a4a4a;
        border-radius: 8px;
        background-color: #ffffff;
    }
    </style>
    """, unsafe_allow_html=True)

# OCRリーダーの初期化
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr_reader()

# --- テキスト正規化関数 ---
def normalize_text(text):
    if not isinstance(text, str):
        text = str(text)
    
    # OCRが「ナ」や漢字の「十」を「+」と誤認するケースの補正
    text = text.replace('+', 'ナ') 
    
    # 全角英数字を半角に、半角カタカナを全角に変換
    text = jaconv.z2h(text, kana=False, ascii=True, digit=True)
    text = jaconv.h2z(text, kana=True, ascii=False, digit=False)
    
    # のばし棒・ハイフン・漢字の「一」の正規化
    text = re.sub(r'[˗‐‑‒–—―⁃⁻−▬─━➖ーｰ-]', 'ー', text)
    
    # 空白、改行、記号の除去
    text = re.sub(r'[\s\t\n\r　.,．，、。！!？?]', '', text)
    
    return text.lower().strip()

# --- 文脈判断付き比較関数 ---
def judge_answer(recognized, possible_answers):
    rec_norm = normalize_text(recognized)
    
    for ans in possible_answers:
        ans_norm = normalize_text(ans)
        
        if rec_norm == ans_norm:
            return True
            
        variants = [rec_norm]
        if 'ナ' in rec_norm: variants.append(rec_norm.replace('ナ', '十'))
        if '十' in rec_norm: variants.append(rec_norm.replace('十', 'ナ'))
        
        current_variants = list(variants)
        for v in current_variants:
            if 'ー' in v: variants.append(v.replace('ー', '一'))
            if '一' in v: variants.append(v.replace('一', 'ー'))
            
        if any(v == ans_norm for v in variants):
            return True
            
    return False

# --- データ読み込み ---
@st.cache_data
def load_data():
    csv_file = "rekishi_questions.xlsx - Sheet1.csv"
    encodings = ['utf-8', 'shift_jis', 'cp932', 'euc-jp']
    
    for enc in encodings:
        try:
            df = pd.read_csv(csv_file, header=None, names=["question", "answer"], encoding=enc)
            return df
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    return pd.DataFrame(columns=["question", "answer"])

df = load_data()

# --- セッション状態の初期化 ---
if "question_pool" not in st.session_state:
    indices = list(range(len(df)))
    random.shuffle(indices)
    st.session_state.question_pool = indices

if "current_pool_idx" not in st.session_state:
    st.session_state.current_pool_idx = 0

if "result" not in st.session_state:
    st.session_state.result = None
if "recognized_text" not in st.session_state:
    st.session_state.recognized_text = ""
if "canvas_key_id" not in st.session_state:
    st.session_state.canvas_key_id = 0

# --- 問題の取得 ---
def get_next_question():
    st.session_state.current_pool_idx += 1
    if st.session_state.current_pool_idx >= len(st.session_state.question_pool):
        random.shuffle(st.session_state.question_pool)
        st.session_state.current_pool_idx = 0
    
    st.session_state.result = None
    st.session_state.recognized_text = ""
    st.session_state.canvas_key_id += 1
    st.rerun()

# --- メインコンテンツ ---
st.title("📝 歴史 手書き自動採点")
st.write("キャンバスサイズを拡大しました。大きな文字で記入してください。")

if not df.empty:
    q_idx = st.session_state.question_pool[st.session_state.current_pool_idx]
    question = df.iloc[q_idx]["question"]
    raw_answer = str(df.iloc[q_idx]["answer"])

    st.info(f"**問題:** {question}")

    # レイアウトの調整
    col_ctrl, col_canvas = st.columns([1, 4])
    
    with col_ctrl:
        stroke_width = st.slider("ペンの太さ", 1, 15, 6)
        if st.button("🔄 次の問題"):
            get_next_question()

    with col_canvas:
        # 手書きキャンバス（サイズを拡大：Height 250 -> 350, Width 500 -> 700）
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=stroke_width,
            stroke_color="#000000",
            background_color="#ffffff",
            height=350,
            width=700,
            drawing_mode="freedraw",
            key=f"canvas_q_{st.session_state.canvas_key_id}",
            update_streamlit=True,
        )

    if st.button("✅ 採点する", use_container_width=True):
        if canvas_result.image_data is not None:
            with st.spinner("AIが文字を読み取っています..."):
                img_data = canvas_result.image_data.astype('uint8')
                img = Image.fromarray(img_data).convert('RGB')
                
                gray_img = ImageOps.grayscale(img)
                inverted_img = ImageOps.invert(gray_img)
                bbox = inverted_img.getbbox()
                
                if bbox:
                    cropped_img = img.crop((max(0, bbox[0]-15), max(0, bbox[1]-15), min(img.width, bbox[2]+15), min(img.height, bbox[3]+15)))
                    img_np = np.array(cropped_img)
                else:
                    img_np = np.array(img)
                
                try:
                    ocr_results = reader.readtext(img_np, detail=0, paragraph=False, x_ths=1.0)
                    recognized_raw = "".join(ocr_results)
                    st.session_state.recognized_text = recognized_raw
                    
                    possible_answers = [a.strip() for a in raw_answer.split('/')]
                    
                    if judge_answer(recognized_raw, possible_answers):
                        st.session_state.result = "正解"
                    else:
                        st.session_state.result = "不正解"
                except Exception as e:
                    st.error(f"エラー: {e}")

    # 結果表示
    if st.session_state.result:
        st.divider()
        if st.session_state.result == "正解":
            st.balloons()
            st.success(f"🎊 **正解です！** (読み取り: {st.session_state.recognized_text})")
        else:
            st.error(f"😭 **不正解...** (読み取り: {st.session_state.recognized_text})")
            display_ans = raw_answer.replace('/', ' または ')
            st.info(f"正解は **{display_ans}** です。")
            
        st.caption(f"現在の進捗: {st.session_state.current_pool_idx + 1} / {len(df)} 問目")
else:
    st.error("問題データが読み込めていません。")

st.caption("Powered by Streamlit & EasyOCR")