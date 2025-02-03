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
                self.image_data[f"image{count}.jpg"] = base_date + timedelta(days=i) + timedelta(minutes=minute)
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
