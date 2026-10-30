"""Stage map S1–S8 and the engagement profile E1–E8 (who asks for what, for whom).

An overlay on the planner's P0–P7: it never moves the flow. At the end of every analysed round `check` works out,
from the database alone, which completion conditions of each stage still have gaps, reopens an earlier stage when a
later one exposes its gap, turns gaps and vague answers into question cards that compete with the analysts' cards
(the shown-card limit is not raised), and in collaboration mode asks at most one "go back?" D2 per round.

Everything here is about relations and process, never an industry: placeholders stand for the persona's own words.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fde_mode import db, decisions as D, lexicon
from fde_mode.state import Ctx
from fde_mode.util import iso, short, write_json

STAGES = [("S1", "상황 파악"), ("S2", "문제 정의"), ("S3", "요구 수집"), ("S4", "확인"), ("S5", "범위 확정"),
          ("S6", "설계"), ("S7", "구현·검수"), ("S8", "전달·운영")]
NAMES = dict(STAGES)
ORDER = [s for s, _ in STAGES]

ENGAGEMENT = {
    "E1": "본인이 직접 쓸 도구(개인 비서·개인 업무 도구)",
    "E2": "본인이 운영하고 다른 사람이 쓰는 서비스",
    "E3": "외주 의뢰(의뢰인의 고객 또는 그 고객의 고객이 씀)",
    "E4": "조직 내부 도구(팀·부서·회사 안)",
    "E5": "조직 이름으로 내는 대외 서비스",
    "E6": "공동체·비영리·모임",
    "E7": "중개·다자(목적이 다른 여러 집단이 함께 씀)",
    "E8": "기타·불명",
}
# Relation signals (who asks, who uses, who runs) in the persona's own words — never an industry noun. Kept narrow:
# a wrong type is worse than an unknown one (an unknown type asks "who uses, runs, decides" first).
SIGNALS = {
    "E1": ("제가 쓸", "제가 직접 쓸", "저 혼자 쓸", "혼자 쓸", "나만 쓸", "저만 쓸", "개인 비서", "제 일정", "저 대신", "나 대신",
           "개인적으로 쓸", "개인용"),
    "E2": ("문의가 와", "문의가 많", "찾아오는 분", "이용하시는 분", "저희를 찾", "제가 운영", "저희가 운영"),
    "E3": ("고객사", "납품", "외주", "의뢰받", "클라이언트", "대행사", "고객의 고객", "맡긴 일", "만들어서 넘"),
    "E4": ("사내", "팀원", "직원들이 쓸", "부서에서", "부서원", "부서별", "다른 부서", "저희 부서", "우리 부서",
           "회사 안", "내부용", "저희 팀 ", "저희 팀이", "저희 팀에서", "저희 팀은", "저희 팀원", "동료들이 쓸", "부서 안"),
    "E5": ("공식 채널", "공식 답변", "공식 입장", "대외", "기관 공식", "공공기관", "저희 기관", "우리 기관", "기관에서",
           "약관", "민원", "회사 이름으로", "대표로 요청"),
    "E6": ("봉사로", "봉사를", "봉사해", "봉사 모임", "봉사 단체", "봉사하는", "저희 모임", "모임이에요", "동호회", "비영리", "후원", "자원봉사", "회비"),
    "E7": ("중개", "서로 연결해", "양쪽을", "양쪽 다 쓰", "공급하는 쪽", "찾는 쪽", "매칭", "여러 집단"),
}
# The users named as customers: E2 (one's own service) — unless it is someone else's service (E3 outsourced, E5 an
# organisation's), where the client's customers are expected and say nothing new about the type
CUSTOMER_WORDS = ("손님들이", "고객님들이", "고객들이", "회원들이", "이용자들이")
# What makes it someone else's (an organisation's) service — not "약관"·"민원", which one's own customers raise too
ORG_E5 = ("공식 채널", "공식 답변", "공식 입장", "대외", "기관 공식", "공공기관", "저희 기관", "우리 기관", "기관에서",
          "회사 이름으로", "대표로 요청")
CONF_RANK = {"확실": 0, "가능성 높음": 1, "추측": 2, "모름": 3}


def _hit(text: str, sig: str) -> bool:
    """`sig` said, and not denied right after it ("제가 쓸 게 아니라…")."""
    i = text.find(sig)
    while i >= 0:
        after = re.split(r"[.?!\n]", text[i + len(sig): i + len(sig) + 8])[0]  # the denial must be in the same sentence
        if "아니" not in after:
            return True
        i = text.find(sig, i + 1)
    return False

ROLES = [("requester", "의뢰인(요청자)"), ("decider", "결정권자"), ("payer", "비용 부담자"),
         ("end_users", "최종 사용자"), ("operator", "운영·관리자(매일 손대는 사람)"), ("data_owner", "데이터 주인·공급자"),
         ("incident", "장애·민원 책임자"), ("third_party", "영향받는 제3자"), ("channel", "전달 채널의 주인"),
         ("handover", "인수인계 받을 사람")]
ROLE_NAMES = dict(ROLES)
ROLE_SHORT = {"requester": "의뢰인", "decider": "결정권자", "payer": "비용 부담", "end_users": "최종 사용자",
              "operator": "운영·관리", "data_owner": "데이터 주인", "incident": "장애·민원 책임", "third_party": "영향받는 제3자",
              "channel": "채널 주인", "handover": "인수인계"}
# Answer forms in the persona's own lines (questions are the interviewer's, the brief is not the persona)
ROLE_SIGNALS = {
    "requester": ("의뢰한 곳", "의뢰한 분", "의뢰인은", "요청한 곳", "요청한 분", "맡긴 곳"),
    "decider": ("결정은", "정하는 건", "허락", "승인", "윗분", "결재", "최종 결정", "내가 정해", "제가 정해", "내가 정하",
                "제가 정하", "가 정해요", "이 정해요", "가 정하", "이 정하", "결정해"),
    "payer": ("비용은", "예산", "돈은", "비용 부담"),
    "end_users": ("사용자는", "이용자는", "쓰게 될", "주로 쓰", "들이 쓰", "들이 써", "들이 쓸", "분이 쓰", "분이 써", "이 쓰게",
                  "가 쓰게", "이 써요", "가 써요", "다 써", "쓰게 돼", "이용하시는 분", "찾아오는 분", "물어보시는 분",
                  "저만 쓸", "제가 쓸", "혼자 쓸"),
    "operator": ("관리는", "매일 보", "운영은", "업데이트", "이 보고", "가 보고", "이 봐요", "가 봐요", "가 관리", "이 관리",
                 "제가 관리", "제가 봐", "내가 봐"),
    "data_owner": ("자료는", "파일은", "명단은", "엑셀은", "기록은", "자료를 주", "데이터는"),
    "incident": ("문제 생기면", "장애", "민원", "책임은", "고장 나면"),
    "third_party": ("영향", "모르는 사람", "다른 분들도"),
    "channel": ("카톡 채널", "카카오톡 채널", "채널은", "계정은", "누구 이름으로", "카카오톡으로 나가", "카톡으로 나가"),
    "handover": ("인수인계", "넘겨받", "유지보수", "이후 관리"),
}
# The interviewer asking about a role (question forms), answered by the persona's next line: that role was asked
ROLE_ASK = {
    "requester": ("누가 맡기", "의뢰하신", "누구 요청", "맡기시는"),
    "decider": ("누가 정하", "결정은", "결정하시", "승인은"),
    "payer": ("비용은", "누가 내", "예산은"),
    "end_users": ("누가 쓰", "쓰실 분", "사용하실 분", "이용하실 분"),
    "operator": ("운영은", "누가 운영", "관리는", "누가 관리", "맡아서 관리", "매일 보", "매일 들여다보", "직접 관리하시",
                 "꾸준히 챙길"),
    "data_owner": ("자료는", "데이터는", "누가 가지고"),
    "incident": ("문제가 생기면", "틀리면 누가", "연락을 받"),
    "third_party": ("영향을 받", "곤란해질"),
    "channel": ("채널은", "누구 이름으로", "어느 계정", "채널·계정"),
    "handover": ("이어받", "인수인계", "다 만든 뒤", "그 뒤 운영"),
}
# A role question asks who ("그 뒤에는요?", "어떻게 관리하세요?" ask about the process, not a person) — unless it names
# the role itself
ASK_WHO = ("누가", "누구", "어느 분", "어떤 분", "어느 쪽")
ASK_SPECIFIC = ("인수인계", "이어받", "결정권", "승인은", "대신 맡기", "다른 곳에 맡기", "직접 운영하", "몇 분")
UNDECIDED = ("아직", "정해지지 않", "안 정해", "모르겠", "미정", "생각 안 해", "생각해 본 적")
SELF_WORDS = ("제가", "저희", "저 혼자", "내가", "본인", "직접")
# A type's first question that is answered once its role was asked in other words
OPENER_ROLES = {"E3": ("handover", "operator"), "E6": ("operator",)}
# Adverbs ending in 이 that would read as "〈누구〉이 써요" ("돈이 많이 써요")
ADVERBS = ("많이 ", "같이 ", "깊이 ", "높이 ", "길이 ")
# Roles a type cannot do without, in the order they matter for that type (asked before the common three)
TYPE_ROLES = {"E1": (), "E2": ("end_users", "operator"), "E3": ("handover", "data_owner", "channel"),
              "E4": ("decider", "data_owner"), "E5": ("channel", "incident", "decider"), "E6": ("operator", "payer"),
              "E7": ("end_users",), "E8": ()}
BASE_ROLES = ("end_users", "operator", "decider")
ROLE_WHY = {
    "requester": "누가 맡기는지에 따라 범위와 승인 경로가 정해진다",
    "decider": "누가 승인해야 범위가 확정되는지 정해진다",
    "payer": "비용을 누가 내는지에 따라 무엇을 아끼고 무엇에 쓸지가 정해진다",
    "end_users": "누구에게 맞춘 말투·길이·내용인지가 정해진다",
    "operator": "아무도 고치지 않으면 봇 답이 낡는다",
    "data_owner": "자료 주인이 없으면 봇이 지어내거나 낡은 답을 한다",
    "incident": "잘못된 답이 나갔을 때 받을 사람이 없으면 문제가 커진다",
    "third_party": "말하지 않은 사람이 곤란해질 수 있다",
    "channel": "누구 이름으로 나가는지에 따라 말투·책임이 달라진다",
    "handover": "넘겨받는 사람이 없으면 다 만든 뒤 멈춘다",
}
# What each type must learn (relation questions, placeholders only) — for the seats, the report and the role panel
MUST_KNOW = {
    "E1": ["하루·일주일 흐름에서 언제 쓰는지", "민감한 개인 정보가 있는지", "알림을 어떻게 받고 싶은지", "실수했을 때 되돌리는 방법"],
    "E2": ["〈인물의 상대〉가 지금 어떻게 묻고 기다리는지", "운영자가 놓치는 순간", "운영자의 하루 부담", "〈인물의 상대〉마다 다른 점"],
    "E3": ["의뢰인의 고객이 누구이고 의뢰인이 얻는 것", "고객이 한 곳인지 여러 곳인지",
           "최종 사용자와 의뢰인 요구가 다를 때 누구를 우선하는지", "인수인계 형태와 이후 운영 주체",
           "말투·이름 규칙, 데이터 소유권, 범위 밖 요청 처리"],
    "E4": ["승인·권한", "내부 시스템·자료 위치", "보안 규정", "바뀌기 싫어하는 사람", "성공을 누가 판단하는지"],
    "E5": ["대외 정책·약관·책임", "공식 답과 하면 안 되는 답", "민원 경로", "요청자와 결정권자의 차이"],
    "E6": ["운영할 사람과 시간", "예산", "다양한 숙련도", "교대로 돕는 사람"],
    "E7": ["집단마다 목적·권한·보이는 정보", "충돌이 날 때의 규칙"],
    "E8": ["누가 쓰는지, 누가 관리하는지, 누가 정하는지부터", "다른 분을 대신해 요청하는 것인지, 보여 주기용 시제품인지"],
}
# The first question that only this engagement type needs (asked once, right after the type is known)
TYPE_OPENERS = {
    "E1": "하루 중 언제 이걸 가장 많이 쓰시게 될 것 같으세요?",
    "E2": "지금은 물어보시는 분들이 답을 받기까지 얼마나 기다리세요?",
    "E3": "완성되면 이 봇은 고객 쪽에서 직접 운영하나요, 아니면 계속 맡아서 관리하시나요, 아니면 아직 안 정해졌나요?",
    "E4": "같이 쓰실 분들 중에 봐서는 안 되는 자료가 있는 분도 있나요?",
    "E5": "봇이 절대 하면 안 되는 답이나, 정해진 문구 그대로 해야 하는 답이 있나요?",
    "E6": "완성되면 이걸 꾸준히 챙길 수 있는 분이 몇 분이나 되나요?",
    "E7": "양쪽이 원하는 게 서로 부딪히면, 지금은 누가 어떻게 정하나요?",
}
TYPE_OPENER_WHY = {
    "E1": "언제 쓰는지에 따라 알림 시점과 답 길이가 정해진다",
    "E2": "지금 얼마나 기다리는지가 봇이 줄여 줄 몫이다",
    "E3": "넘긴 뒤 누가 운영하는지에 따라 인수인계와 관리 기능이 정해진다",
    "E4": "볼 수 없는 자료가 있으면 사람마다 답을 달리해야 한다",
    "E5": "하면 안 되는 답과 정해진 문구가 봇의 규칙이 된다",
    "E6": "챙길 사람이 적으면 손이 덜 드는 방식이어야 한다",
    "E7": "양쪽이 부딪힐 때의 규칙이 없으면 봇이 한쪽 편을 든다",
}
# [0] the type question; [1] the same when the persona already said who uses it (then it asks who runs it)
TYPE_QUESTIONS = ["완성되면 이걸 실제로 쓰실 분은 누구인가요? 직접 쓰시나요, 다른 분들이 쓰시나요, 아니면 둘 다인가요?",
                  "완성되면 이건 직접 관리하시나요, 아니면 다른 분이나 다른 곳에 맡기시나요, 아니면 아직 안 정해졌나요?"]
ROLE_QUESTIONS = {
    "requester": "이 일은 직접 정해서 맡기시는 건가요, 아니면 다른 분이 정한 걸 대신 맡기시는 건가요?",
    "decider": "결정은 어느 분이 하시나요?",
    "payer": "비용은 어느 쪽에서 부담하나요?",
    "end_users": "실제로 쓰실 분들은 누구인가요?",
    "operator": "완성되면 누가 매일 들여다보고 관리하나요?",
    "data_owner": "봇이 답할 때 필요한 자료는 지금 누가 가지고 있나요?",
    "incident": "봇이 틀린 답을 하거나 멈추면, 누가 연락을 받고 처리하게 되나요?",
    "channel": "누구의 채널·계정 이름으로 나가나요?",
    "handover": "다 만든 뒤에 이걸 이어받아 운영할 분이 따로 있나요?",
}
# Vague answers, by what they leave open
VAGUE_FREQ = ("가끔", "때에 따라", "그때그때", "종종", "들쭉날쭉")  # not "보통" alone ("보통 이렇게 해요" is an answer)
VAGUE_DELEGATE = ("다 알아서", "알아서 해", "알아서 잘", "알아서들", "알아서 하시", "알아서 만들", "알아서 정해 주", "적당히", "대충",
                  "웬만하면", "어지간하면")
FOLLOW_UPS = {"freq": "대략 얼마나 자주인가요? 하루나 일주일에 몇 번 정도로요.",
              "delegate": "어떻게 해 주면 '잘했다' 싶으실지 한 가지만 예를 들어 주실 수 있을까요?"}
FOLLOW_LIMIT = 2          # same topic: two follow-ups actually asked, then an assumption to confirm
NEW_CARDS_PER_ROUND = 2   # stage cards made in one round (they still compete for the shown places)
NONFUNC = {"개인정보": ("개인정보", "전화번호", "연락처", "보관", "지워 주", "저장하지"),
           "속도": ("빨리 답", "바로 답", "기다리", "응답 속도", "늦게 오"),
           "운영 부담": ("업데이트", "손이 많이", "고칠 사람", "관리할 사람", "자주 바뀌")}
DONE, PARTIAL, OPEN, REOPENED = "done", "partial", "open", "reopened"
MARK = {DONE: "✓", PARTIAL: "◐", OPEN: "○", REOPENED: "↺"}
PHASE_STAGE = {"P0": "S1", "P1": "S1", "P2": "S4", "P3": "S5", "P4": "S6", "P5": "S7", "P6": "S8", "P7": "S8"}


# ---------- engagement ----------

def _lines(ctx: Ctx, speakers: tuple = ("P", "B"), after: str = "") -> list[dict]:
    q = ",".join("?" * len(speakers))
    # >= : lines stored in the same second as the seat's judgement are still checked for a type it did not name
    return db.rows(ctx.conn, f"SELECT id, round, speaker, text, tags, area, created_at FROM utterances WHERE speaker IN ({q}) "
                             "AND COALESCE(created_at,'') >= ? ORDER BY seq", (*speakers, after))


def _signal_types(utts: list[dict], known: set | frozenset = frozenset()) -> list[dict]:
    found: dict[str, list[str]] = {}
    for u in utts:
        for code, sigs in SIGNALS.items():
            if any(_hit(u["text"], sg) for sg in sigs):
                found.setdefault(code, []).append(u["id"])
    someone_else = "E3" in found or {"E3", "E5"} & set(known) or any(_hit(u["text"], s) for u in utts for s in ORG_E5)
    if not someone_else:  # G1: customers of someone else's service (outsourced, an organisation's) are not an E2 signal
        for u in utts:
            if any(_hit(u["text"], w) for w in CUSTOMER_WORDS) and u["id"] not in found.get("E2", []):
                found.setdefault("E2", []).append(u["id"])
    types = []
    order = {u["id"]: i for i, u in enumerate(utts)}  # a tie goes to the type said most recently (a shift)
    for code, ids in sorted(found.items(), key=lambda kv: (-len(kv[1]), -max(order[x] for x in kv[1]))):
        conf = "확실" if len(ids) >= 3 else "가능성 높음" if len(ids) == 2 else "추측"
        types.append({"code": code, "label": ENGAGEMENT[code], "confidence": conf, "evidence": ids[:6]})
    if len(types) > 1:  # mixed signals: the leading type is a guess until someone confirms it (the type card asks)
        types[0]["confidence"] = "추측"
    return types


def _signal_roles(persona: list[dict]) -> dict[str, dict]:
    roles: dict[str, dict] = {}
    for key, _ in ROLES:
        ev = [u for u in persona if any(_hit(re.sub("|".join(ADVERBS), " ", u["text"]), sg) for sg in ROLE_SIGNALS.get(key, ()))]
        # a signal gives the sentence, not a name: shown as a quote until a seat names the person
        roles[key] = {"who": "“" + short(ev[0]["text"], 30) + "”" if ev else "모름", "evidence": [u["id"] for u in ev[:4]],
                      **({"confidence": "추측"} if ev else {})}
    return roles


def _asked_roles(utts: list[dict]) -> dict[str, dict]:
    """Roles the interviewer asked about and the persona answered on the next line: 미정 when the answer is undecided,
    else the answer as a quote (추측). Asked is asked — not to be asked again, whatever a seat or a signal says."""
    out: dict[str, dict] = {}
    for q, a in zip(utts, utts[1:]):
        if q["speaker"] != "I" or a["speaker"] != "P":
            continue
        for key, forms in ROLE_ASK.items():
            if key not in out and any(any(f in sent for f in forms) and any(w in sent for w in ASK_WHO + ASK_SPECIFIC)
                                      for sent in re.split(r"[?.!]", q["text"])):  # the role and "who" in one sentence
                named = bool(lexicon.people(a["text"])) or any(w in a["text"] for w in SELF_WORDS)
                undecided = any(w in a["text"] for w in UNDECIDED) and not named  # "아직은 제가 해요" is an answer
                # an answer on the topic names someone (a person, oneself, a role phrase) or says it is undecided;
                # anything else ("알아서 해 주세요") left the role open — it may be asked again
                if not (undecided or named or any(_hit(a["text"], sg) for sg in ROLE_SIGNALS.get(key, ()))):
                    continue
                out[key] = {"who": "미정(물었음)" if undecided else "“" + short(a["text"], 30) + "”",
                            "evidence": [q["id"], a["id"]], "confidence": "추측", "asked": True}
    return out


def detect(ctx: Ctx) -> dict[str, Any]:
    """Engagement types and role map. Types come from the persona's lines and the brief; roles only from the persona's
    own lines (a question or the brief is not an answer) and the interviewer's question → persona answer pairs. The
    stakeholder mapper's judgement (`extra.engagement`, stored by sync) wins for what it names, except that its '모름'
    never erases a role the persona's own line gave (shown as 추측 with its U ids); signals after its judgement still
    add a type it did not name (marked `new`). Every value carries its U ids."""
    stored = db.one(ctx.conn, "SELECT * FROM engagement WHERE id=1")
    persona = _lines(ctx, ("P",))
    roles = _signal_roles(persona)
    if stored and stored.get("source") == "seat":
        types = json.loads(stored["types"] or "[]")
        have = {t["code"] for t in types}
        for t in _signal_types(_lines(ctx, ("P", "B"), stored.get("updated_at") or ""), have):
            if t["code"] not in have and t["code"] != "E8":  # the type shifted after the seat judged: ask
                types.append({**t, "confidence": "추측", "new": True})
        for k, v in (json.loads(stored["roles"] or "{}") or {}).items():  # what the seat named wins — but its 모름
            if v.get("who") not in (None, "", "모름") or not roles.get(k, {}).get("evidence"):  # never erases a role
                roles[k] = {**v, "by": "seat"}                                # the persona's own line gave (17:4x)
        source = "seat"
    else:
        types = _signal_types(_lines(ctx, ("P", "B"))) or [{"code": "E8", "label": ENGAGEMENT["E8"], "confidence": "모름",
                                                            "evidence": []}]
        if [t["code"] for t in types] == ["E1"]:  # only one's own tool: requester = user = operator = decider
            for key in ("requester", "end_users", "operator", "decider"):
                if not roles[key]["evidence"] or key == "end_users":
                    roles[key] = {"who": "인물 본인", "evidence": roles[key]["evidence"] or types[0]["evidence"][:2]}
        source = "signals"
    for k, v in _asked_roles(_lines(ctx, ("I", "P"))).items():  # (가)(나)(다): asked in the interview → never 모름
        if roles.get(k, {}).get("who") in (None, "", "모름") or not roles.get(k, {}).get("evidence"):
            roles[k] = v
    best = types[0]["confidence"] if types else "모름"  # the leading type's (a mixed lead is 추측: the type card asks)
    if any(t.get("new") for t in types):
        best = "추측"
    return {"types": types, "roles": roles, "confidence": best, "source": source}


def needed_roles(codes: list[str]) -> list[str]:
    """The roles this engagement cannot do without: the leading type's own first, then the common three, then the rest."""
    lead = list(TYPE_ROLES.get(codes[0], ())) if codes else []
    return list(dict.fromkeys(lead + list(BASE_ROLES) + [r for c in codes[1:] for r in TYPE_ROLES.get(c, ())]))


