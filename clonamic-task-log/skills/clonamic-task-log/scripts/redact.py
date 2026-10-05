"""Input abstraction (paths -> labels, identifiers scrubbed) and the output gate.

Nothing that leaves this module for the agent carries a path, file name, commit hash,
e-mail, URL, host, IP, env var name, ticket/branch id, or secret.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePosixPath

from common import Profile, is_code, is_doc, is_test

MASK = "‹비공개›"
TYPE_KO = {"feat": "기능", "perf": "성능", "fix": "수정", "refactor": "구조 개선", "change": "변경", "test": "테스트",
           "docs": "문서", "revert": "되돌림", "chore": "유지보수", "style": "스타일"}
REASON_KO = {"merge": "병합 커밋", "duplicate": "다른 브랜치의 같은 변경", "bot": "봇 커밋", "revert_pair": "되돌림 쌍", "excluded_path": "제외 경로만", "out_of_scope": "범위 밖",
             "empty": "빈 커밋", "generated_only": "생성·잠금·외부 파일만", "whitespace_only": "공백만",
             "comment_only": "주석만"}
DIR_LABELS = {
    "auth": "인증", "login": "로그인", "oauth": "인증", "api": "API 계층", "apis": "API 계층", "routes": "라우팅",
    "router": "라우팅", "ui": "UI 컴포넌트", "components": "UI 컴포넌트", "pages": "화면", "views": "화면",
    "screens": "화면", "db": "데이터 계층", "database": "데이터 계층", "models": "데이터 모델", "schema": "데이터 스키마",
    "migrations": "DB 마이그레이션", "config": "설정", "configs": "설정", "settings": "설정", ".github": "CI 설정",
    "ci": "CI 설정", "workflows": "CI 설정", "payments": "결제", "payment": "결제", "billing": "결제",
    "users": "사용자 관리", "user": "사용자 관리", "accounts": "계정", "admin": "관리자 기능", "cli": "CLI",
    "server": "서버", "backend": "백엔드", "client": "클라이언트", "frontend": "프런트엔드", "web": "웹",
    "mobile": "모바일", "ios": "iOS 앱", "android": "Android 앱", "utils": "공통 유틸리티", "util": "공통 유틸리티",
    "helpers": "공통 유틸리티", "common": "공통 모듈", "shared": "공통 모듈", "core": "핵심 모듈",
    "infra": "인프라", "deploy": "배포", "deployment": "배포", "docker": "컨테이너 설정", "k8s": "배포 설정",
    "styles": "스타일", "css": "스타일", "assets": "정적 자원", "static": "정적 자원", "public": "정적 자원",
    "i18n": "다국어", "locales": "다국어", "hooks": "훅", "services": "서비스 계층", "service": "서비스 계층",
    "workers": "백그라운드 작업", "jobs": "백그라운드 작업", "queue": "작업 큐", "cache": "캐시",
    "search": "검색", "notifications": "알림", "notification": "알림", "chat": "채팅", "analytics": "분석",
    "data": "데이터 처리", "etl": "데이터 파이프라인", "pipeline": "파이프라인", "pipelines": "파이프라인",
    "ml": "머신러닝", "model": "모델", "training": "모델 학습", "inference": "추론", "plugin": "플러그인",
    "plugins": "플러그인", "skills": "스킬", "agents": "에이전트", "scripts": "스크립트", "tools": "도구",
    "templates": "템플릿", "examples": "예제", "docs": "문서", "doc": "문서", "tests": "테스트", "test": "테스트",
    "__tests__": "테스트", "spec": "테스트", "e2e": "E2E 테스트", "bench": "벤치마크", "benchmarks": "벤치마크",
    "monitoring": "모니터링", "logging": "로깅", "security": "보안", "storage": "저장소 계층", "upload": "업로드",
    "editor": "편집기", "dashboard": "대시보드", "reports": "보고서", "export": "내보내기", "import": "가져오기",
}
CONTAINERS = {"src", "lib", "app", "apps", "packages", "pkg", "internal", "source", "main", "java", "kotlin",
              "com", "org", "modules", "module", "python", "go", "js", "ts"}

PUBLIC_TERMS = {
    "GitHub", "GitLab", "JavaScript", "TypeScript", "PostgreSQL", "MySQL", "MongoDB", "OAuth", "iOS", "macOS",
    "iPadOS", "NumPy", "PyTorch", "FastAPI", "OpenAI", "DevOps", "YouTube", "WebSocket", "GraphQL", "LaTeX",
    "SQLite", "NestJS", "NextJS", "VSCode", "IntelliJ", "PowerShell", "GitOps", "WebAssembly", "WebGL",
    "TensorFlow", "LangChain", "LlamaIndex", "ChatGPT", "DynamoDB", "BigQuery", "CloudFront", "OpenSearch",
    "ElasticSearch", "Elasticsearch", "RabbitMQ", "MariaDB", "SwiftUI", "UIKit", "AppKit", "CocoaPods",
    "PyPI", "npm", "pnpm", "JUnit", "pytest", "eBPF", "gRPC", "tRPC", "WebRTC", "OpenAPI", "JWT", "SaaS",
    "Node.js", "Vue.js", "Next.js", "Nuxt.js", "Express.js", "Three.js", "D3.js", "Chart.js", "ASP.NET", ".NET",
    "UTF-8", "UTF-16", "SHA-1", "SHA-256", "SHA-512", "ISO-8601", "AES-128", "AES-256", "GPT-4", "GPT-5",
    "HTTP/2", "HTTP/3", "req/s", "ops/s", "MB/s", "GB/s", "KB/s", "km/h", "Socket.IO", "socket.io",
    "iPhone", "iPad", "watchOS", "tvOS", "visionOS", "JSON", "YAML",
}

KNOWN_EXT = (
    "py|pyi|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|kts|swift|rb|php|c|h|cc|cpp|hpp|cs|m|mm|scala|dart|lua|pl|sh|"
    "bash|zsh|ps1|sql|vue|svelte|ex|exs|erl|hs|clj|zig|nim|jl|html|htm|css|scss|sass|less|proto|graphql|tf|"
    "ipynb|md|mdx|rst|adoc|txt|json|jsonl|yaml|yml|toml|ini|cfg|conf|xml|gradle|properties|env|lock|csv|tsv|"
    "parquet|db|sqlite|log|pem|key|crt|p12|pfx|jar|war|so|dll|dylib|exe|bin|zip|tar|gz|tgz|whl|png|jpe?g|gif|"
    "svg|webp|ico|pdf|docx?|xlsx?|pptx?|hwp|plist|pbxproj|xcconfig|nix|dockerfile|mk|cmake|bat|r"
)
A, I = re.ASCII, re.IGNORECASE  # ASCII word boundaries: Korean particles attach directly to identifiers
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("code_span", re.compile(r"`[^`\n]+`")),
    ("url", re.compile(r"\b(?:https?|ftp|ssh|git|s3|gs|file)://[^\s)>\]]+|\bwww\.[^\s)>\]]+|\bgit@[\w.-]+:[\w./-]*", A | I)),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", A)),
    ("secret", re.compile(
        r"-----BEGIN [A-Z ]+-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_\w{20,}|"
        r"\bsk-[A-Za-z0-9_-]{16,}|\bxox[abprs]-[\w-]{10,}|\bAIza[\w-]{30,}|\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]*|"
        r"\b(?:api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*\S+", A | I)),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b|\b(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}\b", A | I)),
    ("host", re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|kr|co|ai|app|cloud|local|internal|corp|lan|"
                        r"svc|cluster|intra|test|example|xyz|me|us|jp|cn|de|uk)\b(?::\d+)?", A | I)),
    ("path", re.compile(r"(?<![\w/])(?:~|\.{1,2})?/?[A-Za-z0-9_.@-]+(?:/[A-Za-z0-9_.@-]+)+/?|\b[A-Za-z]:\\\S+|\b\w+\\\w[\w\\.]*", A)),
    ("dotfile", re.compile(r"(?<![\w.])\.(?:env\w*|gitignore|gitattributes|github|claude|codex|cursor|grok|vscode|idea|"
                           r"npmrc|nvmrc|dockerignore|eslintrc\w*|prettierrc\w*|babelrc|editorconfig|bashrc|zshrc)\b", A)),
    ("filename", re.compile(rf"(?<![A-Za-z0-9_.-])[^\s()\[\]{{}}<>\"'`,;:/\\|*?]+?\.(?:{KNOWN_EXT})(?![A-Za-z0-9_])", I)),
    ("env_var", re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b", A)),
    ("ticket", re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b|(?<![\w&])#\d+\b|\b(?:PR|MR)\s?\d+\b", A)),
    ("hash", re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b", A)),
    ("identifier", re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b", A)),
    ("mask", re.compile(re.escape(MASK))),
]
UPPER_PAIR = re.compile(r"^(?:[A-Z]{1,4}(?:/[A-Z]{1,4})+|\d+(?:/\d+)+)$")  # CI/CD, I/O, UI/UX, A/B, 3/5


def _allowed(token: str, extra_public: set[str]) -> bool:
    token = token.strip(".,;:()[]")
    return token in PUBLIC_TERMS or token in extra_public or bool(UPPER_PAIR.match(token))


def _term_patterns(profile: Profile | None) -> list[re.Pattern]:
    if not profile:
        return []
    pats = [re.compile(re.escape(term), re.I) for term in profile.private_terms]
    pats += [re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(term)}(?![A-Za-z0-9_-])", re.I) for term in profile.repo_terms]
    return pats


def findings(text: str, profile: Profile | None = None) -> list[dict]:
    """Every blocked token in text. The gate passes only when this is empty."""
    public = set(profile.public_terms) if profile else set()
    hits: list[dict] = []
    for kind, pattern in PATTERNS:
        for m in pattern.finditer(text):
            if kind in {"path", "filename", "identifier", "ticket", "host"} and _allowed(m.group(), public):
                continue
            hits.append({"kind": kind, "token": m.group(), "line": text.count("\n", 0, m.start()) + 1})
    for pattern in _term_patterns(profile):
        for m in pattern.finditer(text):
            hits.append({"kind": "private_term", "token": m.group(), "line": text.count("\n", 0, m.start()) + 1})
    return hits


def scrub(text: str, profile: Profile | None = None) -> str:
    public = set(profile.public_terms) if profile else set()
    for pattern in _term_patterns(profile):
        text = pattern.sub(MASK, text)
    for kind, pattern in PATTERNS:
        if kind == "mask":
            continue
        text = pattern.sub(lambda m: m.group() if kind in {"path", "filename", "identifier", "ticket", "host"}
                           and _allowed(m.group(), public) else MASK, text)
    text = re.sub(rf"{MASK}(?:[\s,./:+-]*{MASK})+", MASK, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


INTERNAL_NAME = re.compile(r"^(?=.{4,}$)(?=.*[-_0-9])[A-Za-z0-9][A-Za-z0-9_-]*[A-Za-z0-9]$")


def repo_terms(paths: list[str], project: str) -> list[str]:
    """Internal names (hyphen/underscore/digit-bearing dir names and file stems) found in the repo."""
    terms: set[str] = set()
    for path in paths:
        for part in PurePosixPath(path).parts:
            stem = part.split(".", 1)[0] if not part.startswith(".") else ""
            if INTERNAL_NAME.match(stem) and not re.fullmatch(r"[\d_-]+|v?\d+(?:[-_]\d+)*", stem):
                terms.add(stem.lower())
                pieces = re.split(r"[-_]", stem)
                if len(pieces) >= 3 and len(tail := "-".join(pieces[1:])) >= 6:
                    terms.add(tail.lower())  # 'acme-safe-patch' also hides 'safe-patch'

    terms -= {project.lower()} | {t.lower() for t in PUBLIC_TERMS}
    return sorted(terms, key=lambda s: (-len(s), s))


def strip_prefix(subject: str) -> str:
    return re.sub(r"^[A-Za-z]+(?:\([^)]*\))?!?:\s*", "", subject).strip()


def area_label(path: str, profile: Profile) -> str:
    from score import feature_of  # local import keeps module graph acyclic for tests

    if label := feature_of(path, profile):
        return label
    parts = [p.lower() for p in PurePosixPath(path).parts[:-1]]
    for part in parts:
        if part in DIR_LABELS:
            return DIR_LABELS[part]
    if is_test(path):
        return "테스트"
    if is_doc(path):
        return "문서"
    if is_code(path):
        return "코드 모듈"
    return "설정·기타 파일"


def kind_of(path: str) -> str:
    if is_test(path):
        return "테스트"
    if is_doc(path):
        return "문서"
    if is_code(path):
        return "코드"
    return "설정·자원"


def abstract_commit(commit: dict, profile: Profile, rank: int) -> dict:
    areas = Counter()
    for f in commit["files"]:
        areas[area_label(f["path"], profile)] += f["added"] + f["deleted"] + 1
    files = Counter(f["status"] for f in commit["files"])
    return {
        "rank": rank,
        "score": commit["score"],
        "score_parts": commit["score_parts"],
        "type": commit["type"],
        "type_ko": TYPE_KO.get(commit["type"], "변경"),
        "date": commit["date"][:10],
        "feature": commit["features"][0] if commit.get("features") and not commit.get("cross_cutting") else "",
        "cross_cutting": bool(commit.get("cross_cutting")),
        "areas": [a for a, _ in areas.most_common(4)],
        "summary": scrub(strip_prefix(commit["subject"]), profile),
        "detail": scrub(commit["body"], profile)[:400],
        "files": {"added": files.get("A", 0), "modified": files.get("M", 0), "deleted": files.get("D", 0)},
        "lines": {"added": commit["added"], "deleted": commit["deleted"]},
        "tests_added": commit["tests_added"],
        "new_module": commit["score_parts"]["new"] == 10,
        "breaking": commit["breaking"],
    }


def abstract_metric(metric: dict, commit: dict, profile: Profile) -> dict:
    before, after = metric["before"], metric["after"]
    change = round(100 * (after - before) / before, 1) if before else None
    return {
        "feature": commit["features"][0] if commit.get("features") else "",
        "before": before, "after": after, "unit": metric["unit"],
        "change_pct": change,
        "basis": scrub(strip_prefix(metric["line"]), profile),
        "from_summary": scrub(strip_prefix(commit["subject"]), profile),
        "date": commit["date"][:10],
    }


def work_items(detailed: list[dict]) -> list[dict]:
    """Group the detailed commits into work areas (one '### ' item each in 작업 상세)."""
    groups: dict[str, dict] = {}
    for item in detailed:
        title = item["feature"] or ("여러 영역에 걸친 작업" if item["cross_cutting"] or not item["areas"] else item["areas"][0])
        group = groups.setdefault(title, {"title": title, "score": 0, "ranks": [], "types": []})
        group["score"] = max(group["score"], item["score"])
        group["ranks"].append(item["rank"])
        if item["type_ko"] not in group["types"]:
            group["types"].append(item["type_ko"])
    return sorted(groups.values(), key=lambda g: (-g["score"], g["ranks"][0]))


def abstract_run(scored: dict, progress: dict, profile: Profile, meta: dict) -> dict:
    included = scored["included"]
    n = scored["detailed_count"]
    detailed = [abstract_commit(c, profile, i + 1) for i, c in enumerate(included[:n])]
    rest = Counter(TYPE_KO.get(c["type"], "변경") for c in included[n:])
    new_things = Counter()
    for c in included:
        for f in c["files"]:
            if f["status"] == "A":
                new_things[(area_label(f["path"], profile), kind_of(f["path"]))] += 1
    metrics = [abstract_metric(m, c, profile) for c in included for m in c["metrics"]]
    excluded = scored["excluded_by_reason"]
    return {
        "date": meta["date"],
        "key": meta["key"],
        "period": meta["period"],
        "project": meta["project"],
        "part": profile.part,
        "counts": {
            "collected": len(included) + len(scored["excluded"]),
            "included": len(included),
            "detailed": len(detailed),
            "excluded": {REASON_KO[r]: n for r, n in excluded.items()},
            "lines": {"added": sum(c["added"] for c in included), "deleted": sum(c["deleted"] for c in included)},
            "by_type": dict(Counter(TYPE_KO.get(c["type"], "변경") for c in included).most_common()),
        },
        "work_items": work_items(detailed),
        "detailed": detailed,
        "others": {"count": sum(rest.values()), "by_type": dict(rest.most_common())},
        "new_things": [{"area": a, "kind": k, "count": cnt} for (a, k), cnt in new_things.most_common(8)],
        "progress": progress["features"],
        "work_unit": progress["work_unit"],
        "metrics": metrics,
        "mask": MASK,
    }
