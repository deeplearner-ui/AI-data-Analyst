from __future__ import annotations

import ipaddress
import math
import re
from datetime import datetime
from typing import Any

import pandas as pd


MAX_VALUES_PER_COLUMN = 10_000

_COLUMN_HINTS: dict[str, tuple[str, str]] = {
    "email": (r"(^|[^a-z])(e[-_ ]?mail|email address|邮箱|电子邮件)([^a-z]|$)", "high"),
    "phone": (r"(^|[^a-z])(phone|mobile|cell|telephone|tel|手机号|手机号码|联系电话|电话)([^a-z]|$)", "high"),
    "cn-id": (r"(^|[^a-z])(id card|identity card|national id|身份证|身份证号|公民身份)([^a-z]|$)", "high"),
    "bank-card": (r"(^|[^a-z])(bank card|card number|银行卡|银行卡号|信用卡)([^a-z]|$)", "high"),
    "passport": (r"(^|[^a-z])(passport|护照|护照号)([^a-z]|$)", "high"),
    "name": (r"(^|[^a-z])(full name|first name|last name|surname|customer name|姓名|名字|客户名称)([^a-z]|$)", "medium"),
    "address": (r"(^|[^a-z])(home address|street address|postal address|住址|家庭地址|详细地址|通讯地址)([^a-z]|$)", "medium"),
    "date-of-birth": (r"(^|[^a-z])(date of birth|birth date|birthday|dob|出生日期|生日)([^a-z]|$)", "medium"),
    "account": (r"(^|[^a-z])(user name|username|account id|login id|用户账号|登录账号)([^a-z]|$)", "medium"),
    "ip-address": (r"(^|[^a-z])(ip address|client ip|ip地址)([^a-z]|$)", "medium"),
}

_EMAIL = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}$", re.IGNORECASE)
_INLINE_EMAIL = re.compile(r"(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}(?![A-Z0-9._%+-])", re.IGNORECASE)
_PHONE = re.compile(r"^(?:\+?86)?1[3-9]\d{9}$")
_CN_ID = re.compile(r"^\d{17}[0-9Xx]$")
_DIGITS = re.compile(r"\D+")
_WINDOWS_PATH = re.compile(r"(?i)(?:file:///)?[A-Z]:\\[^\r\n\t\"'<>|]+")
_USER_HOME = re.compile(r"(?i)(?:/Users|/home)/[^/\s]+")
_BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[-_ ]?key|password|passwd|access[-_ ]?token|authorization|secret)(\s*[:=]\s*)([^\s,;]+)"
)


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _valid_cn_id(value: str) -> bool:
    if not _CN_ID.fullmatch(value):
        return False
    try:
        datetime.strptime(value[6:14], "%Y%m%d")
    except ValueError:
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checks = "10X98765432"
    return checks[sum(int(digit) * weight for digit, weight in zip(value[:17], weights)) % 11] == value[-1].upper()


def _valid_bank_card(value: str) -> bool:
    digits = _DIGITS.sub("", value)
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        number = int(character)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        checksum += number
    return checksum % 10 == 0


def _value_categories(value: Any) -> set[str]:
    text = _text(value)
    compact = re.sub(r"[\s()-]+", "", text)
    categories: set[str] = set()
    if _EMAIL.fullmatch(text):
        categories.add("email")
    if _PHONE.fullmatch(compact):
        categories.add("phone")
    if _valid_cn_id(compact):
        categories.add("cn-id")
    elif _valid_bank_card(text):
        categories.add("bank-card")
    try:
        if ipaddress.ip_address(text).version in {4, 6}:
            categories.add("ip-address")
    except ValueError:
        pass
    return categories


def privacy_scan(frame: pd.DataFrame) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned_rows = min(len(frame), MAX_VALUES_PER_COLUMN)
    for raw_column in frame.columns:
        column = str(raw_column)
        detected: dict[str, dict[str, Any]] = {}
        normalized = re.sub(r"[_\-.]+", " ", column).strip().lower()
        for category, (pattern, confidence) in _COLUMN_HINTS.items():
            if re.search(pattern, normalized, re.IGNORECASE):
                detected[category] = {
                    "category": category,
                    "confidence": confidence,
                    "matchCount": 0,
                    "reasons": ["column-name"],
                }
        values = frame[raw_column].dropna().head(MAX_VALUES_PER_COLUMN)
        for value in values:
            for category in _value_categories(value):
                finding = detected.setdefault(category, {
                    "category": category,
                    "confidence": "high",
                    "matchCount": 0,
                    "reasons": [],
                })
                finding["confidence"] = "high"
                finding["matchCount"] += 1
                if "value-pattern" not in finding["reasons"]:
                    finding["reasons"].append("value-pattern")
        for finding in detected.values():
            findings.append({"column": column, **finding})
    findings.sort(key=lambda item: (item["confidence"] != "high", item["column"], item["category"]))
    high = sum(1 for finding in findings if finding["confidence"] == "high")
    return {
        "status": "sensitive" if high else "warning" if findings else "clear",
        "hasPersonalData": bool(findings),
        "scannedRows": scanned_rows,
        "totalRows": len(frame),
        "findings": findings,
        "summary": {"highConfidence": high, "mediumConfidence": len(findings) - high},
    }


def sanitize_diagnostic(value: Any) -> str:
    text = str(value)
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = _WINDOWS_PATH.sub("<local-path>", text)
    text = _USER_HOME.sub("<user-home>", text)
    text = _INLINE_EMAIL.sub("<email>", text)
    text = re.sub(r"(?<!\d)(?:\+?86)?1[3-9]\d{9}(?!\d)", "<phone>", text)
    text = re.sub(r"(?<!\d)\d{17}[0-9Xx](?!\d)", "<identity-number>", text)
    return text[:4000]
