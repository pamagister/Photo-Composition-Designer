from datetime import datetime, timedelta

import pytest

from designer.tools.ImageDistributor import ImageDistributor


class TestImageDistributor:
    @pytest.fixture(scope="function", autouse=True)
    def setup(self):
        base_date = datetime(2024, 1, 1)
        self.image_data = {}
        count = 1
        for i in range(9):
            minute = 40
            for _ in range(7 if i % 7 == 0 else 4 if i % 4 == 0 else 2 if i % 2 == 1 else 3 if i % 3 == 1 else 1):
                img_date = base_date + timedelta(days=i * i) + timedelta(minutes=minute)
                self.image_data[f"image_{str(img_date.month).zfill(2)}-{str(img_date.day).zfill(2)}_{count}.jpg"] = (
                    img_date
                )
                minute += 1
                count += 1

    def test_distribute_equally(self):
        distributor = ImageDistributor(self.image_data, 6)
        distributed_images = distributor.distribute_equally()
        for group in distributed_images.values():
            assert len(group) == 5

    def test_distribute_equally(self):
        distributor = ImageDistributor(self.image_data, 4)
        distributed_images = distributor.distribute_equally()
        assert len(distributed_images[0]) == 8
        assert len(distributed_images[1]) == 8
        assert len(distributed_images[2]) == 7
        assert len(distributed_images[3]) == 7

    def test_distribute_randomly(self):
        distributor = ImageDistributor(self.image_data, 4)
        distributed_images = distributor.distribute_randomly(2)
        assert sum(len(group) for group in distributed_images.values()) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 8
        assert len(distributed_images[1]) == 9
        assert len(distributed_images[2]) == 7
        assert len(distributed_images[3]) == 6

    def test_distribute_group_matching_dates_6(self):
        distributor = ImageDistributor(self.image_data, 6)
        distributed_images = distributor.distribute_group_matching_dates(2)
        assert sum(len(group) for group in distributed_images.values()) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 7
        assert len(distributed_images[1]) == 5
        assert len(distributed_images[2]) == 6
        assert len(distributed_images[3]) == 3
        assert len(distributed_images[4]) == 5
        assert len(distributed_images[5]) == 4

    def test_distribute_group_matching_dates_10(self):
        distributor = ImageDistributor(self.image_data, 10)
        distributed_images = distributor.distribute_group_matching_dates(2)
        assert sum(len(group) for group in distributed_images.values()) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 2
        assert len(distributed_images[1]) == 2
        assert len(distributed_images[2]) == 5
        assert len(distributed_images[3]) == 3
        assert len(distributed_images[4]) == 5
        assert len(distributed_images[5]) == 2

    def test_distribute_by_week(self):
        distributor = ImageDistributor(self.image_data, 55)
        distributed_images = distributor.distribute_by_week(datetime(2024, 12, 30, 1, 1, 1))
        assert sum(len(group) for group in distributed_images.values()) == 30  # Prüft die Gesamtanzahl
        assert len(distributed_images[0]) == 10
        assert len(distributed_images[1]) == 2
        assert len(distributed_images[9]) == 4
