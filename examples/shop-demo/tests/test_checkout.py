from shop.checkout import checkout
from shop.notify import discount_message
from shop.orders import place_order
from shop.tax import tax_on

from pace import pace


def test_checkout_percent():
    pace("test_checkout_percent")
    assert checkout(100, 10, 1, 5) == 90


def test_checkout_bulk():
    pace("test_checkout_bulk")
    assert checkout(100, 0, 10, 12) == 90


def test_order_discounted_total():
    pace("test_order_discounted_total")
    assert place_order("BOOK", 18) == {"sku": "BOOK", "total": 18}


def test_tax_after_discount():
    pace("test_tax_after_discount")
    assert tax_on(90) == 9


def test_notify_on_discount():
    pace("test_notify_on_discount")
    assert discount_message("SAVE10") == "Applied SAVE10"
