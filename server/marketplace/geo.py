"""
Coarse geography for distance filters, without PostGIS.

Coordinates are snapped to a ~1 km grid before they're stored, so a seller's
exact position is never kept, and other users only ever see them rounded to
~11 km. Distances are great-circle (haversine) and computed in SQL with
Django's math functions, which SQLite and Postgres both provide.
"""
import math
import re
from django.db.models import F, FloatField, Value
from django.db.models.functions import ASin, Cos, Least, Power, Radians, Sin, Sqrt

EARTH_RADIUS_KM = 6371.0
STORE_PLACES = 2                 # ~1.1 km: the precision kept in the database
PUBLIC_PLACES = 1                # ~11 km: the precision other users see
MAX_RADIUS_KM = 500

# Centroids of South African cities and large towns (lat, lng), used when a
# seller types a location but doesn't share their position.
CITY_CENTROIDS = {
    'Johannesburg': (-26.2041, 28.0473),
    'Cape Town': (-33.9249, 18.4241),
    'Durban': (-29.8587, 31.0218),
    'Pretoria': (-25.7479, 28.2293),
    'Gqeberha': (-33.9608, 25.6022),
    'Bloemfontein': (-29.0852, 26.1596),
    'East London': (-33.0153, 27.9116),
    'Polokwane': (-23.9045, 29.4689),
    'Mbombela': (-25.4753, 30.9694),
    'Kimberley': (-28.7282, 24.7499),
    'Pietermaritzburg': (-29.6006, 30.3794),
    'Rustenburg': (-25.6676, 27.2421),
    'George': (-33.9630, 22.4617),
    'Stellenbosch': (-33.9321, 18.8602),
    'Soweto': (-26.2485, 27.8540),
    'Sandton': (-26.1076, 28.0567),
    'Centurion': (-25.8603, 28.1894),
    'Midrand': (-25.9992, 28.1263),
    'Benoni': (-26.1885, 28.3208),
    'Vereeniging': (-26.6731, 27.9261),
    'Welkom': (-27.9774, 26.7351),
    'Upington': (-28.4478, 21.2561),
    'Mahikeng': (-25.8560, 25.6403),
    'Makhanda': (-33.3042, 26.5328),
    'Paarl': (-33.7342, 18.9621),
    'Richards Bay': (-28.7807, 32.0383),
    'Potchefstroom': (-26.7145, 27.0970),
    'Knysna': (-34.0363, 23.0471),
}
# Older or alternative names people still type.
_ALIASES = {'port elizabeth': 'Gqeberha', 'nelspruit': 'Mbombela', 'grahamstown': 'Makhanda',
            'joburg': 'Johannesburg', 'jozi': 'Johannesburg', 'jhb': 'Johannesburg', 'cpt': 'Cape Town',
            'pta': 'Pretoria', 'tshwane': 'Pretoria', 'pe': 'Gqeberha', 'bloem': 'Bloemfontein'}
_LOOKUP = {**{k.lower(): k for k in CITY_CENTROIDS}, **_ALIASES}


def city_for(location):
    """The known city named in a free-text location ("Sea Point, Cape Town" -> "Cape Town"), or None."""
    text = (location or '').lower()
    if not text:
        return None
    parts = [p.strip() for p in re.split(r'[,/;\-]', text) if p.strip()]
    for part in [text, *reversed(parts)]:
        if part in _LOOKUP:
            return _LOOKUP[part]
    # Longest names first so "East London" wins over a bare "London".
    for key in sorted(_LOOKUP, key=len, reverse=True):
        if len(key) > 3 and re.search(rf'\b{re.escape(key)}\b', text):
            return _LOOKUP[key]
    return None


def centroid_for(location):
    city = city_for(location)
    return CITY_CENTROIDS[city] if city else None


def snap(value):
    """Round a coordinate to the stored precision."""
    return round(float(value), STORE_PLACES)


def public(value):
    return None if value is None else round(float(value), PUBLIC_PLACES)


def valid_point(lat, lng):
    return lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180


def bounding_box(lat, lng, radius_km):
    """A cheap index-friendly prefilter around the point before the exact distance."""
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    dlng = math.degrees(radius_km / (EARTH_RADIUS_KM * max(math.cos(math.radians(lat)), 0.01)))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def distance_expression(lat, lng):
    """Haversine distance in km from (lat, lng) to each row's latitude/longitude."""
    lat1, lng1 = Radians(Value(lat, FloatField())), Radians(Value(lng, FloatField()))
    lat2, lng2 = Radians(F('latitude')), Radians(F('longitude'))
    a = (Power(Sin((lat2 - lat1) / 2), 2)
         + Cos(lat1) * Cos(lat2) * Power(Sin((lng2 - lng1) / 2), 2))
    return Value(2 * EARTH_RADIUS_KM, FloatField()) * ASin(Least(Sqrt(a), Value(1.0, FloatField())))


def haversine_km(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
