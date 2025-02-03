from collections import defaultdict
from datetime import datetime


class ImageDistributor:
    def __init__(self, image_dict: dict[str, datetime], distributions_count: int):
        self.image_dict = dict(sorted(image_dict.items(), key=lambda item: item[1]))  # Sortiere nach Datum
        self.distribution_count = distributions_count

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

    def distribute_by_week(self, start_date):
        pass
        # TODO: alle Bilder in die jeweils passende Woche einordnen, beginnend mit start_date


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
