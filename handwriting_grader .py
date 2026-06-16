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
st.set_page_config(page_title="歴史手書きクイズ", layout="centered")

# --- CSS: シンプルで美しい固定ダークUI ＆ 組み込みツールバーのプレミアム化 ---
st.markdown("""
    <style>
    /* 全体のコンテナ余白の最適化 */
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    
    /* アプリタイトル */
    .game-title {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #FF9800, #F44336);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }
    
    /* シンプルなステータスバー */
    .status-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background-color: #1e1e24;
        padding: 0.8rem 1.2rem;
        border-radius: 12px;
        border-left: 5px solid #FF9800;
        margin-bottom: 1rem;
        color: #ffffff;
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
    }
    
    .status-item {
        font-size: 1rem;
        font-weight: bold;
    }
    
    .status-val {
        color: #FFC107;
        font-size: 1.15rem;
        font-family: 'Courier New', Courier, monospace;
    }

    /* 問題提示カード */
    .quiz-card {
        background-color: #2b2b36;
        border: 2px solid #3f3f52;
        border-radius: 15px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    .quiz-num {
        font-size: 0.85rem;
        color: #9e9e9e;
        font-weight: bold;
    }
    .quiz-text {
        font-size: 1.25rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.5;
        margin-top: 5px;
    }

    /* キャンバス外観スタイル */
    div[data-testid="stCanvas"] {
        border: 2px solid #3f3f52 !important;
        border-radius: 12px !important;
        overflow: hidden !important;
        margin-bottom: 0.5rem !important;
    }

    /* 🛡️ キャンバス内蔵ツールバーをはっきり見えるように極上スタイリング */
    div[data-testid="stCanvas"] button {
        background-color: #2b2b36 !important;
        border: 1px solid #3f3f52 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        padding: 6px 12px !important;
        margin-right: 5px !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stCanvas"] button:hover {
        background-color: #ff9800 !important;
        color: #000000 !important;
        border-color: #ff9800 !important;
    }
    div[data-testid="stCanvas"] .lucide {
        color: #ff9800 !important;
    }

    /* コンボ表示バッジ */
    .combo-badge {
        display: inline-block;
        background: linear-gradient(45deg, #ff5722, #ffc107);
        color: white;
        font-weight: bold;
        padding: 0.25rem 0.6rem;
        border-radius: 12px;
        font-size: 0.95rem;
        margin-top: 5px;
    }

    /* ガイド案内 */
    .guide-box {
        background-color: #1e1e24;
        border: 1px dashed #3f3f52;
        padding: 0.8rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        font-size: 0.85rem;
        color: #ccc;
    }
    </style>
""", unsafe_allow_html=True)

# --- ユーザー保存データ用のパス定義 ---
LOG_DIR = "user_data"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- OCRリーダーの初期化 (キャッシュ) ---
@st.cache_resource
def load_ocr_reader():
    import easyocr
    return easyocr.Reader(['ja', 'en'], gpu=False)

try:
    reader = load_ocr_reader()
except Exception as e:
    st.error(f"OCR初期化中にエラーが発生しました: {e}")
    reader = None

# --- CSV問題データのロードとフィルタリング (q0187〜q0361) ---
CSV_FILE_PATH = "rekishi_questions.xlsx - Sheet1.csv"

