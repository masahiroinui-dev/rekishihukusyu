import streamlit as st
from streamlit_drawable_canvas import st_canvas
import pandas as pd
from PIL import Image, ImageOps
import random
import numpy as np
import re
import cv2
import os

# ライブラリのインポートチェック
try:
    import easyocr
    import jaconv
except ModuleNotFoundError:
    st.error("必要なライブラリが見つかりません。")
    st.stop()

# --- 設定 ---
st.set_page_config(page_title="歴史・手書き自動採点アプリ", layout="centered")

# CSS: UI調整（ダークモード対応・ボタン視認性向上）
st.markdown("""
    <style>
    .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    div[data-testid="stCanvas"] button {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        margin: 2px !important;
    }
    .stCanvasContainer { border: 2px solid #4a4a4a; border-radius: 8px; background-color: #ffffff; }
    .stAlert { padding: 0.5rem !important; margin-bottom: 0.5rem !important; }
    </style>
    """, unsafe_allow_html=True)

# OCRリーダーの初期化
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr_reader()

# --- 画像前処理 (OpenCV) ---
def preprocess_image(img_np):
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 11, 2
    )
    final_img = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
    return final_img

# --- テキスト正規化関数 ---
def normalize_text(text):
    if not isinstance(text, str): text = str(text)
    text = text.replace('+', 'ナ') 
    confused_chars = {
        'g': '9', 'q': '9', 'G': '6', 'b': '6',
        'o': '0', 'O': '0', 'I': '1', 'l': '1', 'i': '1',
        'Z': '2', 'z': '2', 'S': '5', 's': '5', 'y': 'り',
    }
    for old, new in confused_chars.items():
        text = text.replace(old, new)

    text = jaconv.z2h(text, kana=False, ascii=True, digit=True)
    text = jaconv.h2z(text, kana=True, ascii=False, digit=False)
    text = re.sub(r'[˗‐‑‒–—―⁃⁻−▬─━➖ーｰ-]', 'ー', text)
    text = re.sub(r'[a-zA-Z]', '', text)
    text = re.sub(r'[^0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFー]', '', text)
    return text.lower().strip()

# --- 比較関数 ---
def judge_answer(recognized, possible_answers):
    rec_norm = normalize_text(recognized)
    for ans in possible_answers:
        ans_norm = normalize_text(ans)
        if rec_norm == ans_norm: return True
        variants = [rec_norm]
        if '偶' in ans_norm:
            if '僧' in rec_norm: variants.append(rec_norm.replace('僧', '偶'))
            if '伸' in rec_norm: variants.append(rec_norm.replace('伸', '偶'))
        if 'ナ' in rec_norm: variants.append(rec_norm.replace('ナ', '十'))
        if '十' in rec_norm: variants.append(rec_norm.replace('十', 'ナ'))
        current_variants = list(variants)
        for v in current_variants:
            if 'ー' in v: variants.append(v.replace('ー', '一'))
            if '一' in v: variants.append(v.replace('一', 'ー'))
        if any(v == ans_norm for v in variants): return True
    return False

# --- データ読み込み（エラーハンドリング強化） ---
@st.cache_data
def load_data():
    # 正確なファイル名。実際のファイル名と完全に一致している必要があります。
    csv_file = "rekishi_questions.xlsx - Sheet1.csv"
    
    # 読み込みを試みるエンコーディングのリスト
    encodings = ['utf-8', 'cp932', 'shift_jis', 'utf-8-sig']
    
    if os.path.exists(csv_file):
        for enc in encodings:
            try:
                # header=Noneの場合、列名を指定する
                df = pd.read_csv(csv_file, header=None, names=["question", "answer"], encoding=enc)
                # 空白行を除去
                df = df.dropna()
                if not df.empty:
                    return df
            except Exception:
                continue
    
    # ファイルが見つからない、または読み込めない場合のサンプルデータ
    st.warning(f"CSVファイル '{csv_file}' が読み込めませんでした。サンプルデータを表示します。")
    sample_data = {
        "question": ["江戸幕府を開いたのは誰？", "1192年に作られた幕府は？", "聖徳太子が定めた制度は？"],
        "answer": ["徳川家康", "鎌倉幕府", "冠位十二階"]
    }
    return pd.DataFrame(sample_data)

df = load_data()

# --- セッション ---
if "question_pool" not in st.session_state:
    indices = list(range(len(df)))
    random.shuffle(indices)
    st.session_state.question_pool = indices
if "current_pool_idx" not in st.session_state: st.session_state.current_pool_idx = 0
if "result" not in st.session_state: st.session_state.result = None
if "recognized_text" not in st.session_state: st.session_state.recognized_text = ""
if "canvas_key_id" not in st.session_state: st.session_state.canvas_key_id = 0

def get_next_question():
    st.session_state.current_pool_idx = (st.session_state.current_pool_idx + 1) % len(df)
    st.session_state.result = None
    st.session_state.recognized_text = ""
    st.session_state.canvas_key_id += 1
    st.rerun()

# --- UI ---
st.title("📝 歴史 手書き採点 (OpenCV強化版)")

if not df.empty:
    q_idx = st.session_state.question_pool[st.session_state.current_pool_idx]
    question = df.iloc[q_idx]["question"]
    raw_answer = str(df.iloc[q_idx]["answer"])

    st.info(f"**問題:** {question}")

    col_s1, col_s2, col_btn = st.columns([2, 2, 1])
    with col_s1: stroke_width = st.select_slider("ペンの太さ", options=range(1, 16), value=6)
    with col_btn:
        if st.button("🔄 次へ", use_container_width=True): get_next_question()

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=280, width=700,
        drawing_mode="freedraw",
        key=f"canvas_q_{st.session_state.canvas_key_id}",
        update_streamlit=True,
    )

    if st.button("✅ 採点する", use_container_width=True, type="primary"):
        if canvas_result.image_data is not None:
            with st.spinner("OpenCVで画像を最適化中..."):
                img_data = canvas_result.image_data.astype('uint8')
                img_rgb = cv2.cvtColor(img_data, cv2.COLOR_RGBA2RGB)
                
                # 1. トリミング
                gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
                inv = cv2.bitwise_not(gray)
                coords = cv2.findNonZero(inv)
                
                if coords is not None:
                    x, y, w, h = cv2.boundingRect(coords)
                    pad = 15
                    img_cropped = img_rgb[max(0, y-pad):min(img_rgb.shape[0], y+h+pad), 
                                          max(0, x-pad):min(img_rgb.shape[1], x+w+pad)]
                    
                    processed_img = preprocess_image(img_cropped)
                    
                    try:
                        ocr_results = reader.readtext(processed_img, detail=0)
                        recognized_raw = "".join(ocr_results)
                        clean_text = normalize_text(recognized_raw)
                        st.session_state.recognized_text = clean_text if clean_text else recognized_raw
                        
                        possible_answers = [a.strip() for a in raw_answer.split('/')]
                        st.session_state.result = "正解" if judge_answer(recognized_raw, possible_answers) else "不正解"
                    except Exception as e:
                        st.error(f"OCR Error: {e}")
                else:
                    st.warning("文字が記入されていません。")

    if st.session_state.result:
        if st.session_state.result == "正解":
            st.balloons()
            st.success(f"🎊 **正解！** (読み: {st.session_state.recognized_text})")
        else:
            st.error(f"😭 **不正解** (読み: {st.session_state.recognized_text})")
            st.info(f"正解: **{raw_answer.replace('/', ' / ')}**")
else:
    st.error("問題データがありません。CSVファイルがプログラムと同じフォルダにあるか確認してください。")