# ---------- stages ----------

def _gap(stage: str, key: str, text: str, why: str, question: str = "", role: str = "") -> dict:
    return {"stage": stage, "key": key, "text": text, "why": why, "question": question, "role": role}


def compute(ctx: Ctx) -> dict[str, Any]:
    """Every stage's gaps from the database (read-only)."""
    eng = detect(ctx)
    st = ctx.refresh()
    flags = st.get("flags") or {}
    utts = _lines(ctx, ("P", "B"))
    areas: dict[str, list[str]] = {}
    for u in utts:
        if u["speaker"] == "P" and u.get("area"):
            areas.setdefault(u["area"], []).append(u["id"])
    reqs = db.rows(ctx.conn, "SELECT id, type, statement, status, evidence, conflict FROM requirements")
    words = " ".join([u["text"] for u in utts] + [r["statement"] or "" for r in reqs])
    gaps: dict[str, list[dict]] = {s: [] for s in ORDER}
    # S1 situation
    codes = [t["code"] for t in eng["types"]]
    uncertain = CONF_RANK.get(eng["confidence"], 3) > CONF_RANK["가능성 높음"]
    if uncertain:  # asked as a card only when nobody has talked about people yet — then it cannot be a re-ask (§2.4)
        talked = any(lexicon.people(u["text"]) or any(w in u["text"] for w in SELF_WORDS) for u in utts if u["speaker"] == "P") \
            or any(any(w in u["text"] for w in ASK_WHO) for u in _lines(ctx, ("I",)))
        gaps["S1"].append(_gap("S1", "type", "의뢰 유형이 아직 불확실함(" + ", ".join(codes) + ")",
                               "누가 쓰고 누가 관리하고 누가 정하는지에 따라 질문·요구·완료 조건이 달라진다",
                               "" if talked else TYPE_QUESTIONS[0]))
    elif codes[0] in TYPE_OPENERS and not any(eng["roles"].get(r, {}).get("asked") for r in OPENER_ROLES.get(codes[0], ())) \
            and not db.scalar(  # the first question only this engagement type needs, until asked (or its role was)
            ctx.conn, "SELECT COUNT(*) FROM questions WHERE lens LIKE ? AND lens NOT LIKE ? AND status IN "
                      "('asked','answered','assumed','dropped')", (f'%"gap": "open:{codes[0]}"%', '%"stale": true%'), 0):
        gaps["S1"].append(_gap("S1", f"open:{codes[0]}", f"{codes[0]} {ENGAGEMENT[codes[0]]}에 꼭 필요한 첫 질문을 아직 하지 않음",
                               TYPE_OPENER_WHY[codes[0]], TYPE_OPENERS[codes[0]]))
    # a guessed type's own roles wait for the type; a seat-judged type keeps its roles while a new signal is checked
    for role in (BASE_ROLES if uncertain and eng["source"] != "seat" else needed_roles(codes)):
        if not eng["roles"].get(role, {}).get("evidence") and eng["roles"].get(role, {}).get("who") in (None, "모름"):
            gaps["S1"].append(_gap("S1", f"role:{role}", f"역할 지도의 '{ROLE_NAMES[role]}' 칸이 비어 있음",
                                   ROLE_WHY[role], ROLE_QUESTIONS.get(role, ""), role))
    if not areas.get("현재방식"):
        gaps["S1"].append(_gap("S1", "current", "지금 방식이 한 번도 재구성되지 않음",
                               "지금 어떻게 하는지 모르면 무엇을 덜어 줄지 정할 수 없다", "지금 그 일은 어떤 순서로 하세요?"))
    # S2 problem
    if len(areas.get("문제", [])) < 2:
        gaps["S2"].append(_gap("S2", "problem", "근본 문제의 근거가 2개 미만", "한 번 들은 불편은 진짜 문제인지 알 수 없다",
                               "최근에 이 일 때문에 곤란했던 적이 있으면, 하나만 말씀해 주실 수 있나요?"))
    if not areas.get("성공기준"):
        gaps["S2"].append(_gap("S2", "success", "인물 말로 된 성공 기준이 없음", "무엇이 되면 성공인지 모르면 완료를 판정할 수 없다",
                               "이게 잘 되면 무엇이 달라져 있을까요?"))
    # S3 requirements
    noev = [r["id"] for r in reqs if not json.loads(r["evidence"] or "[]") and r["status"] != "가정"]
    if noev:
        gaps["S3"].append(_gap("S3", "req-evidence", f"근거 발화가 없는 요구 {len(noev)}개({', '.join(noev[:4])})",
                               "근거 없는 요구는 인물의 말이 아니라 짐작이다"))
    if len(areas.get("예외", [])) < 2:
        gaps["S3"].append(_gap("S3", "exceptions", "예외 상황이 2개 미만", "잘 될 때만 맞는 봇은 첫 예외에서 멈춘다",
                               "평소와 다르게 꼬였던 적이 있으면 하나만 말씀해 주세요."))
    if not areas.get("데이터") and not db.scalar(ctx.conn, "SELECT COUNT(*) FROM data_assets", default=0):
        gaps["S3"].append(_gap("S3", "data", "자료의 출처·형식·주인이 확인되지 않음", "봇이 답할 사실이 어디서 오는지 모르면 지어낸다",
                               "봇이 답하려면 알아야 할 내용은 지금 어디에 적혀 있나요?"))
    for name, keys in NONFUNC.items():
        if not any(k in words for k in keys):
            gaps["S3"].append(_gap("S3", f"nf:{name}", f"비기능 '{name}'을 확인하지 않음", "개인정보·속도·운영 부담은 나중에 바꾸기 어렵다",
                                   {"개인정보": "봇이 기억하면 안 되는 정보가 있나요?", "속도": "답이 얼마 안에 오면 괜찮으세요?",
                                    "운영 부담": "봇에 넣을 내용은 얼마나 자주 바뀌나요?"}[name]))
    # S4 confirmation
    if not db.scalar(ctx.conn, "SELECT COUNT(*) FROM dispatches WHERE agent='fde-readback-writer' AND status='done'", default=0):
        gaps["S4"].append(_gap("S4", "readback", "확인 요약(readback)이 아직 없음", "들은 대로 정리했는지 확인 없이 만들면 어긋난다"))
    conflicts = [r["id"] for r in reqs if json.loads(r["conflict"] or "[]") and r["status"] not in ("폐기", "해결")]
    if conflicts:
        gaps["S4"].append(_gap("S4", "conflict", f"열린 모순 {len(conflicts)}개({', '.join(conflicts[:4])})",
                               "모순을 둔 채 동결하면 어느 쪽으로 만들지 짐작하게 된다"))
    # S5 scope
    if not flags.get("core_frozen"):
        gaps["S5"].append(_gap("S5", "freeze", "핵심 동결 전", "'제작 시작해도 될까요?'에 사용자가 답해야 한다"))
    # S6–S8 (machine part; judgement is the seats')
    tasks = db.rows(ctx.conn, "SELECT id, requirements FROM tasks")
    if flags.get("core_frozen") and not tasks:
        gaps["S6"].append(_gap("S6", "slices", "설계된 조각이 없음", "동결 뒤에는 조각 설계가 있어야 한다"))
    loose = [t["id"] for t in tasks if not json.loads(t["requirements"] or "[]")]
    if loose:
        gaps["S6"].append(_gap("S6", "task-req", f"근거 요구 없는 작업 {len(loose)}개", "요구와 이어지지 않은 작업은 범위 밖일 수 있다"))
    if tasks and not db.scalar(ctx.conn, "SELECT COUNT(*) FROM releases WHERE good=1", default=0):
        gaps["S7"].append(_gap("S7", "accepted", "인수 시나리오를 통과한 배포가 없음", "통과하지 않은 조각은 전달할 수 없다"))
    if not (ctx.p.docs / "operations.md").exists() and not (ctx.p.docs / "handover.md").exists():
        gaps["S8"].append(_gap("S8", "ops", "운영 안내(할 일·문의 경로·장애 대응)가 없음", "넘겨받는 사람이 무엇을 해야 하는지 알아야 한다"))
    if any(c in ("E3", "E5") for c in codes) and not (ctx.p.docs / "handover.md").exists():
        gaps["S8"].append(_gap("S8", "handover", "인수인계 문서가 없음(외주·대외 서비스는 필수)", "다른 사람이 운영을 이어받는다"))
    current = _current(st.get("phase", "P0"), gaps)
    return {"engagement": eng, "gaps": gaps, "current": current, "must_know": {c: MUST_KNOW[c] for c in codes},
            "vague": vague_lines(ctx)}


