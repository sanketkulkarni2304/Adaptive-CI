def percent_discount(price: float, percent: float) -> float:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    rate = percent / 100
    return round(price * (1 - rate), 2)


def bulk_discount(price: float, quantity: int) -> float:
    rate = 0.10 if quantity >= 10 else 0.0
    return round(price * (1 - rate), 2)


def coupon_discount(price: float, code: str) -> float:
    amounts = {"SAVE5": 5.0, "SAVE10": 10.0}
    if code not in amounts:
        raise ValueError(f"unknown coupon: {code}")
    return round(max(0.0, price - amounts[code]), 2)


def price_floor(price: float, floor: float = 1.0) -> float:
    return round(max(price, floor), 2)


def stack_discounts(price: float, percent: float, quantity: int) -> float:
    return price_floor(bulk_discount(percent_discount(price, percent), quantity))
