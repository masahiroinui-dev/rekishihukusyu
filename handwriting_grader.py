import streamlit as st
from streamlit_drawable_canvas import st_canvas
import pandas as pd
from PIL import Image, ImageOps
import random
import numpy as np
import re
import cv2
import os
from datetime import datetime

# --- 設定 ---
st.set_page_config(page_title="歴史・手書き自動採点アプリ", layout="centered")

# CSS: タブレット横向きで1画面に収めるためのコンパクト設計＆ダークモード対応
st.markdown("""
    <style>
    /* 全体の余白を極限まで削減 */
    .block-container { padding-top: 0.5rem !important; padding-bottom: 0rem !important; }
    
    /* ヘッダー・タイトルのサイズ縮小 */
    h1 { font-size: 1.4rem !important; margin-bottom: 0.2rem !important; margin-top: 0rem !important; }
    h3 { font-size: 1.1rem !important; margin-top: 0.2rem !important; margin-bottom: 0.2rem !important; }

    /* キャンバスのツールバーボタンを強制的に視認性の高いスタイルに固定 */
    div[data-testid="stCanvas"] button {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 4px !important;
        margin: 1px !important;
        padding: 2px !important;
    }
    
    /* キャンバスの外枠 */
    .stCanvasContainer { border: 2px solid #4a4a4a; border-radius: 8px; background-color: #ffffff; }
    
    /* Alertやウィジェット間の余白を削減 */
    .stAlert { padding: 0.3rem 0.5rem !important; margin-bottom: 0.3rem !important; }
    
    /* ログイン・成績表示エリアのスタイル */
    .stats-box {
        background-color: #f0f2f6;
        padding: 0.4rem;
        border-radius: 6px;
        margin-top: 0.3rem;
        font-size: 0.85rem;
        color: #31333F;
        border-left: 5px solid #4CAF50;
    }
    </style>
    """, unsafe_allow_html=True)

# --- EasyOCR のセットアップ ---
try:
    import easyocr
    import jaconv
except ModuleNotFoundError:
    st.error("必要なライブラリ（easyocr または jaconv）が見つかりません。")
    st.stop()

@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['ja', 'en'], gpu=False)

reader = load_ocr_reader()

# --- 保存用の履歴CSVファイルのパス ---
LOG_FILE = "study_log.csv"

# --- 画像前処理 (OpenCV) ---
def preprocess_image(img_np):
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    thresh = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 15, 5
    )
    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.erode(thresh, kernel, iterations=1)
    return cv2.cvtColor(dilated, cv2.COLOR_GRAY2RGB)

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
    
    return re.sub(r'[^0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFー]', '', text).lower().strip()

# --- 比較判定関数 ---
def judge_answer(recognized, possible_answers):
    rec_norm = normalize_text(recognized)
    
    # 手書き特有の誤認・難読漢字救済マップ
    kanji_fix_map = {
        '隋': ['随', '晴', '階', '陸', '隊', '隔'],
        '徭': ['揺', '採', '様', '徭', '描'],
        '殷': ['段', '殻', '毅', '殺'],
        '鐸': ['沢', '訳', '輝', '解'],
        '珎': ['珍', '玲', '弥'],
        '魏': ['魂', '塊', '魔', '醜'],
        '偶': ['僧', '伸', '保', '個'],
        '国': ['因', '固', '圀', '目'],
        '団': ['困', '回', '園'],
        # 🛡️ 「栄」と「宋」の見分け・誤認対策
        '宋': ['栄', '宗', '崇', '室', '案', '客', '宇'],
        '栄': ['宋', '宮', '学', '楽', '堂', '木', '染'],
        # 🛡️ 超高難読字「鸞（親鸞など）」の誤認・画数潰れ対策
        '鸞': ['驚', '蘭', '葛', '鷲', '藍', '難', 'らん', 'ラン', '属', '恋', '糸']
    }
    
    for ans in possible_answers:
        ans_norm = normalize_text(ans)
        if rec_norm == ans_norm: return True
        
        variants = [rec_norm]
        for correct_kanji, error_list in kanji_fix_map.items():
            if correct_kanji in ans_norm:
                for error_kanji in error_list:
                    if error_kanji in rec_norm:
                        variants.append(rec_norm.replace(error_kanji, correct_kanji))
                        
        if 'ナ' in rec_norm: variants.append(rec_norm.replace('ナ', '十'))
        if '十' in rec_norm: variants.append(rec_norm.replace('十', 'ナ'))
        
        current_variants = list(variants)
        for v in current_variants:
            if 'ー' in v: variants.append(v.replace('ー', '一'))
            if '一' in v: variants.append(v.replace('一', 'ー'))
            
        if any(v == ans_norm for v in variants): return True
    return False

