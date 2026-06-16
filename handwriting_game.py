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
import base64

# --- 設定 ---
st.set_page_config(page_title="歴史手書きクエスト - 漢字で答える歴史ゲーム", layout="centered")

# --- 効果音再生用ヘルパー (Web Audio API を使って合成音を発生させる) ---
def play_sound(sound_type):
    if sound_type == "correct":
        # ピコーンと高めの良い音
        js_code = """
        <script>
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var osc1 = ctx.createOscillator();
            var osc2 = ctx.createOscillator();
            var gain = ctx.createGain();
            
            osc1.type = 'sine';
            osc1.frequency.setValueAtTime(523.25, ctx.currentTime); // C5
            osc1.frequency.setValueAtTime(659.25, ctx.currentTime + 0.1); // E5
            osc1.frequency.setValueAtTime(783.99, ctx.currentTime + 0.2); // G5
            
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            
            osc1.connect(gain);
            gain.connect(ctx.destination);
            osc1.start();
            osc1.stop(ctx.currentTime + 0.4);
        } catch(e) {}
        </script>
        """
    elif sound_type == "incorrect":
        # ブブーと低い残念な音
        js_code = """
        <script>
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(150, ctx.currentTime);
            osc.frequency.linearRampToValueAtTime(100, ctx.currentTime + 0.3);
            
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.3);
        } catch(e) {}
        </script>
        """
    elif sound_type == "gameover":
        # ゲームオーバーの悲しい音
        js_code = """
        <script>
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(300, ctx.currentTime);
            osc.frequency.setValueAtTime(250, ctx.currentTime + 0.15);
            osc.frequency.setValueAtTime(180, ctx.currentTime + 0.3);
            osc.frequency.setValueAtTime(120, ctx.currentTime + 0.45);
            
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.8);
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.8);
        } catch(e) {}
        </script>
        """
    elif sound_type == "clear":
        # ファンファーレ
        js_code = """
        <script>
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var gain = ctx.createGain();
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 1.2);
            gain.connect(ctx.destination);
            
            function playTone(freq, start, duration) {
                var osc = ctx.createOscillator();
                osc.type = 'square';
                osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
                osc.connect(gain);
                osc.start(ctx.currentTime + start);
                osc.stop(ctx.currentTime + start + duration);
            }
            playTone(523.25, 0, 0.15); // C5
            playTone(659.25, 0.15, 0.15); // E5
            playTone(783.99, 0.3, 0.15); // G5
            playTone(1046.50, 0.45, 0.5); // C6
        } catch(e) {}
        </script>
        """
    else:
        return
    st.components.v1.html(js_code, height=0, width=0)

