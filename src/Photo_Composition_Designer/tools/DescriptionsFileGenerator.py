import os
from pathlib import Path


class DescriptionsFileGenerator:
    """
    Auxiliary class to generate a descriptions.txt file
    """

    def __init__(self, photo_dir: Path, output_dir: Path):
        self.photo_dir: Path = photo_dir
        self.output_dir: Path = output_dir
        self.move_files = False
        self.distribute_images = True
        self.generateLocationFile = False

    def generateDescriptionFile(self):
        global_description_text: list[str] = []

        for element in sorted(os.listdir(self.photo_dir)):
            folder_path = os.path.join(self.photo_dir, element)
            if not os.path.isdir(folder_path):
                continue
            global_description_text.append(f"{element}: ")

        description_file_global = os.path.join(self.output_dir, "descriptions.txt")
        if not os.path.exists(description_file_global):
            with open(description_file_global, "w", encoding="utf-8") as f:
                f.writelines(text + "\n" for text in global_description_text)


if __name__ == "__main__":
    photodir = Path("../../../images")
    outputdir = Path("../../../temp")
    folderGen = DescriptionsFileGenerator(photodir, outputdir)
    folderGen.generateDescriptionFile()
