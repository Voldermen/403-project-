"""
demo_transit.py

Asks for a starting address and a destination address, finds the closest transit stop
to each (Transitland), plans the route between them (Transit API), and prints
everything in the Example.json format.

Requirements (all in the same folder):
    transit_route.py
    address_coords.py    (your geocoding program)
    api_keys.txt         containing:
                             transit = YOUR_TRANSIT_API_KEY
                             transitland = YOUR_TRANSITLAND_KEY

Run:
    python demo_transit.py
"""

import json

from transit_route import TransitAPIError, get_transit_route

SEARCH_RADIUS_M = 5000   # how far to look for a stop (Transitland allows up to 10,000)


def ask(prompt):
    """Keep asking until the user types something."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("  Please enter a value.")


def ask_address(label):
    print(f"\n{label}")
    return {
        "street": ask("  Street: "),
        "city": ask("  City: "),
        "state": ask("  State: "),
    }


def main():
    origin = ask_address("Starting address")
    destination = ask_address("Destination address")

    print("\nSearching...")
    try:
        # About 3 API calls: 2 for the stops (Transitland) + 1 for the route (Transit)
        options = get_transit_route(origin, destination, radius=SEARCH_RADIUS_M, max_options=1)
    except ValueError as exc:
        print(f"Bad input or address not found: {exc}")
        return
    except TransitAPIError as exc:
        print(f"API problem: {exc}")
        return

    if not options:
        print(
            "No route found. Either no stop was within "
            f"{SEARCH_RADIUS_M} m of the start/destination, or no transit route connects the two stops."
        )
        return

    print()
    print(json.dumps(options, indent=2))

    # Save to a file if you want to hand it to another program
    with open("transit_options.json", "w", encoding="utf-8") as f:
        json.dump(options, f, indent=2)
    print("\nSaved to transit_options.json")


if __name__ == "__main__":
    main()
