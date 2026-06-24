def test_bar_creation():
    from strategy.core.bar import Bar
    bar = Bar(timestamp=1000000, open=100.0, high=105.0, low=95.0, close=102.0, volume=1000.0, symbol="BTCUSDT")
    assert bar.close == 102.0
    assert bar.symbol == "BTCUSDT"

def test_order_creation():
    from strategy.core.order import Order, OrderSide
    order = Order(symbol="BTCUSDT", side=OrderSide.BUY, quantity=0.1, price=50000.0)
    assert order.side == OrderSide.BUY
    assert order.quantity == 0.1