def _current(phase: str, gaps: dict) -> str:
    base = PHASE_STAGE.get(phase, "S1")
    if base == "S1":  # interviewing: the first of S1–S4 that still has gaps
        return next((s for s in ORDER[:4] if gaps[s]), "S4")
    return base


def vague_lines(ctx: Ctx) -> list[dict]:
    """Persona answers that stay vague — a frequency word or a "leave it to you" word, no number, no example."""
    out = []
    for u in db.rows(ctx.conn, "SELECT id, round, text, tags, area FROM utterances WHERE speaker='P' ORDER BY seq"):
        tags = set(json.loads(u["tags"] or "[]"))
        if re.search(r"\d", u["text"]) or tags & {"숫자·시간 포함", "예시 제공"}:
            continue
        kind = "freq" if any(w in u["text"] for w in VAGUE_FREQ) else "delegate" if any(w in u["text"] for w in VAGUE_DELEGATE) else ""
        if kind:
            out.append({"id": u["id"], "round": u["round"], "area": u.get("area") or "일반", "kind": kind,
                        "text": short(u["text"], 60)})
    return out


# ---------- the round-end check ----------

# Gaps judged from word lists (a role, a non-functional need, the current way): the persona may have said it in other
# words, so the card tells the interviewer to close it instead of asking again (G6)
WORDLIST_GAPS = ("role", "nf", "current")


