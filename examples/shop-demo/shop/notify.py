def discount_message(code: str) -> str:
    if not code:
        raise ValueError("code is required")
    return f"Applied {code}"
