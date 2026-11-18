# Whisper GPU / CPU 대응 논의 기록 (2026-11-18)

배포(bat)와 GPU 없는 PC 대응을 논의한 내용 정리. 내부 기록이며 코드 반영 범위와 남은 일을 함께 적는다.

## 1. 결론 요약
- 배포는 exe 패키징보다 **bat 파일 2개(setup.bat · run.bat)** 가 현실적이다.
  - 의존성이 무겁다(MediaPipe, faster-whisper, GPU, Ollama). exe로 묶으면 용량이 수 GB가 되고 CUDA 경로 문제로 빌드가 자주 깨진다.
  - Ollama는 어차피 별도 설치라 exe의 원클릭 장점이 작다.
- Whisper는 **코드 하나**로 GPU/CPU를 모두 처리한다. 분기는 코드가 아니라 설정값(크기·장치·연산 방식)에서만 갈린다.

| 환경 | 크기 | 장치 | 연산 방식 |
|---|---|---|---|
| NVIDIA GPU 있음 | medium | cuda | float16 |
| 그 외 (GPU 없음, 인텔·AMD 내장그래픽 포함) | small | cpu | int8 |

## 2. 내장그래픽
- faster-whisper(ctranslate2)는 **CPU와 NVIDIA CUDA만** 지원한다. 인텔·AMD 내장그래픽, DirectML 경로는 없다.
- 인텔 내장그래픽 노트북은 CUDA 장치 0개로 잡혀 CPU 방식으로 간다.
- 내장그래픽 가속은 whisper.cpp(Vulkan), OpenVINO, ONNX Runtime(DirectML) 등 다른 라이브러리로 갈아타야 하며, 인식 코드를 새로 써야 해서 지금은 비용 대비 효과가 낮다.
- CPU small + int8의 실제 속도는 **이 프로젝트에서 측정하지 않았다** (일반적 예상: 짧은 명령 1~3초).

## 3. 코드 반영 내용 (app/ 폴더, 미커밋)
- `app/voicemodule.py`
  - `MODEL_SIZE = "medium"`과 기존 로드 줄(`WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")`)은 주석으로 남김.
  - `WHISPER_PROFILES`(gpu/cpu), `has_cuda_gpu()`, `resolve_whisper_profile()` 추가.
  - `auto`는 `ctranslate2.get_cuda_device_count()`로 GPU 유무를 확인.
- `app/settings.py`: 기본값 `"whisper_mode": "auto"`.
- `app/settings_window.py`: 음성 탭에 "음성 인식 실행 방식" 선택 상자(자동 / GPU / CPU). 바꾸면 **다음 실행부터** 적용(모델은 시작 때 한 번만 로드).
- `app/tray_main.py`: 저장 함수와 설정창 연결.
- 루트의 `voicemodule.py`(실험용 콘솔 버전)는 그대로 둠.
- 문법 검사(컴파일)만 했고 실행은 하지 않음.

## 4. bat 배포 구상 (아직 미작성)
- `setup.bat`: 가상환경 생성 → `pip install -r requirements.txt` → `nvidia-smi` 성공 여부로 GPU 판별 → GPU면 CUDA 패키지(nvidia-cublas-cu12, nvidia-cudnn-cu12) 설치 → `ollama pull`.
- `run.bat`: 가상환경 활성화 후 `pythonw app\main.py` (콘솔 창 없이 트레이 실행). 실제 진입 파일명은 확인 필요(트레이 앱은 `app/tray_main.py`).
- 판별 결과를 설정에 기록하는 방식과, 앱이 시작할 때 판별하는 방식(`auto`)이 둘 다 가능하다. 현재는 `auto`가 코드에 있으므로 bat은 CUDA 패키지 설치 분기만 맡아도 된다.
- 한글 출력은 `chcp 65001`과 UTF-8 저장 필요. 깨지면 영문 안내가 안전하다.

## 5. 남은 일 / 확인할 것
- 문서가 코드와 맞지 않는다. 고칠 곳:
  - `requirements.txt` 16번 줄 ("GPU 권장, CUDA 환경 필요")
  - `README.md` 약 326~328행, 369행 ("CUDA 고정이라 GPU가 없으면 실패")
  - 덱 9장 한계 칸 "GPU 없는 환경의 Whisper 대체 미구현" → 구현 후 "CUDA 외에는 CPU로 동작, 내장그래픽 가속은 미지원"
- 새 PC에서 GPU 방식이 바로 되는지 미확인. cuDNN 관련 오류가 나면 CUDA 패키지 설치 안내 필요.
- 시작 로그에서 `medium / cuda / float16`이 찍히는지, 설정창에서 CPU 선택 후 재실행했을 때 `small / cpu / int8`이 찍히는지 사용자가 확인.
- 첫 실행 때 모델을 내려받으므로 시간과 인터넷 연결이 필요하다는 점을 설명에 포함.
- GPU가 있어도 VRAM이 작으면 medium이 부담될 수 있음. 기준을 둘지 미정.