def _rnum(rnd: str) -> int:
    m = re.search(r"\d+", rnd or "")
    return int(m.group()) if m else 0


def _panel_only(g: dict) -> bool:
    """Role and type gaps are judged from words, which do not carry over to natural speech well enough to ask again
    (19:0x real session): the stage band and the role panel show them as 확인 필요; no card, no top-3, no D2."""
    return g["key"].startswith("role:") or (g["key"] == "type" and not g.get("question"))


def _stored(ctx: Ctx) -> dict[str, dict]:
    return {r["id"]: r for r in db.rows(ctx.conn, "SELECT * FROM stages")}


def _card_rounds(ctx: Ctx) -> dict[str, str]:
    """Stage cards by gap key (all statuses) → the latest round one was made in. A card closed because its gap went
    away (`stale`) does not count: if the gap comes back, it is asked again."""
    keys: dict[str, str] = {}
    for q in db.rows(ctx.conn, "SELECT round, lens FROM questions WHERE lens LIKE '%\"stage\"%'"):
        lens = json.loads(q["lens"] or "{}") or {}
        if lens.get("gap") and not lens.get("stale"):
            keys[lens["gap"]] = max(keys.get(lens["gap"], ""), q["round"] or "")
    return keys


def _last_event(ctx: Ctx, kind: str, ref: str | None = None) -> dict:
    row = db.one(ctx.conn, "SELECT payload FROM events WHERE kind=? AND (? IS NULL OR ref=?) ORDER BY id DESC LIMIT 1",
                 (kind, ref, ref))
    return json.loads((row or {}).get("payload") or "{}") or {}