@st.cache_data
def load_questions(filepath):
    def create_fallback_data():
        dummy_data = []
        for i in range(187, 362):
            dummy_data.append([f"q{i:04d}", f"【テスト問題 {i}】織田信長が明智光秀に襲われた京都のお寺はどこか？(答え:本能寺)", "本能寺"])
        return pd.DataFrame(dummy_data, columns=["q_id", "question", "answer"])

    if not os.path.exists(filepath):
        st.warning(f"問題ファイル '{filepath}' が見つかりませんでした。テスト用データを使用します。")
        return create_fallback_data()
    
    try:
        df = None
        for encoding_type in ["utf-8-sig", "utf-8", "shift-jis", "cp932", "latin1"]:
            try:
                df = pd.read_csv(filepath, header=None, encoding=encoding_type)
                break
            except Exception:
                continue
        
        if df is None or df.empty:
            raise ValueError("CSVデータのパースに失敗しました。")
            
        df = df.iloc[:, :3]
        df.columns = ["q_id", "question", "answer"]
        
        df["q_id"] = df["q_id"].astype(str).str.strip()
        df["question"] = df["question"].astype(str).str.strip()
        df["answer"] = df["answer"].astype(str).str.strip()
        
        # q0187 から q0361 までの範囲を抽出
        def get_qid_num(qid):
            match = re.search(r'\d+', qid)
            return int(match.group()) if match else 0
        
        df["q_num"] = df["q_id"].apply(get_qid_num)
        filtered_df = df[(df["q_num"] >= 187) & (df["q_num"] <= 361)].copy()
        filtered_df = filtered_df.drop(columns=["q_num"])
        
        if len(filtered_df) == 0:
            return df
            
        return filtered_df
    except Exception as e:
        st.error(f"CSVのロードに失敗しました({e})。フォールバックデータで起動します。")
        return create_fallback_data()

df_questions = load_questions(CSV_FILE_PATH)

# --- ユーザーデータ管理機能 ---
def get_user_file(username, kind="stats"):
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', username)
    return os.path.join(LOG_DIR, f"{safe_name}_{kind}.csv")

def load_user_stats(username):
    filepath = get_user_file(username, "stats")
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath)
            if not df.empty:
                return df.iloc[0].to_dict()
        except:
            pass
    return {
        "username": username,
        "high_score": 0,
        "max_combo": 0,
        "total_questions": 0,
        "correct_answers": 0
    }

def save_user_stats(username, stats):
    filepath = get_user_file(username, "stats")
    pd.DataFrame([stats]).to_csv(filepath, index=False)

def save_answer_log(username, q_id, question, correct_ans, user_ans, is_correct, score):
    filepath = get_user_file(username, "log")
    new_row = {
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "q_id": q_id,
        "question": question,
        "correct_answer": correct_ans,
        "user_answer": user_ans,
        "is_correct": 1 if is_correct else 0,
        "score_earned": score
    }
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath)
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        except:
            df = pd.DataFrame([new_row])
    else:
        df = pd.DataFrame([new_row])
    df.to_csv(filepath, index=False)

# --- テキスト表記ゆれ処理 ---
def normalize_text(text):
    if not text:
        return ""
    import jaconv
    text = text.replace(" ", "").replace("　", "")
    text = jaconv.h2z(text, kana=True, digit=True, ascii=True)
    text = jaconv.hira2kata(text)
    text = text.lower()
    return text

def judge_answer(raw_recognized, model_answer):
    choices = [ans.strip() for ans in model_answer.split("/") if ans.strip()]
    cleaned_recognized = normalize_text(raw_recognized)
    for choice in choices:
        cleaned_choice = normalize_text(choice)
        if cleaned_choice in cleaned_recognized or cleaned_recognized in cleaned_choice:
            if len(cleaned_recognized) > 0 and len(cleaned_choice) > 0:
                return True
    return False

