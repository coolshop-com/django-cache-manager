# -*- coding: utf-8 -*-

"""
Integration tests for models using CacheManager
Use models defined in tests t

1. Black box tests - input model data,  retrieve, delete, update -assert that right data is retrieved
"""
import django
from django.forms.models import model_to_dict
from django.core.exceptions import ObjectDoesNotExist
from django.db import (
    connection,
    reset_queries
)
from django.test import TestCase
if django.get_version() > '1.7':
    from django.test import override_settings
else:
    from django.test.utils import override_settings

from tests.models import(
    Car,
    Driver,
    Engine,
    Manufacturer,
)
from tests.factories import(
    CarFactory,
    DriverFactory,
    EngineFactory,
    ManufacturerFactory,
)


class ModelCRUDTests(TestCase):
    """
    Create, read, update and delete tests
    """

    def setUp(self):
        self.manufacturers = ManufacturerFactory.create_batch(size=5)
        self.cars = CarFactory.create_batch(size=5, make=self.manufacturers[0])
        self.drivers = DriverFactory.create_batch(size=5, cars=[self.cars[0]])

    def test_create_new_manufacturer(self):
        """
        Number of manufacturers returned by objects should increment after
        creating a new manufacturer
        """
        ManufacturerFactory.create()
        self.assertEqual(
            len(Manufacturer.objects.all()), len(self.manufacturers) + 1)

    def test_update_manufacturer(self):
        """
        Cache manager returns most recently updated record
        even if it has been cached and an update happens after.
        """
        m = self.manufacturers[0]
        self.assertEqual(
            model_to_dict(m), model_to_dict(Manufacturer.objects.get(id=m.id)))
        m.name = 'Toyota'
        m.save()
        self.assertEqual(
            model_to_dict(m), model_to_dict(Manufacturer.objects.get(id=m.id)))

    def test_delete_manufacturer(self):
        """
        When a cached record is deleted Cache manager raises ObjectDoesNotExist when trying to retrieve
        """
        m = self.manufacturers[0]
        self.assertEqual(
            model_to_dict(m), model_to_dict(Manufacturer.objects.get(id=m.id)))
        m.delete()
        with self.assertRaises(ObjectDoesNotExist):
            Manufacturer.objects.get(id=m.id)


class ModelCacheTests(TestCase):
    """
    Test cache hits and misses
    """

    def setUp(self):
        self.manufacturers = ManufacturerFactory.create_batch(size=5)
        self.engine = EngineFactory.create(name='test_engine')
        self.car = CarFactory.create(engine=self.engine, year=2015)
        self.driver = DriverFactory.create(cars=[self.car])
        reset_queries()

    @override_settings(DEBUG=True)
    def test_cache_hit(self):
        """
        The query should be cached when making the same query repeatedly.
        """
        for i in range(5):
            len(Manufacturer.objects.all())
        self.assertEqual(len(connection.queries), 1)

    def test_dummy_cache(self):
        """
        There should not be any query caching when cache backend is dummy.
        """
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
            },
            'django_cache_manager.cache_backend': {
                'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
            }
        }
        with override_settings(DEBUG=True, CACHES=CACHES):
            for i in range(5):
                len(Manufacturer.objects.all())
            self.assertEqual(len(connection.queries), 5)

    @override_settings(DEBUG=True)
    def test_one_to_one_mapping_cache(self):
        """
        Queries should be cached when making the same select queries
        on related objects query repeatedly
        """
        for i in range(5):
            Car.objects.get(id=self.car.id).engine.name
        # The above query is actually composed of 2 sql queries:
        # one for fetching cars and the other engines.
        self.assertEqual(len(connection.queries), 2)

    @override_settings(DEBUG=True)
    def test_one_to_one_mapping_cache_with_save(self):
        """
        Cache should be invalidated when calling 'save' on related objects
        """
        Car.objects.get(id=self.car.id).engine.name
        self.engine.name = 'new_engine'
        self.engine.save()
        reset_queries()

        # Only 1 cache (the one for engine selection query) will be invalidated
        # as we only update data on Engine table
        Car.objects.get(id=self.car.id).engine.name
        self.assertEqual(len(connection.queries), 1)

    @override_settings(DEBUG=True)
    def test_one_to_one_mapping_cache_with_delete(self):
        """
        Cache should be invalidated when calling 'delete' related objects
        """
        Car.objects.get(id=self.car.id).engine.name
        self.engine.delete()
        reset_queries()

        with self.assertRaises(ObjectDoesNotExist):
            Car.objects.get(id=self.car.id).engine.name

    @override_settings(DEBUG=True)
    def test_many_to_many_mapping_cache(self):
        """
        Queries should be cached when making the same select queries
        on related objects repeatedly
        """
        car2 = CarFactory.create()
        self.driver.cars.add(car2)
        reset_queries()

        for i in range(5):
            Driver.objects.get(id=self.driver.id).cars.all()[0].year
        # The above query is actually composed of 2 sql queries:
        # one for fetching drivers and the other cars.
        self.assertEqual(len(connection.queries), 2)

    @override_settings(DEBUG=True)
    def test_many_to_many_mapping_cache_with_save(self):
        """
        Cache should be invalidated when calling 'save' on related objects
        """
        car2 = CarFactory.create()
        self.driver.cars.add(car2)
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        car2.name = 'gti'
        car2.save()
        reset_queries()

        # Only 1 cache (the one for car selection query) will be invalidated
        # as we only update data on Car table
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        self.assertEqual(len(connection.queries), 1)

    @override_settings(DEBUG=True)
    def test_many_to_many_mapping_cache_with_delete(self):
        """
        Cache should be invalidated when calling 'delete' on related objects
        """
        car2 = CarFactory.create()
        self.driver.cars.add(car2)
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        car2.delete()
        reset_queries()

        # Only 1 cache (the one for car selection query) will be invalidated
        # as we only delete data on Car table
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        self.assertEqual(len(connection.queries), 1)

    @override_settings(DEBUG=True)
    def test_many_to_many_mapping_cache_with_add(self):
        """
        Cache for both models in this many-to-many relationship should
        be updated when calling 'add' on related objects
        """
        new_cars = CarFactory.create_batch(size=3)
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        # Using add() with a many-to-many relationship will call
        # QuerySet.bulk_create() to create the relationships.
        # https://docs.djangoproject.com/en/1.7/ref/models/relations/#django.db.models.fields.related.RelatedManager.add
        self.driver.cars.add(*new_cars)
        reset_queries()

        # Cache for both models should be invalidated as add is an m2m change
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        self.assertEqual(len(connection.queries), 2)

    @override_settings(DEBUG=True)
    def test_many_to_many_mapping_cache_with_remove(self):
        """
        Cache for both models in this many-to-many relationship should
        be updated when calling 'remove' on related objects
        """
        new_car = CarFactory.create()
        self.driver.cars.add(new_car)
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        self.driver.cars.remove(self.car)
        reset_queries()

        # Cache for both models should be invalidated as remove is an m2m change
        Driver.objects.get(id=self.driver.id).cars.all()[0].year
        self.assertEqual(len(connection.queries), 2)

    @override_settings(DEBUG=True)
    def test_many_to_many_mapping_cache_with_clear(self):
        """
        Cache for both models in this many-to-many relationship should
        be updated when calling 'clear' on related objects
        """
        len(Driver.objects.get(id=self.driver.id).cars.all())
        self.driver.cars.clear()
        reset_queries()

        # Cache for both models should be invalidated as clear is an m2m change
        len(Driver.objects.get(id=self.driver.id).cars.all())
        self.assertEqual(len(connection.queries), 2)