def _depth_state(ctx: Ctx, key: str) -> tuple[int, bool]:
    """(follow-ups actually asked, one still waiting to be asked) for a depth topic."""
    rows = db.rows(ctx.conn, "SELECT status, asked_u, lens FROM questions WHERE lens LIKE ?", (f'%"gap": "{key}"%',))
    asked = sum(1 for r in rows if r["asked_u"] or r["status"] == "asked"
                or (r["status"] == "answered" and not (json.loads(r["lens"] or "{}") or {}).get("stale")))
    waiting = any(r["status"] in ("open", "held") and not r["asked_u"] for r in rows)
    return asked, waiting


def _add_card(ctx: Ctx, rnd: str, text: str, stage: str, key: str, why: str, evidence: list, impact: str,
              first: bool = False) -> str:
    qid = db.next_id(ctx.conn, "questions", "Q-")
    db.upsert(ctx.conn, "questions", {
        # 추측: a stage card asks, it never holds the core-freeze gate (that counts 확실/가능성 높음 cards)
        "id": qid, "round": rnd, "candidate": None, "text": text, "confidence": "추측", "impact": impact,
        "bucket": "ask", "flags": json.dumps([f"단계 {stage}"] + (["이미 들었으면 닫기"] if key.split(":")[0] in WORDLIST_GAPS
                                                                 else []), ensure_ascii=False),
        "evidence": json.dumps(evidence, ensure_ascii=False), "decision_at_stake": why,
        "lens": json.dumps({"stage": stage, "gap": key}, ensure_ascii=False), "verifier": "{}", "counter": "{}",
        # after this round's analyst cards (they keep their order), except the type question: it goes first
        "ord": -1 if first else 900, "status": "open", "asked_u": None, "answer_us": "[]", "updated_at": iso()})
    return qid


