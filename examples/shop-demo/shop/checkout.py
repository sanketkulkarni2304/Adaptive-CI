from .inventory import reserve
from .pricing import bulk_discount, percent_discount


def checkout(price: float, percent: float, quantity: int, stock: int) -> float:
    reserve(stock, quantity)
    return bulk_discount(percent_discount(price, percent), quantity)


def hold(stock: int, quantity: int) -> int:
    return reserve(stock, quantity)
