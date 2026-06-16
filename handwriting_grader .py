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
st.set_page_config(page_title="歴史手書きクエスト - 漢字で答える歴史ゲーム", layout="centered")

# --- CSS: ゲーミフィケーションデザイン (DOMレイアウト完全固定・常駐型) ---
st.markdown("""
    <style>
    /* 全体のコンテナ調整 */
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    
    /* ヘッダー・ゲームタイトル */
    .game-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #FF9800, #F44336);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }
    
    /* ステータスバーのデザイン */
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
        font-size: 1.2rem;
        font-family: 'Courier New', Courier, monospace;
    }

    .heart-active { color: #E91E63; font-size: 1.4rem; margin-right: 2px;}
    .heart-broken { color: #555555; font-size: 1.4rem; margin-right: 2px;}

    /* 問題カード */
    .quiz-card {
        background-color: #2b2b36;
        border: 2px solid #3f3f52;
        border-radius: 15px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    .quiz-num {
        font-size: 0.9rem;
        color: #9e9e9e;
        font-weight: bold;
    }
    .quiz-text {
        font-size: 1.3rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.5;
        margin-top: 5px;
    }

    /* キャンバス周り */
    div[data-testid="stCanvas"] button {
        background-color: #3f51b5 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 6px 12px !important;
        font-weight: bold !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2) !important;
        transition: all 0.3s ease !important;
    }
    div[data-testid="stCanvas"] button:hover {
        background-color: #5c6bc0 !important;
        transform: translateY(-1px) !important;
    }

    /* コンボ表示用 */
    .combo-badge {
        display: inline-block;
        background: linear-gradient(45deg, #ff5722, #ffc107);
        color: white;
        font-weight: bold;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 1.1rem;
        margin-bottom: 0.5rem;
    }

    /* ランク演出 */
    .rank-box {
        text-align: center;
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 8px 16px rgba(0,0,0,0.25);
    }
    .rank-title {
        font-size: 3rem;
        font-weight: 900;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    </style>
""", unsafe_allow_html=True)

# --- ユーザー保存データ用のパス定義 ---
LOG_DIR = "user_data"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- OCRリーダーの初期化 (キャッシュして高速化) ---
@st.cache_resource
def load_ocr_reader():
    import easyocr
    return easyocr.Reader(['ja', 'en'], gpu=False)

try:
    reader = load_ocr_reader()
except Exception as e:
    st.error(f"OCR初期化中にエラーが発生しました。requirements.txt の設定を確認してください: {e}")
    reader = None

# --- CSV問題データのロードとフィルタリング ---
CSV_FILE_PATH = "rekishi_questions.xlsx - Sheet1.csv"

@st.cache_data
def load_questions(filepath):
    def create_fallback_data():
        dummy_data = []
        for i in range(187, 362):
            dummy_data.append([f"q{i:04d}", f"【フォールバック問題 {i}】織田信長が明智光秀に襲われた京都のお寺はどこか？(答え:本能寺)", "本能寺"])
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
            raise ValueError("CSVデータのパースに失敗、または空のファイルです。")
            
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
            st.error("指定範囲(q0187～q0361)の質問データが見つかりませんでした。全問題データを使用します。")
            return df
            
        return filtered_df
    except Exception as e:
        st.error(f"CSVのロードに失敗しました({e})。フォールバックデータで起動します。")
        return create_fallback_data()

df_questions = load_questions(CSV_FILE_PATH)

# --- ユーザーデータ・ログイン管理 ---
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
        "total_games": 0,
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

def get_answer_logs(username):
    filepath = get_user_file(username, "log")
    if os.path.exists(filepath):
        try:
            return pd.read_csv(filepath)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

# --- テキスト処理 (表記ゆれ吸収) ---
def normalize_text(text):
    if not text:
        return ""
    import jaconv
    text = text.replace(" ", "").replace("　", "")
    text = jaconv.h2z(text, kana=True, digit=True, ascii=True)  # 半角を全角に
    text = jaconv.hira2kata(text)  # ひらがなをカタカナに統一
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

# --- 画像前処理 (OCR精度向上) ---
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

# --- ゲーム状態の初期化 ---
def init_game_state():
    st.session_state.game_active = True
    st.session_state.game_over = False
    st.session_state.score = 0
    st.session_state.combo = 0
    st.session_state.lives = 3
    st.session_state.answered_count = 0
    st.session_state.correct_count = 0
    
    num_questions = len(df_questions)
    sample_size = min(10, num_questions)
    
    if num_questions > 0:
        st.session_state.q_index_list = random.sample(range(num_questions), sample_size)
    else:
        st.session_state.q_index_list = []
        
    st.session_state.current_quiz_pos = 0
    st.session_state.has_evaluated = False
    st.session_state.result_status = None
    st.session_state.ocr_text = ""
    st.session_state.canvas_key = 0

