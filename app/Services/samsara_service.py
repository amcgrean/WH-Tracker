import os
import requests
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

    def _get(self, endpoint, params=None):
        """Generic GET request to Samsara API."""
        if not self.api_token:
            print("SamsaraService: No API token configured. Returning mock data.")
            return None
        try:
            url = f"{self.BASE_URL}{endpoint}"
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Samsara API Error: {e}")
            return None

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

    def get_vehicle_locations(self):
        """
        GET /fleet/vehicles/locations - Get real-time GPS locations for all vehicles.
        Returns list of dicts: {vehicle_id, name, latitude, longitude, speed, heading, time}
        """
        data = self._get('/fleet/vehicles/locations')
        if data and 'data' in data:
            locations = []
            for v in data['data']:
                loc = v.get('location', {})
                locations.append({
                    'vehicle_id': v.get('id'),
                    'name': v.get('name', 'Unknown'),
                    'latitude': loc.get('latitude'),
                    'longitude': loc.get('longitude'),
                    'speed_mph': loc.get('speedMilesPerHour', 0),
                    'heading': loc.get('heading', 0),
                    'time': loc.get('time', ''),
                    'address': loc.get('reverseGeo', {}).get('formattedLocation', '')
                })
            return locations
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
                'speed_mph': loc.get('speedMilesPerHour', 0),
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