# --- CSV問題データのロードとフィルタリング (q0187〜q0426) ---
@st.cache_data
def load_data():
    csv_file = "rekishi_questions.xlsx - Sheet1.csv"
    encodings = ['utf-8', 'cp932', 'shift_jis', 'utf-8-sig']
    
    # 失敗時のダミーデータ生成（q0187〜q0426）
    def create_fallback_data():
        dummy_data = []
        for i in range(187, 427):  # 187 から 426
            dummy_data.append([f"q{i:04d}", f"【テスト問題 {i}】織田信長が明智光秀に襲われた京都のお寺はどこか？(答え:本能寺)", "本能寺"])
        df_fallback = pd.DataFrame(dummy_data, columns=["id", "question", "answer"])
        return df_fallback

    if os.path.exists(csv_file):
        for enc in encodings:
            try:
                temp_df = pd.read_csv(csv_file, header=None, nrows=5, encoding=enc)
                col_count = temp_df.shape[1]
                
                if col_count >= 3:
                    df = pd.read_csv(csv_file, header=None, names=["id", "question", "answer"], usecols=[0, 1, 2], encoding=enc)
                else:
                    df = pd.read_csv(csv_file, header=None, names=["question", "answer"], usecols=[0, 1], encoding=enc)
                    df.insert(0, 'id', [f"q_{i+1:03d}" for i in range(len(df))])
                
                df = df.dropna(subset=["question", "answer"])
                df["id"] = df["id"].astype(str).str.strip()
                df["question"] = df["question"].astype(str).str.strip()
                df["answer"] = df["answer"].astype(str).str.strip()
                
                # IDの数字部分を抽出し、q0187〜q0426にフィルタリング
                def get_qid_num(qid):
                    if pd.isna(qid):
                        return 0
                    match = re.search(r'\d+', str(qid))
                    return int(match.group()) if match else 0
                
                df["q_num"] = df["id"].apply(get_qid_num)
                filtered_df = df[(df["q_num"] >= 187) & (df["q_num"] <= 426)].copy()
                filtered_df = filtered_df.drop(columns=["q_num"])
                
                if len(filtered_df) == 0:
                    return df
                return filtered_df
            except Exception:
                continue
                
    return create_fallback_data()

df = load_data()

# --- 学習ログの保存/読込関数 ---
def save_log(username, q_id, question, result):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = pd.DataFrame([{
        "datetime": now,
        "username": username,
        "q_id": q_id,
        "question": question,
        "result": result
    }])
    
    if not os.path.exists(LOG_FILE):
        new_data.to_csv(LOG_FILE, index=False, encoding="utf-8")
    else:
        new_data.to_csv(LOG_FILE, mode="a", header=False, index=False, encoding="utf-8")

def get_user_stats(username):
    if not os.path.exists(LOG_FILE) or len(username.strip()) == 0:
        return 0, 0
    try:
        log_df = pd.read_csv(LOG_FILE, encoding="utf-8")
        user_log = log_df[log_df["username"].str.strip().str.lower() == username.strip().lower()]
        total = len(user_log)
        correct = len(user_log[user_log["result"] == "正解"])
        return correct, total
    except Exception:
        return 0, 0

# --- セッション状態の管理 ---
if "question_pool" not in st.session_state or len(st.session_state.get("question_pool", [])) != len(df):
    indices = list(range(len(df)))
    random.shuffle(indices)
    st.session_state.question_pool = indices
if "current_pool_idx" not in st.session_state: st.session_state.current_pool_idx = 0
if "result" not in st.session_state: st.session_state.result = None
if "recognized_text" not in st.session_state: st.session_state.recognized_text = ""
if "canvas_key_id" not in st.session_state: st.session_state.canvas_key_id = 0
if "has_graded" not in st.session_state: st.session_state.has_graded = False

