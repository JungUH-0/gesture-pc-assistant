# ============================================================
#  프레임 저하 원인 확인용 스크립트
#  카메라만 돌릴 때와, 오디오/음성(Whisper)을 하나씩 더할 때의 FPS를 구간별로 비교한다.
#  카메라 창은 띄우지 않고, PC 제어(main.py)도 하지 않는다.
#
#  구간 (총 약 1분):
#   1. 손 모드, 카메라만
#   2. 포즈 모드, 카메라만
#   3. 포즈 모드 + 오디오(AudioModule)
#   4. 포즈 모드 + 오디오 + 음성(VoiceModule, 웨이크워드 검사)
#   5. 손 모드 + 오디오 + 음성
#  구간마다 평균 / 최저 / 하위 5% FPS와 (음성 구간은) 웨이크워드 검사 1회 소요 시간을 출력한다.
#
#  사용: python perf_check.py   (카메라 앞에 앉은 채로 끝날 때까지 기다리면 된다)
# ============================================================

import time
import threading

from cameramodule import CameraModule
from posemodule import PoseModule
from audiomodule import AudioModule
from voicemodule import VoiceModule

SAMPLE_SEC = 0.05     # FPS 읽는 주기
PHASE_SEC  = 10.0     # 구간 길이
WARMUP_SEC = 1.5      # 구간 시작 직후 값은 버림 (전환 직후 흔들림)


def _measure(cam, label, voice=None):
    n_before = len(voice.check_times) if voice else 0
    samples = []
    start = time.time()
    while time.time() - start < PHASE_SEC:
        time.sleep(SAMPLE_SEC)
        if time.time() - start < WARMUP_SEC:
            continue
        fps = cam.get_result()["fps"]
        if fps > 0:
            samples.append(fps)

    samples.sort()
    avg = sum(samples) / len(samples)
    low5 = samples[max(int(len(samples) * 0.05) - 1, 0)]
    print(f"[{label}] 평균 {avg:5.1f} / 최저 {samples[0]:5.1f} / 하위5% {low5:5.1f} FPS")

    if voice:
        times = voice.check_times[n_before:]
        if times:
            print(f"        웨이크워드 검사 {len(times)}회: 평균 {sum(times)/len(times):.2f}초, 최대 {max(times):.2f}초 "
                  f"(검사 주기 1.5초 + 검사 시간)")
    return avg


if __name__ == "__main__":
    print("[perf_check] 모듈 준비 중 (Whisper 모델 로딩 포함, 시간이 걸릴 수 있음)")
    pose = PoseModule()
    cam = CameraModule(camera_id=0, show_window=False, pose_module=pose)
    audio = AudioModule()
    voice = VoiceModule()

    cam.set_mode("hand")
    threading.Thread(target=cam.run, daemon=True).start()
    time.sleep(2.0)  # 카메라 시작 대기

    print(f"[perf_check] 측정 시작 - 구간당 {PHASE_SEC:.0f}초, 카메라 앞에 앉아 계세요")
    results = {}
    results["1 손, 카메라만"] = _measure(cam, "1 손, 카메라만")

    cam.set_mode("pose")
    results["2 포즈, 카메라만"] = _measure(cam, "2 포즈, 카메라만")

    threading.Thread(target=audio.run, daemon=True).start()
    results["3 포즈 + 오디오"] = _measure(cam, "3 포즈 + 오디오")

    threading.Thread(target=voice.run, daemon=True).start()
    results["4 포즈 + 오디오 + 음성"] = _measure(cam, "4 포즈 + 오디오 + 음성", voice)

    cam.set_mode("hand")
    results["5 손 + 오디오 + 음성"] = _measure(cam, "5 손 + 오디오 + 음성", voice)

    cam.running = False
    audio.stop()
    voice.stop()
    print("[perf_check] 끝 - 2→3→4 구간에서 평균이 크게 떨어지는 지점이 원인입니다")
