import random
from collections import defaultdict, deque
from datetime import datetime, timedelta

from Photo_Composition_Designer.common.Photo import Photo


class ImageDistributor:
    def __init__(self, photos: list[Photo], distributions_count: int):
        self.photos = photos
        self.sorted_photos = sorted(photos, key=lambda photo: photo.get_date() or datetime.min)

        self.distribution_count = distributions_count

    def distribute_equally(self) -> list[list[Photo]]:
        """
        Verteilt die Bilder möglichst gleichmäßig auf die gewünschte Anzahl von Gruppen.
        """
        grouped_images = []  # Liste von Listen für die Verteilung

        # Anzahl der Bilder pro Gruppe berechnen
        images_per_group = len(self.sorted_photos) // self.distribution_count
        extra_images = (
            len(self.sorted_photos) % self.distribution_count
        )  # Falls es nicht exakt aufgeht

        photo_queue = deque(self.sorted_photos)  # Nutzt deque für effiziente Pop-Operationen

        for i in range(self.distribution_count):
            group_size = images_per_group + (
                1 if i < extra_images else 0
            )  # Extra-Bilder gleichmäßig verteilen
            grouped_images.append([photo_queue.popleft() for _ in range(group_size) if photo_queue])

        return grouped_images

    def distribute_randomly(self, allowed_delta: int = 1) -> list[list[Photo]]:
        """
        Ähnlich wie distribute_equally, aber mit einem gewissen Zufallseffekt,
        sodass die Anzahl der Bilder pro Gruppe leicht variieren kann.
        Die Reihenfolge bleibt sortiert, und ein Zufalls-Seed sorgt für Reproduzierbarkeit.
        """
        random.seed(11)  # Fester Seed für reproduzierbare Ergebnisse
        grouped_images = []
        photo_queue = deque(self.sorted_photos)  # Nutzt deque für effizientes Entfernen
        remaining_images = len(photo_queue)
        remaining_groups = self.distribution_count

        for _i in range(self.distribution_count - 1):
            images_per_group = remaining_images // remaining_groups
            group_size = max(
                1, images_per_group + random.choice(range(-allowed_delta, allowed_delta + 1))
            )
            grouped_images.append(
                [photo_queue.popleft() for _ in range(min(group_size, remaining_images))]
            )
            remaining_images -= len(grouped_images[-1])
            remaining_groups -= 1

        # Alle verbleibenden Bilder der letzten Gruppe zuweisen
        grouped_images.append(list(photo_queue))

        return grouped_images

    def distribute_group_matching_dates(
        self, allowed_over_saturation: int = 2, allowed_under_saturation: int = 1
    ) -> list[list[Photo]]:
        """
        Gruppiert Bilder mit demselben Datum zusammen,
        während eine Über- oder Unterfüllung pro Gruppe erlaubt ist.
        Bilder eines Tages können auf mehrere Gruppen aufgeteilt werden.
        """
        grouped_images = []
        date_groups = defaultdict(list)

        # Gruppiere Bilder nach ihrem Datum
        for img in self.sorted_photos:
            date_groups[img.get_date()].append(img)

        sorted_dates = sorted(date_groups.keys())
        remaining_images = sum(len(v) for v in date_groups.values())
        remaining_groups = self.distribution_count

        while sorted_dates and remaining_groups > 0:
            avg_per_group = remaining_images // remaining_groups
            current_group = []
            current_date = sorted_dates[0]

            # Füge das erste Bild des Tages hinzu
            current_group.append(date_groups[current_date].pop(0))
            if not date_groups[current_date]:
                sorted_dates.pop(0)  # Datum entfernen, wenn keine Bilder mehr vorhanden sind

            while sorted_dates:
                next_date = sorted_dates[0]

                if (
                    not self.is_same_calendar_week(current_date, next_date)
                    and len(current_group) >= avg_per_group - allowed_under_saturation
                ):
                    # Dieses Datum gehört nicht zur gleichen Woche & Gruppe ist ausreichend voll
                    break
                elif len(current_group) >= avg_per_group + allowed_over_saturation:
                    # Gruppe hat das erlaubte Maximum erreicht
                    break
                else:
                    current_group.append(date_groups[next_date].pop(0))
                    if not date_groups[next_date]:
                        sorted_dates.pop(0)

            grouped_images.append(current_group)
            remaining_images -= len(current_group)
            remaining_groups -= 1

        # Falls noch Bilder übrig sind, der letzten Gruppe zuweisen
        if sorted_dates:
            for remaining_date in sorted_dates:
                grouped_images[-1].extend(date_groups[remaining_date])

        return grouped_images

    def get_monday_of_same_week(self, date: datetime) -> datetime:
        return date - timedelta(days=date.weekday())

    def is_same_calendar_week(self, date1: datetime, date2: datetime) -> bool:
        """
        Prüft, ob zwei Datumswerte in der gleichen Kalenderwoche liegen.
        Berücksichtigt dabei das Jahr und die Kalenderwochen-Nummer.
        """
        return date1.isocalendar()[:2] == date2.isocalendar()[:2]

    def distribute_by_week(self, start_date: datetime) -> list[list[Photo]]:
        grouped_images = []

        for week in range(self.distribution_count):
            week_start = start_date + timedelta(weeks=week)
            week_end = week_start + timedelta(days=6)

            # Fotos auswählen, die in diese Woche passen
            photos_in_week = [
                photo
                for photo in self.sorted_photos
                if week_start.date() <= photo.get_date().date() <= week_end.date()
            ]

            # Entferne gefilterte Fotos aus der Hauptliste
            self.sorted_photos = [
                photo for photo in self.sorted_photos if photo not in photos_in_week
            ]

            grouped_images.append(photos_in_week)

        return grouped_images
