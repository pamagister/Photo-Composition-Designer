import os
from pathlib import Path


class DescriptionsFileGenerator:
    """
    Auxiliary class to generate a descriptions.txt file
    """

    def __init__(self, photo_dir: Path):
        self.photo_dir: Path = photo_dir

    def generate_description_file(self, overwrite=False) -> str:
        global_description_text: list[str] = []

        for element in sorted(os.listdir(self.photo_dir)):
            folder_path = os.path.join(self.photo_dir, element)
            if not os.path.isdir(folder_path):
                continue
            global_description_text.append(f"{element}: Description text for this week")

        if overwrite or self.description_file_exists():
            with open(self._descriptions_file_path(), "w", encoding="utf-8") as f:
                f.writelines(text + "\n" for text in global_description_text)

        return self._descriptions_file_path()

    def description_file_exists(self) -> bool:
        return os.path.exists(self._descriptions_file_path())

    def _descriptions_file_path(self) -> str:
        return os.path.join(self.photo_dir, "descriptions.txt")


if __name__ == "__main__":
    photodir = Path("../../../images")
    _description_file_generator = DescriptionsFileGenerator(photodir)
    _description_file_generator.generate_description_file()
