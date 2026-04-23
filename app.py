import streamlit as st
import asyncio
import edge_tts  
import os
import difflib
import html
import json
from pathlib import Path

# 페이지 설정
st.set_page_config(page_title="우리집 받아쓰기 마스터", page_icon="📝")

st.title("📝 우리집 받아쓰기 마스터")
st.caption("2, 3, 5학년 모두 모여라! 아빠가 만든 학년별 통합 앱")

# 데이터 로딩 (캐시 적용)
@st.cache_data
def load_dictation_data() -> dict:
    data_path = Path(__file__).with_name("dictation_data.json")
    with data_path.open("r", encoding="utf-8") as f:
        return json.load(f)

# 채점 유틸
def _normalize_for_scoring(text: str) -> str:
    # 유사도/정답 판정에만 사용: 앞뒤 공백 정리 + 연속 공백 1개로
    return " ".join((text or "").strip().split())

def _similarity_score(user_text: str, answer_text: str) -> int:
    u = _normalize_for_scoring(user_text)
    a = _normalize_for_scoring(answer_text)
    return int(round(difflib.SequenceMatcher(None, u, a).ratio() * 100))

def _diff_highlight_html(user_text: str, answer_text: str) -> tuple[str, str]:
    """
    ndiff 결과를 바탕으로 '내 입력'과 '정답'을 각각 HTML로 렌더링.
    - 틀린 글자/빠진 글자/추가 글자는 분홍 배경으로 표시
    """
    u = _normalize_for_scoring(user_text)
    a = _normalize_for_scoring(answer_text)

    user_out: list[str] = []
    ans_out: list[str] = []

    def _span(txt: str, is_wrong: bool) -> str:
        safe = html.escape(txt).replace("\u00A0", "&nbsp;").replace(" ", "&nbsp;")
        if is_wrong:
            return f"<span class='diff-wrong'>{safe}</span>"
        return f"<span class='diff-ok'>{safe}</span>"

    for line in difflib.ndiff(list(a), list(u)):
        tag = line[:2]
        ch = line[2:]
        if tag == "  ":
            user_out.append(_span(ch, False))
            ans_out.append(_span(ch, False))
        elif tag == "- ":
            # 정답에는 있는데 내가 빠뜨린 글자
            ans_out.append(_span(ch, True))
            # 내 입력에는 '□'를 추가하지 않고, 빈칸을 분홍색으로만 표시
            user_out.append(_span("\u00A0\u00A0", True))
        elif tag == "+ ":
            # 내가 추가로 쓴 글자
            user_out.append(_span(ch, True))
        else:
            # "? " 라인 (힌트) 는 표시하지 않음
            continue

    user_html = "".join(user_out) if user_out else _span("", False)
    ans_html = "".join(ans_out) if ans_out else _span("", False)

    return user_html, ans_html

# 1. 데이터 설정 (JSON에서 로딩)
try:
    dictation_data = load_dictation_data()
except FileNotFoundError:
    st.error("`dictation_data.json` 파일을 찾을 수 없어요. 앱 폴더에 파일이 있는지 확인해줘요.")
    st.stop()
except json.JSONDecodeError as e:
    st.error(f"`dictation_data.json` 파일 형식이 올바르지 않아요. (JSON 파싱 오류: {e})")
    st.stop()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했어요: {e}")
    st.stop()

# 2. 사이드바 - 학년 및 급수 선택
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 학년 선택
    selected_grade = st.selectbox("학년을 선택하세요", list(dictation_data.keys()))
    
    # 선택된 학년에 맞는 급수 리스트
    grade_levels = list(dictation_data[selected_grade].keys())
    level = st.selectbox(f"{selected_grade} 급수 선택", grade_levels)
    
    # 속도 조절
    speed_rate = st.slider("말하기 속도 조절 (%)", min_value=-50, max_value=0, value=-20, step=5)
    rate_str = f"{speed_rate}%"
    
    st.divider()
    if st.button("🔄 기록 초기화"):
        st.session_state.clear()
        st.rerun()

# 3. 문제 선택 로직
sentences = dictation_data[selected_grade][level]
problem_list = [f"{i}번 문제" for i in range(1, len(sentences) + 1)]

selected_label = st.selectbox(
    "풀고 싶은 문제를 고르세요",
    options=problem_list,
    index=0
)

selected_idx = int(selected_label.replace("번 문제", ""))
target = sentences[selected_idx - 1]

# 4. 메인 화면 - 문제 풀이
st.divider()
st.write(f"### [ {selected_grade} {level} ] {selected_label}")

col1, col2 = st.columns([1, 2])

with col1:
    if st.button("🔊 소리 듣기", use_container_width=True):
        with st.spinner('아빠 목소리 변환 중...'):
            try:
                voice = "ko-KR-SunHiNeural" 
                async def make_voice():
                    communicate = edge_tts.Communicate(target, voice, rate=rate_str)
                    await communicate.save("temp_voice.mp3")
                asyncio.run(make_voice())
                st.audio("temp_voice.mp3", autoplay=True)
            except Exception as e:
                st.error(f"오류가 발생했어요: {e}")

with col2:
    user_input = st.text_input(
        "문장을 써보세요", 
        key=f"input_{selected_grade}_{level}_{selected_label}",
        placeholder="받아쓰기 준비 완료!"
    )

# 5. 채점 및 결과
if st.button("✅ 채점하기", type="primary", use_container_width=True):
    if not user_input.strip():
        st.warning("먼저 정답을 입력해야지!")
    else:
        st.markdown(
            """
            <style>
              .diff-wrap { line-height: 1.9; font-size: 1.05rem; }
              .diff-label { font-weight: 700; margin-right: 8px; }
              .diff-box { padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.10); }
              .diff-ok { padding: 1px 0px; }
              .diff-wrong { background: pink; color: #111; padding: 1px 2px; border-radius: 4px; }
              .score-pill { display:inline-block; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.20); }
            </style>
            """,
            unsafe_allow_html=True,
        )

        similarity = _similarity_score(user_input, target)
        user_html, ans_html = _diff_highlight_html(user_input, target)

        st.markdown(f"<div class='score-pill'>[유사도 점수: {similarity}점]</div>", unsafe_allow_html=True)

        is_perfect = _normalize_for_scoring(user_input) == _normalize_for_scoring(target)
        if is_perfect:
            st.success("🎉 정답이야! 정말 대단한걸? (Bagus sekali!)")
            st.balloons()
        elif similarity >= 80:
            st.warning("아까워! 한 글자만 더 확인해볼까? (Hampir 맞았어요!)")
        else:
            st.error("다시 한번 집중해서 들어보자!")

        st.markdown(
            f"""
            <div class="diff-wrap diff-box">
              <div><span class="diff-label">내 입력</span>{user_html}</div>
              <div style="margin-top:6px;"><span class="diff-label">정답</span>{ans_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("💡 정답 확인하기"):
            st.markdown(
                f"""
                <div class="diff-wrap diff-box">
                  <div><span class="diff-label">정답</span>{ans_html}</div>
                  <div style="margin-top:6px;"><span class="diff-label">내 입력</span>{user_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# 6. 진행 상황 표시
st.divider()
progress = selected_idx / len(sentences)
st.progress(progress, text=f"{selected_grade} {level} 진행률: {int(progress*100)}%")