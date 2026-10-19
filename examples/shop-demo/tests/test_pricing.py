from shop.pricing import (
    bulk_discount,
    coupon_discount,
    percent_discount,
    price_floor,
    stack_discounts,
)

from pace import pace


def test_percent_discount():
    pace("test_percent_discount")
    assert percent_discount(100, 10) == 90


def test_stack_discounts():
    pace("test_stack_discounts")
    assert stack_discounts(100, 10, 1) == 90


def test_coupon_discount():
    pace("test_coupon_discount")
    assert coupon_discount(20, "SAVE10") == 10


def test_bulk_discount():
    pace("test_bulk_discount")
    assert bulk_discount(100, 10) == 90


def test_zero_percent():
    pace("test_zero_percent")
    assert percent_discount(100, 0) == 100


def test_price_floor():
    pace("test_price_floor")
    assert price_floor(0.2) == 1


def test_rounding():
    pace("test_rounding")
    assert bulk_discount(10, 10) == 9


def test_full_price():
    pace("test_full_price")
    assert price_floor(80) == 80


def test_pricing_audit():
    pace("test_pricing_audit")
    assert percent_discount(50, 0) == 50
    assert coupon_discount(8, "SAVE5") == 3
