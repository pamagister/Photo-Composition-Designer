import os
from pathlib import Path

from designer.common.Config import Config


class DescriptionsFileGenerator:
    """
    Auxiliary class to generate a descriptions.txt file
    """

    def __init__(self, config=None):
        self.config = config or Config()
        self.photo_dir: Path = self.config.photoDirectory
        self.output_dir: Path = self.photo_dir
        self.startDate = self.config.startDate
        self.move_files = False
        self.distribute_images = True
        self.generateLocationFile = False
        self.collagesToGenerate = self.config.collagesToGenerate

    def generateDescriptionFile(self):
        global_description_text: list[str] = []

        for element in sorted(os.listdir(self.photo_dir)):
            global_description_text.append(f"{element}: ")

        description_file_global = os.path.join(self.output_dir, "descriptions.txt")
        if not os.path.exists(description_file_global):
            with open(description_file_global, "w", encoding="utf-8") as f:
                f.writelines(text + "\n" for text in global_description_text)


if __name__ == "__main__":
    folderGen = DescriptionsFileGenerator()
    folderGen.generateDescriptionFile()
