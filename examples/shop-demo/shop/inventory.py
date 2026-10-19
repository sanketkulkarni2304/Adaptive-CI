def reserve(stock: int, quantity: int) -> int:
    if quantity < 1:
        raise ValueError("quantity must be positive")
    if quantity > stock:
        raise ValueError("not enough stock")
    return stock - quantity
