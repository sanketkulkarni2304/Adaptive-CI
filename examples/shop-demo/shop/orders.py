def place_order(sku: str, total: float) -> dict:
    if not sku or total < 0:
        raise ValueError("sku and total are required")
    return {"sku": sku, "total": round(total, 2)}
