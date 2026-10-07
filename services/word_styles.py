"""Per-operation style preflight; no preferences or Word content are changed."""


def fallback_styles(word, required, confirm, error_type):
    """Return missing names approved for Normal, preserving strict headless use."""
    missing = word.missing_styles([name for _label, name in required])
    if not missing:
        return set()
    if confirm is None:
        raise error_type('当前 Word 文档缺少样式：' + '、'.join(missing))
    details = [(label, name) for label, name in required if name in missing]
    if not confirm(details):
        raise error_type('已取消本次 Word 输出，未写入任何内容。')
    # Resolve the language-independent built-in before the first mutation.
    word.normal_style()
    return set(missing)