def check(ctx: Ctx, rnd: str) -> dict[str, Any]:
    """Round end: store the stage map, reopen stages a later stage exposed, make gap/depth cards (≤2 per round) and at
    most one "go back?" D2 per round in collaboration mode (autonomy takes the recommendation). Never moves P."""
    _apply_answers(ctx)
    m = compute(ctx)
    gaps, current = m["gaps"], m["current"]
    cur_i = ORDER.index(current)
    stored = _stored(ctx)
    _close_stale(ctx, gaps, rnd)
    prev_types = db.one(ctx.conn, "SELECT types FROM engagement WHERE id=1")
    prev_codes = [t["code"] for t in json.loads((prev_types or {}).get("types") or "[]")]
    now_codes = [t["code"] for t in m["engagement"]["types"]]
    type_changed = bool(prev_codes) and prev_codes != ["E8"] and (
        (prev_codes[:1] != now_codes[:1] and now_codes[:1] != ["E8"]) or bool(set(now_codes) - set(prev_codes) - {"E8"})
        or any(t.get("new") for t in m["engagement"]["types"]))
    if type_changed and sorted(now_codes) in [sorted(p) for r in db.rows(
            ctx.conn, "SELECT payload FROM events WHERE kind='stage.type_changed'")
            for p in (json.loads(r["payload"] or "{}") or {}).values()]:
        # ponytail: a mix of types already flagged (as "from" or "to", any lead) is not flagged again, so a wavering
        # lead asks once; a type never seen before still asks
        type_changed = False
    reopened_now = []
    with db.write_txn(ctx.conn):
        for i, s in enumerate(ORDER):
            row = stored.get(s) or {}
            was = row.get("status") or OPEN
            g = gaps[s]
            if not g:
                status = DONE if i <= cur_i or was == DONE else OPEN  # a stage not reached yet is not "done"
            elif was == DONE or (s == "S1" and type_changed and was != REOPENED and row):
                status = REOPENED  # a later stage exposed this stage's gap, or the engagement type changed
            elif was == REOPENED:
                status = REOPENED
            else:
                status = PARTIAL if (i <= cur_i or row.get("opened_at")) else OPEN
            reopened = int(row.get("reopened") or 0) + (1 if status == REOPENED and was != REOPENED else 0)
            if status == REOPENED and was != REOPENED:
                reopened_now.append(s)
            ctx.conn.execute(
                "INSERT INTO stages(id, status, opened_at, closed_at, reopened, gaps) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, closed_at=excluded.closed_at, "
                "reopened=excluded.reopened, gaps=excluded.gaps",
                (s, status, row.get("opened_at") or (iso() if i <= cur_i else None), iso() if status == DONE else None,
                 reopened, json.dumps(g, ensure_ascii=False)))
        e = m["engagement"]
        if e["source"] != "seat":
            ctx.conn.execute("INSERT INTO engagement(id, types, roles, confidence, evidence, source, updated_at) "
                             "VALUES(1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET types=excluded.types, roles=excluded.roles, "
                             "confidence=excluded.confidence, evidence=excluded.evidence, source=excluded.source, "
                             "updated_at=excluded.updated_at WHERE engagement.source IS NOT 'seat'",
                             (json.dumps(e["types"], ensure_ascii=False), json.dumps(e["roles"], ensure_ascii=False),
                              e["confidence"], json.dumps(sorted({x for t in e["types"] for x in t["evidence"]})),
                              e["source"], iso()))
    made = _cards(ctx, rnd, m, reopened_now)
    d2 = _go_back(ctx, rnd, m, reopened_now, prev_codes if type_changed else None) or _depth_d2(ctx, rnd, m)
    if d2:
        _apply_answers(ctx)  # autonomy: the recommendation was taken at once
    if type_changed:
        ctx.event("stage.type_changed", rnd, {"from": prev_codes, "to": now_codes})
    for s in reopened_now:
        ctx.event("stage.reopened", s, {"round": rnd, "gaps": len(gaps[s])})
    out = {**m, "stages": _stored(ctx), "cards": made, "d2": d2, "reopened_now": reopened_now}
    write_json(ctx.p.docs / "stage-map.json", summary(out))
    return out


