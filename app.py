import streamlit as st
import pandas as pd
import os
from streamlit_drawable_canvas import st_canvas

def load_data(file_path):
    """
    Excelファイルを読み込む関数
    A列: 問題, B列: 解答
    """
    if not os.path.exists(file_path):
        return None
    try:
        # ヘッダーなしで読み込み
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        return df
    except Exception as e:
        st.error(f"Excelの読み込み中にエラーが発生しました: {e}")
        return None

def main():
    st.set_page_config(page_title="手書きクイズ学習", page_icon="✍️", layout="centered")

    st.title("✍️ 手書き解答クイズアプリ")
    
    # Excelファイルの読み込み
    file_name = "questions.xlsx"
    df = load_data(file_name)

    if df is None:
        st.warning(f"'{file_name}' が見つかりません。GitHubにExcelファイルをアップロードしてください。")
        return

    # セッション状態（状態保持）の初期化
    if 'current_question' not in st.session_state:
        st.session_state.current_question = None
    if 'show_answer' not in st.session_state:
        st.session_state.show_answer = False
    if 'canvas_key' not in st.session_state:
        st.session_state.canvas_key = 0

    # サイドバー：問題の切り替え
    if st.button("次の問題を表示 ➔"):
        random_row = df.sample(n=1).iloc[0]
        st.session_state.current_question = {
            'q': random_row['question'],
            'a': random_row['answer']
        }
        st.session_state.show_answer = False
        # キャンバスをリセットするためにキーを更新
        st.session_state.canvas_key += 1

    # メイン画面の表示
    if st.session_state.current_question:
        st.markdown("---")
        st.subheader("【問題】")
        st.info(st.session_state.current_question['q'])

        st.write("▼ ここに解答を書いてください")
        
        # 手書きキャンバスの設定
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",  # 背景色
            stroke_width=3,                       # 線の太さ
            stroke_color="#000000",               # 線の色
            background_color="#ffffff",            # キャンバスの背景
            height=200,                           # 高さ
            width=500,                            # 幅
            drawing_mode="freedraw",              # 自由描画モード
            key=f"canvas_{st.session_state.canvas_key}",
        )

        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("答えを確認する"):
                st.session_state.show_answer = True
        
        with col2:
            if st.button("書き直す（リセット）"):
                st.session_state.canvas_key += 1
                st.rerun()

        # 答えの表示
        if st.session_state.show_answer:
            st.markdown("---")
            st.success(f"正解: {st.session_state.current_question['a']}")
            st.write("自分の書いた文字と見比べてみましょう！")
            
    else:
        st.write("上の「次の問題を表示」ボタンを押して開始してください。")

    # サイドバー情報
    st.sidebar.header("学習状況")
    st.sidebar.write(f"収録問題数: {len(df)} 問")

if __name__ == "__main__":
    main()