# --- セッションステート初期化 ---
if "screen" not in st.session_state:
    st.session_state.screen = "login"
if "game_active" not in st.session_state:
    st.session_state.game_active = False
if "game_over" not in st.session_state:
    st.session_state.game_over = False
if "user_stats" not in st.session_state:
    st.session_state.user_stats = None

# ログイン状態の確認・強制画面制御
if "username" not in st.session_state:
    st.session_state.screen = "login"
elif not st.session_state.game_active and not st.session_state.game_over:
    st.session_state.screen = "lobby"
elif st.session_state.game_over:
    st.session_state.screen = "result"
else:
    st.session_state.screen = "game"


# --- 1. [LOGIN SCREEN] ---
if st.session_state.screen == "login":
    st.subheader("👤 冒険者登録 / ログイン")
    username_input = st.text_input("プレイヤー名を入力してください:", max_chars=12, placeholder="例: レキシ丸").strip()
    
    if st.button("ゲームスタート！", use_container_width=True):
        if username_input:
            st.session_state.username = username_input
            st.session_state.user_stats = load_user_stats(username_input)
            st.session_state.screen = "lobby"
            st.success(f"ようこそ、{username_input} さん！ロビーへ進みます。")
            st.rerun()
        else:
            st.warning("名前を入力してください。")