def _close_stale(ctx: Ctx, gaps: dict, rnd: str = "") -> None:
    """A stage card whose gap has closed is answered by the conversation itself: it leaves the open cards (it must not
    hold a freeze gate or a shown place). So is one whose question changed (the type card once who uses it was said:
    a new card asks the next thing, or none when both were said). A depth card stays until asked — or until two rounds
    passed unasked (the interviewer asked it in other words, which links no card): then a new follow-up may come."""
    now = {(g["key"], g["question"]) for gs in gaps.values() for g in gs}
    for q in db.rows(ctx.conn, "SELECT id, round, text, lens, asked_u FROM questions WHERE status IN ('open','held') "
                               "AND lens LIKE ?", ('%"stage"%',)):
        lens = json.loads(q["lens"] or "{}") or {}
        key = lens.get("gap", "")
        unasked_long = key.startswith("depth:") and not q["asked_u"] and _rnum(rnd) - _rnum(q.get("round") or rnd) >= 2
        if key and ((not key.startswith("depth:") and (key, q["text"]) not in now) or unasked_long):
            ctx.conn.execute("UPDATE questions SET status='answered', lens=?, updated_at=? WHERE id=?",
                             (json.dumps({**lens, "stale": True}, ensure_ascii=False), iso(), q["id"]))
            ctx.event("stage.card_closed", q["id"], {"gap": key})


def _apply_answers(ctx: Ctx) -> None:
    """Answered stage D2s take effect once: an answer with "가정" turns the open cards they cover into assumptions
    (assumed) and a reopened stage back to partial (no more go-back); "나중에" / "…묻기" leave the cards open."""
    done = {r["ref"] for r in db.rows(ctx.conn, "SELECT ref FROM events WHERE kind='stage.d2_applied'")}
    for d in db.rows(ctx.conn, "SELECT * FROM decisions WHERE source='stage' AND status IN ('answered','auto')"):
        if d["id"] in done:
            continue
        target = (json.loads(d["blocking"] or "[]") or [""])[0]  # "stage:S3" or "depth:<topic>"
        ans = str(d["answer"] or "").strip()
        if ans.startswith("가정으로") or ans.endswith("(가정)"):  # the offered assumption options, not any "가정" in free text
            if target.startswith("stage:"):
                ctx.conn.execute("UPDATE stages SET status=? WHERE id=? AND status=?", (PARTIAL, target[6:], REOPENED))
            covered = 0
            for q in db.rows(ctx.conn, "SELECT id, text, lens FROM questions WHERE status IN ('open','held') AND lens LIKE ?",
                             ('%"stage"%',)):
                lens = json.loads(q["lens"] or "{}") or {}
                if (target.startswith("stage:") and lens.get("stage") == target[6:] and not lens.get("gap", "").startswith("depth:")) \
                        or (target.startswith("depth:") and lens.get("gap") == target):
                    ctx.conn.execute("UPDATE questions SET status='assumed', updated_at=? WHERE id=?", (iso(), q["id"]))
                    aid = db.next_id(ctx.conn, "assumptions", "A-")
                    db.upsert(ctx.conn, "assumptions", {"id": aid, "text": f"{q['text']} → 가정으로 진행(확인 안 됨)",
                                                        "reason": f"{d['id']} {d['answer']}", "related": json.dumps([q["id"]]),
                                                        "round": d["round"], "status": "active"})
                    covered += 1
            if not covered:  # nothing open to settle: the topic or the stage itself becomes the assumption
                aid = db.next_id(ctx.conn, "assumptions", "A-")
                what = f"[{target[6:]}] 막연한 답" if target.startswith("depth:") else f"{target[6:]} 빈칸"
                db.upsert(ctx.conn, "assumptions", {"id": aid, "text": f"{what} → 가정으로 진행(확인 안 됨)",
                                                    "reason": f"{d['id']} {d['answer']}", "related": json.dumps([]),
                                                    "round": d["round"], "status": "active"})
        ctx.event("stage.d2_applied", d["id"], {"answer": d["answer"], "target": target})


def _cards(ctx: Ctx, rnd: str, m: dict, reopened_now: list[str]) -> list[str]:
    """New stage cards, at most NEW_CARDS_PER_ROUND per round (counting cards made earlier in the same round).
    Priority: the engagement-type question, gaps of a reopened stage, follow-ups to this round's vague answers, then
    the remaining gaps of the current and earlier stages."""
    keys = _card_rounds(ctx)
    since = {s: rnd if s in reopened_now else _last_event(ctx, "stage.reopened", s).get("round", "")
             for s, row in _stored(ctx).items() if row.get("status") == REOPENED}
    room = NEW_CARDS_PER_ROUND - int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM questions WHERE round=? AND lens LIKE ?",
                                                (rnd, '%"stage"%'), 0))
    gaps, cur_i = m["gaps"], ORDER.index(m["current"])
    todo: list[tuple[int, dict]] = []
    open_keys = {(json.loads(q["lens"] or "{}") or {}).get("gap") for q in db.rows(
        ctx.conn, "SELECT lens FROM questions WHERE status IN ('open','held') AND lens LIKE ?", ('%"stage"%',))}
    for s in ORDER[:max(cur_i + 1, 4)]:  # the current stage and everything before it (interview stages always)
        for g in gaps[s]:
            if _panel_only(g):  # H7 fallback (19:1x): shown on the stage band and the role panel, never a card
                continue
            if g["question"] and g["key"] not in open_keys and (g["key"] not in keys or keys[g["key"]] < since.get(s, "")):
                todo.append((0 if g["key"] == "type" else 1 if s in since else 3, g))
    seen: set[str] = set()
    for v in m["vague"]:  # depth: a vague answer of this round gets a follow-up (≤ FOLLOW_LIMIT asked per topic)
        key = f"depth:{v['area']}"
        asked, waiting = _depth_state(ctx, key)
        if v["round"] == rnd and key not in seen and asked < FOLLOW_LIMIT and not waiting:
            seen.add(key)
            q = f"아까 \"{short(v['text'].rstrip('.!?~ '), 30)}\"라고 하셨는데, " + FOLLOW_UPS[v["kind"]]
            todo.append((2, {"stage": m["current"], "key": key, "depth": v, "question": q}))
    todo.sort(key=lambda t: (t[0], ORDER.index(t[1]["stage"])))
    tq = next((g["question"] for _, g in todo[:max(0, room)] if g["key"] == "type"), None)
    if tq:  # the type question already asks who uses it (or, when that was said, who runs it)
        todo = [t for t in todo if t[1]["key"] != ("role:end_users" if tq == TYPE_QUESTIONS[0] else "role:operator")]
    made: list[str] = []
    for _, g in todo[:max(0, room)]:
        if "depth" in g:
            v = g["depth"]
            made.append(_add_card(ctx, rnd, g["question"], g["stage"], g["key"],
                                  f"[깊이] {v['id']} \"{v['text']}\" — 막연한 답이라 한 번 더 구체적으로", [v["id"]], "중간"))
        else:
            made.append(_add_card(ctx, rnd, g["question"], g["stage"], g["key"],
                                  f"[{g['stage']} {NAMES[g['stage']]}] {g['why']}", [],
                                  # only the type card is 높음: any other 높음 stage card would take the P-03 place
                                  # of an earlier analyst card and count in the full-freeze check
                                  "높음" if g["key"] == "type" else "중간",
                                  first=g["key"] == "type"))
    return made


