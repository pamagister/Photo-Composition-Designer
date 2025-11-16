from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from Photo_Composition_Designer.common.Photo import Photo
from Photo_Composition_Designer.tools.ImageDistributor import ImageDistributor


class TestImageDistributor:
    @pytest.fixture(scope="function", autouse=True)
    def setup(self):
        self.image_data = {}
        minute = 0
        base_date = datetime(2024, 12, 30)
        for i in range(2):
            minute += 1
            img_date = base_date + timedelta(days=i) + timedelta(minutes=minute)
            self.image_data[
                f"image_{str(img_date.month).zfill(2)}-{str(img_date.day).zfill(2)}_{minute}.jpg"
            ] = img_date
        base_date = datetime(2025, 1, 1)
        for i in range(5):
            minute += 1
            img_date = base_date + timedelta(days=i) + timedelta(minutes=minute)
            self.image_data[
                f"image_{str(img_date.month).zfill(2)}-{str(img_date.day).zfill(2)}_{minute}.jpg"
            ] = img_date
            img_date = base_date + timedelta(days=15) + timedelta(minutes=minute)
            self.image_data[
                f"image_{str(img_date.month).zfill(2)}-{str(img_date.day).zfill(2)}_{minute}.jpg"
            ] = img_date
        base_date = datetime(2025, 3, 1)
        for i in range(9):
            minute += 1
            img_date = base_date + timedelta(days=0) + timedelta(minutes=minute)
            self.image_data[
                f"image_{str(img_date.month).zfill(2)}-{str(img_date.day).zfill(2)}_{minute}.jpg"
            ] = img_date
            img_date = base_date + timedelta(days=15 + 2 * i) + timedelta(minutes=minute)
            self.image_data[
                f"image_{str(img_date.month).zfill(2)}-{str(img_date.day).zfill(2)}_{minute}.jpg"
            ] = img_date

    def create_mock_photo(self, img_date):
        mock_photo = MagicMock(spec=Photo)
        mock_photo.get_date.return_value = img_date
        return mock_photo

    def test_distribute_equally_6(self):
        # Erstelle eine Liste von Mock-Photo-Objekten
        photos = [self.create_mock_photo(date) for date in self.image_data.values()]

        distributor = ImageDistributor(photos, 6)
        distributed_images = distributor.distribute_equally()

        # Überprüfen, dass alle Gruppen gleichmäßig verteilt sind
        for group in distributed_images:
            assert len(group) == 5

    def test_distribute_equally_4(self):
        # Erstelle eine Liste von Mock-Photo-Objekten
        photos = [self.create_mock_photo(date) for date in self.image_data.values()]

        distributor = ImageDistributor(photos, 4)
        distributed_images = distributor.distribute_equally()

        # Überprüfen, dass die Bilder gleichmäßig auf die 4 Gruppen verteilt sind
        assert sum(len(group) for group in distributed_images) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 8
        assert len(distributed_images[1]) == 8
        assert len(distributed_images[2]) == 7
        assert len(distributed_images[3]) == 7

    def test_distribute_randomly(self):
        # Erstelle eine Liste von Mock-Photo-Objekten
        photos = [self.create_mock_photo(date) for date in self.image_data.values()]

        distributor = ImageDistributor(photos, 4)
        distributed_images = distributor.distribute_randomly(2)

        # Überprüfen, dass die Bilder verteilt wurden (ohne strikte Gleichverteilung)
        assert sum(len(group) for group in distributed_images) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) in [6, 7, 8, 9]
        assert len(distributed_images[1]) in [6, 7, 8, 9]
        assert len(distributed_images[2]) in [6, 7, 8, 9]
        assert len(distributed_images[3]) in [6, 7, 8, 9]

    def test_distribute_group_matching_dates_6(self):
        # Erstelle eine Liste von Mock-Photo-Objekten
        photos = [self.create_mock_photo(date) for date in self.image_data.values()]

        distributor = ImageDistributor(photos, 6)
        distributed_images = distributor.distribute_group_matching_dates(2, 2)
        assert sum(len(group) for group in distributed_images) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 7
        assert len(distributed_images[1]) == 5
        assert len(distributed_images[2]) == 6
        assert len(distributed_images[3]) == 3
        assert len(distributed_images[4]) == 2
        assert len(distributed_images[5]) == 7

    def test_distribute_group_matching_dates_10(self):
        photos = [self.create_mock_photo(date) for date in self.image_data.values()]

        distributor = ImageDistributor(photos, 10)
        distributed_images = distributor.distribute_group_matching_dates(1, 1)
        assert sum(len(group) for group in distributed_images) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 4
        assert len(distributed_images[1]) == 3
        assert len(distributed_images[2]) == 3
        assert len(distributed_images[3]) == 2
        assert len(distributed_images[4]) == 4
        assert len(distributed_images[5]) == 3
        assert len(distributed_images[6]) == 2
        assert len(distributed_images[7]) == 2
        assert len(distributed_images[8]) == 2
        assert len(distributed_images[9]) == 5

    def test_distribute_by_week(self):
        photos = [self.create_mock_photo(date) for date in self.image_data.values()]
        distributor = ImageDistributor(photos, 55)
        distributed_images = distributor.distribute_by_week(datetime(2024, 12, 30, 1, 1, 1))
        assert sum(len(group) for group in distributed_images) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 7
        assert len(distributed_images[1]) == 0
        assert len(distributed_images[2]) == 5
        assert len(distributed_images[8]) == 9
        assert len(distributed_images[10]) == 1
        assert len(distributed_images[11]) == 3
        assert len(distributed_images[12]) == 4
        assert len(distributed_images[13]) == 1
