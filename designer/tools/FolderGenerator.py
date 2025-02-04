import os
import random
import shutil
from datetime import timedelta
from designer.common.Config import Config
from designer.tools.ImageDateAnalyzer import ImageDateAnalyzer


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
        imageAnalyzer = ImageDateAnalyzer()
        imageAnalyzer.run()
        self.image_date_dict = imageAnalyzer.image_date_dict  # Dictionary {image_path: date}
        self.distribute = False
        self.generateDescriptionFile = False
        self.generateLocationFile = False
        self.collagesToGenerate = self.config.collagesToGenerate

    def generateFolders(self):
        if not os.path.exists(self.outputDir):
            os.makedirs(self.outputDir)

        for week in range(self.collagesToGenerate):
            week_start = self.startDate + timedelta(weeks=week)
            folder_name = f"{week:02d}_{week_start.strftime('%b-%d')}"
            folder_path = os.path.join(self.outputDir, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            print(f"Folder created: {folder_path}")

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
        for image_path, image_date in self.image_date_dict.items():
            print(f"  → Image {image_path.name} NOT considered")


if __name__ == "__main__":
    folderGen = FolderGenerator()
    folderGen.generateFolders()
