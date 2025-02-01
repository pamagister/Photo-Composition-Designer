import os
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
        self.outputDir = self.photoDirectory.parent / "folders"
        self.startDate = self.config.startDate
        self.move_files = False
        imageSorter = ImageSorter()
        imageSorter.run()
        self.sorted_images = imageSorter.sorted_images

        self.generateDescriptionFile = False
        self.generateLocationFile = False

    def generateFolders(self, weeksToGenerate=55):
        """Generates the desired folders with optional files and sorts images into them."""
        if not os.path.exists(self.outputDir):
            os.makedirs(self.outputDir)

        for week in range(weeksToGenerate):
            week_start = self.startDate + timedelta(weeks=week)
            week_end = week_start + timedelta(days=6)
            folder_name = f"{week:02d}_{week_start.strftime('%Y-%m-%d')}"
            folder_path = os.path.join(self.outputDir, folder_name)

            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder created: {folder_path}")

            images_to_remove = []

            for image_path, image_date in self.sorted_images.items():
                if (
                    (week_start.month, week_start.day)
                    <= (image_date.month, image_date.day)
                    <= (week_end.month, week_end.day)
                ):
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
                    print(f"  → {description_file} created")

            if self.generateLocationFile:
                location_file = os.path.join(folder_path, f"{week:02d}_location.txt")
                with open(location_file, "w", encoding="utf-8") as loc_file:
                    loc_file.write("51.0504, 13.7373\n")
                    print(f"  → {location_file} created")


if __name__ == "__main__":
    folderGen = FolderGenerator()
    folderGen.generateFolders(50)
