import os
import shutil
from datetime import timedelta
from pathlib import Path

from designer.common.Config import Config
from designer.tools.ImageDateAnalyzer import ImageDateAnalyzer
from designer.tools.ImageDistributor import ImageDistributor


class FolderGenerator:
    """
    Auxiliary class for generating folders that can then be filled with images.
    * A folder is generated for each week in the format Week_<index>_YYYY-MM-DD, e.g. Week_01_2024-07-23
    * An empty "description.txt" is generated in each folder if required
    * A location.txt is also generated if required, which contains the GPX position 51.0504, 13.7373
    """

    def __init__(self, config=None):
        self.config = config or Config()
        self.photo_dir: Path = self.config.photoDirectory
        self.output_dir: Path = self.photo_dir
        self.startDate = self.config.startDate
        self.move_files = False
        self.distribute_images = True
        self.generateDescriptionFile = False
        self.generateLocationFile = False
        self.collagesToGenerate = self.config.collagesToGenerate

        # prepare image sorting:
        image_files = [img_file.as_posix() for img_file in self.photo_dir.iterdir()]
        image_analyzer = ImageDateAnalyzer(image_files)
        image_date_dict = image_analyzer.image_date_dict
        self.images_undated = image_analyzer.images_undated

        # prepare image distribution
        image_distributor = ImageDistributor(image_date_dict, self.collagesToGenerate)
        self.image_groups = image_distributor.distribute_group_matching_dates()

    def generateFolders(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        global_description_text: list[str] = []

        week_start = self.startDate
        folder_name = "00_00_TITLE"
        folder_path = os.path.join(self.output_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        for week in range(self.collagesToGenerate):
            week_start = self.startDate + timedelta(weeks=week)
            folder_name = f"{week:02d}_{week_start.strftime('%b-%d')}"
            folder_path = os.path.join(self.output_dir, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder created: {folder_path}")

            if self.generateDescriptionFile:
                description_file = os.path.join(folder_path, f"{week:02d}_description.txt")
                with open(description_file, "w", encoding="utf-8") as f:
                    print(f"  → {f.name} created")

            global_description_text.append(f"{folder_name}: ")

            if self.generateLocationFile:
                location_file = os.path.join(folder_path, f"{week:02d}_location.txt")
                with open(location_file, "w", encoding="utf-8") as loc_file:
                    loc_file.write("51.0504, 13.7373\n")
                    print(f"  → {location_file} created")

            if self.distribute_images:
                images_in_group = self.image_groups.pop(week)
                for image_path, image_date in images_in_group:
                    image_file_name = Path(image_path).name
                    destination_path = os.path.join(folder_path, image_file_name)
                    if self.move_files:
                        shutil.move(image_path, destination_path)
                    else:
                        shutil.copy2(image_path, destination_path)
                    print(f"  → Image {image_path} sorted into {folder_name}")

        description_file_global = os.path.join(self.output_dir, "descriptions.txt")
        if not os.path.exists(description_file_global):
            with open(description_file_global, "w", encoding="utf-8") as f:
                f.writelines(text + "\n" for text in global_description_text)

        # print all remaining images that are not distributed:
        print("\n\n ##############################################")
        for image_path in self.images_undated:
            print(f"  → Image {image_path} NOT considered")


if __name__ == "__main__":
    folderGen = FolderGenerator()
    folderGen.generateFolders()
