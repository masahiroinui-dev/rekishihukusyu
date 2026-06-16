import streamlit as st
import pandas as pd
import random
import numpy as np
import re
import os
from datetime import datetime
import streamlit.components.v1 as components

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

# --- CSV問題データのロードとフィルタリング (q0187〜q0361) ---
CSV_FILE_PATH = "rekishi_questions.xlsx - Sheet1.csv"

@st.cache_data
def load_questions_safe(filepath):
    def create_fallback_data():
        dummy_data = []
        for i in range(187, 362):
            dummy_data.append([f"q{i:04d}", f"【テスト問題 {i}】織田信長が明智光秀に襲われた京都のお寺はどこか？(答え:本能寺)", "本能寺"])
        df_fallback = pd.DataFrame(dummy_data, columns=["q_id", "question", "answer"])
        return df_fallback, False

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

# --- 🛡️ 超安定 HTML5 手書きカスタムコンポーネント (Google Input Tools API搭載) ---
# このフォルダ/HTMLファイルを起動時に動的生成し、双方向通信コンポーネントとして宣言。
# React iframe のアンマウントを完全に回避し、100%安全かつ世界最高の手書き漢字認識を提供します。

HTML_CONTENT = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="streamlit-component-lib.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #000000;
            color: #ffffff;
            font-family: sans-serif;
            overflow: hidden;
        }
        #canvas-container {
            position: relative;
            width: 100%;
            max-width: 400px;
            margin: 0 auto;
        }
        canvas {
            background-color: #111115;
            border: 2px solid #3f3f52;
            border-radius: 12px;
            display: block;
            touch-action: none;
            cursor: crosshair;
        }
        #tools {
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            max-width: 400px;
            margin-left: auto;
            margin-right: auto;
        }
        button {
            background-color: #2b2b36;
            border: 1px solid #3f3f52;
            color: #ffffff;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.2s ease;
            flex: 1;
            margin: 0 4px;
        }
        button:hover {
            background-color: #ff9800;
            color: #000000;
            border-color: #ff9800;
        }
        #btn-submit {
            background-color: #ff9800;
            color: #000000;
            border-color: #ff9800;
        }
        #btn-submit:hover {
            background-color: #ffa726;
        }
        #status {
            text-align: center;
            font-size: 12px;
            color: #888;
            margin-top: 6px;
        }
    </style>
