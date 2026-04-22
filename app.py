import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import random
import os

# --- Data Loading ---
@st.cache_data
def load_data(file_path):
    """
    Excelファイルを読み込む関数
    A列: 問題, B列: 解答 (ヘッダーなし)
    """
    if not os.path.exists(file_path):
        return None
    try:
        # A列(0)をquestion, B列(1)をanswerとして読み込み
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        # 問題が空の行を削除
        df = df.dropna(subset=['question'])
        return df
    except Exception as e:
        st.error(f"Excelの読み込み中にエラーが発生しました: {e}")
        return None

def main():
    st.set_page_config(page_title="手書き学習アプリ", layout="centered")

    st.title("📝 手書き学習アプリ")
    st.caption("Excelから問題を読み込み、手書きで解答するアプリです。")

    # Excelファイルのパス指定
    file_name = "questions.xlsx"
    df = load_data(file_name)

    if df is None or df.empty:
        st.warning(f"'{file_name}' が見つかりません。GitHubにExcelファイルをアップロードしてください。")
        st.info("Excelは、A列に「問題」、B列に「解答」を入力してください。")
        return

    # セッション状態の初期化
    if 'q_index' not in st.session_state:
        st.session_state.q_index = random.randint(0, len(df) - 1)
    if 'show_answer' not in st.session_state:
        st.session_state.show_answer = False
    if 'canvas_key' not in st.session_state:
        st.session_state.canvas_key = 0

    # 現在の問題を取得
    current_q = df.iloc[st.session_state.q_index]

    st.markdown("---")
    st.subheader("【問題】")
    st.info(current_q['question'])

    st.write("▼ 下の枠に解答を書いてください")
    
    # 手書きキャンバスの設定
    # keyを更新することで「書き直し」時にキャンバスをリセットします
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=4,
        stroke_color="#000000",
        background_color="#ffffff",
        height=250,
        width=600,
        drawing_mode="freedraw",
        key=f"canvas_{st.session_state.canvas_key}",
    )

    # ボタン配置
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("答えを確認", use_container_width=True):
            st.session_state.show_answer = True
            st.rerun()

    with col2:
        if st.button("書き直す", use_container_width=True):
            st.session_state.canvas_key += 1
            st.rerun()

    with col3:
        if st.button("次の問題へ ➔", use_container_width=True):
            st.session_state.q_index = random.randint(0, len(df) - 1)
            st.session_state.show_answer = False
            st.session_state.canvas_key += 1
            st.rerun()

    # 解答の表示
    if st.session_state.show_answer:
        st.markdown("---")
        st.subheader("正解:")
        st.success(f"{current_q['answer']}")
        st.write("自分の書いた文字と合っているか確認しましょう！")

    # サイドバーに登録数を表示
    st.sidebar.header("学習ステータス")
    st.sidebar.write(f"登録問題数: {len(df)} 問")

if __name__ == "__main__":
    main()