def _stage_d2_this_round(ctx: Ctx, rnd: str) -> bool:
    """At most one stage D2 per round, and none while another stage D2 is still waiting for an answer."""
    return bool(db.scalar(ctx.conn, "SELECT COUNT(*) FROM decisions WHERE source='stage' AND (round=? OR status IN "
                                    "('new','asked'))", (rnd,), 0))


def _go_back(ctx: Ctx, rnd: str, m: dict, reopened_now: list[str], switched_from: list[str] | None) -> str | None:
    # `blocking` names what the answer settles ("stage:S3", "depth:<topic>"); it is a D2, so no D1 freeze gate reads it
    if not reopened_now or _stage_d2_this_round(ctx, rnd):
        return None
    s = reopened_now[0]
    if s == "S1" and switched_from is not None:
        return None  # a type shift is a role/type matter: shown on the panel (새 유형 신호), never a D2 (H7 fallback)
    n = sum(1 for g in m["gaps"][s] if g["question"] and not _panel_only(g))  # what can be asked of the persona
    if not n:
        return None  # nothing to ask the persona: no D2 stops the user (the map still shows ↺)
    gaps = "; ".join(g["text"] for g in m["gaps"][s][:3])
    if s == "S1" and switched_from is not None:  # the engagement type shifted: S1 is asked again for the new type
        types = m["engagement"]["types"]
        ids = sorted({x for t in types if t.get("new") or t["code"] not in switched_from for x in t["evidence"]})[:4]
        added = [t["code"] for t in types if t["code"] not in switched_from]
        what = (f"{'/'.join(switched_from)}에 {'/'.join(added)} 신호가 더해졌습니다" if added
                else f"1위가 {switched_from[0]}에서 {types[0]['code']}로 바뀌었습니다")
        title = (f"의뢰 유형이 바뀐 신호가 있습니다: {what}" + (f"({', '.join(ids)})" if ids else "")
                 + f". 새 유형에 필요한 S1 질문 {n}개를 물을까요?")
        opts = [f"S1 질문 {n}개 묻기", "지금 유형으로 진행(가정)", "나중에"]
        why = "유형 전환 신호: " + (", ".join(ids) or "좌석 판단 뒤 발화") + " · 남은 빈칸: " + gaps
    else:
        title = f"{s} {NAMES[s]}에 빈칸 {n}개가 드러났습니다. 돌아가서 물을까요?"
        opts, why = [f"{s}로 돌아가 {n}개 묻기", "가정으로 진행", "나중에"], "뒤 단계에서 드러난 빈칸: " + gaps
    return D.add(ctx, title, "D2", why, opts, opts[0], source="stage", round_id=rnd, blocking=[f"stage:{s}"])


def _depth_d2(ctx: Ctx, rnd: str, m: dict) -> str | None:
    """A topic asked twice and still vague: confirm an assumption instead of a third follow-up."""
    if _stage_d2_this_round(ctx, rnd):
        return None
    for v in m["vague"]:
        key = f"depth:{v['area']}"
        if v["round"] == rnd and _depth_state(ctx, key)[0] >= FOLLOW_LIMIT and not db.scalar(
                ctx.conn, "SELECT COUNT(*) FROM decisions WHERE source='stage' AND title LIKE ?", (f"%[{v['area']}]%",), 0):
            opts = ["가정으로 정리", "나중에"]  # a third follow-up is past FOLLOW_LIMIT
            return D.add(ctx, f"[{v['area']}] 두 번 물어도 답이 막연합니다. 가정으로 정리할까요?", "D2",
                         f"{v['id']} \"{v['text']}\"", opts, opts[0], source="stage", round_id=rnd, blocking=[key])
    return None


# ---------- read model / report ----------

def summary(m: dict) -> dict:
    stored = m.get("stages") or {}
    stages = []
    cur_i = ORDER.index(m["current"])
    for i, s in enumerate(ORDER):
        row = stored.get(s) or {}
        g = m["gaps"][s]
        status = row.get("status") or (DONE if not g and i <= cur_i else PARTIAL if g and i <= cur_i else OPEN)
        stages.append({"id": s, "name": NAMES[s], "status": status, "mark": MARK.get(status, "○"), "gaps": g,
                       "reopened": int(row.get("reopened") or 0), "current": s == m["current"]})
    e = m["engagement"]
    need = set(needed_roles([t["code"] for t in e["types"]]))
    # H7 (19:15 real session): only what the stakeholder seat judged is shown; a value read from word signals or a
    # question/answer pair is used inside (gaps) but shown as 모름 (확인 필요) — a wrong value looks settled
    shown = {k: (v if v.get("by") == "seat" else {"who": "확인 필요", "evidence": []}) for k, v in e["roles"].items()}
    return {"current": m["current"], "stages": stages, "engagement": {**e, "roles": shown},
            "roles": [{"key": k, "name": ROLE_SHORT[k], "title": ROLE_NAMES[k], "needed": k in need,
                       **shown.get(k, {"who": "확인 필요", "evidence": []})} for k, _ in ROLES],
            "must_know": m.get("must_know", {}), "vague": m.get("vague", [])[-10:]}


def line(s: dict) -> str:
    return " · ".join(f"{x['id']} {x['mark']}" + (f"(빈칸 {len(x['gaps'])})" if x["gaps"] and x["status"] != "done" else "")
                      + (" ←지금" if x["current"] else "") for x in s["stages"])


def holes(s: dict, n: int = 3, cards: dict | None = None) -> list[str]:
    """The top gaps for the interviewer: reopened first, then the current stage, then earlier stages. `cards`
    (gap key → open card id) points each gap at the card that would close it."""
    ranked = sorted((g for x in s["stages"] for g in x["gaps"] if (x["status"] in ("reopened", "partial") or x["current"])
                     and not _panel_only(g)),  # role/type gaps live on the role panel (H7 fallback)
                    key=lambda g: (next(x for x in s["stages"] if x["id"] == g["stage"])["status"] != "reopened",
                                   g["stage"] != s["current"], ORDER.index(g["stage"])))
    cards = cards or {}
    return [f"[{g['stage']}] {g['text']} — {g['why']}" + (f" → {cards[g['key']]}" if g["key"] in cards else "")
            for g in ranked[:n]]


def open_cards_by_gap(ctx: Ctx) -> dict[str, str]:
    out: dict[str, str] = {}
    for q in db.rows(ctx.conn, "SELECT id, lens FROM questions WHERE status='open' AND lens LIKE '%\"stage\"%' ORDER BY id"):
        out.setdefault((json.loads(q["lens"] or "{}") or {}).get("gap", ""), q["id"])
    return out