# --- 2. [LOBBY SCREEN] ---
if st.session_state.screen == "lobby":
    username = st.session_state.username
    stats = st.session_state.user_stats

    # サイドバーはゲーム中以外も共通表示
    with st.sidebar:
        st.subheader(f"🛡️ プレイヤー: {username}")
        st.metric("🏆 最高ハイスコア", f"{stats['high_score']} pts")
        st.metric("🔥 最大コンボ", f"{stats['max_combo']} 連鎖")
        st.metric("📊 累計正解率", f"{ (stats['correct_answers']/stats['total_questions']*100) if stats['total_questions'] > 0 else 0:.1f} %")
        st.write(f"🎮 挑戦回数: {stats['total_games']} 回")
        
        st.markdown("---")
        if st.button("🚪 別のユーザーでログイン"):
            del st.session_state.username
            del st.session_state.user_stats
            st.session_state.screen = "login"
            st.rerun()

    st.markdown("""
    <div style="background-color: #1e1e24; padding: 1.5rem; border-radius: 15px; border: 1px solid #333; text-align: center;">
        <h3>⚔️ クエストに挑戦する準備はできましたか？ ⚔️</h3>
        <p>1回につきランダムに10問出題されます。<br>
        持ちライフは <b>3つ</b> 。間違えるとライフが減少し、0になるとゲームオーバーです！<br>
        連続で正解すると <b>コンボボーナス</b> が発生し、スコアが跳ね上がります！</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔥 クエスト開始！ (10問)", use_container_width=True, type="primary"):
            init_game_state()
            st.session_state.screen = "game"
            st.rerun()
    with col2:
        with st.expander("📝 あなたの過去の回答ログを表示"):
            logs_df = get_answer_logs(username)
            if not logs_df.empty:
                st.dataframe(logs_df.sort_values(by="datetime", ascending=False), use_container_width=True)
            else:
                st.info("まだ回答ログがありません。まずはクエストに挑戦してみましょう！")


# --- 3. [RESULT SCREEN] ---
if st.session_state.screen == "result":
    username = st.session_state.username
    stats = st.session_state.user_stats

    with st.sidebar:
        st.subheader(f"🛡️ プレイヤー: {username}")
        st.metric("🏆 最高ハイスコア", f"{stats['high_score']} pts")
        st.metric("🔥 最大コンボ", f"{stats['max_combo']} 連鎖")
        st.metric("📊 累計正解率", f"{ (stats['correct_answers']/stats['total_questions']*100) if stats['total_questions'] > 0 else 0:.1f} %")
        st.write(f"🎮 挑戦回数: {stats['total_games']} 回")
        st.markdown("---")

    stats_updated = False
    if st.session_state.score > stats["high_score"]:
        stats["high_score"] = st.session_state.score
        stats_updated = True
    if st.session_state.combo > stats["max_combo"]:
        stats["max_combo"] = st.session_state.combo
        stats_updated = True
    
    if "stats_saved" not in st.session_state or not st.session_state.stats_saved:
        stats["total_games"] += 1
        stats["total_questions"] += st.session_state.answered_count
        stats["correct_answers"] += st.session_state.correct_count
        save_user_stats(username, stats)
        st.session_state.stats_saved = True
    
    accuracy = (st.session_state.correct_count / st.session_state.answered_count * 100) if st.session_state.answered_count > 0 else 0
    if accuracy >= 90:
        rank, r_color, r_bg = "SSランク", "#FFD700", "rgba(255, 215, 0, 0.1)"
    elif accuracy >= 75:
        rank, r_color, r_bg = "Sランク", "#FF8C00", "rgba(255, 140, 0, 0.1)"
    elif accuracy >= 50:
        rank, r_color, r_bg = "Aランク", "#4CAF50", "rgba(76, 175, 80, 0.1)"
    else:
        rank, r_color, r_bg = "Bランク", "#9E9E9E", "rgba(158, 158, 158, 0.1)"

    st.markdown(f"""
    <div class="rank-box" style="background-color: {r_bg}; border: 3px solid {r_color};">
        <h4 style="color: {r_color}; margin: 0;">🎉 リザルト発表 🎉</h4>
        <div class="rank-title" style="color: {r_color};">{rank}</div>
        <p style="font-size: 1.2rem; color: #fff; margin: 10px 0;">最終スコア: <b style="color: #FFC107; font-size: 1.5rem;">{st.session_state.score}</b> pts</p>
        <p style="color: #ccc;">正解数: {st.session_state.correct_count} / 挑戦した問題: {st.session_state.answered_count}問 (正解率: {accuracy:.1f}%)</p>
    </div>
    """, unsafe_allow_html=True)
    
    if stats_updated:
        st.success("🏆 ハイスコアまたは最大コンボを更新しました！")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 もう一度クエストに挑戦", use_container_width=True, type="primary"):
            st.session_state.stats_saved = False
            init_game_state()
            st.session_state.screen = "game"
            st.rerun()
    with col_btn2:
        if st.button("🏠 ロビー（トップ）に戻る", use_container_width=True):
            st.session_state.stats_saved = False
            st.session_state.game_active = False
            st.session_state.game_over = False
            st.session_state.screen = "lobby"
            st.rerun()


# --- 4. [GAME SCREEN & CONSTANT CANVAS RENDERING] ---
# Reactの仮想DOMクラッシュ（removeChild）を防ぐため、st_canvasはログイン/ロビー/結果中も含めて
# 「常に裏で実行（Pythonコードを通過）」させ、CSSを用いて見えなくさせます。

# キャンバス用問題の安全な初期値確保
if "q_index_list" in st.session_state and len(st.session_state.q_index_list) > 0:
    g_curr_pos = st.session_state.current_quiz_pos
    g_list = st.session_state.q_index_list
    # 配列外アクセス保護
    if g_curr_pos >= len(g_list):
        g_curr_pos = len(g_list) - 1
    g_idx = g_list[g_curr_pos]
    g_row = df_questions.iloc[g_idx]
    g_qid = g_row["q_id"]
    g_question = g_row["question"]
    g_model_answer = g_row["answer"]
else:
    g_curr_pos = 0
    g_list = []
    g_qid = "q0000"
    g_question = "準備中..."
    g_model_answer = ""

# ゲーム画面、または裏でのキャンバス常駐用プレースホルダー
canvas_container = st.container()

with canvas_container:
    # 現在の画面が 'game' でない場合、CSSでキャンバスとゲームUI要素をブラウザ上で完全非表示にする
    # これにより、ReactはDOMノードの削除（アンマウント）を行わず非表示にするだけになり、クラッシュが100%防げます。
    if st.session_state.screen != "game":
        st.markdown("""
            <style>
            div[data-testid="stCanvas"] { display: none !important; }
            .stable-game-layout { display: none !important; }
            </style>
        """, unsafe_allow_html=True)

    # 安定したゲーム画面レイアウト（アンマウントされない枠組み）
    st.markdown('<div class="stable-game-layout">', unsafe_allow_html=True)
    
    # 判定状態に応じた自動遷移
    if st.session_state.game_active:
        if len(g_list) == 0 or st.session_state.current_quiz_pos >= len(g_list) or st.session_state.lives <= 0:
            st.session_state.game_over = True
            st.session_state.game_active = False
            st.session_state.screen = "result"
            st.rerun()

    # ステータスバー
    g_hearts = "".join(['<span class="heart-active">❤️</span>' for _ in range(st.session_state.get('lives', 3))])
    g_broken_hearts = "".join(['<span class="heart-broken">🖤</span>' for _ in range(3 - st.session_state.get('lives', 3))])
    
    st.markdown(f"""
        <div class="status-container">
            <div class="status-item">🏆 SCORE: <span class="status-val">{st.session_state.get('score', 0)}</span></div>
            <div class="status-item">🔥 COMBO: <span class="status-val">{st.session_state.get('combo', 0)}</span></div>
            <div class="status-item">💖 LIFE: {g_hearts}{g_broken_hearts}</div>
        </div>
    """, unsafe_allow_html=True)

    # プログレスバー
    g_total = len(g_list) if len(g_list) > 0 else 10
    g_prog_val = (g_curr_pos + 1) / g_total
    st.progress(g_prog_val, text=f"進捗: {g_curr_pos + 1} / {g_total} 問目")

    # 問題カード
    st.markdown(f"""
        <div class="quiz-card">
            <div class="quiz-num">問題 ID: {g_qid}</div>
            <div class="quiz-text">{g_question}</div>
        </div>
    """, unsafe_allow_html=True)

    # 左右カラム配置
    g_col1, g_col2 = st.columns([2, 1])

    with g_col1:
        st.write("✍️ 下の黒いキャンバスに答えを書いてください。")
        # 【重要】update_streamlit=False に変更
        # ユーザーが1画書くごとにリアルタイムでStreamlit全体をリランさせないようにし、
        # React DOMとWebSocket送信の非同期ラグによる 'removeChild' クラッシュを100%防ぎます。
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=6,
            stroke_color="#FFFFFF",
            background_color="#000000",
            height=180,
            width=400,
            drawing_mode="freedraw",
            key=f"canvas_stable_{st.session_state.get('canvas_key', 0)}",
            update_streamlit=False,
        )

    with g_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        submit_btn = st.button("🔥 判定する！", use_container_width=True, type="primary", disabled=st.session_state.get('has_evaluated', False))
        
        if st.button("🧹 キャンバスをクリア", use_container_width=True):
            st.session_state.canvas_key = st.session_state.get('canvas_key', 0) + 1
            st.session_state.has_evaluated = False
            st.session_state.result_status = None
            st.rerun()

    # 判定実行ロジック
    if submit_btn and st.session_state.screen == "game":
        if canvas_result is not None and canvas_result.image_data is not None:
            img_data = canvas_result.image_data
            if np.sum(img_data[:, :, 3]) > 0:
                with st.spinner("手書き文字をAIが解読中..."):
                    try:
                        pil_img = Image.fromarray(img_data.astype('uint8'), 'RGBA')
                        processed_img = preprocess_image(pil_img)
                        
                        img_np = np.array(processed_img)
                        ocr_results = reader.readtext(img_np)
                        
                        detected_text = ""
                        if ocr_results:
                            detected_text = "".join([res[1] for res in ocr_results]).strip()
                        
                        if not detected_text:
                            detected_text = "（読み取れませんでした）"
                        
                        st.session_state.ocr_text = detected_text
                        st.session_state.has_evaluated = True
                        st.session_state.answered_count += 1
                        
                        is_correct = judge_answer(detected_text, g_model_answer)
                        
                        if is_correct:
                            st.session_state.result_status = "correct"
                            st.session_state.combo += 1
                            st.session_state.correct_count += 1
                            earned = 100 + (st.session_state.combo - 1) * 20
                            st.session_state.score += earned
                            st.session_state.earned_this_turn = earned
                        else:
                            st.session_state.result_status = "incorrect"
                            st.session_state.lives -= 1
                            st.session_state.combo = 0
                            st.session_state.earned_this_turn = 0
                            
                        save_answer_log(
                            st.session_state.username, 
                            g_qid, 
                            g_question, 
                            g_model_answer, 
                            detected_text, 
                            is_correct, 
                            st.session_state.earned_this_turn
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"判定エラー: {e}")
            else:
                st.warning("⚠️ キャンバスに何も書かれていません！")

    # 結果表示
    if st.session_state.get('has_evaluated', False):
        st.markdown("---")
        if st.session_state.result_status == "correct":
            st.success(f"🎯 **正解！** 手書き認識: 「{st.session_state.ocr_text}」 (+{st.session_state.earned_this_turn} pts)")
            st.markdown(f'<div class="combo-badge">🔥 {st.session_state.combo} COMBO</div>', unsafe_allow_html=True)
        else:
            st.error(f"❌ **不正解** 手書き認識: 「{st.session_state.ocr_text}」")
            st.info(f"正解は **{g_model_answer.replace('/', ' / ')}** でした。")
            st.warning(f"💔 ライフが1つ減少しました。残りライフ: {st.session_state.lives}")

        if st.button("➡️ 次の問題へ進む", use_container_width=True, type="primary"):
            st.session_state.current_quiz_pos += 1
            st.session_state.has_evaluated = False
            st.session_state.result_status = None
            st.session_state.canvas_key = st.session_state.get('canvas_key', 0) + 1
            st.rerun()

    # ゲームの中断
    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("🏳️ クエストを断念してリザルトへ進む", use_container_width=True, help="現在のスコアでゲームを終了します"):
        st.session_state.game_over = True
        st.session_state.game_active = False
        st.session_state.screen = "result"
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)