import os
import random
import shutil
from datetime import timedelta
from designer.common.Config import Config
from designer.tools.ImageSorter import ImageSorter


class FolderGenerator:
    """
    Auxiliary class for generating folders that can then be filled with images.
    * A folder is generated for each week in the format Week_<index>_YYYY-MM-DD, e.g. Week_01_2024-07-23
    * An empty "description.txt" is generated in each folder if required
    * A location.txt is also generated if required, which contains the GPX position 51.0504, 13.7373
    """

    def __init__(self, config=None):
        self.config = config or Config()
        self.photoDirectory = self.config.photoDirectory
        self.outputDir = self.photoDirectory / "folders"
        self.startDate = self.config.startDate
        self.move_files = False
        imageSorter = ImageSorter()
        imageSorter.run()
        self.sorted_images = imageSorter.sorted_images  # Dictionary {image_path: date}
        self.distribute = False
        self.generateDescriptionFile = False
        self.generateLocationFile = False
        self.collagesToGenerate = self.config.collagesToGenerate

    def generateFolders(self):
        if not os.path.exists(self.outputDir):
            os.makedirs(self.outputDir)

        sorted_images = sorted(self.sorted_images.items(), key=lambda x: x[1])  # Sort images by date
        total_images = len(sorted_images)
        avg_images_per_week = total_images // self.collagesToGenerate
        remaining_images = total_images

        for week in range(self.collagesToGenerate):
            week_start = self.startDate + timedelta(weeks=week)
            folder_name = f"{week:02d}_{week_start.strftime('%b-%d')}"
            folder_path = os.path.join(self.outputDir, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder created: {folder_path}")

            if self.distribute and remaining_images > 0:
                num_images = avg_images_per_week + random.choice([-1, 0, 1])
                num_images = min(num_images, remaining_images)  # Ensure we don’t exceed available images

                for _ in range(num_images):
                    image_path, _ = sorted_images.pop(0)  # Take first available image chronologically
                    destination_path = os.path.join(folder_path, image_path.name)

                    if self.move_files:
                        shutil.move(image_path, destination_path)
                    else:
                        shutil.copy2(image_path, destination_path)

                    print(f"  → Image {image_path.name} sorted into {folder_name}")
                    remaining_images -= 1
            else:
                images_to_remove = []
                week_end = week_start + timedelta(days=6)
                end_date_md = (week_end.month, week_end.day)
                if week_start.year < week_end.year:
                    start_date_md = (0, week_start.day)
                else:
                    start_date_md = (week_start.month, week_start.day)
                for image_path, image_date in self.sorted_images.items():
                    image_date_md = (image_date.month, image_date.day)
                    if start_date_md <= image_date_md <= end_date_md:
                        destination_path = os.path.join(folder_path, image_path.name)
                        if self.move_files:
                            shutil.move(image_path, destination_path)
                        else:
                            shutil.copy2(image_path, destination_path)
                        images_to_remove.append(image_path)
                        print(f"  → Image {image_path.name} sorted into {folder_name}")

                for image_path in images_to_remove:
                    del self.sorted_images[image_path]

            if self.generateDescriptionFile:
                description_file = os.path.join(folder_path, f"{week:02d}_description.txt")
                with open(description_file, "w", encoding="utf-8") as f:
                    print(f"  → {f.name} created")

            if self.generateLocationFile:
                location_file = os.path.join(folder_path, f"{week:02d}_location.txt")
                with open(location_file, "w", encoding="utf-8") as loc_file:
                    loc_file.write("51.0504, 13.7373\n")
                    print(f"  → {location_file} created")

        # print all remaining images that are not distributed:
        for image_path, image_date in self.sorted_images.items():
            print(f"  → Image {image_path.name} NOT considered")


if __name__ == "__main__":
    folderGen = FolderGenerator()
    folderGen.generateFolders()
