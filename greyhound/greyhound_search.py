"""Greyhound trip retrieval and conversion. Python 3.12, no extra packages.

Run saved data: python greyhound_search.py --input sample_response.json
Run live search: python greyhound_search.py --date 2026-10-23
Defaults: Dallas to Houston, one adult, USD, Greyhound-branded bus legs only.
Use --from-city and --to-city with the UUIDs from the site's search URL.

This is an undocumented website endpoint, not a guaranteed public API.
GPS is absent in this response: output nulls are intentional. The team's
Algorithm/least_cost_path.py requires numeric station GPS before integration.
Optional --stations supplies {station_uuid: {"LAT": number, "LONG": number}}.
Cost includes the platform fee when provided. Priority is deliberately omitted:
the team loader defaults it to 99; Scope describes intercity travel, not price rank.
"""
import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ENDPOINT = 'https://global.api.flixbus.com/search/service/v4/search'
DALLAS = '54f13a66-59ee-41d4-b017-e4240add0403'
HOUSTON = '364040d5-ebfc-4628-b7b0-13e2377203c6'


def fetch_response(origin, destination, travel_date):
    """One network request. Never silently substitute saved data on failure."""
    if origin == destination:
        raise ValueError('Choose different origin and destination cities.')
    params = dict(from_city_id=origin, to_city_id=destination,
                  departure_date=travel_date.strftime('%d.%m.%Y'),
                  products=json.dumps({'adult': 1}), currency='USD', locale='en_US',
                  search_by='cities', include_after_midnight_rides='0',
                  disable_distribusion_trips='0', disable_global_trips='0',
                  disable_trips=json.dumps(['AU']))
    request = Request(ENDPOINT + '?' + urlencode(params),
                      headers={'Accept': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def location(endpoint, data, coordinates):
    station_id = endpoint['station_id']
    city = data['cities'][endpoint['city_id']]['name']
    city_name, separator, state = city.rpartition(', ')
    gps = coordinates.get(station_id, {'LAT': None, 'LONG': None})
    for key, bound in [('LAT', 90), ('LONG', 180)]:
        value = gps.get(key)
        if value is not None and (type(value) not in (int, float)
                or not math.isfinite(value) or abs(value) > bound):
            raise ValueError(f'Invalid {key} for station {station_id}')
    return {'City': city_name if separator else city,
            'State': state if separator else '',
            'Name': data['stations'][station_id]['name'],
            'Station ID': station_id,
            'GPS': {'LAT': gps.get('LAT'), 'LONG': gps.get('LONG')}}


def convert_response(data, coordinates=None):
    """Keep available itineraries whose every leg is a Greyhound-branded bus.

    Retain complete timestamps as extra fields so overnight/time-zone data is
    not lost, while 24-hour Departure/Arrival match the existing loader.
    """
    if not isinstance(data, dict) or not isinstance(data.get('trips'), list):
        raise ValueError('Expected a search response containing a trips list.')
    coordinates = coordinates or {}
    brands = data.get('brands', {})
    records = []
    seen = set()
    for group in data['trips']:
        results = group.get('results', {})
        if not isinstance(results, dict):
            raise ValueError('Unexpected results format; expected an object.')
        for uid, trip in results.items():
            legs = trip.get('legs', [])
            if trip.get('status') != 'available' or not legs or uid in seen:
                continue
            if not all(leg.get('means_of_transport') == 'bus' and
                       brands.get(leg.get('brand_id'), {}).get('name', '').casefold()
                       == 'greyhound' for leg in legs):
                continue
            start = datetime.fromisoformat(trip['departure']['date'])
            end = datetime.fromisoformat(trip['arrival']['date'])
            if start.utcoffset() is None or end.utcoffset() is None:
                raise ValueError('Trip timestamps must include UTC offsets.')
            minutes = (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() / 60
            if minutes < 0:
                raise ValueError('Arrival precedes departure.')
            price = trip['price']
            cost = price.get('total_with_platform_fee')
            basis = 'total_with_platform_fee'
            if cost is None:
                if data.get('platform_fee_in_price_required'):
                    raise ValueError('Required platform-fee-inclusive price missing.')
                cost, basis = price['total'], 'total'
            cost = float(cost)
            if not math.isfinite(cost) or cost < 0:
                raise ValueError('Invalid price.')
            records.append({'method': {
                'info': {'Type': 'Bus', 'Name': 'Greyhound', 'Scope': 'Interstate',
                         'Cost': cost, 'Currency': 'USD', 'Price Basis': basis,
                         'Travel Time (min)': round(minutes),
                         'Departure': start.strftime('%H:%M'),
                         'Arrival': end.strftime('%H:%M'),
                         'Date': start.strftime('%m/%d/%Y'),
                         'Departure Timestamp': start.isoformat(),
                         'Arrival Timestamp': end.isoformat(),
                         'Transfers': len(legs) - 1, 'Trip ID': uid},
                'starting_location': location(trip['departure'], data, coordinates),
                'destination': location(trip['arrival'], data, coordinates)}})
            seen.add(uid)
    return sorted(records, key=lambda row: row['method']['info']['Departure Timestamp'])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', type=Path, help='Convert a saved USD, one-adult response instead of fetching live.')
    parser.add_argument('--date', type=date.fromisoformat, help='Live search date YYYY-MM-DD')
    parser.add_argument('--from-city', default=DALLAS)
    parser.add_argument('--to-city', default=HOUSTON)
    parser.add_argument('--stations', type=Path, help='Optional verified station-coordinate mapping')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('greyhound_trips.json'))
    args = parser.parse_args()
    if not args.input and not args.date:
        parser.error('Supply --input sample_response.json OR --date YYYY-MM-DD.')
    if args.input and args.date:
        parser.error('Choose either saved input or live date, not both.')
    try:
        if args.input:
            data = json.loads(args.input.read_text(encoding='utf-8-sig'))
        else:
            if args.date < date.today():
                raise ValueError('Live searches require today or a future date.')
            data = fetch_response(args.from_city, args.to_city, args.date)
        coordinates = json.loads(args.stations.read_text(encoding='utf-8-sig')) if args.stations else {}
        records = convert_response(data, coordinates)
        args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f"Saved {len(records)} Greyhound trip(s) from {'SAVED RESPONSE' if args.input else 'LIVE SEARCH'} to {args.output.resolve()}")
        missing = sum(any(row['method'][side]['GPS'][key] is None for side in
                          ('starting_location', 'destination') for key in ('LAT', 'LONG')) for row in records)
        if missing:
            print(f'NOT READY FOR ROUTE ALGORITHM: {missing} trip(s) need verified station GPS coordinates.')
        if records:
            info = records[0]['method']['info']
            print(f"First trip: {info['Departure']} -> {info['Arrival']}, {info['Travel Time (min)']} min, USD {info['Cost']:.2f}")
    except (OSError, ValueError, KeyError, TypeError, HTTPError, URLError) as exc:
        print(f'Could not produce trip output: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
