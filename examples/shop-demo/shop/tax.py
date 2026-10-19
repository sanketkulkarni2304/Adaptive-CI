def tax_on(amount: float, rate: float = 0.1) -> float:
    if amount < 0 or rate < 0:
        raise ValueError("amount and rate must be non-negative")
    return round(amount * rate, 2)
