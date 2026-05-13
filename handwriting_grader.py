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

# CSS: UI調整
st.markdown("""
    <style>
    .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; }
    h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem !important; }
    div[data-testid="stCanvas"] button {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        margin: 2px !important;
    }
    .stCanvasContainer { border: 2px solid #4a4a4a; border-radius: 8px; background-color: #ffffff; }
    .stAlert { padding: 0.4rem !important; margin-bottom: 0.5rem !important; }
    [data-testid="stVerticalBlock"] > div { margin-top: -0.3rem !important; }
    .stButton > button { margin-top: 0.2rem !important; }
    </style>
    """, unsafe_allow_html=True)

# OCRリーダーの初期化
@st.cache_resource
def load_ocr_reader():
    # 認識精度を上げるため、モデルのロードをキャッシュ
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr_reader()

# --- 画像前処理 (OpenCV) ---
def preprocess_image(img_np):
    # グレースケール化
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # ノイズ除去（点描のようなノイズを消す）
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    
    # コントラスト強調 (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # 適応的二値化（国構えや複雑な漢字の潰れを防ぐ）
    thresh = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 15, 5
    )
    
    # 少しだけ線を太くして認識しやすくする（膨張処理）
    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.erode(thresh, kernel, iterations=1) # 黒文字なのでerodeで太くなる
    
    final_img = cv2.cvtColor(dilated, cv2.COLOR_GRAY2RGB)
    return final_img

# --- テキスト正規化関数 ---
def normalize_text(text):
    if not isinstance(text, str): text = str(text)
    
    # 歴史特有の誤認補正（OCRが間違えやすいパターン）
    replacements = {
        '+': 'ナ',
        '|': '',
        'I': '1',
        'l': '1',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = jaconv.z2h(text, kana=False, ascii=True, digit=True)
    text = jaconv.h2z(text, kana=True, ascii=False, digit=False)
    text = re.sub(r'[˗‐‑‒–—―⁃⁻−▬─━➖ーｰ-]', 'ー', text)
    text = re.sub(r'[a-zA-Z]', '', text)
    # 記号排除
    text = re.sub(r'[^0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFー]', '', text)
    return text.lower().strip()

# --- 比較関数 (難読漢字補正強化版) ---
def judge_answer(recognized, possible_answers):
    rec_norm = normalize_text(recognized)
    
    # 歴史用語特有の「OCRが間違えやすい漢字」の対応表
    # キー：正解に含まれるべき漢字, 値：OCRが誤認しやすい漢字のリスト
    kanji_fix_map = {
        '隋': ['随', '晴', '階', '陸', '隊', '隔'],
        '徭': ['揺', '採', '様', '徭', '描'],
        '殷': ['段', '殻', '毅', '殺'],
        '鐸': ['沢', '訳', '輝', '解'],
        '珎': ['珍', '玲', '弥'],
        '魏': ['魂', '塊', '魔', '醜'],
        '偶': ['僧', '伸', '保', '個'],
        '国': ['因', '固', '圀', '目'],
        '団': ['困', '回', '園']
    }

    for ans in possible_answers:
        ans_norm = normalize_text(ans)
        if rec_norm == ans_norm: return True
        
        variants = [rec_norm]
        
        # 難読漢字の補正ロジック
        for correct_kanji, error_list in kanji_fix_map.items():
            if correct_kanji in ans_norm:
                for error_kanji in error_list:
                    if error_kanji in rec_norm:
                        variants.append(rec_norm.replace(error_kanji, correct_kanji))
        
        # 特殊記号補正
        if 'ナ' in rec_norm: variants.append(rec_norm.replace('ナ', '十'))
        if '十' in rec_norm: variants.append(rec_norm.replace('十', 'ナ'))
        
        current_variants = list(variants)
        for v in current_variants:
            if 'ー' in v: variants.append(v.replace('ー', '一'))
            if '一' in v: variants.append(v.replace('一', 'ー'))
            
        if any(v == ans_norm for v in variants): return True
    return False

# --- データ読み込み ---
@st.cache_data
def load_data():
    csv_file = "rekishi_questions.xlsx - Sheet1.csv"
    encodings = ['utf-8', 'cp932', 'shift_jis', 'utf-8-sig']
    if os.path.exists(csv_file):
        for enc in encodings:
            try:
                df = pd.read_csv(csv_file, header=None, names=["question", "answer"], encoding=enc)
                df = df.dropna()
                if not df.empty:
                    return df
            except Exception:
                continue
    
    st.warning("サンプルデータを表示します。")
    sample_data = {
        "question": ["『和同開珎』の最後の漢字は？", "聖徳太子が送った使節が向かった国は？（漢字1文字）", "魏志倭人伝の『魏』を書けますか？"],
        "answer": ["珎", "隋", "魏"]
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
st.title("📝 歴史 手書き採点")

if not df.empty:
    q_idx = st.session_state.question_pool[st.session_state.current_pool_idx]
    question = df.iloc[q_idx]["question"]
    raw_answer = str(df.iloc[q_idx]["answer"])

    st.info(f"**問題:** {question}")

    col_s1, col_btn = st.columns([3, 1])
    with col_s1:
        stroke_width = st.select_slider("ペンの太さ", options=range(1, 11), value=6)
    with col_btn:
        if st.button("🔄 次へ", use_container_width=True):
            get_next_question()

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=200, 
        width=700,
        drawing_mode="freedraw",
        key=f"canvas_q_{st.session_state.canvas_key_id}",
        update_streamlit=True,
    )

    if st.button("✅ 採点する", use_container_width=True, type="primary"):
        if canvas_result.image_data is not None:
            with st.spinner("高度な文字解析中..."):
                img_data = canvas_result.image_data.astype('uint8')
                img_rgb = cv2.cvtColor(img_data, cv2.COLOR_RGBA2RGB)
                
                # 文字範囲の抽出
                gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
                inv = cv2.bitwise_not(gray)
                coords = cv2.findNonZero(inv)
                
                if coords is not None:
                    x, y, w, h = cv2.boundingRect(coords)
                    pad = 20
                    img_cropped = img_rgb[max(0, y-pad):min(img_rgb.shape[0], y+h+pad), 
                                          max(0, x-pad):min(img_rgb.shape[1], x+w+pad)]
                    
                    # OpenCV強化処理
                    processed_img = preprocess_image(img_cropped)
                    
                    try:
                        # decoderを'wordbeamsearch'等にすると精度が変わるが、標準でもparagraph=Falseで1単語に集中させる
                        ocr_results = reader.readtext(processed_img, detail=0, paragraph=False)
                        recognized_raw = "".join(ocr_results)
                        
                        # 内部的なマッチング
                        possible_answers = [a.strip() for a in raw_answer.split('/')]
                        is_correct = judge_answer(recognized_raw, possible_answers)
                        
                        # 表示用のテキスト
                        clean_text = normalize_text(recognized_raw)
                        st.session_state.recognized_text = clean_text if clean_text else "認識不能"
                        st.session_state.result = "正解" if is_correct else "不正解"
                    except Exception as e:
                        st.error(f"OCR Error: {e}")
                else:
                    st.warning("文字が記入されていません。")

    if st.session_state.result:
        if st.session_state.result == "正解":
            st.balloons()
            st.success(f"🎊 **正解！** (認識: {st.session_state.recognized_text})")
        else:
            st.error(f"😭 **不正解** (認識: {st.session_state.recognized_text})")
            st.info(f"正解: **{raw_answer.replace('/', ' / ')}**")
else:
    st.error("問題データがありません。")