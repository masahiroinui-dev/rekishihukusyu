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

# OCRリーダーの初期化
@st.cache_resource
def load_ocr_reader():
    # ja: 日本語, en: 英語
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr_reader()

# --- テキスト正規化関数 ---
def normalize_text(text):
    if not isinstance(text, str):
        text = str(text)
    # 全角英数字を半角に、半角カタカナを全角に変換
    text = jaconv.z2h(text, kana=False, ascii=True, digit=True) # 英数字を半角へ
    text = jaconv.h2z(text, kana=True, ascii=False, digit=False) # カタカナを全角へ
    
    # のばし棒・ハイフンの統一
    text = re.sub(r'[˗‐‑‒–—―⁃⁻−▬─━➖ーｰ-]', 'ー', text)
    
    # 空白、改行、記号の除去
    text = re.sub(r'[\s\t\n\r　.,．，、。！!？?]', '', text)
    
    return text.lower().strip()

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
    # 全問題のインデックスをシャッフルして保持
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
    # プールを使い切ったら再シャッフル
    if st.session_state.current_pool_idx >= len(st.session_state.question_pool):
        random.shuffle(st.session_state.question_pool)
        st.session_state.current_pool_idx = 0
    
    st.session_state.result = None
    st.session_state.recognized_text = ""
    st.session_state.canvas_key_id += 1
    st.rerun()

# --- メインコンテンツ ---
st.title("📝 歴史 手書き自動採点")
st.write("精度の向上と出題順序の最適化を行いました。")

if not df.empty:
    q_idx = st.session_state.question_pool[st.session_state.current_pool_idx]
    question = df.iloc[q_idx]["question"]
    raw_answer = str(df.iloc[q_idx]["answer"])

    st.info(f"**問題:** {question}")

    col_ctrl, col_canvas = st.columns([1, 3])
    
    with col_ctrl:
        stroke_width = st.slider("ペンの太さ", 1, 15, 6)
        if st.button("🔄 次の問題へ"):
            get_next_question()

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
            with st.spinner("AIが文字を読み取っています..."):
                # 画像の取得と前処理
                img_data = canvas_result.image_data.astype('uint8')
                img = Image.fromarray(img_data).convert('RGB')
                
                # 余白をトリミングして文字を強調（認識率向上）
                # 一旦グレースケールにしてバウンディングボックスを探す
                gray_img = ImageOps.grayscale(img)
                inverted_img = ImageOps.invert(gray_img)
                bbox = inverted_img.getbbox()
                
                if bbox:
                    # 少し余白を持たせてクロップ
                    cropped_img = img.crop((max(0, bbox[0]-10), max(0, bbox[1]-10), min(img.width, bbox[2]+10), min(img.height, bbox[3]+10)))
                    # 認識しやすいサイズにリサイズ
                    img_np = np.array(cropped_img)
                else:
                    img_np = np.array(img)
                
                try:
                    # OCR実行
                    # decoder='wordbeamsearch' は単語のまとまりを重視するが、辞書が必要なため
                    # 今回は x_ths (横方向の結合しきい値) を少し上げて文字の切れを防ぐ
                    ocr_results = reader.readtext(img_np, detail=0, paragraph=False, x_ths=1.0)
                    recognized_raw = "".join(ocr_results)
                    
                    # 認識結果の正規化
                    normalized_rec = normalize_text(recognized_raw)
                    st.session_state.recognized_text = recognized_raw
                    
                    # 正解の正規化
                    possible_answers = [normalize_text(a) for a in raw_answer.split('/')]
                    
                    if normalized_rec in possible_answers:
                        st.session_state.result = "正解"
                    else:
                        # 部分一致の救済措置（オプション: 必要に応じて有効化）
                        # if any(ans in normalized_rec for ans in possible_answers):
                        #     st.session_state.result = "正解"
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

st.caption("Powered by Streamlit & EasyOCR (Enhanced Recognition)")