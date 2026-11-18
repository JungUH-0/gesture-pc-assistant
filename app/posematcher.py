# ============================================================
#  개인 AI 비서 - 사용자 등록 자세 비교 (템플릿 매칭)
#
#  등록한 자세마다 22차원 특징 샘플을 모아 "중심(centroid)"과 허용 거리를 만들어 두고,
#  현재 프레임의 특징이 어느 자세와 가까운지를 본다. 학습 단계가 없어서 등록 즉시 사용할 수 있다.
#  특징은 어깨 너비 기준으로 정규화되어 있어(posemodule.extract_pose_features) 카메라와의 거리·
#  화면상 위치에 영향을 받지 않는다.
#
#  카메라 없이 시험할 수 있도록 posemodule과 분리한 순수 계산 모듈이다.
#  ※ 아래 상수는 추정치이며 실측 전이다. 개발 모드에서 미리보기에 표시되는 "가장 가까운 자세와 거리"로 조정한다.
# ============================================================

import threading

import numpy as np

# ── 허용 거리 ───────────────────────────────────────────────
SPREAD_FACTOR = 3.0   # 허용 거리 = 등록 샘플들이 중심에서 평균적으로 흩어진 정도 × 이 값
MIN_THRESHOLD = 0.30  # 허용 거리의 하한 (샘플이 너무 모여 있어도 이보다는 넉넉히)
MAX_THRESHOLD = 0.80  # 허용 거리의 상한 (너무 넓으면 다른 자세까지 잡힘)
EXIT_RATIO    = 1.25  # 한번 맞은 자세는 허용 거리의 이 배수까지 벗어나야 "벗어남"으로 봄 (히스테리시스)

# ── 판정 ────────────────────────────────────────────────────
HOLD_SEC          = 1.0   # 가깝게 유지해야 하는 시간 (스치듯 지나가는 자세 방지)
GRACE_SEC         = 0.3   # 이 시간 안의 순간적 이탈·검출 실패는 유지로 본다 (프레임 단위 떨림 방지)
COOLDOWN_SEC      = 2.0   # 같은 자세를 한 번 인정한 뒤 다시 인정하기까지의 최소 간격
AMBIGUOUS_RATIO   = 1.2   # 두 번째로 가까운 자세 거리가 첫째의 이 배수 미만이면 "모호"해서 인정하지 않음

# ── 등록 검사 ───────────────────────────────────────────────
MIN_SAMPLES        = 20    # 등록에 필요한 최소 샘플 수 (약 2초 촬영 중 검출된 프레임)
MAX_SPREAD         = 0.45  # 샘플이 중심에서 평균 이만큼 넘게 흩어져 있으면 "자세가 흔들렸다"고 거부
MIN_SEPARATION     = 0.60  # 새 자세의 중심이 기존 자세의 중심과 이보다 가까우면 "너무 비슷하다"고 거부


def summarize(samples):
    """샘플 목록 → (중심, 평균 흩어짐, 허용 거리)"""
    arr = np.asarray(samples, dtype=np.float32)
    centroid = arr.mean(axis=0)
    spread = float(np.linalg.norm(arr - centroid, axis=1).mean())
    threshold = float(min(max(spread * SPREAD_FACTOR, MIN_THRESHOLD), MAX_THRESHOLD))
    return centroid, spread, threshold


class PoseMatcher:
    """
    update(now, features)를 매 프레임 호출한다.
    반환: (이벤트 이름 또는 None, 화면 표시용 정보 dict 또는 None)
      - 이벤트: 어떤 자세에 가까운 상태가 HOLD_SEC 동안 이어졌을 때 한 번만 이름을 돌려준다.
      - 정보: {"name", "dist", "thr", "matched"} — 가장 가까운 자세 (개발 모드 표시용)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._templates = {}     # 이름 → (중심, 허용 거리)
        self._reset_state()

    def _reset_state(self):
        self._candidate = None      # 지금 가깝게 유지 중인 자세
        self._since = None          # 그 상태가 시작된 시각
        self._lost_since = None     # 가깝지 않게 된 시각 (GRACE_SEC 안이면 유지로 봄)
        self._fired = False         # 이번 유지 구간에서 이미 이벤트를 냈는지
        self._last_fire = {}        # 자세별 마지막 이벤트 시각 (쿨다운)

    def set_templates(self, samples_by_name):
        """samples_by_name: {이름: 샘플 목록}. 샘플이 없는 이름은 무시한다."""
        templates = {}
        for name, samples in samples_by_name.items():
            if samples is not None and len(samples) > 0:
                centroid, _spread, threshold = summarize(samples)
                templates[name] = (centroid, threshold)
        with self._lock:
            self._templates = templates
            self._reset_state()

    def has_templates(self):
        with self._lock:
            return bool(self._templates)

    def reset(self):
        with self._lock:
            self._reset_state()

    def update(self, now, features):
        with self._lock:
            if features is None or not self._templates:
                self._lose(now)
                return None, None

            feats = np.asarray(features, dtype=np.float32)
            ranked = sorted(
                ((float(np.linalg.norm(feats - c)), name, thr) for name, (c, thr) in self._templates.items()),
                key=lambda t: t[0])
            d1, n1, t1 = ranked[0]

            # 모호함: 두 번째 자세도 허용 거리 안이고 첫째와 거리 차이가 작으면 어느 쪽인지 알 수 없음
            ambiguous = (len(ranked) > 1 and ranked[1][0] < ranked[1][2]
                         and ranked[1][0] < d1 * AMBIGUOUS_RATIO)

            # 히스테리시스: 이미 유지 중인 자세는 더 넉넉한 거리까지 허용
            limit = t1 * EXIT_RATIO if self._candidate == n1 else t1
            matched = d1 < limit and not ambiguous
            info = {"name": n1, "dist": d1, "thr": t1, "matched": matched}

            if not matched:
                self._lose(now)
                return None, info

            self._lost_since = None
            if self._candidate != n1:
                self._candidate, self._since, self._fired = n1, now, False

            if (not self._fired and now - self._since >= HOLD_SEC
                    and now - self._last_fire.get(n1, -1e9) >= COOLDOWN_SEC):
                self._fired = True
                self._last_fire[n1] = now
                return n1, info
            return None, info

    def _lose(self, now):
        """가깝지 않은 프레임. GRACE_SEC를 넘겨야 유지가 끊긴 것으로 본다."""
        if self._candidate is None:
            return
        if self._lost_since is None:
            self._lost_since = now
        elif now - self._lost_since > GRACE_SEC:
            self._candidate, self._since, self._fired, self._lost_since = None, None, False, None
