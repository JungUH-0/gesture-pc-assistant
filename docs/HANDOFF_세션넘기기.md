# 세션 넘기기 (2026-11-18)

다른 PC(노트북)나 새 대화에서 이어갈 때 먼저 읽는 문서. 내부 기록이다.

## 프로젝트
- 개인 AI 비서: 손동작 · 음성 · 포즈를 로컬 LLM(Ollama, Qwen2.5-3B)으로 해석해 PC를 제어.
- 저장소: https://github.com/JungUH-0/gesture-pc-assistant
- 트레이 앱은 `app/` 폴더(진입 파일 `app/tray_main.py`), 루트의 `*.py`는 실험용 콘솔 버전.
- 환경: Windows, Python 3.10, `pip install -r requirements.txt`, Ollama 별도 설치 후 `ollama pull qwen2.5:3b-instruct`.

## 이번에 한 일 (11-18)
1. **포트폴리오 덱** `assistant_submit_pose.pptx`를 제출용 9장으로 정리 (소스: `myproject/ppt/build.js`, `node build.js submitpose`).
   - D:\정의형\202611\포폴모음 사본은 사용자가 PowerPoint에서 다시 저장한 파일이라 표지 "발표자: 정의형" 줄이 빠져 있음. 어느 쪽을 기준으로 할지 미정.
   - 음성 슬라이드 이미지는 나중에 교체 예정.
2. **Whisper GPU/CPU 대응** 코드 반영 (`app/`, 이번 커밋에 포함).
   - `whisper_mode`: auto / gpu / cpu. GPU면 medium·cuda·float16, 아니면 small·cpu·int8.
   - 설정창 음성 탭에 선택 상자. 바꾸면 다음 실행부터 적용.
   - 기존 `MODEL_SIZE`와 로드 줄은 주석으로 남김.
   - 논의 전체는 `docs/whisper_GPU_CPU_논의.md`.
3. **사용자 포즈 등록**(`app/posematcher.py`, `app/posestore.py` 등)도 이번 커밋에 같이 올라감.

## 검증 상태 (중요)
- Whisper 변경: **컴파일만 했고 실행하지 않음.**
- 포즈 등록·인식: 구현만 됨, **실제 카메라 인식은 사용자가 아직 검증하지 않음.** 인식 기준값은 추정치.
- 카메라·학습 코드는 Claude가 실행하지 않는다(사용자가 직접 실행).

## 다음 할 일 (노트북에서 확인 후 진행)
1. 노트북에서 시작 로그의 `Whisper 모델 로딩 중: 크기 / 장치 / 연산방식` 줄 확인. 내장그래픽이면 `small / cpu / int8`이어야 함.
2. CPU 방식에서 웨이크워드 인식이 되는지, 검사 1회 시간, 음성 켬/끔 FPS 차이 확인.
3. NVIDIA 노트북이 있다면 CUDA 라이브러리 없는 상태에서 `auto`가 어떻게 동작하는지 확인 (첫 인식 오류 가능성).
4. 결과에 따라 보완 결정:
   - GPU 판별을 짧은 인식 시험으로 검증하고 실패 시 CPU로 전환
   - CPU 방식 부하 줄이기 (소리 있을 때만 검사, 검사 주기 늘리기, `cpu_threads` 제한)
5. 배포: `setup.bat` / `run.bat` 구상은 논의 문서 4절. 아직 작성 안 함.
6. 낡은 문구 수정 (사용자가 말할 때만):
   - `requirements.txt` 16번 줄, `README.md` 326~328행 · 369행
   - 덱 9장 한계 칸 "GPU 없는 환경의 Whisper 대체 미구현"
   - GitHub 공개 문서라서 수정 후 푸시 전 확인

## 작업 원칙 (사용자 지시)
- 답변은 한국어 존댓말, 호칭 없이.
- 요청한 것 하나만. 관련 개선점은 넣지 말고 알리기만.
- 실행 전에 무엇을 왜 돌리는지 먼저 설명.
- 환경 설치(conda·pip)는 명령어만 안내, 대신 실행하지 않음.
- 카메라를 켜는 테스트·실행은 사용자가 직접.
- 슬라이드는 개조식(명사형), 제출용 문서는 한자어 명사구 + 마침표 없음.
