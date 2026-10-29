"""Simple, deterministic comparison algorithms for aggregator results.

Never modify the scraper's Method dictionaries: the flight JSON format stays
identical to the user's approved schema and its Priority=1 means AIR mode.
"""


def as_number(value):
    """Accept numeric fare/duration values but skip unknown data safely."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    return None


def sort_by_price(routes):
    """Sort available options by total quoted cost, regardless of transport mode."""
    return sorted(routes, key=lambda row: (
        as_number(row["Method"].get("Cost")) is None,
        as_number(row["Method"].get("Cost")) if as_number(row["Method"].get("Cost")) is not None else float("inf")
    ))


def recommend_routes(routes):
    """Compare valid priced/timed routes by cheapest, fastest, and balanced.

    The balanced score weighs normalized cost and duration equally. It is an
    example comparison algorithm, not the team's unprovided custom algorithm.
    """
    eligible = []
    for route in routes:
        data = route["Method"]
        price = as_number(data.get("Cost"))
        minutes = as_number(data.get("Travel Time (min)"))
        if price is not None and minutes is not None:
            eligible.append((route, price, minutes))
    if not eligible:
        return {}

    prices = [x[1] for x in eligible]
    times = [x[2] for x in eligible]
    low_cost, high_cost = min(prices), max(prices)
    low_time, high_time = min(times), max(times)

    def balanced_score(item):
        _, price, minutes = item
        c = (price - low_cost) / (high_cost - low_cost) if high_cost > low_cost else 0
        t = (minutes - low_time) / (high_time - low_time) if high_time > low_time else 0
        return (c + t) / 2

    return {
        "cheapest": min(eligible, key=lambda x: (x[1], x[2]))[0],
        "fastest": min(eligible, key=lambda x: (x[2], x[1]))[0],
        "balanced": min(eligible, key=lambda x: (balanced_score(x), x[1]))[0],
    }