# --- コールバック関数の定義 ---
def get_next_question():
    st.session_state.current_pool_idx = (st.session_state.current_pool_idx + 1) % len(df)
    st.session_state.result = None
    st.session_state.recognized_text = ""
    st.session_state.canvas_key_id += 1
    st.session_state.has_graded = False

# --- ユーザーログイン領域 (サイドバー) ---
st.sidebar.markdown("### 👤 ユーザーログイン")
username = st.sidebar.text_input("ユーザー名を入力", value="ゲスト", key="username_input")
username = username.strip() if username.strip() else "ゲスト"

# --- メインコンテンツ ---
st.title("📝 歴史 手書き自動採点")

if not df.empty:
    q_idx = st.session_state.question_pool[st.session_state.current_pool_idx]
    q_id = df.iloc[q_idx]["id"]
    question = df.iloc[q_idx]["question"]
    raw_answer = str(df.iloc[q_idx]["answer"])

    st.info(f"**問題:** {question} (ID: {q_id})")

    # 操作系とペンの太さ
    col_s1, col_btn = st.columns([3, 1])
    with col_s1:
        stroke_width = st.select_slider("ペンの太さ", options=range(1, 11), value=6)
    with col_btn:
        st.button("🔄 次へ", use_container_width=True, on_click=get_next_question)

    # キャンバス
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=200, 
        width=700,
        drawing_mode="freedraw",
        key=f"canvas_q_stable_key_{st.session_state.canvas_key_id}",
        update_streamlit=True,
    )

    if st.button("✅ 採点する", use_container_width=True, type="primary"):
        if canvas_result.image_data is not None:
            img_data = canvas_result.image_data.astype('uint8')
            img_rgb = cv2.cvtColor(img_data, cv2.COLOR_RGBA2RGB)
            
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            inv = cv2.bitwise_not(gray)
            coords = cv2.findNonZero(inv)
            
            if coords is not None:
                x, y, w, h = cv2.boundingRect(coords)
                pad = 20
                img_cropped = img_rgb[max(0, y-pad):min(img_rgb.shape[0], y+h+pad), 
                                      max(0, x-pad):min(img_rgb.shape[1], x+w+pad)]
                
                processed_img = preprocess_image(img_cropped)
                
                try:
                    ocr_results = reader.readtext(processed_img, detail=0, paragraph=False)
                    recognized_raw = "".join(ocr_results)
                    
                    possible_answers = [a.strip() for a in raw_answer.split('/')]
                    is_correct = judge_answer(recognized_raw, possible_answers)
                    
                    result_str = "正解" if is_correct else "不正解"
                    
                    if not st.session_state.has_graded:
                        save_log(username, q_id, question, result_str)
                        st.session_state.has_graded = True
                    
                    clean_text = normalize_text(recognized_raw)
                    st.session_state.recognized_text = clean_text if clean_text else "認識不能"
                    st.session_state.result = result_str
                except Exception as e:
                    st.error(f"OCR処理中にエラーが発生しました: {e}")
            else:
                st.warning("キャンバスに文字が記入されていません。")

    # 結果表示および累積成績表示
    result_box = st.empty()
    if st.session_state.result:
        if st.session_state.result == "正解":
            st.balloons()
            result_box.success(f"🎊 **正解！** (認識: {st.session_state.recognized_text})")
        else:
            result_box.error(f"😭 **不正解** (認識: {st.session_state.recognized_text})")
            st.info(f"正解: **{raw_answer.replace('/', ' / ')}**")
        
        correct, total = get_user_stats(username)
        incorrect = total - correct
        rate = (correct / total * 100) if total > 0 else 0
        
        st.markdown(f"""
        <div class="stats-box">
            📊 <b>{username} さんの学習統計（累計）</b><br>
            正解回数: <b>{correct}</b> 回 / 誤答回数: <b>{incorrect}</b> 回 （総解答数: {total} 回）<br>
            現在の学習正解率: <b>{rate:.1f}%</b>
        </div>
        """, unsafe_allow_html=True)
else:
    st.error("問題データがありません。")