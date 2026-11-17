# ============================================================
#  양손 모임(모드 전환) 판정 진단용 스크립트
#  카메라 + MediaPipe 손 인식만 돌려서, 양손이 검출되는 비율과 두 손 중심 거리,
#  "양손 모임" 상태가 끊기지 않고 이어진 시간을 보여 준다. (PC 제어는 하지 않음)
#
#  사용: python hands_check.py
#        카운트다운 뒤 30초 동안 양손을 모아 2초 유지 -> 떼기를 3번 반복한다.
#  전환에는 끊김 없는 1.0초 이상의 구간이 필요하다 (main.py의 MODE_SWITCH_HOLD_SEC).
# ============================================================

import time

import cv2 as cv
import numpy as np
import mediapipe as mp

CENTER = [0, 5, 9, 13, 17]   # 손 중심점 계산용 랜드마크 (cameramodule.HAND_CENTER_INDICES와 같음)
TH = 0.15                    # 양손 모임 거리 기준 (cameramodule.HANDS_TOGETHER_THRESHOLD와 같음)
COUNTDOWN_SEC = 5
MEASURE_SEC = 30

hands = mp.solutions.hands.Hands(max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5)
cap = cv.VideoCapture(0, cv.CAP_DSHOW)
print("카메라 열림:", cap.isOpened(), flush=True)

for i in range(COUNTDOWN_SEC, 0, -1):
    cap.read()
    print(f"준비... {i}", flush=True)
    time.sleep(1)
print(f">>> 측정 시작: 양손을 모아 2초 유지 -> 떼기를 3번 반복하세요 ({MEASURE_SEC}초)", flush=True)

t0 = time.time()
frames = 0
cnt = {0: 0, 1: 0, 2: 0}
dists = []
stretches = []
start = None
together_frames = 0

while time.time() - t0 < MEASURE_SEC:
    ok, f = cap.read()
    if not ok:
        break
    res = hands.process(cv.cvtColor(cv.flip(f, 1), cv.COLOR_BGR2RGB))
    n = len(res.multi_hand_landmarks) if res.multi_hand_landmarks else 0
    frames += 1
    cnt[n] += 1

    together = False
    if n == 2:
        c = [(np.mean([h.landmark[j].x for j in CENTER]), np.mean([h.landmark[j].y for j in CENTER]))
             for h in res.multi_hand_landmarks]
        d = ((c[0][0] - c[1][0]) ** 2 + (c[0][1] - c[1][1]) ** 2) ** 0.5
        dists.append(d)
        together = d < TH

    now = time.time()
    if together:
        together_frames += 1
        if start is None:
            start = now
    elif start is not None:
        stretches.append(now - start)
        start = None

if start is not None:
    stretches.append(time.time() - start)
cap.release()

print(f"프레임 {frames}개 (약 {frames / MEASURE_SEC:.0f} FPS) / 검출된 손 0개:{cnt[0]} 1개:{cnt[1]} 2개:{cnt[2]}")
if dists:
    print(f"양손 검출 프레임의 중심 거리: 최소 {min(dists):.2f} / 중앙값 {np.median(dists):.2f} / 최대 {max(dists):.2f}  (기준 < {TH})")
print(f"거리 기준을 만족한 프레임: {together_frames}개")
print("끊김 없이 이어진 '양손 모임' 구간(초):", [round(s, 2) for s in stretches] or "없음", " (전환에는 1.0초 이상 필요)")
