"""
Text formatting helpers for Telegram messages
"""
import re


def escape_markdown(text: str) -> str:
    """Escape MarkdownV2 special characters"""
    special_chars = r"\_*[]()~`>#+-=|{}.!"
    for ch in special_chars:
        text = text.replace(ch, f"\\{ch}")
    return text


def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """Truncate text to max length"""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def format_concept_type(concept_type: str) -> str:
    """Return emoji + label for concept type"""
    mapping = {
        "ALGORITHM": "⚙️ Algorithm",
        "THEORY": "📚 Theory",
        "METHOD": "🔧 Method",
        "DATASET": "🗄️ Dataset",
        "VARIABLE": "📏 Variable",
        "ENTITY": "🔵 Entity",
        "INSTITUTION": "🏛️ Institution",
        "AUTHOR": "👤 Author",
        "DOMAIN": "🌐 Domain",
        "METRIC": "📊 Metric",
    }
    return mapping.get(concept_type.upper() if concept_type else "", f"● {concept_type}")


def split_long_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a long message into parts that fit Telegram's limit"""
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        # Try to split at newline
        split_idx = text.rfind("\n", 0, max_len)
        if split_idx == -1:
            split_idx = max_len
        parts.append(text[:split_idx])
        text = text[split_idx:].lstrip("\n")
    return parts


def relationship_arrow(source: str, relation: str, target: str) -> str:
    """Format a relationship as a readable arrow"""
    rel_label = relation.replace("_", " ").lower()
    return f"`{source}` ──[{rel_label}]──▶ `{target}`"
