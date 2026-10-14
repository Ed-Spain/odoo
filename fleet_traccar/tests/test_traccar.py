from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTraccar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env['traccar.server'].create({'name': 'Test', 'url': 'http://localhost:8082', 'web_url': 'http://localhost:8082', 'username': 'test', 'password': 'secret'})
        cls.device = cls.env['traccar.device'].create({'name': 'Test', 'server_id': cls.server.id, 'remote_id': 42})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Test'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'Test', 'brand_id': brand.id})
        cls.vehicle = cls.env['fleet.vehicle'].create({'model_id': model.id, 'company_id': cls.env.company.id, 'odometer_unit': 'miles'})

    def position(self, **kw):
        return dict({'id': 1, 'deviceId': 42, 'fixTime': '2026-09-01T12:00:00Z', 'valid': True, 'latitude': 0, 'longitude': 0, 'speed': 10, 'address': 'Existing address', 'attributes': {'totalDistance': 160934.4}}, **kw)

    def test_position_units_and_idempotency(self):
        self.device.write({'vehicle_id': self.vehicle.id, 'sync_odometer': True})
        self.device._apply_position(self.position())
        self.assertTrue(self.device.valid)  # Equator/prime meridian are valid.
        self.assertAlmostEqual(self.device.speed_kmh, 18.52)
        self.assertAlmostEqual(self.vehicle.odometer, 100)
        domain = [('vehicle_id', '=', self.vehicle.id)]
        count = self.env['fleet.vehicle.odometer'].search_count(domain)
        self.device._apply_position(self.position())
        self.assertEqual(self.env['fleet.vehicle.odometer'].search_count(domain), count)
        self.device._apply_position(self.position(fixTime='2026-08-01T00:00:00Z', latitude=50))
        self.assertEqual(self.device.latitude, 0)
        self.device._apply_position(self.position(id=2, fixTime='2026-09-02T00:00:00Z', attributes={'totalDistance': 1000}))
        self.assertAlmostEqual(self.vehicle.odometer, 100)

    def test_optional_and_invalid_mileage(self):
        self.device.vehicle_id = self.vehicle
        self.device._apply_position(self.position())
        self.assertFalse(self.env['fleet.vehicle.odometer'].search([('vehicle_id', '=', self.vehicle.id)]))
        self.device.sync_odometer = True
        self.device._apply_position(self.position(
            id=2,
            fixTime='2026-09-01T13:00:00Z',
            valid=False,
            latitude=39.47364,
            longitude=-0.38876,
        ))
        self.assertFalse(self.device.valid)
        self.assertAlmostEqual(self.device.latitude, 39.47364)
        self.assertAlmostEqual(self.device.longitude, -0.38876)
        self.assertFalse(self.env['fleet.vehicle.odometer'].search([('vehicle_id', '=', self.vehicle.id)]))
        self.device._apply_position(self.position(
            id=3,
            fixTime='2026-09-01T14:00:00Z',
            attributes={},
        ))
        self.assertFalse(self.device.has_distance)

    def test_reverse_geocode_and_stationary_address_cache(self):
        with patch.object(type(self.server), '_reverse_geocode', return_value='Carrer de Test, València') as geocode:
            self.device._apply_position(self.position(latitude=39.47364, longitude=-0.388757, address=False))
            self.assertEqual(self.device.address, 'Carrer de Test, València')
            geocode.assert_called_once_with(39.47364, -0.388757)
            self.device._apply_position(self.position(
                id=2,
                fixTime='2026-09-01T13:00:00Z',
                latitude=39.47364,
                longitude=-0.388757,
                address=False,
            ))
            self.assertEqual(self.device.address, 'Carrer de Test, València')
            geocode.assert_called_once()

    def test_reverse_geocode_api(self):
        with patch('odoo.addons.fleet_traccar.models.traccar.requests.get') as get:
            get.return_value.status_code = 200
            get.return_value.text = '  Carrer de Test, València  '
            self.assertEqual(self.server._reverse_geocode(39.4, -0.3), 'Carrer de Test, València')
            self.assertEqual(get.call_args.kwargs['params'], {'latitude': 39.4, 'longitude': -0.3})

    def test_import_idempotency_and_missing_device(self):
        payload = [{'id': 42, 'name': 'Renamed', 'uniqueId': 'abc', 'status': 'offline'}]
        with patch.object(type(self.server), '_get', side_effect=lambda endpoint: payload if endpoint == 'devices' else [self.position()]):
            self.server._sync()
            self.server._sync()
        self.assertEqual(len(self.server.device_ids), 1)
        self.assertEqual(self.device.name, 'Renamed')
        with patch.object(type(self.server), '_get', return_value=[]):
            self.server._sync()
        self.assertFalse(self.device.available)

    def test_company_and_credentials(self):
        other = self.env['res.company'].create({'name': 'Other'})
        user = self.env['res.users'].create({'name': 'Fleet officer', 'login': 'traccar-test-officer',
            'company_id': self.env.company.id, 'company_ids': [Command.set([self.env.company.id])],
            'groups_id': [Command.set([self.env.ref('fleet.fleet_group_user').id])]})
        with self.assertRaises(AccessError):
            self.server.with_user(user).read(['password'])
        with self.assertRaises(AccessError):
            self.server.with_user(user).action_sync()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.vehicle.company_id = other
            self.device.vehicle_id = self.vehicle
        hidden = self.env['traccar.server'].create({'name': 'Other', 'url': 'http://localhost', 'web_url': 'http://localhost', 'company_id': other.id})
        self.assertNotIn(hidden.id, self.env['traccar.server'].with_user(user).search([]).ids)

    def test_bad_auth_message(self):
        with patch('odoo.addons.fleet_traccar.models.traccar.requests.get') as get:
            get.return_value.status_code = 401
            with self.assertRaisesRegex(UserError, 'rejected'):
                self.server._get('devices')

    def test_manager_sync_without_secret_access(self):
        user = self.env['res.users'].create({'name': 'Fleet manager', 'login': 'traccar-test-manager',
            'company_id': self.env.company.id, 'company_ids': [Command.set([self.env.company.id])],
            'groups_id': [Command.set([self.env.ref('fleet.fleet_group_manager').id])]})
        with self.assertRaises(AccessError):
            self.server.with_user(user).read(['password'])
        with patch.object(type(self.server), '_get', return_value=[]):
            self.server.with_user(user).action_sync()
        self.assertTrue(self.server.last_sync)

    def test_browser_link(self):
        self.device.unique_id = 'abc&def'
        self.assertEqual(self.device.action_open_traccar()['url'], 'http://localhost:8082/?uniqueId=abc%26def')
