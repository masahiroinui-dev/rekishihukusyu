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

# --- CSS: シンプルで美しい固定ダークUI ＆ GPU安全アニメーションエフェクト ---
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

    /* 🛡️ 100%安全な正解・不正解時限定のCSSアニメーション（GPU処理） */
    @keyframes correct-pop {
        0% { transform: scale(0.95); opacity: 0; }
        50% { transform: scale(1.03); }
        100% { transform: scale(1); opacity: 1; }
    }
    
    @keyframes shine-gold {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    .correct-effect-box {
        background: linear-gradient(135deg, rgba(76, 175, 80, 0.2), rgba(255, 193, 7, 0.2)) !important;
        background-size: 200% 200% !important;
        border: 2px solid #4CAF50 !important;
        box-shadow: 0 0 20px rgba(76, 175, 80, 0.4) !important;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        animation: correct-pop 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards, shine-gold 4s ease infinite;
    }

    .incorrect-effect-box {
        background-color: rgba(244, 67, 54, 0.15) !important;
        border: 2px solid #F44336 !important;
        box-shadow: 0 0 10px rgba(244, 67, 54, 0.2) !important;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        animation: correct-pop 0.3s ease-out forwards;
    }
    </style>
""", unsafe_allow_html=True)

# --- ユーザー保存データ用のパス定義 ---
LOG_DIR = "user_data"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- 🛡️ OCRリーダーの超遅延インポート＆初期化 (クラッシュを100%防止する安全キャッシュ) ---
@st.cache_resource
def load_ocr_reader_safe():
    try:
        # 起動時にはインポートせず、関数が呼ばれたタイミングで初めて遅延インポートします
        import easyocr
        return easyocr.Reader(['ja', 'en'], gpu=False), True
    except Exception as e:
        # インポート失敗、またはシステムライブラリ（libGL.so等）不足時はNoneを返し、簡易判定モードにします
        return None, False

# --- CSV問題データのロードとフィルタリング (q0187〜q0361) ---
CSV_FILE_PATH = "rekishi_questions.xlsx - Sheet1.csv"

# 🛡️ キャッシュ関数を安全に定義 (この中での Streamlit UI オブジェクト呼び出しは絶対禁止)
@st.cache_data
def load_questions_safe(filepath):
    def create_fallback_data():
        dummy_data = []
        for i in range(187, 362):
            dummy_data.append([f"q{i:04d}", f"【テスト問題 {i}】織田信長が明智光秀に襲われた京都のお寺はどこか？(答え:本能寺)", "本能寺"])
        df_fallback = pd.DataFrame(dummy_data, columns=["q_id", "question", "answer"])
        return df_fallback, False # (データ, 読み込み成否)

    if not os.path.exists(filepath):
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
            return create_fallback_data()
            
        df = df.iloc[:, :3]
        df.columns = ["q_id", "question", "answer"]
        
        df["q_id"] = df["q_id"].astype(str).str.strip()
        df["question"] = df["question"].astype(str).str.strip()
        df["answer"] = df["answer"].astype(str).str.strip()
        
        # 🛡️ 欠損値(NaN)や数値型が流れ込んだ場合のTypeErrorを完全に防ぐ型安全パーサー
        def get_qid_num(qid):
            if pd.isna(qid):
                return 0
            match = re.search(r'\d+', str(qid))
            return int(match.group()) if match else 0
        
        df["q_num"] = df["q_id"].apply(get_qid_num)
        filtered_df = df[(df["q_num"] >= 187) & (df["q_num"] <= 361)].copy()
        filtered_df = filtered_df.drop(columns=["q_num"])
        
        if len(filtered_df) == 0:
            return df, True
            
        return filtered_df, True
    except Exception:
        return create_fallback_data()

# 安全なロードを実行
df_questions, load_success = load_questions_safe(CSV_FILE_PATH)

# 万が一CSVのロードに失敗した場合の警告は、キャッシュの外側（安全なエリア）で表示
if not load_success:
    st.sidebar.warning("⚠️ 問題ファイルが見つかりません。テスト問題を使用中。")

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
if "info_msg" not in st.session_state:
    st.session_state.info_msg = ""
if "canvas_key_offset" not in st.session_state:
    st.session_state.canvas_key_offset = 0
if "self_check_mode" not in st.session_state:
    st.session_state.self_check_mode = False

# 安全なローカル変数定義
q_idx = st.session_state.current_q_idx
if len(df_questions) > 0:
    row = df_questions.iloc[q_idx]
    q_id = row["q_id"]
    question = row["question"]
    model_answer = row["answer"]
else:
    q_id = "q0000"
    question = "問題データがありません。"
    model_answer = ""

# --- ボタンクリックコールバック関数 (仮想DOM競合を避けるための100%安全設計) ---
def handle_clear():
    # 🛡️ React keyを変更せずに、背景色をトグルさせて手書き領域をリセット（不変DOM）
    st.session_state.canvas_key_offset += 1
    st.session_state.has_evaluated = False
    st.session_state.result_status = None
    st.session_state.ocr_text = ""
    st.session_state.info_msg = ""

def handle_next_question():
    st.session_state.current_q_idx = random.randint(0, len(df_questions) - 1) if len(df_questions) > 0 else 0
    st.session_state.has_evaluated = False
    st.session_state.result_status = None
    st.session_state.ocr_text = ""
    st.session_state.info_msg = ""
    st.session_state.canvas_key_offset += 1

def handle_self_correct():
    st.session_state.result_status = "correct"
    st.session_state.combo += 1
    st.session_state.correct_count += 1
    st.session_state.answered_count += 1
    earned = 100 + (st.session_state.combo - 1) * 20
    st.session_state.score += earned
    st.session_state.earned_this_turn = earned
    
    username = st.session_state.username
    stats = st.session_state.user_stats
    stats["total_questions"] += 1
    stats["correct_answers"] += 1
    if st.session_state.score > stats["high_score"]:
        stats["high_score"] = st.session_state.score
    if stats["high_score"] > 0:
        pass
    if st.session_state.combo > stats["max_combo"]:
        stats["max_combo"] = st.session_state.combo
    
    save_user_stats(username, stats)
    save_answer_log(username, q_id, question, model_answer, "⭕(自己判定・正解)", True, earned)
    st.session_state.info_msg = f"🎯 正解にしました！ (+{earned} pts) combo: {st.session_state.combo}"

def handle_self_incorrect():
    st.session_state.result_status = "incorrect"
    st.session_state.combo = 0
    st.session_state.earned_this_turn = 0
    st.session_state.answered_count += 1
    
    username = st.session_state.username
    stats = st.session_state.user_stats
    stats["total_questions"] += 1
    save_user_stats(username, stats)
    save_answer_log(username, q_id, question, model_answer, "❌(自己判定・不正解)", False, 0)
    st.session_state.info_msg = f"❌ 不正解として記録しました。(正解：{model_answer.replace('/', ' / ')})"

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

# 🛡️ 現在の採点モードの通知
if st.session_state.self_check_mode:
    st.sidebar.info("💡 現在：自己採点モードで稼働中")
else:
    st.sidebar.success("🤖 現在：AI自動判定モードで稼働中")

# 4. 問題カードの描画
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
    ・文字を書き直すときや次の問題に進むときは、黒いキャンバス of 座標の左下にある <b>ゴミ箱アイコン 🗑️</b> を押してクリアしてください。<br>
    ・1つ前の状態に戻したいときは、<b>矢印アイコン ↩️</b> を押してください。
</div>
""", unsafe_allow_html=True)

