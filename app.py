import streamlit as st
import pandas as pd
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
from PIL import Image, ImageOps, ImageFilter
import random
import difflib
import cv2

# ページ設定
st.set_page_config(page_title="英単語手書き採点アプリ", layout="centered")

@st.cache_resource
def load_ocr():
    # アルファベットのみをターゲットにロード
    return easyocr.Reader(['en'], gpu=False)

reader = load_ocr()

@st.cache_data
def load_data():
    try:
        df = pd.read_excel("questions.xlsx")
        df.columns = df.columns.str.strip()
        df = df.dropna(subset=["sentence", "word", "meaning"])
        return df
    except Exception as e:
        st.error(f"エラー: {e}")
        return pd.DataFrame(columns=["sentence", "word", "meaning"])

df = load_data()

# サイドバー設定
st.sidebar.title("🖌️ 書き心地と精度の調整")
stroke_width = st.sidebar.slider("ペンの太さ", 1, 15, 7)
st.sidebar.info("【精度向上のコツ】\n・dの縦棒を長めに書く\n・aの丸をしっかり閉じる\n・gの尻尾を明確に下げる")

if 'q_index' not in st.session_state:
    st.session_state.q_index = random.randint(0, len(df)-1) if not df.empty else 0
if 'answer_status' not in st.session_state:
    st.session_state.answer_status = None

st.title("📝 例文穴埋め手書き練習")

if not df.empty:
    current_question = df.iloc[st.session_state.q_index]
    
    with st.container():
        st.info(f"💡 **意味**: {current_question['meaning']}")
        raw_sentence = str(current_question['sentence'])
        display_sentence = raw_sentence.replace("[ ]", " ___ ( ? ) ___ ")
        st.markdown(f"### {display_sentence}")

    # キャンバス
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=stroke_width,
        stroke_color="#000000",
        background_color="#ffffff",
        height=250,
        width=600,
        drawing_mode="freedraw",
        key=f"canvas_{st.session_state.q_index}",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("採点する", use_container_width=True):
            if canvas_result.image_data is not None:
                # 1. 画像の取得とグレースケール化
                img_rgba = canvas_result.image_data.astype('uint8')
                # 透明度がある場合は白背景と合成
                img_pil = Image.fromarray(img_rgba)
                bg = Image.new("RGB", img_pil.size, (255, 255, 255))
                bg.paste(img_pil, mask=img_pil.split()[3])
                
                # 2. OpenCV形式に変換して画像処理
                open_cv_image = np.array(bg)
                gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
                
                # 二値化処理 (文字をはっきりさせる)
                _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
                
                # 文字の線を少し太くする（膨張処理）
                kernel = np.ones((2,2), np.uint8)
                dilated = cv2.dilate(binary, kernel, iterations=1)
                
                # 再度白背景に黒文字に戻す
                processed_img = cv2.bitwise_not(dilated)
                
                with st.spinner('AIが形状を分析中...'):
                    # 3. OCR認識
                    # allowlistで数字（0, 9など）を排除
                    results = reader.readtext(
                        processed_img, 
                        detail=0, 
                        allowlist='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
                        mag_ratio=2.0 # 拡大認識
                    )
                    recognized_text = "".join(results).replace(" ", "").lower()
                    
                    correct_word = str(current_question['word']).strip().lower()
                    
                    # 4. 判定ロジック
                    similarity = difflib.SequenceMatcher(None, recognized_text, correct_word).ratio()
                    
                    if recognized_text == correct_word:
                        st.session_state.answer_status = ("success", f"完璧です！ 正解: {correct_word}")
                    elif similarity >= 0.75: # 予測精度のしきい値を少し下げて柔軟に
                        st.session_state.answer_status = ("success", f"正解！ (認識結果: {recognized_text} → 推測判定: {correct_word})")
                    else:
                        st.session_state.answer_status = ("error", f"認識結果: {recognized_text} / 正解: {correct_word}")
            else:
                st.warning("何か書いてください。")

    with col2:
        if st.button("次の問題へ ➡️", use_container_width=True):
            if len(df) > 1:
                new_idx = st.session_state.q_index
                while new_idx == st.session_state.q_index:
                    new_idx = random.randint(0, len(df)-1)
                st.session_state.q_index = new_idx
            st.session_state.answer_status = None
            st.rerun()

    if st.session_state.answer_status:
        status, msg = st.session_state.answer_status
        if status == "success":
            st.success(msg)
            st.balloons()
            st.markdown(f"✅ **{raw_sentence.replace('[ ]', f'**{current_question['word']}**')}**")
        else:
            st.error(msg)
            st.caption("【ヒント】dは縦棒を長く、aは丸を閉じて書くとAIが認識しやすくなります。")
            if st.checkbox("認識された画像を表示（デバッグ用）"):
                st.image(processed_img, caption="AIに渡されている画像の状態")
else:
    st.warning("問題データがありません。")