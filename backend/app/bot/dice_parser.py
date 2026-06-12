"""Dice Result Parser — reads dice-robot (骰娘) output from group chat.

Does NOT roll dice itself. Silently parses dice-robot messages to extract
structured results, which feed into State Tracking, RAG, and Plot Deviation.

Supported formats (COC common dice bots):
  - .r 1d100 = 75
  - 检定/侦查 70/45 失败
  - 1D100=32/60 成功
  - .ra 侦查 70 = 45/70 成功
  - .st 力量 对抗 50 vs 30 => 成功
  - {nick} 进行 侦查检定: D100=28/65 困难成功
  - 暗骰: No output or "???" — skipped
"""

import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class DiceResult:
    """Structured dice result extracted from dice-robot message."""
    check_type: str = ""          # 检定类型: "侦查", "图书馆使用", "力量对抗", etc.
    target: int = 0               # 技能值/目标值
    rolled: int = 0               # 实际投出值
    outcome: str = "unknown"      # critical_success | extreme_success | hard_success |
                                  # normal_success | failure | fumble
    raw_text: str = ""            # 原始骰娘消息原文
    is_secret: bool = False       # 是否为暗骰 (no visible result)

    def is_success(self) -> bool:
        return self.outcome in (
            "critical_success", "extreme_success",
            "hard_success", "normal_success",
        )

    def is_critical(self) -> bool:
        return self.outcome in ("critical_success", "fumble")


# ── Regex patterns ─────────────────────────────────────────────

# Pattern 1: .r 1d100 = 75  (most common)
PATTERN_DOT_R = re.compile(
    r'\.r\s+(?:1?d100|d100)\s*[=＝]\s*(\d{1,3})',
    re.IGNORECASE,
)

# Pattern 2: 检定/侦查 70/45 失败
#           检定/侦查 70/45 成功
#           Check/Investigation 70/32 Success
PATTERN_CHECK_RESULT = re.compile(
    r'(?:检定|Check)[：:/]\s*'
    r'(?P<check_type>[^\s\d/]+)\s*'
    r'(?P<target>\d{1,3})\s*/\s*'
    r'(?P<rolled>\d{1,3})\s*'
    r'(?P<outcome>成功|失败|大成功|大失败|Success|Failure)',
    re.IGNORECASE,
)

# Pattern 3: D100=32/60 成功
PATTERN_D100_RESULT = re.compile(
    r'(?:D100|d100)\s*[=＝]\s*(?P<rolled>\d{1,3})\s*/\s*(?P<target>\d{1,3})'
    r'\s*(?P<outcome>成功|失败|大成功|大失败|Success|Failure|'
    r'critical[\s_]*success|fumble)',
    re.IGNORECASE,
)

# Pattern 4: .ra 侦查 70 = 45/70 成功
PATTERN_RA = re.compile(
    r'\.ra\s+(?P<check_type>[^\d=]+?)\s*(?P<target>\d{1,3})?\s*[=＝]\s*'
    r'(?P<rolled>\d{1,3})\s*/\s*(?P<target2>\d{1,3})?'
    r'\s*(?P<outcome>成功|失败|大成功|大失败|Success|Failure)?',
    re.IGNORECASE,
)

# Pattern 5: .st 力量 对抗 50 vs 30 => 成功
PATTERN_ST = re.compile(
    r'\.st\s+(?P<check_type>[^对]*?)\s*对抗\s*'
    r'(?P<rolled>\d{1,3})\s*(?:vs|v)\s*(?P<target>\d{1,3})'
    r'.*?(?P<outcome>成功|失败|Success|Failure)?',
    re.IGNORECASE,
)

# Pattern 6: {nick} 进行 侦查检定: D100=28/65 困难成功
PATTERN_NAMED = re.compile(
    r'进行\s*(?P<check_type>[^检]*?)检定?[：:]\s*'
    r'(?:D100|d100)\s*[=＝]\s*(?P<rolled>\d{1,3})\s*/\s*(?P<target>\d{1,3})'
    r'(?:\s*(?P<outcome>成功|失败|大成功|大失败|困难成功|极限成功|'
    r'Success|Failure|Hard[_\s]*Success|Extreme[_\s]*Success))?',
    re.IGNORECASE,
)


