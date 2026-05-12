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

# ダークモードでもキャンバスのアイコン（消去、戻る等）を見やすくするための強力なCSS
st.markdown("""
    <style>
    /* タイトルの上の余白を消す */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
    }
    
    /* キャンバスのツールバーボタンを強制的に視認性の高いスタイルに固定 */
    div[data-testid="stCanvas"] button {
        background-color: #FFFFFF !important;  /* 背景を常に白に */
        color: #000000 !important;             /* アイコン色を常に黒に */
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        margin: 2px !important;
        opacity: 1.0 !important;               /* 透明度を無効化 */
    }
    
    /* ホバー時の色（少しグレーに） */
    div[data-testid="stCanvas"] button:hover {
        background-color: #EEEEEE !important;
    }

    /* キャンバスの外枠 */
    .stCanvasContainer {
        border: 2px solid #4a4a4a;
        border-radius: 8px;
        background-color: #ffffff;
    }
    
    /* 問題文のフォントサイズ調整 */
    .stAlert {
        padding: 0.5rem !important;
        margin-bottom: 0.5rem !important;
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
    
    # 1. 誤認補正（歴史用語に頻出する文字への変換）
    text = text.replace('+', 'ナ') 
    confused_chars = {
        'g': '9', 'q': '9', 'G': '6', 'b': '6',
        'o': '0', 'O': '0', 'I': '1', 'l': '1', 'i': '1',
        'Z': '2', 'z': '2', 'S': '5', 's': '5', 'y': 'り',
    }
    for old, new in confused_chars.items():
        text = text.replace(old, new)

    # 全角・半角の統一
    text = jaconv.z2h(text, kana=False, ascii=True, digit=True)
    text = jaconv.h2z(text, kana=True, ascii=False, digit=False)
    
    # のばし棒（ー）の正規化
    text = re.sub(r'[˗‐‑‒–—―⁃⁻−▬─━➖ーｰ-]', 'ー', text)
    
    # アルファベットの完全除去
    text = re.sub(r'[a-zA-Z]', '', text)
    
    # ひらがな・カタカナ・漢字・数字・のばし棒 以外をすべて除去
    text = re.sub(r'[^0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFー]', '', text)
    
    return text.lower().strip()

# --- 比較関数 ---
def judge_answer(recognized, possible_answers):
    rec_norm = normalize_text(recognized)
    
    for ans in possible_answers:
        ans_norm = normalize_text(ans)
        
        # 1. 基本的な一致確認
        if rec_norm == ans_norm:
            return True
        
        # 2. 誤認しやすいバリエーションの生成
        variants = [rec_norm]
        
        # にんべん系の誤認補正 (「偶」が「僧」や「伸」になるケース)
        # 正解に「偶」が含まれる場合、認識結果の「僧」や「伸」を「偶」に置換してみる
        if '偶' in ans_norm:
            if '僧' in rec_norm: variants.append(rec_norm.replace('僧', '偶'))
            if '伸' in rec_norm: variants.append(rec_norm.replace('伸', '偶'))
        
        # 「ナ」←→「十」の補完
        if 'ナ' in rec_norm: variants.append(rec_norm.replace('ナ', '十'))
        if '十' in rec_norm: variants.append(rec_norm.replace('十', 'ナ'))
        
        # 「ー」←→「一」の補完
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
        except:
            continue
    return pd.DataFrame(columns=["question", "answer"])

df = load_data()

# --- セッション状態 ---
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
st.title("📝 歴史 手書き採点")

if not df.empty:
    q_idx = st.session_state.question_pool[st.session_state.current_pool_idx]
    question = df.iloc[q_idx]["question"]
    raw_answer = str(df.iloc[q_idx]["answer"])

    st.info(f"**問題:** {question}")

    # 上部に操作系をまとめる
    col_s1, col_s2, col_btn = st.columns([2, 2, 1])
    with col_s1:
        stroke_width = st.select_slider("ペンの太さ", options=range(1, 16), value=6)
    with col_s2:
        st.write("") # スペース調整
    with col_btn:
        if st.button("🔄 次へ", use_container_width=True):
            get_next_question()

    # キャンバス
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=280,
        width=700,
        drawing_mode="freedraw",
        key=f"canvas_q_{st.session_state.canvas_key_id}",
        update_streamlit=True,
    )

    if st.button("✅ 採点する", use_container_width=True, type="primary"):
        if canvas_result.image_data is not None:
            with st.spinner("判定中..."):
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
                    
                    # 記号を除去した認識結果
                    clean_text = normalize_text(recognized_raw)
                    st.session_state.recognized_text = clean_text if clean_text else recognized_raw
                    
                    possible_answers = [a.strip() for a in raw_answer.split('/')]
                    if judge_answer(recognized_raw, possible_answers):
                        st.session_state.result = "正解"
                    else:
                        st.session_state.result = "不正解"
                except Exception as e:
                    st.error(f"エラー: {e}")

    # 結果表示
    if st.session_state.result:
        if st.session_state.result == "正解":
            st.balloons()
            st.success(f"🎊 **正解！** (読み: {st.session_state.recognized_text})")
        else:
            st.error(f"😭 **不正解** (読み: {st.session_state.recognized_text})")
            st.info(f"正解: **{raw_answer.replace('/', ' / ')}**")
        st.caption(f"進捗: {st.session_state.current_pool_idx + 1} / {len(df)}")
else:
    st.error("問題データがありません。")