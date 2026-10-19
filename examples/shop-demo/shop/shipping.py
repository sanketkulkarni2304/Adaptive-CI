def cost(weight: float, express: bool = False) -> float:
    if weight <= 0:
        raise ValueError("weight must be positive")
    base = 5.0 + weight
    return round(base * (2.0 if express else 1.0), 2)
