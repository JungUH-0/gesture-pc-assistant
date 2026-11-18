# ============================================================
#  개인 AI 비서 - 등록 자세 저장 (app/poses.json)
#
#  사용자가 설정창 포즈 탭에서 촬영해 등록한 자세를 저장한다. 개인 설정이라 git에는 올리지 않는다.
#  - 최대 MAX_POSES개 (기본 제공 ㅡ자 자세가 켜져 있으면 그것도 한 자리를 차지한다)
#  - 포즈만 등록할 수 있다. 명령은 나중에 명령 등록 탭에서 `pose_이름`으로 연결한다
#  - 기본 제공 ㅡ자(화면 캡처)는 삭제할 수 있고, 다시 켜서(복원) 쓸 수도 있다
# ============================================================

import json
import os
import re
import time

import numpy as np

import posematcher

POSES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poses.json")

MAX_POSES = 10
BUILTIN_NAME = "ㅡ자(화면 캡처)"   # 기본 제공 자세의 표시 이름 (사용자 이름으로는 쓸 수 없음)
NAME_PATTERN = re.compile(r"^[0-9A-Za-z가-힣_]{1,20}$")


def _empty():
    return {"poses": {}, "builtin_tpose": True}


def load():
    """{"poses": {이름: {"samples": [...], "created": 시각}}, "builtin_tpose": 켜짐 여부}"""
    data = _empty()
    try:
        with open(POSES_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            if isinstance(saved.get("poses"), dict):
                data["poses"] = {n: p for n, p in saved["poses"].items()
                                 if isinstance(p, dict) and isinstance(p.get("samples"), list)}
            data["builtin_tpose"] = bool(saved.get("builtin_tpose", True))
    except (OSError, ValueError):
        pass
    return data


def save(data):
    try:
        with open(POSES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def count(data):
    """사용 중인 자리 수 (기본 제공 자세가 켜져 있으면 포함)"""
    return len(data["poses"]) + (1 if data["builtin_tpose"] else 0)


def user_pose_names(data=None):
    return list((data or load())["poses"].keys())


def templates(data=None):
    """matcher에 넘길 {이름: 샘플 배열}"""
    return {n: np.asarray(p["samples"], dtype=np.float32) for n, p in (data or load())["poses"].items()}


def validate_name(name, data):
    """이름이 괜찮으면 None, 문제가 있으면 안내 문구를 반환"""
    if not name:
        return "포즈 이름을 입력하세요."
    if name == BUILTIN_NAME:
        return "기본 제공 자세의 이름은 사용할 수 없습니다."
    if not NAME_PATTERN.match(name):
        return "이름은 한글·영문·숫자·밑줄만 20자까지 쓸 수 있습니다 (공백·기호 불가)."
    if name.lower() in (n.lower() for n in data["poses"]):
        return f"'{name}' 이름이 이미 있습니다."
    if count(data) >= MAX_POSES:
        return f"포즈는 최대 {MAX_POSES}개까지 등록할 수 있습니다. 하나를 삭제한 뒤 등록하세요."
    return None


def check_samples(samples, data):
    """촬영한 샘플이 등록할 만한지 검사. 문제가 없으면 None, 있으면 안내 문구."""
    if len(samples) < posematcher.MIN_SAMPLES:
        return (f"자세를 충분히 인식하지 못했습니다 ({len(samples)}프레임). "
                "상체와 양팔이 화면에 다 보이게 하고 다시 촬영하세요.")
    centroid, spread, _thr = posematcher.summarize(samples)
    if spread > posematcher.MAX_SPREAD:
        return "촬영하는 동안 자세가 많이 움직였습니다. 자세를 고정한 채 다시 촬영하세요."
    for other, pose in data["poses"].items():
        other_centroid, _s, _t = posematcher.summarize(pose["samples"])
        if float(np.linalg.norm(centroid - other_centroid)) < posematcher.MIN_SEPARATION:
            return f"'{other}' 자세와 너무 비슷합니다. 구분되도록 팔의 높이나 모양을 더 다르게 취해 보세요."
    return None


def add_pose(name, samples):
    """검사를 마친 자세를 저장. 반환 (성공 여부, 안내 문구)"""
    data = load()
    problem = validate_name(name, data) or check_samples(samples, data)
    if problem:
        return False, problem
    data["poses"][name] = {
        "samples": [[round(float(v), 4) for v in s] for s in samples],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not save(data):
        return False, "자세를 저장하지 못했습니다 (poses.json에 쓸 수 없음)."
    return True, f"'{name}' 자세를 등록했습니다 ({len(samples)}프레임)."


def delete_pose(name):
    """사용자 자세를 삭제. 지웠으면 True"""
    data = load()
    if name not in data["poses"]:
        return False
    del data["poses"][name]
    save(data)
    return True


def set_builtin(enabled):
    """기본 제공 ㅡ자 자세 켜기(복원)/끄기(삭제). 켤 때 자리가 없으면 (False, 문구)"""
    data = load()
    if enabled and not data["builtin_tpose"] and count(data) >= MAX_POSES:
        return False, f"포즈가 이미 {MAX_POSES}개라 복원할 수 없습니다. 하나를 삭제한 뒤 복원하세요."
    data["builtin_tpose"] = bool(enabled)
    save(data)
    return True, ""