# --- CSS: ゲーミフィケーションデザイン ---
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

    /* コンボ表示用アニメーション効果 */
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
    }
    .combo-badge {
        display: inline-block;
        background: linear-gradient(45deg, #ff5722, #ffc107);
        color: white;
        font-weight: bold;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 1.1rem;
        animation: pulse 1s infinite;
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
    # 日本語('ja')と英語('en')をサポート
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
    if not os.path.exists(filepath):
        # 万が一ファイルが無い場合のフォールバックダミーデータ
        st.warning(f"問題ファイル '{filepath}' が見つかりませんでした。テスト用データを使用します。")
        dummy_data = []
        for i in range(187, 362):
            dummy_data.append([f"q{i:04d}", f"【テスト問 {i}】織田信長が明智光秀に襲われたお寺はどこか？(答え:本能寺)", "本能寺"])
        return pd.DataFrame(dummy_data, columns=["q_id", "question", "answer"])
    
    try:
        # Shift-JIS or UTF-8 等のエンコーディング対応
        try:
            df = pd.read_csv(filepath, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding="shift-jis")
        
        # 列名を統一化
        df.columns = ["q_id", "question", "answer"]
        df["q_id"] = df["q_id"].astype(str).str.strip()
        df["question"] = df["question"].astype(str).str.strip()
        df["answer"] = df["answer"].astype(str).str.strip()
        
        # q0187 から q0361 までの範囲を抽出
        # q_id を数値化してフィルタリングする
        def get_qid_num(qid):
            match = re.search(r'\d+', qid)
            return int(match.group()) if match else 0
        
        df["q_num"] = df["q_id"].apply(get_qid_num)
        filtered_df = df[(df["q_num"] >= 187) & (df["q_num"] <= 361)].copy()
        
        # 補助用の列を削除
        filtered_df = filtered_df.drop(columns=["q_num"])
        
        if len(filtered_df) == 0:
            st.error("指定範囲(q0187～q0361)の質問データが見つかりませんでした。全データを表示します。")
            return df
            
        return filtered_df
    except Exception as e:
        st.error(f"CSVのロードに失敗しました: {e}")
        return pd.DataFrame()

df_questions = load_questions(CSV_FILE_PATH)

# --- ユーザーデータ・ログイン管理 ---
def get_user_file(username, kind="stats"):
    # stats: ユーザーの戦績、log: 詳細回答ログ
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
    # 初期値
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
    # モデル回答は "/" 区切りで複数許容
    choices = [ans.strip() for ans in model_answer.split("/") if ans.strip()]
    cleaned_recognized = normalize_text(raw_recognized)
    
    for choice in choices:
        cleaned_choice = normalize_text(choice)
        # 完全一致、または認識文字の中に正解が含まれる
        if cleaned_choice in cleaned_recognized or cleaned_recognized in cleaned_choice:
            # 漢字部分が一致しているか等の簡易確認 (空文字排除)
            if len(cleaned_recognized) > 0 and len(cleaned_choice) > 0:
                return True
    return False

# --- 画像前処理 (OCR精度向上) ---
def preprocess_image(pil_img):
    # キャンバスから切り出されたRGBA画像をグレースケールに変換
    img_np = np.array(pil_img)
    if img_np.shape[2] == 4:
        # 透明度を考慮して白い背景と結合
        alpha = img_np[:, :, 3] / 255.0
        bg = np.ones_like(img_np[:, :, :3]) * 255
        for c in range(3):
            bg[:, :, c] = img_np[:, :, c] * alpha + bg[:, :, c] * (1 - alpha)
        gray = cv2.cvtColor(bg.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    else:
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # 2値化 (黒背景に白文字 or 白背景に黒文字)
    # キャンバスが明るい背景で、インクが暗い場合
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    
    # 文字部分のバウンディングボックスを検出し余白カット
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        # マージンを追加して切り抜き
        margin = 15
        h_img, w_img = gray.shape
        x_start = max(0, x - margin)
        y_start = max(0, y - margin)
        x_end = min(w_img, x + w + margin)
        y_end = min(h_img, y + h + margin)
        
        cropped = gray[y_start:y_end, x_start:x_end]
        # コントラスト改善
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
    st.session_state.q_index_list = random.sample(range(len(df_questions)), min(10, len(df_questions))) # 1プレイ10問
    st.session_state.current_quiz_pos = 0 # 10問中何問目か
    st.session_state.has_evaluated = False
    st.session_state.result_status = None # "correct", "incorrect", None
    st.session_state.ocr_text = ""
    st.session_state.canvas_key = 0 # キャンバスリセット用

if "game_active" not in st.session_state:
    st.session_state.game_active = False
if "game_over" not in st.session_state:
    st.session_state.game_over = False
if "user_stats" not in st.session_state:
    st.session_state.user_stats = None

# --- UI構築 ---
st.markdown('<div class="game-title">⚔️ 歴史手書きクエスト ⚔️</div>', unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9e9e9e;'>【出題範囲: 鎌倉・室町・戦国時代等 (q0187〜q0361)】正確な漢字手書きでハイスコアを狙え！</p>", unsafe_allow_html=True)

# ----------------- ログインセクション -----------------
if "username" not in st.session_state:
    st.subheader("👤 冒険者登録 / ログイン")
    username_input = st.text_input("プレイヤー名を入力してください:", max_chars=12, placeholder="例: レキシ丸").strip()
    
    if st.button("ゲームスタート！", use_container_width=True):
        if username_input:
            st.session_state.username = username_input
            st.session_state.user_stats = load_user_stats(username_input)
            st.success(f"ようこそ、{username_input} さん！データ読み込み完了。")
            st.rerun()
        else:
            st.warning("名前を入力してください。")
    st.stop()

# ----------------- ログイン後のステータス -----------------
username = st.session_state.username
stats = st.session_state.user_stats

# ログアウトボタンをサイドバーに配置
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
        st.rerun()

# ----------------- ゲームが開始されていないとき -----------------
if not st.session_state.game_active and not st.session_state.game_over:
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
            st.rerun()
    with col2:
        # 詳細履歴をアコーディオンで表示
        with st.expander("📝 あなたの過去の回答ログを表示"):
            logs_df = get_answer_logs(username)
            if not logs_df.empty:
                st.dataframe(logs_df.sort_values(by="datetime", ascending=False), use_container_width=True)
            else:
                st.info("まだ回答ログがありません。まずはクエストに挑戦してみましょう！")
    st.stop()

# ----------------- ゲームオーバー画面 -----------------
if st.session_state.game_over:
    play_sound("gameover")
    
    # ハイスコア・最大コンボ更新チェックと保存
    stats_updated = False
    if st.session_state.score > stats["high_score"]:
        stats["high_score"] = st.session_state.score
        stats_updated = True
    if st.session_state.combo > stats["max_combo"]:
        stats["max_combo"] = st.session_state.combo
        stats_updated = True
    
    # 累計更新
    stats["total_games"] += 1
    stats["total_questions"] += st.session_state.answered_count
    stats["correct_answers"] += st.session_state.correct_count
    save_user_stats(username, stats)
    
    # ランク算出
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
        st.toast("🏆 ハイスコアまたは最大コンボを更新しました！", icon="🎉")
    
    if st.button("🔄 もう一度クエストに挑戦する", use_container_width=True, type="primary"):
        init_game_state()
        st.rerun()
    if st.button("🏠 ロビー（トップ）に戻る", use_container_width=True):
        st.session_state.game_active = False
        st.session_state.game_over = False
        st.rerun()
    st.stop()

# ----------------- プレイ中のゲーム画面 -----------------

# 現在解くべき問題の情報を引き出す
current_pos = st.session_state.current_quiz_pos
q_list = st.session_state.q_index_list

# すべて完了したらクリア
if current_pos >= len(q_list) or st.session_state.lives <= 0:
    st.session_state.game_over = True
    st.session_state.game_active = False
    play_sound("clear")
    st.rerun()

current_q_idx = q_list[current_pos]
quiz_row = df_questions.iloc[current_q_idx]
q_id = quiz_row["q_id"]
question = quiz_row["question"]
model_answer = quiz_row["answer"]

# --- 画面上部ステータスバー ---
hearts_html = "".join(['<span class="heart-active">❤️</span>' for _ in range(st.session_state.lives)])
hearts_broken_html = "".join(['<span class="heart-broken">🖤</span>' for _ in range(3 - st.session_state.lives)])

st.markdown(f"""
    <div class="status-container">
        <div class="status-item">🏆 SCORE: <span class="status-val">{st.session_state.score}</span></div>
        <div class="status-item">🔥 COMBO: <span class="status-val">{st.session_state.combo}</span></div>
        <div class="status-item">💖 LIFE: {hearts_html}{hearts_broken_html}</div>
    </div>
""", unsafe_allow_html=True)

# 進捗プログレスバー
st.progress((current_pos + 1) / len(q_list), text=f"進捗: {current_pos + 1} / {len(q_list)} 問目")

# --- 問題提示カード ---
st.markdown(f"""
    <div class="quiz-card">
        <div class="quiz-num">問題 ID: {q_id}</div>
        <div class="quiz-text">{question}</div>
    </div>
""", unsafe_allow_html=True)

# ----------------- 手書きキャンバスセクション -----------------
col_canvas, col_control = st.columns([2, 1])

with col_canvas:
    st.write("✍️ 下の黒いキャンバスに、**マウスや指(タブレット)**で答えを書いてください。")
    canvas_result = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=6,
        stroke_color="#FFFFFF",
        background_color="#000000",
        height=180,
        width=400,
        drawing_mode="freedraw",
        key=f"canvas_{st.session_state.canvas_key}",
        update_streamlit=True,
    )

with col_control:
    st.markdown("<br>", unsafe_allow_html=True)
    # 決定ボタン
    submit_btn = st.button("🔥 判定する！", use_container_width=True, type="primary", disabled=st.session_state.has_evaluated)
    
    # 書き直す(リセット)ボタン
    if st.button("🧹 キャンバスをクリア", use_container_width=True):
        st.session_state.canvas_key += 1
        st.session_state.has_evaluated = False
        st.session_state.result_status = None
        st.rerun()

# ----------------- OCR判定処理 -----------------
if submit_btn:
    if canvas_result.image_data is not None:
        # 画像から手書き部分を抽出して判定
        img_data = canvas_result.image_data
        # 透明なだけか（全く書いてないか）の簡易判定
        if np.sum(img_data[:, :, 3]) > 0:
            with st.spinner("手書き文字をAIが解読中..."):
                try:
                    pil_img = Image.fromarray(img_data.astype('uint8'), 'RGBA')
                    # 精度向上のための前処理
                    processed_img = preprocess_image(pil_img)
                    
                    # EasyOCR での検出
                    img_np = np.array(processed_img)
                    ocr_results = reader.readtext(img_np)
                    
                    # 複数検出テキストを連結
                    detected_text = ""
                    if ocr_results:
                        detected_text = "".join([res[1] for res in ocr_results]).strip()
                    
                    # 空だった場合
                    if not detected_text:
                        detected_text = "（読み取れませんでした）"
                    
                    st.session_state.ocr_text = detected_text
                    
                    # 判定
                    is_correct = judge_answer(detected_text, model_answer)
                    st.session_state.has_evaluated = True
                    st.session_state.answered_count += 1
                    
                    if is_correct:
                        st.session_state.result_status = "correct"
                        st.session_state.combo += 1
                        st.session_state.correct_count += 1
                        # スコア計算: 基本点 100 ＋ コンボボーナス(1コンボにつき 20 点)
                        earned = 100 + (st.session_state.combo - 1) * 20
                        st.session_state.score += earned
                        st.session_state.earned_this_turn = earned
                        play_sound("correct")
                    else:
                        st.session_state.result_status = "incorrect"
                        st.session_state.lives -= 1
                        st.session_state.combo = 0
                        st.session_state.earned_this_turn = 0
                        play_sound("incorrect")
                        
                    # 回答ログの保存
                    save_answer_log(
                        username, 
                        q_id, 
                        question, 
                        model_answer, 
                        detected_text, 
                        is_correct, 
                        st.session_state.earned_this_turn
                    )
                    
                    st.rerun()
                except Exception as e:
                    st.error(f"判定エラー: {e}")
        else:
            st.warning("⚠️ キャンバスに何も書かれていません！")

# ----------------- 判定結果表示 & 次の問題へ -----------------
if st.session_state.has_evaluated:
    st.markdown("---")
    if st.session_state.result_status == "correct":
        st.balloons()
        st.markdown(f"""
        <div style="background-color: rgba(76, 175, 80, 0.2); border-left: 6px solid #4CAF50; padding: 1rem; border-radius: 8px;">
            <h3 style="color: #4CAF50; margin: 0;">🎉 正解！</h3>
            <p style="margin: 5px 0;">あなたの手書き文字認識: <b>{st.session_state.ocr_text}</b></p>
            <div class="combo-badge">🔥 {st.session_state.combo} COMBO (+{st.session_state.earned_this_turn} pts)</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background-color: rgba(244, 67, 54, 0.2); border-left: 6px solid #F44336; padding: 1rem; border-radius: 8px;">
            <h3 style="color: #F44336; margin: 0;">😭 不正解...</h3>
            <p style="margin: 5px 0;">あなたの手書き文字認識: <b>{st.session_state.ocr_text}</b></p>
            <p style="margin: 5px 0; font-size: 1.1rem;">正解の例: <span style="color: #FFC107; font-weight: bold;">{model_answer.replace('/', ' / ')}</span></p>
            <p style="margin: 0; color: #ccc; font-size: 0.9rem;">(ライフが1つ減少しました。コンボ終了)</p>
        </div>
        """, unsafe_allow_html=True)

    # 次へ進むボタン
    if st.button("➡️ 次の問題へ進む", use_container_width=True, type="primary"):
        # 状態リセット
        st.session_state.current_quiz_pos += 1
        st.session_state.has_evaluated = False
        st.session_state.result_status = None
        st.session_state.canvas_key += 1 # キャンバスを自動リフレッシュ
        st.rerun()

# ----------------- ゲームの中断 -----------------
st.markdown("<br><br>", unsafe_allow_html=True)
if st.button("🏳️ クエストを断念してリザルトへ進む", use_container_width=True, help="現在のスコアでゲームを終了します"):
    st.session_state.game_over = True
    st.session_state.game_active = False
    st.rerun()