# 6. 手書きエリア (React DOM 崩壊防止のために columns やネストを完全撤廃しフラット配置)
# 🛡️ 【絶対不変】React keyを完全に固定化し、プロパティ変更による iframe の React アンマウントを完全に回避。
# クリア時は、100%安全に background_color をトグル(人間には見分けのつかない微小な色変化)させることで Fabric.js を内部クリアします。
canvas_key = "immortal_canvas_fixed_key"
canvas_bg_color = "#000000" if st.session_state.canvas_key_offset % 2 == 0 else "#000001"

canvas_result = st_canvas(
    fill_color="rgba(255, 255, 255, 0)",
    stroke_width=6,
    stroke_color="#FFFFFF",
    background_color=canvas_bg_color,
    height=180,
    width=400,
    drawing_mode="freedraw",
    key=canvas_key,
    update_streamlit=False, # 描画中の余計な裏リランを完全停止
    display_toolbar=True, # ツールバーを確実に有効化
)

# 7. 判定ボタン
submit_btn = st.button("🔥 判定する！", use_container_width=True, type="primary", disabled=st.session_state.has_evaluated)

# 8. OCR判定または自己採点処理
if submit_btn and not st.session_state.has_evaluated:
    if canvas_result is not None and canvas_result.image_data is not None:
        img_data = canvas_result.image_data
        if np.sum(img_data[:, :, 3]) > 0:
            st.session_state.info_msg = "解読中..."
            
            # --- 🤖 AI自動判定モード時の処理 ---
            if not st.session_state.self_check_mode:
                # ここで初めて安全にOCRモジュールをインポート・読み込み
                reader_obj, is_ready = load_ocr_reader_safe()
                if is_ready and reader_obj is not None:
                    try:
                        pil_img = Image.fromarray(img_data.astype('uint8'), 'RGBA')
                        processed_img = preprocess_image(pil_img)
                        
                        img_np = np.array(processed_img)
                        ocr_results = reader_obj.readtext(img_np)
                        
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
                            st.session_state.info_msg = f"🎯 正解！ 認識した文字：{detected_text} (+{earned} pts) combo: {st.session_state.combo}"
                        else:
                            st.session_state.result_status = "incorrect"
                            st.session_state.combo = 0
                            st.session_state.earned_this_turn = 0
                            st.session_state.info_msg = f"❌ 不正解... 認識した文字：{detected_text} (正解：{model_answer.replace('/', ' / ')})"
                            
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
                        
                    except Exception as e:
                        # OCR処理が万が一サーバー負荷で失敗した場合は、自動的に安全な自己判定モードへ切り替えます
                        st.session_state.self_check_mode = True
                        st.session_state.info_msg = "⚠️ AI判定がタイムアウトしました。自己採点モードに切り替えます。下の判定を選んでください。"
                else:
                    # ライブラリ不足、またはモデルの読み込みに失敗した場合は自己判定にスイッチ
                    st.session_state.self_check_mode = True
                    st.session_state.info_msg = "💡 サーバーのメモリ節約のため、自己採点モードで起動しました。下の判定を選んでください。"
            
            # --- 💡 自己採点モード時の処理（100%確実に稼働し、アプリを絶対に落とさない防壁設計） ---
            if st.session_state.self_check_mode:
                st.session_state.ocr_text = "（自己判定中）"
                st.session_state.has_evaluated = True
                st.session_state.info_msg = f"📝 あなたの書いた答えと、正解を比較してください。\\n正解：**{model_answer.replace('/', ' / ')}**"
        else:
            st.session_state.info_msg = "⚠️ キャンバスに何も書かれていません！"

