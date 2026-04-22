import streamlit as st
import pandas as pd
import random
import os

def load_data(file_path):
    """
    Excelファイルを読み込む関数
    A列: 問題, B列: 解答
    """
    if not os.path.exists(file_path):
        return None
    try:
        # ヘッダーがない場合を想定し、header=None、列名を指定
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        return df
    except Exception as e:
        st.error(f"Error loading Excel file: {e}")
        return None

def main():
    st.set_page_config(page_title="自作クイズアプリ", page_icon="📝")

    st.title("📝 自作クイズ学習アプリ")
    st.markdown("""
    Excelファイル (`questions.xlsx`) から問題を読み込みます。
    - **A列**: 問題文
    - **B列**: 正解
    """)

    # Excelの読み込み
    file_name = "questions.xlsx"
    df = load_data(file_name)

    if df is None:
        st.warning(f"'{file_name}' が見つかりません。同じフォルダにExcelファイルを作成してください。")
        return

    if 'current_question' not in st.session_state:
        st.session_state.current_question = None
    if 'show_answer' not in st.session_state:
        st.session_state.show_answer = False

    # 問題を出すボタン
    if st.button("次の問題を表示"):
        # ランダムに1行選択
        random_row = df.sample(n=1).iloc[0]
        st.session_state.current_question = {
            'q': random_row['question'],
            'a': random_row['answer']
        }
        st.session_state.show_answer = False

    # 問題の表示
    if st.session_state.current_question:
        st.markdown("---")
        st.subheader("問題:")
        st.info(st.session_state.current_question['q'])

        # 答えを見るボタン
        if st.button("答えを確認"):
            st.session_state.show_answer = True

        # 答えの表示
        if st.session_state.show_answer:
            st.success(f"正解: {st.session_state.current_question['a']}")
    else:
        st.write("上のボタンを押してクイズを開始してください。")

    # サイドバーに現在のデータ数（問題数）を表示
    st.sidebar.write(f"現在の登録問題数: {len(df)} 問")

if __name__ == "__main__":
    main()