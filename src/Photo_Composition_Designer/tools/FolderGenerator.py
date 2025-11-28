import os
import shutil
from datetime import timedelta
from pathlib import Path

from Photo_Composition_Designer.common.Photo import get_photos_from_dir
from Photo_Composition_Designer.tools.DescriptionsFileGenerator import DescriptionsFileGenerator
from Photo_Composition_Designer.tools.ImageDistributor import ImageDistributor


class FolderGenerator:
    """
    Auxiliary class for generating folders that can then be filled with images.
    * A folder is generated for each week in the format
    Week_<index>_YYYY-MM-DD, e.g. Week_01_2024-07-23
    * An empty "description.txt" is generated in each folder if required
    * A location.txt is also generated if required,
    which contains the GPX position 51.0504, 13.7373
    """

    def __init__(self, config=None):
        self.config = config
        self.photo_dir: Path = self.config.photoDirectory
        self.output_dir: Path = self.photo_dir
        self.startDate = self.config.startDate
        self.move_files = False
        self.distribute_images = True
        self.generateDescriptionFile = False
        self.generateLocationFile = False
        self.collagesToGenerate = self.config.collagesToGenerate

        # prepare image sorting:
        photos = get_photos_from_dir(self.photo_dir)

        # prepare image distribution
        image_distributor = ImageDistributor(photos, self.collagesToGenerate)
        self.image_groups = image_distributor.distribute_group_matching_dates()

    def generateFolders(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

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
                    print(f"  --> {f.name} created")

            if self.generateLocationFile:
                location_file = os.path.join(folder_path, f"{week:02d}_location.txt")
                with open(location_file, "w", encoding="utf-8") as loc_file:
                    loc_file.write("51.0504, 13.7373\n")
                    print(f"  --> {location_file} created")

            if self.distribute_images:
                if not self.image_groups:
                    continue
                images_in_group = self.image_groups.pop(0)
                for photo in images_in_group:
                    image_file_name = photo.file_path.name
                    destination_path = os.path.join(folder_path, image_file_name)
                    if self.move_files:
                        shutil.move(photo.file_path, destination_path)
                    else:
                        shutil.copy2(photo.file_path, destination_path)
                    print(f"  --> Image {photo.file_path.name} sorted into {folder_name}")
        # Generate descriptions text file
        DescriptionsFileGenerator(self.config).generate_description_file()


if __name__ == "__main__":
    folderGen = FolderGenerator()
    folderGen.generateFolders()