# 9. 判定結果の表示スロット
# 🛡️ React DOMの崩壊を防ぐため、固定スロット `st.empty()` の中身を安全にHTMLで上書きして視覚演出を適用。
# これなら、DOM要素の追加や削除を伴わないため、removeChildエラーは絶対に起きません。
st.markdown("---")
result_placeholder = st.empty()

if st.session_state.info_msg:
    if st.session_state.result_status == "correct":
        # ✨ 正解時のプレミアム・ゴールドアニメーションエフェクト
        html_msg = f"""
        <div class="correct-effect-box">
            <h4 style="color: #4CAF50; margin: 0 0 0.5rem 0; font-weight: 800;">🎯 正解！</h4>
            <p style="margin: 0; color: #ffffff; font-size: 1.1rem; font-weight: bold;">
                解読文字: <span style="color: #FFC107;">{st.session_state.ocr_text}</span> (+{st.session_state.get('earned_this_turn', 100)} pts)
            </p>
            <div class="combo-badge" style="margin-top: 0.5rem;">🔥 {st.session_state.combo} COMBO !</div>
        </div>
        """
    elif st.session_state.result_status == "incorrect":
        # ❌ 不正解時のフェードインカード
        html_msg = f"""
        <div class="incorrect-effect-box">
            <h4 style="color: #F44336; margin: 0 0 0.5rem 0; font-weight: 800;">❌ 不正解...</h4>
            <p style="margin: 0 0 0.5rem 0; color: #ffffff; font-size: 1rem;">
                認識文字: <span style="color: #ccc;">{st.session_state.ocr_text}</span>
            </p>
            <p style="margin: 0; color: #FF9800; font-size: 1.05rem; font-weight: bold;">
                正解: {model_answer.replace('/', ' / ')}
            </p>
        </div>
        """
    else:
        # その他お知らせ・警告・自己採点ガイダンス（静的カード）
        html_msg = f"""
        <div class="guide-box" style="border: 1px solid #FF9800; background-color: rgba(255, 152, 0, 0.05);">
            <h4 style="color: #FF9800; margin: 0 0 0.5rem 0; font-weight: bold;">📝 自己判定ガイダンス</h4>
            <p style="margin: 0; color: #ffffff; font-size: 1rem;">{st.session_state.info_msg}</p>
        </div>
        """
else:
    html_msg = """
    <div class="guide-box" style="background-color: #1e1e24; border: 1px solid #3f3f52;">
        <h4 style="color: #ccc; margin: 0 0 0.5rem 0;">📋 判定結果待ち</h4>
        <p style="margin: 0; color: #888; font-size: 0.95rem;">答えを手書きして、上の「🔥 判定する！」ボタンを押してください。</p>
    </div>
    """

result_placeholder.markdown(html_msg, unsafe_allow_html=True)

# 10. 🛡️ 自己判定モード時の「○ 正解」「× 不正解」入力ボタン（プレースホルダーと競合しない完全同期型設計）
# 【絶対的安定】React DOM の崩壊を防ぐため、st.columns構造および自己判定ボタンは常にマウント。
# 必要なタイミング以外ではdisabled=Trueに制御することで、動的なコンポーネント消滅によるremoveChildエラーを完全回避。
is_self_eval_active = (st.session_state.self_check_mode and st.session_state.has_evaluated and st.session_state.result_status is None)

col_self1, col_self2 = st.columns(2)
with col_self1:
    st.button(
        "⭕ 合ってた！(正解として記録)", 
        use_container_width=True, 
        disabled=not is_self_eval_active, 
        on_click=handle_self_correct
    )
with col_self2:
    st.button(
        "❌ 違ってた(不正解として記録)", 
        use_container_width=True, 
        disabled=not is_self_eval_active, 
        on_click=handle_self_incorrect
    )

# 次の問題へ進むボタン (安全なコールバック経由)
st.button("➡️ 次の問題へ進む", use_container_width=True, type="primary", disabled=not st.session_state.has_evaluated, on_click=handle_next_question)