</head>
<body>
    <div id="canvas-container">
        <canvas id="canvas" width="400" height="180"></canvas>
        <div id="tools">
            <button id="btn-clear">🧹 クリア</button>
            <button id="btn-submit">🔥 判定する！</button>
        </div>
        <div id="status">ここに文字を書いてください</div>
    </div>

    <script>
        // Streamlit APIの初期化
        function onStreamlitAPIReady() {
            Streamlit.setFrameHeight(245);
        }
        
        if (window.Streamlit) {
            onStreamlitAPIReady();
        } else {
            window.addEventListener("message", function(e) {
                if (e.data.type === "streamlit:render") {
                    if (window.Streamlit) onStreamlitAPIReady();
                }
            });
        }

        const canvas = document.getElementById("canvas");
        const ctx = canvas.getContext("2d");
        const btnClear = document.getElementById("btn-clear");
        const btnSubmit = document.getElementById("btn-submit");
        const statusDiv = document.getElementById("status");

        // ストロークデータの記録用
        let ink = [];
        let currentStrokeX = [];
        let currentStrokeY = [];
        let currentStrokeT = [];
        let isDrawing = false;
        let lastX = 0;
        let lastY = 0;

        // 描画パラメータ設定
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 6;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        function getPos(e) {
            const rect = canvas.getBoundingClientRect();
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;
            return {
                x: clientX - rect.left,
                y: clientY - rect.top
            };
        }

        function startDrawing(e) {
            isDrawing = true;
            const pos = getPos(e);
            lastX = pos.x;
            lastY = pos.y;
            
            currentStrokeX = [pos.x];
            currentStrokeY = [pos.y];
            currentStrokeT = [Date.now()];
            
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y);
            e.preventDefault();
        }

        function draw(e) {
            if (!isDrawing) return;
            const pos = getPos(e);
            
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(pos.x, pos.y);
            ctx.stroke();
            
            lastX = pos.x;
            lastY = pos.y;
            
            currentStrokeX.push(pos.x);
            currentStrokeY.push(pos.y);
            currentStrokeT.push(Date.now());
            
            e.preventDefault();
        }

        function stopDrawing(e) {
            if (!isDrawing) return;
            isDrawing = false;
            
            if (currentStrokeX.length > 0) {
                ink.push([currentStrokeX, currentStrokeY, currentStrokeT]);
            }
            e.preventDefault();
        }

        // マウス & タッチイベントハンドラ
        canvas.addEventListener("mousedown", startDrawing);
        canvas.addEventListener("mousemove", draw);
        window.addEventListener("mouseup", stopDrawing);

        canvas.addEventListener("touchstart", startDrawing, {passive: false});
        canvas.addEventListener("touchmove", draw, {passive: false});
        window.addEventListener("touchend", stopDrawing);

        // 🧹 画面クリア処理
        btnClear.addEventListener("click", () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ink = [];
            statusDiv.textContent = "クリアしました。文字を書いてください。";
            statusDiv.style.color = "#888";
            if (window.Streamlit) {
                Streamlit.setComponentValue(""); // 空文字を返却
            }
        });

        // 🤖 Google Input Tools API を用いた超高精度手書き認識
        btnSubmit.addEventListener("click", async () => {
            if (ink.length === 0) {
                statusDiv.textContent = "⚠️ キャンバスに何も書かれていません！";
                statusDiv.style.color = "#ff9800";
                return;
            }

            statusDiv.textContent = "🤖 AIで文字を高速解読中...";
            statusDiv.style.color = "#ff9800";

            const payload = {
                "app": "mobilesearch",
                "iscjk": "1",
                "oe": "utf-8",
                "input_type": "0",
                "car_backspace": "1",
                "car_forwardspace": "1",
                "car_space": "1",
                "car_newline": "1",
                "car_tab": "1",
                "ink": ink,
                "language": "ja"
            };

            try {
                const response = await fetch("https://www.google.com/inputtools/request?ime=handwriting&app=mobilesearch&cs=1&oe=utf-8", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                if (data && data[0] === "SUCCESS" && data[1] && data[1][0] && data[1][0][1]) {
                    const candidates = data[1][0][1];
                    const bestCandidate = candidates[0]; // 最有力候補の漢字
                    
                    statusDiv.textContent = `解読結果: 「${bestCandidate}」 を判定中...`;
                    statusDiv.style.color = "#4CAF50";
                    
                    // Streamlit（Python側）へリアルタイムに双方向通信！
                    if (window.Streamlit) {
                        Streamlit.setComponentValue(bestCandidate);
                    }
                } else {
                    throw new Error("フォーマットエラー");
                }
            } catch (err) {
                statusDiv.textContent = "⚠️ 通信エラーが発生しました。もう一度判定ボタンを押してください。";
                statusDiv.style.color = "#F44336";
            }
        });
    </script>
</body>
</html>
"""

# --- 🛡️ 起動時の一時フォルダ構築 ＆ コンポーネント登録 ---
PARENT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PARENT_DIR, "handwriting_component")

if not os.path.exists(BUILD_DIR):
    os.makedirs(BUILD_DIR)

# index.html 書き出し
with open(os.path.join(BUILD_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(HTML_CONTENT)

# Streamlit Component 宣言 (双方向バインディング)
handwriting_canvas = components.declare_component("handwriting_canvas", path=BUILD_DIR)

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
if "canvas_reset_trigger" not in st.session_state:
    st.session_state.canvas_reset_trigger = 0

# 安全な問題データバインディング
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
def handle_next_question():
    st.session_state.current_q_idx = random.randint(0, len(df_questions) - 1) if len(df_questions) > 0 else 0
    st.session_state.has_evaluated = False
    st.session_state.result_status = None
    st.session_state.ocr_text = ""
    st.session_state.info_msg = ""
    st.session_state.canvas_reset_trigger += 1 # コンポーネントを安全にリセット

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
st.markdown(f"""
    <div class="quiz-card">
        <div class="quiz-num">問題 ID: {q_id}</div>
        <div class="quiz-text">{question}</div>
    </div>
""", unsafe_allow_html=True)

# 5. 手書きコンポーネントの配置（完全不変DOM ➔ 100%クラッシュフリー）
st.write("✍️ 下の黒いキャンバスに、答えを漢字で書いて「判定する！」を押してください。")

# 双方向通信手書きカスタムコンポーネントを実行！
# ユーザーがHTML側で「判定する！」を押すと、認識結果の文字列がPython側に一瞬で入ります。
recognized_text = handwriting_canvas(key=f"handwriting_canvas_trigger_v_{st.session_state.canvas_reset_trigger}")

# 6. リアルタイム判定トリガー処理（Streamlit標準の安全同期処理）
if recognized_text and not st.session_state.has_evaluated:
    # 認識された文字列を検知
    st.session_state.ocr_text = recognized_text
    st.session_state.has_evaluated = True
    st.session_state.answered_count += 1
    
    is_correct = judge_answer(recognized_text, model_answer)
    
    if is_correct:
        st.session_state.result_status = "correct"
        st.session_state.combo += 1
        st.session_state.correct_count += 1
        earned = 100 + (st.session_state.combo - 1) * 20
        st.session_state.score += earned
        st.session_state.earned_this_turn = earned
        st.session_state.info_msg = f"🎯 正解！ 認識文字: {recognized_text} (+{earned} pts)"
    else:
        st.session_state.result_status = "incorrect"
        st.session_state.combo = 0
        st.session_state.earned_this_turn = 0
        st.session_state.info_msg = f"❌ 不正解... 認識文字: {recognized_text} (正解：{model_answer.replace('/', ' / ')})"
        
    # 個人データの更新と保存
    stats["total_questions"] += 1
    if is_correct:
        stats["correct_answers"] += 1
    if st.session_state.score > stats["high_score"]:
        stats["high_score"] = st.session_state.score
    if st.session_state.combo > stats["max_combo"]:
        stats["max_combo"] = st.session_state.combo
    
    save_user_stats(username, stats)
    save_answer_log(username, q_id, question, model_answer, recognized_text, is_correct, st.session_state.earned_this_turn)
    st.rerun()

# 7. 判定結果の表示スロット (動的なHTML挿入でも、キャンバス自体が不変なので100%安全に稼働)
st.markdown("---")
result_placeholder = st.empty()

if st.session_state.has_evaluated:
    if st.session_state.result_status == "correct":
        # ✨ 正解時のゴールドアニメーション演出（DOM変化なしで安全）
        html_msg = f"""
        <div class="correct-effect-box">
            <h4 style="color: #4CAF50; margin: 0 0 0.5rem 0; font-weight: 800;">🎯 正解！</h4>
            <p style="margin: 0; color: #ffffff; font-size: 1.1rem; font-weight: bold;">
                書いた漢字: <span style="color: #FFC107;">{st.session_state.ocr_text}</span> (+{st.session_state.get('earned_this_turn', 100)} pts)
            </p>
            <div class="combo-badge" style="margin-top: 0.5rem;">🔥 {st.session_state.combo} COMBO !</div>
        </div>
        """
    else:
        # ❌ 不正解時のフェードインカード
        html_msg = f"""
        <div class="incorrect-effect-box">
            <h4 style="color: #F44336; margin: 0 0 0.5rem 0; font-weight: 800;">❌ 不正解...</h4>
            <p style="margin: 0 0 0.5rem 0; color: #ffffff; font-size: 1rem;">
                認識された文字: <span style="color: #ccc;">{st.session_state.ocr_text}</span>
            </p>
            <p style="margin: 0; color: #FF9800; font-size: 1.05rem; font-weight: bold;">
                正解: {model_answer.replace('/', ' / ')}
            </p>
        </div>
        """
else:
    html_msg = """
    <div class="guide-box" style="background-color: #1e1e24; border: 1px solid #3f3f52;">
        <h4 style="color: #ccc; margin: 0 0 0.5rem 0;">📋 判定結果待ち</h4>
        <p style="margin: 0; color: #888; font-size: 0.95rem;">キャンバスに漢字を書き、左下の「🔥 判定する！」ボタンを押してください。</p>
    </div>
    """

result_placeholder.markdown(html_msg, unsafe_allow_html=True)

# 8. 次の問題へ進むボタン
st.button("➡️ 次の問題へ進む", use_container_width=True, type="primary", disabled=not st.session_state.has_evaluated, on_click=handle_next_question)