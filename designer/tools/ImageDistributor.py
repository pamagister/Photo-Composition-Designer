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
        Die Reihenfolge bleibt sortiert, und ein Zufalls-Seed sorgt für Reproduzierbarkeit.
        """
        random.seed(11)  # Fester Seed für deterministische Ergebnisse
        grouped_images = defaultdict(list)
        images = list(self.image_dict.items())
        remaining_images = len(images)
        remaining_groups = self.distribution_count

        iterator = iter(images)
        for i in range(self.distribution_count - 1):
            images_per_group = remaining_images // remaining_groups
            group_size = images_per_group + random.choice(range(-allowed_delta, allowed_delta + 1))
            grouped_images[i] = [next(iterator) for _ in range(min(group_size, remaining_images))]
            remaining_images -= len(grouped_images[i])
            remaining_groups -= 1

        # Alle verbleibenden Bilder der letzten Gruppe zuweisen
        grouped_images[self.distribution_count - 1] = list(iterator)

        return grouped_images

    def distribute_group_matching_dates(self, allowed_over_saturation: int = 2, allowed_under_saturation: int = 1):
        """
        Gruppiert Bilder mit demselben Datum zusammen, während eine Über- oder Unterfüllung pro Gruppe erlaubt ist.
        """
        grouped_images = defaultdict(list)
        date_groups = defaultdict(list)

        for img, date in self.image_dict.items():
            date_groups[date.date()].append((img, date))

        sorted_dates = sorted(date_groups.keys())
        remaining_images = sum(len(v) for v in date_groups.values())
        remaining_groups = self.distribution_count

        while sorted_dates and remaining_groups > 0:
            avg_per_group = remaining_images // remaining_groups
            current_group = []
            current_date = sorted_dates.pop(0)
            current_group.extend(date_groups.pop(current_date))

            while sorted_dates:
                next_date = sorted_dates[0]
                if (
                    len(date_groups[next_date]) >= avg_per_group
                    and len(current_group) >= avg_per_group - allowed_under_saturation
                ):
                    break
                elif len(current_group) >= avg_per_group + allowed_over_saturation:
                    break
                else:
                    current_group.extend(date_groups.pop(next_date))
                    sorted_dates.pop(0)

            grouped_images[len(grouped_images)] = current_group
            remaining_images -= len(current_group)
            remaining_groups -= 1

        # Falls noch Bilder übrig sind, der letzten Gruppe zuweisen
        if date_groups:
            for remaining_date in sorted_dates:
                grouped_images[len(grouped_images) - 1].extend(date_groups[remaining_date])

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