def _classify_outcome(rolled: int, target: int, outcome_text: str = "") -> str:
    """Classify dice outcome using COC rules.

    COC 7th edition success levels:
      - Critical success: rolled <= 1 (or <= 5 if target > 50)
      - Extreme success: rolled <= target / 5
      - Hard success: rolled <= target / 2
      - Normal success: rolled <= target
      - Failure: rolled > target
      - Fumble: rolled >= 96 (or 100 if target > 50)
    """
    ot = outcome_text.strip().lower() if outcome_text else ""

    # Text-based classification takes priority
    if "大成功" in ot or "critical" in ot:
        return "critical_success"
    if "大失败" in ot or "fumble" in ot:
        return "fumble"
    if "极限成功" in ot or "extreme" in ot:
        return "extreme_success"
    if "困难成功" in ot or "hard" in ot:
        return "hard_success"
    if "成功" in ot or "success" in ot:
        return "normal_success"
    if "失败" in ot or "failure" in ot:
        return "failure"

    # Numeric fallback when no text outcome
    if target <= 0:
        return "unknown"
    if rolled <= 1 or (rolled <= 5 and target > 50):
        return "critical_success"
    if rolled >= 96 and target < 50:
        return "fumble"
    if rolled >= 100:
        return "fumble"
    if rolled <= target // 5:
        return "extreme_success"
    if rolled <= target // 2:
        return "hard_success"
    if rolled <= target:
        return "normal_success"
    return "failure"


def parse_dice_message(text: str) -> Optional[DiceResult]:
    """Parse a single dice-robot message. Returns None if no dice pattern found.

    Args:
        text: Raw message text from group chat.

    Returns:
        DiceResult or None (not a dice message, or dice result unparseable).
    """
    text = text.strip()
    if not text:
        return None

    # ── Check for secret roll first ──────────────────────────
    if text in ("暗骰", "暗中观察", "???", "？？？") or "暗骰" in text:
        return DiceResult(is_secret=True)

    # ── Try each pattern ─────────────────────────────────────
    match = None

    # Pattern: named check (most informative)
    m = PATTERN_NAMED.search(text)
    if m:
        rolled = int(m.group("rolled"))
        target = int(m.group("target")) if m.group("target") else 0
        check_type = m.group("check_type").strip()
        outcome = _classify_outcome(rolled, target, (m.group("outcome") or ""))
        return DiceResult(
            check_type=check_type,
            target=target,
            rolled=rolled,
            outcome=outcome,
            raw_text=text,
        )

    # Pattern: 检定/Check format
    m = PATTERN_CHECK_RESULT.search(text)
    if m:
        rolled = int(m.group("rolled"))
        target = int(m.group("target"))
        check_type = m.group("check_type").strip()
        outcome = _classify_outcome(rolled, target, (m.group("outcome") or ""))
        return DiceResult(
            check_type=check_type,
            target=target,
            rolled=rolled,
            outcome=outcome,
            raw_text=text,
        )

    # Pattern: D100=result/target
    m = PATTERN_D100_RESULT.search(text)
    if m:
        rolled = int(m.group("rolled"))
        target = int(m.group("target"))
        outcome = _classify_outcome(rolled, target, (m.group("outcome") or ""))
        return DiceResult(
            check_type="",
            target=target,
            rolled=rolled,
            outcome=outcome,
            raw_text=text,
        )

    # Pattern: .ra format
    m = PATTERN_RA.search(text)
    if m:
        rolled = int(m.group("rolled"))
        target = int(m.group("target") or m.group("target2") or "0")
        check_type = m.group("check_type").strip()
        outcome = _classify_outcome(rolled, target, (m.group("outcome") or ""))
        return DiceResult(
            check_type=check_type,
            target=target,
            rolled=rolled,
            outcome=outcome,
            raw_text=text,
        )

    # Pattern: .st confrontation
    m = PATTERN_ST.search(text)
    if m:
        rolled = int(m.group("rolled"))
        target = int(m.group("target"))
        check_type = m.group("check_type").strip() + "对抗"
        outcome = _classify_outcome(rolled, target, (m.group("outcome") or ""))
        return DiceResult(
            check_type=check_type,
            target=target,
            rolled=rolled,
            outcome=outcome,
            raw_text=text,
        )

    # Pattern: bare .r with simple result
    m = PATTERN_DOT_R.search(text)
    if m and ("骰" in text or ".r" in text.lower()):
        rolled = int(m.group(1))
        # Can't determine target from bare .r — assume unknown
        return DiceResult(
            check_type="",
            target=0,
            rolled=rolled,
            outcome="unknown",
            raw_text=text,
        )

    return None


def is_dice_message(text: str) -> bool:
    """Quick check: is this likely a dice-robot message?"""
    text = text.strip()
    if ".r" in text.lower():
        return True
    if ".ra" in text.lower():
        return True
    if ".st" in text.lower():
        return True
    if "D100" in text and "/" in text:
        return True
    if "检定" in text and "/" in text:
        return True
    if "进行" in text and "检定" in text:
        return True
    if "对抗" in text:
        return True
    if text in ("暗骰", "暗中观察", "???", "？？？") or "暗骰" in text:
        return True
    return False
