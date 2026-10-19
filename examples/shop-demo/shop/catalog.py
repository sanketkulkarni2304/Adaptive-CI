_PRODUCTS = {"PEN": 2.5, "BOOK": 12.0, "LAMP": 24.0}


def lookup(sku: str) -> float:
    try:
        return _PRODUCTS[sku]
    except KeyError as error:
        raise KeyError(sku) from error
