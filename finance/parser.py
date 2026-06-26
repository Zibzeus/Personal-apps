import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


AMOUNT_RE = re.compile(r"(?i)(?:rp\s*)?(\d+(?:[.,]\d+)?(?:[.,]\d{3})*|\d+)(rb|ribu|k|jt|juta|m)?")
SCIENTIFIC_RE = re.compile(r"(?i)\d+\s*e\s*[+-]?\d+")

CATEGORY_HINTS = {
    "makan": "Makan",
    "food": "Makan",
    "kopi": "Makan",
    "snack": "Makan",
    "groceries": "Groceries",
    "belanja bulanan": "Groceries",
    "transport": "Transport",
    "gojek": "Transport",
    "grab": "Transport",
    "bensin": "Transport",
    "shopping": "Shopping",
    "belanja": "Shopping",
    "hiburan": "Entertainment",
    "netflix": "Subscription",
    "spotify": "Subscription",
    "subscription": "Subscription",
    "langganan": "Subscription",
    "listrik": "Bills",
    "internet": "Bills",
    "air": "Bills",
    "sewa": "Rent",
    "kontrakan": "Rent",
    "gaji": "Salary",
    "salary": "Salary",
    "bonus": "Bonus",
}

INCOME_WORDS = {"gaji", "salary", "bonus", "income", "pemasukan", "masuk", "dibayar"}
TRANSFER_WORDS = {"tf", "transfer", "pindah", "kirim"}
PAYABLE_WORDS = {"utang", "hutang"}
RECEIVABLE_WORDS = {"piutang"}


@dataclass
class ParsedEntry:
    action: str
    amount: Decimal | None
    account_hint: str = ""
    to_account_hint: str = ""
    category_hint: str = ""
    counterparty: str = ""
    note: str = ""
    raw_text: str = ""
    confidence: float = 0.5


def normalize_amount(token: str, suffix: str | None = None) -> Decimal | None:
    cleaned = token.lower().replace("rp", "").replace(" ", "")
    suffix = (suffix or "").lower()
    if "." in cleaned and "," not in cleaned:
        parts = cleaned.split(".")
        if all(len(part) == 3 for part in parts[1:]):
            cleaned = "".join(parts)
    if "," in cleaned and "." not in cleaned:
        parts = cleaned.split(",")
        if all(len(part) == 3 for part in parts[1:]):
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(",", ".")
    cleaned = cleaned.replace(",", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if suffix in {"rb", "ribu", "k"}:
        amount *= Decimal("1000")
    if suffix in {"jt", "juta", "m"}:
        amount *= Decimal("1000000")
    return amount.quantize(Decimal("0.01"))


def extract_amount(text: str) -> tuple[Decimal | None, str]:
    best_match = None
    best_amount = None
    for match in AMOUNT_RE.finditer(text):
        amount = normalize_amount(match.group(1), match.group(2))
        if amount and amount > 0:
            best_match = match
            best_amount = amount
            break
    if not best_match:
        return None, text
    remaining = (text[: best_match.start()] + text[best_match.end() :]).strip()
    remaining = re.sub(r"\s+", " ", remaining)
    return best_amount, remaining


def detect_category(text: str, action: str) -> str:
    lowered = text.lower()
    for keyword, category in CATEGORY_HINTS.items():
        if keyword in lowered:
            return category
    if action == "income":
        return "Other Income"
    if action == "expense":
        return "Uncategorized"
    return ""


def parse_message(text: str) -> ParsedEntry:
    raw = text.strip()
    lowered = raw.lower()
    if SCIENTIFIC_RE.search(lowered):
        return ParsedEntry(
            action="expense",
            amount=None,
            note=raw,
            raw_text=raw,
            confidence=0.1,
        )
    amount, without_amount = extract_amount(lowered)
    tokens = without_amount.split()
    first = tokens[0] if tokens else ""

    if first in TRANSFER_WORDS or lowered.startswith("tf "):
        accounts = [token for token in tokens[1:] if token not in TRANSFER_WORDS]
        return ParsedEntry(
            action="transfer",
            amount=amount,
            account_hint=accounts[0] if len(accounts) >= 1 else "",
            to_account_hint=accounts[1] if len(accounts) >= 2 else "",
            note=raw,
            raw_text=raw,
            confidence=0.85 if amount and len(accounts) >= 2 else 0.45,
        )

    if first in PAYABLE_WORDS:
        counterparty = ""
        if "ke" in tokens:
            idx = tokens.index("ke")
            counterparty = tokens[idx + 1] if idx + 1 < len(tokens) else ""
        elif len(tokens) > 1:
            counterparty = tokens[1]
        return ParsedEntry(
            action="debt_payable",
            amount=amount,
            counterparty=counterparty,
            note=raw,
            raw_text=raw,
            confidence=0.8 if amount and counterparty else 0.45,
        )

    if first in RECEIVABLE_WORDS:
        counterparty = tokens[1] if len(tokens) > 1 else ""
        return ParsedEntry(
            action="debt_receivable",
            amount=amount,
            counterparty=counterparty,
            note=raw,
            raw_text=raw,
            confidence=0.8 if amount and counterparty else 0.45,
        )

    action = "income" if any(word in lowered.split() for word in INCOME_WORDS) else "expense"
    account_hint = tokens[-1] if len(tokens) >= 2 else ""
    category_hint = detect_category(without_amount, action)
    return ParsedEntry(
        action=action,
        amount=amount,
        account_hint=account_hint,
        category_hint=category_hint,
        note=raw,
        raw_text=raw,
        confidence=0.85 if amount else 0.35,
    )
