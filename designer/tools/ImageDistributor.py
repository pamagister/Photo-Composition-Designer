from collections import defaultdict
from datetime import datetime
import random


class ImageDistributor:
    def __init__(self, image_dict: dict[str, datetime], distributions_count: int):
        self.image_dict = dict(sorted(image_dict.items(), key=lambda item: item[1]))  # Sortiere nach Datum
        self.distribution_count = distributions_count
        self.max_images_per_group = 5

    def distribute_equally(self):
        """
        Verteilt die Bilder möglichst gleichmäßig auf die gewünschte Anzahl von Gruppen.
        """
        grouped_images = defaultdict(list)

        # Anzahl der Bilder pro Gruppe berechnen
        images_per_group = len(self.image_dict) // self.distribution_count
        extra_images = len(self.image_dict) % self.distribution_count  # Falls es nicht exakt aufgeht

        iterator = iter(self.image_dict.items())
        for i in range(self.distribution_count):
            group_size = images_per_group + (1 if i < extra_images else 0)  # Falls extra Bilder verteilt werden müssen
            grouped_images[i] = [next(iterator) for _ in range(group_size)]

        return grouped_images

    def distribute_randomly(self, allowed_delta: int = 1):
        """
        Ähnlich wie distribute_equally, aber mit einem gewissen Zufallseffekt,
        sodass die Anzahl der Bilder pro Gruppe leicht variieren kann.
        """
        grouped_images = defaultdict(list)
        images = list(self.image_dict.items())

        images_per_group = len(images) // self.distribution_count

        iterator = iter(images)
        for i in range(self.distribution_count):
            group_size = images_per_group + random.choice(range(-allowed_delta, allowed_delta + 1))

            grouped_images[i] = [
                next(iterator)
                for _ in range(min(group_size, len(images) - sum(len(g) for g in grouped_images.values())))
            ]

        return grouped_images

    def distribute_group_matching_dates(self, allowed_over_saturation: int = 2):
        """
        Gruppiert Bilder mit demselben Datum zusammen, während eine Überfüllung pro Gruppe erlaubt ist.
        """
        grouped_images = defaultdict(list)
        date_groups = defaultdict(list)

        for img, date in self.image_dict.items():
            date_groups[date.date()].append((img, date))

        sorted_dates = sorted(date_groups.keys())
        all_images = [img for date in sorted_dates for img in date_groups[date]]
        avg_per_group = len(all_images) // self.distribution_count

        iterator = iter(all_images)
        for i in range(self.distribution_count):
            max_group_size = avg_per_group + allowed_over_saturation
            grouped_images[i] = [
                next(iterator)
                for _ in range(min(max_group_size, len(all_images) - sum(len(g) for g in grouped_images.values())))
            ]

        return grouped_images


# Beispielaufruf
if __name__ == "__main__":
    image_data = {
        "image1.jpg": datetime(2024, 1, 6, 10, 0, 0),
        "image2.jpg": datetime(2024, 1, 1, 11, 0, 0),
        "image3.jpg": datetime(2024, 1, 11, 12, 0, 0),
        "image4.jpg": datetime(2024, 1, 24, 13, 0, 0),
        "image5.jpg": datetime(2024, 1, 5, 14, 0, 0),
        "image6.jpg": datetime(2024, 1, 9, 15, 0, 0),
    }
    distributor = ImageDistributor(image_data, 3)
    distributed_images = distributor.distribute_equally()

    for group, images in distributed_images.items():
        print(f"Gruppe {group + 1}: {[img[0] for img in images]}")
