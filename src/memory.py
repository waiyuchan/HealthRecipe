"""Only explicit food preferences become hard constraints; feelings are not diagnoses."""

import re


def explicit_exclusions(memories):
    result = []
    for memory in memories:
        # A user can state an allergy and then ask a question in the next clause.
        # Questions/hypotheticals invalidate that clause, not the whole message.
        for part in re.finditer(r"([^，。；,;！？!?]+)([，。；,;！？!?]|$)", memory["content"]):
            text, punctuation = part.groups()
            if punctuation in {"？", "?"} or any(
                word in text
                for word in ["不过敏", "没有过敏", "不是过敏", "如果", "假如", "是否", "会不会", "吗"]
            ):
                continue
            for pattern in [r"对([^，。；,;]{1,35}?)过敏", r"(?:不吃|不能吃|不要吃)([^，。；,;]{1,35})"]:
                for match in re.finditer(pattern, text):
                    names = re.split(r"[、和与及/]", match[1])
                    result.extend(
                        n.strip("了的呀啊哦吧呢啦 ")
                        for n in names
                        if 0 < len(n.strip("了的呀啊哦吧呢啦 ")) <= 20
                    )
    return list(dict.fromkeys(result))


def extract_local_memories(message):
    """Conservative local fallback; keep verbatim assertions, never diagnoses inferred by code."""
    result = []
    for part in re.finditer(r"([^，。；,;！？!?]+)([，。；,;！？!?]|$)", message):
        text, punctuation = part.groups()
        evidence = text.strip()
        if punctuation in {"？", "?"} or any(
            word in text
            for word in [
                "如果",
                "假如",
                "会不会",
                "是否",
                "吗",
                "朋友",
                "妈妈",
                "爸爸",
                "我妈",
                "我爸",
                "他",
                "她",
            ]
        ):
            continue
        if not any(word in text for word in ["我", "最近", "这几天"]):
            continue
        kind, days = None, None
        if explicit_exclusions([{"content": evidence}]) or any(
            w in text for w in ["喜欢", "想吃", "不想吃", "讨厌"]
        ):
            kind = "饮食偏好"
        elif any(
            w in text
            for w in [
                "胃不舒服",
                "胃痛",
                "胃疼",
                "没胃口",
                "腹胀",
                "睡不好",
                "疲惫",
                "便秘",
                "腹泻",
                "不舒服",
                "难受",
            ]
        ):
            if re.search(r"(没有|不再|没有再)(胃痛|胃疼|腹胀|便秘|腹泻)", text):
                continue
            kind, days = "身体感受", 14
        elif any(w in text for w in ["熬夜", "睡得晚", "夜班"]):
            kind, days = "生活习惯", 30
        elif any(w in text for w in ["饮食均衡", "控制体重", "多吃蔬菜", "少油少盐"]):
            kind, days = "饮食目标", 30
        if kind and len(evidence) <= 500:
            result.append({"kind": kind, "evidence": evidence, "days": days})
    return result[:5]
