import streamlit as st
from streamlit_drawable_canvas import st_canvas
import pandas as pd
from PIL import Image
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
    # Streamlit CloudのCPU環境を想定
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr_reader()

# --- テキスト正規化関数 ---
def normalize_text(text):
    if not isinstance(text, str):
        text = str(text)
    # 全角英数字を半角に、半角カタカナを全角に変換
    text = jaconv.z2h(text, kana=False, ascii=True, digit=True) # 英数字を半角へ
    text = jaconv.h2z(text, kana=True, ascii=False, digit=False) # カタカナを全角へ
    
    # のばし棒・ハイフンの統一 (色々な種類を「ー」に統一)
    text = re.sub(r'[˗‐‑‒–—―⁃⁻−▬─━➖ーｰ-]', 'ー', text)
    
    # 空白、改行、記号の除去
    text = re.sub(r'[\s\t\n\r　.,．，、。！!？?]', '', text)
    
    return text.lower().strip()

# --- データ読み込み（文字コードエラー対策版） ---
@st.cache_data
def load_data():
    csv_file = "rekishi_questions.xlsx - Sheet1.csv"
    # 試行するエンコーディングのリスト
    encodings = ['utf-8', 'shift_jis', 'cp932', 'euc-jp']
    
    for enc in encodings:
        try:
            df = pd.read_csv(csv_file, header=None, names=["question", "answer"], encoding=enc)
            return df
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        except Exception as e:
            st.error(f"予期せぬエラー: {e}")
            break
            
    st.error(f"問題データ（{csv_file}）の読み込みに失敗しました。文字コードが対応していないか、ファイルが存在しません。")
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
st.write("表記ゆれ対応版 (全角・半角・のばし棒を自動補正)")

if not df.empty:
    # データのクリーンアップ（NaN対策）
    question = df.iloc[st.session_state.current_q_idx]["question"]
    raw_answer = str(df.iloc[st.session_state.current_q_idx]["answer"])

    st.markdown(f"### 問題: {question}")

    col_ctrl, col_canvas = st.columns([1, 3])
    
    with col_ctrl:
        stroke_width = st.slider("ペンの太さ", 1, 15, 7)
        if st.button("🔄 次の問題へ"):
            st.session_state.current_q_idx = random.randint(0, len(df) - 1)
            st.session_state.result = None
            st.session_state.recognized_text = ""
            st.session_state.canvas_key_id += 1 
            st.rerun()

    with col_canvas:
        # 手書きキャンバス
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
            with st.spinner("判定中..."):
                img_data = canvas_result.image_data.astype('uint8')
                img_rgb = Image.fromarray(img_data).convert('RGB')
                img_np = np.array(img_rgb)
                
                try:
                    # OCR実行
                    ocr_results = reader.readtext(img_np, detail=0)
                    recognized_raw = "".join(ocr_results)
                    
                    # 認識結果の正規化
                    normalized_rec = normalize_text(recognized_raw)
                    st.session_state.recognized_text = recognized_raw # 表示用
                    
                    # 正解データの分割と正規化 (スラッシュ区切りに対応)
                    possible_answers = [normalize_text(a) for a in raw_answer.split('/')]
                    
                    # 判定
                    if normalized_rec in possible_answers:
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
            st.success(f"🎊 **正解です！** (認識: {st.session_state.recognized_text})")
        else:
            st.error(f"😭 **不正解...** (認識: {st.session_state.recognized_text})")
            display_ans = raw_answer.replace('/', ' または ')
            st.info(f"正解は **{display_ans}** です。")
else:
    st.error("問題データが読み込めていません。")

st.caption("Powered by Streamlit & EasyOCR with jaconv")