# --- 画像前処理 ---
def preprocess_image(pil_img):
    img_np = np.array(pil_img)
    if img_np.shape[2] == 4:
        alpha = img_np[:, :, 3] / 255.0
        bg = np.ones_like(img_np[:, :, :3]) * 255
        for c in range(3):
            bg[:, :, c] = img_np[:, :, c] * alpha + bg[:, :, c] * (1 - alpha)
        gray = cv2.cvtColor(bg.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    else:
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        margin = 15
        h_img, w_img = gray.shape
        x_start = max(0, x - margin)
        y_start = max(0, y - margin)
        x_end = min(w_img, x + w + margin)
        y_end = min(h_img, y + h + margin)
        
        cropped = gray[y_start:y_end, x_start:x_end]
        cropped = cv2.equalizeHist(cropped)
        return Image.fromarray(cropped)
    return pil_img

# --- セッションステート初期化 (ゲーム状態) ---
if "score" not in st.session_state:
    st.session_state.score = 0
if "combo" not in st.session_state:
    st.session_state.combo = 0
if "answered_count" not in st.session_state:
    st.session_state.answered_count = 0
if "correct_count" not in st.session_state:
    st.session_state.correct_count = 0
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = random.randint(0, len(df_questions) - 1) if len(df_questions) > 0 else 0
if "has_evaluated" not in st.session_state:
    st.session_state.has_evaluated = False
if "result_status" not in st.session_state:
    st.session_state.result_status = None
if "ocr_text" not in st.session_state:
    st.session_state.ocr_text = ""

# --- ボタンクリックコールバック関数 (仮想DOM競合を避けるための100%安全設計) ---
def handle_next_question():
    st.session_state.current_q_idx = random.randint(0, len(df_questions) - 1) if len(df_questions) > 0 else 0
    st.session_state.has_evaluated = False
    st.session_state.result_status = None
    st.session_state.ocr_text = ""

# -------------------------------------------------------------
# 🛡️ React DOMの崩壊を防ぐ完全固定UI構成
# -------------------------------------------------------------
st.markdown('<div class="game-title">⚔️ 歴史手書きクエスト ⚔️</div>', unsafe_allow_html=True)

# 1. ログイン情報管理 (サイドバーに常駐)
st.sidebar.subheader("👤 プレイヤー情報")
username_input = st.sidebar.text_input("プレイヤー名:", value=st.session_state.get("username", "ゲスト")).strip()

if "username" not in st.session_state or st.session_state.username != username_input:
    st.session_state.username = username_input
    st.session_state.user_stats = load_user_stats(username_input)

username = st.session_state.username
stats = st.session_state.user_stats

# 2. 個人累計スコアをサイドバーに表示
st.sidebar.markdown("---")
st.sidebar.markdown("### 🏆 累計ベストレコード")
st.sidebar.metric("自己ハイスコア", f"{stats['high_score']} pts")
st.sidebar.metric("最大コンボ数", f"{stats['max_combo']} 連鎖")

accumulated_accuracy = (stats['correct_answers'] / stats['total_questions'] * 100) if stats['total_questions'] > 0 else 0.0
st.sidebar.write(f"累計正解数: {stats['correct_answers']} / {stats['total_questions']} 問")
st.sidebar.write(f"累計正答率: {accumulated_accuracy:.1f} %")

# 3. メイン画面のステータスバー (現在のプレイ結果をシンプル表示)
correct_pct = (st.session_state.correct_count / st.session_state.answered_count * 100) if st.session_state.answered_count > 0 else 0.0

st.markdown(f"""
    <div class="status-container">
        <div class="status-item">🏆 SCORE: <span class="status-val">{st.session_state.score}</span></div>
        <div class="status-item">🔥 COMBO: <span class="status-val">{st.session_state.combo}</span></div>
        <div class="status-item">📊 正解率: <span class="status-val">{st.session_state.correct_count}/{st.session_state.answered_count} ({correct_pct:.1f}%)</span></div>
    </div>
""", unsafe_allow_html=True)

# 4. 問題カードの描画
if len(df_questions) > 0:
    q_idx = st.session_state.current_q_idx
    row = df_questions.iloc[q_idx]
    q_id = row["q_id"]
    question = row["question"]
    model_answer = row["answer"]
else:
    q_id = "q0000"
    question = "問題データがありません。"
    model_answer = ""

st.markdown(f"""
    <div class="quiz-card">
        <div class="quiz-num">問題 ID: {q_id}</div>
        <div class="quiz-text">{question}</div>
    </div>
""", unsafe_allow_html=True)

# 5. 操作方法ガイド (ゴミ箱ボタンの案内)
st.markdown("""
<div class="guide-box">
    <b>✍️ キャンバスの操作方法:</b><br>
    ・文字を書き直すときや次の問題に進むときは、黒いキャンバスの左下にある <b>ゴミ箱アイコン 🗑️</b> を押してクリアしてください。<br>
    ・1つ前の状態に戻したいときは、<b>矢印アイコン ↩️</b> を押してください。
</div>
""", unsafe_allow_html=True)

# 6. 手書きエリア (React DOM 崩壊防止のために columns やネストを完全撤廃しフラット配置)
# 【絶対不変】keyを完全に固定化し、プロパティも変化させないことで iframe の React アンマウントを完全に回避。
canvas_result = st_canvas(
    fill_color="rgba(255, 255, 255, 0)",
    stroke_width=6,
    stroke_color="#FFFFFF",
    background_color="#000000", # 固定
    height=180,
    width=400,
    drawing_mode="freedraw",
    key="absolute_immortal_canvas_key_v1", # 固定
    update_streamlit=False, # 描画中の余計な裏リランを完全停止
    display_toolbar=True, # ツールバーを確実に有効化
)

# 7. 判定ボタン
submit_btn = st.button("🔥 判定する！", use_container_width=True, type="primary", disabled=st.session_state.has_evaluated)

# 8. OCR判定処理
if submit_btn and not st.session_state.has_evaluated:
    if canvas_result is not None and canvas_result.image_data is not None:
        img_data = canvas_result.image_data
        if np.sum(img_data[:, :, 3]) > 0:
            with st.spinner("AI採点中..."):
                try:
                    pil_img = Image.fromarray(img_data.astype('uint8'), 'RGBA')
                    processed_img = preprocess_image(pil_img)
                    
                    img_np = np.array(processed_img)
                    ocr_results = reader.readtext(img_np)
                    
                    detected_text = ""
                    if ocr_results:
                        detected_text = "".join([res[1] for res in ocr_results]).strip()
                    
                    if not detected_text:
                        detected_text = "（読み取り不可）"
                    
                    st.session_state.ocr_text = detected_text
                    st.session_state.has_evaluated = True
                    st.session_state.answered_count += 1
                    
                    is_correct = judge_answer(detected_text, model_answer)
                    
                    if is_correct:
                        st.session_state.result_status = "correct"
                        st.session_state.combo += 1
                        st.session_state.correct_count += 1
                        earned = 100 + (st.session_state.combo - 1) * 20
                        st.session_state.score += earned
                        st.session_state.earned_this_turn = earned
                    else:
                        st.session_state.result_status = "incorrect"
                        st.session_state.combo = 0
                        st.session_state.earned_this_turn = 0
                        
                    # 個人データの累積更新と保存
                    stats["total_questions"] += 1
                    if is_correct:
                        stats["correct_answers"] += 1
                    if st.session_state.score > stats["high_score"]:
                        stats["high_score"] = st.session_state.score
                    if st.session_state.combo > stats["max_combo"]:
                        stats["max_combo"] = st.session_state.combo
                    
                    save_user_stats(username, stats)
                    save_answer_log(username, q_id, question, model_answer, detected_text, is_correct, st.session_state.earned_this_turn)
                    
                    # ⚠️ 二重競合の原因だった st.rerun() を完全に排除し、安全に描画を完了させます
                except Exception as e:
                    st.error(f"判定中にエラーが発生しました: {e}")
        else:
            st.warning("⚠️ キャンバスに何も書かれていません！")

# 9. 判定結果の表示スロット
st.markdown("---")
result_title_slot = st.empty()
result_detail_slot = st.empty()

if st.session_state.has_evaluated:
    if st.session_state.result_status == "correct":
        result_title_slot.success(f"🎯 **正解！** 手書き認識: 「{st.session_state.ocr_text}」 (+{st.session_state.earned_this_turn} pts)")
        result_detail_slot.markdown(f'<div class="combo-badge">🔥 {st.session_state.combo} COMBO !</div>', unsafe_allow_html=True)
    else:
        result_title_slot.error(f"❌ **不正解** 手書き認識: 「{st.session_state.ocr_text}」")
        result_detail_slot.info(f"正解は **{model_answer.replace('/', ' / ')}** でした。")
else:
    result_title_slot.info("📋 判定結果：答えを手書きして、上の「🔥判定する！」ボタンを押してください。")
    result_detail_slot.write("ここに正しい判定結果とコンボ数が表示されます。")

# 次の問題へ進むボタン (安全なコールバック経由)
st.button("➡️ 次の問題へ進む", use_container_width=True, type="primary", disabled=not st.session_state.has_evaluated, on_click=handle_next_question)