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
        # A列(0)をquestion, B列(1)をanswerとして読み込む
        df = pd.read_excel(file_path, header=None, names=['question', 'answer'])
        return df
    except Exception as e:
        st.error(f"Excelの読み込み中にエラーが発生しました: {e}")
        return None

def main():
    st.set_page_config(page_title="自作クイズ学習アプリ", page_icon="📝")

    st.title("📝 自作クイズ学習アプリ")
    st.markdown("""
    Excelファイル (`questions.xlsx`) から問題をランダムに出題します。
    - **A列**: 問題文
    - **B列**: 正解
    """)

    # Excelファイルのパス
    file_name = "questions.xlsx"
    df = load_data(file_name)

    if df is None:
        st.warning(f"'{file_name}' が見つかりません。同じフォルダにExcelファイルを作成してアップロードしてください。")
        return

    # セッション状態の初期化
    if 'current_question' not in st.session_state:
        st.session_state.current_question = None
    if 'show_answer' not in st.session_state:
        st.session_state.show_answer = False

    # 操作ボタン
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

    # サイドバー情報
    st.sidebar.header("ステータス")
    st.sidebar.write(f"登録済み問題数: {len(df)} 問")

if __name__ == "__main__":
    main()