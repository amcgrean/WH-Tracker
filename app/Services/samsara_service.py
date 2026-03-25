import os
import requests
import time
from datetime import datetime


class SamsaraService:
    """
    Integration service for Samsara Fleet Management API.
    Provides vehicle location tracking, driver info, and delivery status.

    Requires SAMSARA_API_TOKEN environment variable to be set.
    API Docs: https://developers.samsara.com/reference
    """

    BASE_URL = 'https://api.samsara.com'

    def __init__(self):
        self.api_token = os.environ.get('SAMSARA_API_TOKEN', '')
        self.headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        self._dispatch_cache = {'ts': 0.0, 'data': None}

    def _get(self, endpoint, params=None):
        """Generic GET request to Samsara API."""
        if not self.api_token:
            print("SamsaraService: No API token configured. Falling back to MOCK data.")
            return None
        try:
            url = f"{self.BASE_URL}{endpoint}"
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code != 200:
                print(f"Samsara API HTTP Error: {resp.status_code} - {resp.text}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"Samsara API Exception for {endpoint}: {exc}")
            return None

    def _dispatch_branch_aliases(self):
        raw = (os.environ.get('SAMSARA_BRANCH_TAGS_JSON') or '').strip()
        if not raw:
            return {}
        try:
            import json

            data = json.loads(raw)
            return {
                str(code).upper(): [str(value).lower() for value in values]
                for code, values in data.items()
                if isinstance(values, list)
            }
        except Exception:
            return {}

    def _dispatch_branch_codes(self):
        aliases = self._dispatch_branch_aliases()
        if aliases:
            return list(aliases.keys())
        return ['10FD', '20GR', '25BW', '40CV', 'GRIMES']

    def _dispatch_vehicle_map(self):
        raw = (os.environ.get('SAMSARA_VEHICLE_BRANCH_MAP') or '').strip()
        if not raw:
            return {}
        try:
            import json

            data = json.loads(raw)
            return {str(key).upper(): str(value).upper() for key, value in data.items() if value}
        except Exception:
            return {}

    def _dispatch_ttl(self):
        try:
            return int(os.environ.get('SAMSARA_CACHE_TTL') or '15')
        except ValueError:
            return 15

    def _dispatch_fetch_locations(self, limit=200):
        if not self.api_token:
            raise ValueError("SAMSARA_API_TOKEN is not configured")
        ttl = max(5, self._dispatch_ttl())
        now = time.time()
        if self._dispatch_cache['data'] is not None and now - self._dispatch_cache['ts'] < ttl:
            return self._dispatch_cache['data']
        url = 'https://api.samsara.com/fleet/vehicles/locations'
        resp = requests.get(url, headers=self.headers, params={'limit': limit}, timeout=12)
        resp.raise_for_status()
        payload = resp.json()
        self._dispatch_cache = {'ts': now, 'data': payload}
        return payload

    def _dispatch_fetch_vehicle_meta(self, ids):
        if not ids or not self.api_token:
            return {}
        output = {}
        try:
            batch_size = 50
            for i in range(0, len(ids), batch_size):
                chunk = ids[i:i + batch_size]
                resp = requests.get(
                    'https://api.samsara.com/fleet/vehicles',
                    headers=self.headers,
                    params={'ids': ','.join(chunk)},
                    timeout=12,
                )
                if resp.status_code >= 400:
                    return output
                data = resp.json().get('data') or resp.json().get('vehicles') or []
                for vehicle in data:
                    vehicle_id = str(vehicle.get('id') or vehicle.get('vehicleId') or '')
                    if vehicle_id:
                        output[vehicle_id] = vehicle
        except Exception:
            return output
        return output

    def _infer_dispatch_branch(self, name, vehicle_id, meta):
        codes = {code.upper() for code in self._dispatch_branch_codes()}
        aliases = self._dispatch_branch_aliases()
        vehicle_map = self._dispatch_vehicle_map()

        upper_id = (vehicle_id or '').upper()
        upper_name = (name or '').upper()
        lower_name = upper_name.lower()

        if upper_id in vehicle_map:
            return vehicle_map[upper_id]
        if upper_name in vehicle_map:
            return vehicle_map[upper_name]

        for code in codes:
            if code in upper_name:
                return code

        for code, needles in aliases.items():
            if any(needle and needle in lower_name for needle in needles):
                return code

        tags = meta.get('tags')
        if isinstance(tags, list):
            for tag in tags:
                tag_name = (tag.get('name') or '').upper()
                if tag_name in codes:
                    return tag_name
            tag_blob = ' '.join((tag.get('name') or '') for tag in tags).lower()
            for code, needles in aliases.items():
                if any(needle and needle in tag_blob for needle in needles):
                    return code

        return None

    def get_dispatch_vehicle_payload(self, branch=None, limit=None):
        if not self.api_token:
            return {
                'vehicles': [],
                'count': 0,
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'warning': 'SAMSARA_API_TOKEN is not configured',
            }

        try:
            raw = self._dispatch_fetch_locations(limit=limit or 200)
            rows = raw.get('data') or raw.get('vehicles') or raw.get('items') or raw or []
            if isinstance(rows, dict):
                rows = rows.get('data') or []

            ids = list({str(row.get('id') or '') for row in rows if row.get('id')})
            meta_map = self._dispatch_fetch_vehicle_meta(ids)

            vehicles = []
            for row in rows:
                loc = row.get('location') or {}
                lat = loc.get('latitude')
                lon = loc.get('longitude')
                if lat is None or lon is None:
                    continue

                vehicle_id = str(row.get('id') or '')
                meta = meta_map.get(vehicle_id, {})
                name = row.get('name') or meta.get('name') or (meta.get('externalIds') or {}).get('shortId') or 'Vehicle'
                normalized = {
                    'id': vehicle_id,
                    'name': name,
                    'branch': self._infer_dispatch_branch(name, vehicle_id, meta),
                    'lat': lat,
                    'lon': lon,
                    'heading': loc.get('heading'),
                    'speed': loc.get('speed'),
                    'located_at': loc.get('time'),
                    'tags': [tag.get('name') for tag in (meta.get('tags') or []) if isinstance(tag, dict) and tag.get('name')],
                }
                vehicles.append(normalized)

            wanted_branch = (branch or '').upper()
            if wanted_branch:
                vehicles = [vehicle for vehicle in vehicles if (vehicle.get('branch') or '').upper() == wanted_branch]

            return {
                'vehicles': vehicles,
                'count': len(vehicles),
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'source': 'samsara',
            }
        except ValueError as exc:
            # Missing API token — return the same shape as the no-token early return above
            return {
                'vehicles': [],
                'count': 0,
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'warning': str(exc),
            }
        except requests.HTTPError as exc:
            return {
                'vehicles': [],
                'count': 0,
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'error': 'samsara_http_error',
                'detail': str(exc),
                'status': getattr(exc.response, 'status_code', None),
            }
        except Exception as exc:
            return {
                'vehicles': [],
                'count': 0,
                'fetched_at': datetime.utcnow().isoformat() + 'Z',
                'error': 'unexpected_error',
                'detail': str(exc),
            }

    def get_tags(self):
        """
        GET /tags - List all tags for the organization.
        """
        data = self._get('/tags')
        if data and 'data' in data:
            return data['data']
        return self._mock_tags()

    def get_vehicles(self):
        """
        GET /fleet/vehicles - List all vehicles in the fleet.
        Returns list of vehicle dicts with id, name, vin, etc.
        """
        data = self._get('/fleet/vehicles')
        if data and 'data' in data:
            return data['data']
        # Mock data for development/demo
        return self._mock_vehicles()

    def get_vehicle_locations(self, tag_ids=None):
        """
        GET /fleet/vehicles/locations - Get real-time GPS locations for vehicles.
        Optional tag_ids parameter (comma-separated string or list) to filter.
        """
        params = {}
        if tag_ids:
            if isinstance(tag_ids, list):
                params['tagIds'] = ','.join(map(str, tag_ids))
            else:
                params['tagIds'] = tag_ids

        data = self._get('/fleet/vehicles/locations', params=params)
        if data and 'data' in data:
            locations = []
            for v in data['data']:
                loc = v.get('location', {})
                locations.append({
                    'vehicle_id': v.get('id'),
                    'name': v.get('name', 'Unknown'),
                    'latitude': loc.get('latitude'),
                    'longitude': loc.get('longitude'),
                    'speed_mph': loc.get('speed', 0),
                    'heading': loc.get('heading', 0),
                    'time': loc.get('time', ''),
                    'address': loc.get('reverseGeo', {}).get('formattedLocation', '')
                })
            print(f"Samsara API: Successfully retrieved {len(locations)} vehicles.")
            return locations
            
        print("Samsara API: Failed to get location data or no data returned. Falling back to MOCK data.")
        # Mock data for development/demo
        return self._mock_locations()

    def get_vehicle_location(self, vehicle_id):
        """
        Get location for a specific vehicle.
        """
        data = self._get(f'/fleet/vehicles/{vehicle_id}/locations')
        if data and 'data' in data:
            v = data['data']
            loc = v.get('location', {})
            return {
                'vehicle_id': v.get('id'),
                'name': v.get('name', 'Unknown'),
                'latitude': loc.get('latitude'),
                'longitude': loc.get('longitude'),
                'speed_mph': loc.get('speed', 0),
                'heading': loc.get('heading', 0),
                'time': loc.get('time', ''),
                'address': loc.get('reverseGeo', {}).get('formattedLocation', '')
            }
        return None

    def get_drivers(self):
        """
        GET /fleet/drivers - List all drivers.
        Returns list of driver dicts.
        """
        data = self._get('/fleet/drivers')
        if data and 'data' in data:
            return data['data']
        return self._mock_drivers()

    def get_vehicle_stats(self):
        """
        GET /fleet/vehicles/stats - Get vehicle stats (fuel, odometer, engine state).
        Useful for KPI display on delivery board.
        """
        data = self._get('/fleet/vehicles/stats', params={
            'types': 'engineStates,fuelPercents,obdOdometerMeters'
        })
        if data and 'data' in data:
            return data['data']
        return []

    # --- Mock Data for Development ---

    def _mock_vehicles(self):
        return [
            {'id': 'v-001', 'name': 'Truck 1 - Flatbed', 'vin': 'MOCK1234567890001', 'serial': 'BL-101'},
            {'id': 'v-002', 'name': 'Truck 2 - Boom', 'vin': 'MOCK1234567890002', 'serial': 'BL-102'},
            {'id': 'v-003', 'name': 'Truck 3 - Flatbed', 'vin': 'MOCK1234567890003', 'serial': 'BL-103'},
            {'id': 'v-004', 'name': 'Truck 4 - Box', 'vin': 'MOCK1234567890004', 'serial': 'BL-104'},
            {'id': 'v-005', 'name': 'Truck 5 - Flatbed', 'vin': 'MOCK1234567890005', 'serial': 'BL-105'},
        ]

    def _mock_locations(self):
        return [
            {
                'vehicle_id': 'v-001', 'name': 'Truck 1 - Flatbed',
                'latitude': 41.2565, 'longitude': -95.9345, 'speed_mph': 35,
                'heading': 90, 'time': datetime.utcnow().isoformat(),
                'address': '1234 Dodge St, Omaha, NE'
            },
            {
                'vehicle_id': 'v-002', 'name': 'Truck 2 - Boom',
                'latitude': 41.2230, 'longitude': -95.9980, 'speed_mph': 0,
                'heading': 0, 'time': datetime.utcnow().isoformat(),
                'address': 'Beisser Lumber Yard (Home Base)'
            },
            {
                'vehicle_id': 'v-003', 'name': 'Truck 3 - Flatbed',
                'latitude': 41.2780, 'longitude': -95.9100, 'speed_mph': 45,
                'heading': 180, 'time': datetime.utcnow().isoformat(),
                'address': '72nd & Pacific, Omaha, NE'
            },
            {
                'vehicle_id': 'v-004', 'name': 'Truck 4 - Box',
                'latitude': 41.1920, 'longitude': -95.9500, 'speed_mph': 25,
                'heading': 270, 'time': datetime.utcnow().isoformat(),
                'address': '4500 S 84th St, Omaha, NE'
            },
            {
                'vehicle_id': 'v-005', 'name': 'Truck 5 - Flatbed',
                'latitude': 41.3100, 'longitude': -96.0200, 'speed_mph': 55,
                'heading': 45, 'time': datetime.utcnow().isoformat(),
                'address': 'I-680 & Maple St, Omaha, NE'
            },
        ]

    def _mock_drivers(self):
        return [
            {'id': 'd-001', 'name': 'Mike Johnson', 'phone': '402-555-0101', 'status': 'onDuty'},
            {'id': 'd-002', 'name': 'Tom Williams', 'phone': '402-555-0102', 'status': 'onDuty'},
            {'id': 'd-003', 'name': 'Dave Brown', 'phone': '402-555-0103', 'status': 'onDuty'},
            {'id': 'd-004', 'name': 'Chris Davis', 'phone': '402-555-0104', 'status': 'offDuty'},
            {'id': 'd-005', 'name': 'Steve Miller', 'phone': '402-555-0105', 'status': 'onDuty'},
        ]

    def _mock_tags(self):
        return [
            {'id': '1001', 'name': 'Grimes'},
            {'id': '1002', 'name': 'Birchwood'},
            {'id': '1003', 'name': 'Warehouse'},
            {'id': '1004', 'name': 'GR'},
            {'id': '1005', 'name': 'BW'}
        ]
