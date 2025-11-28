import os
from pathlib import Path


class DescriptionsFileGenerator:
    """
    Auxiliary class to generate a descriptions.txt file
    """

    def __init__(self, photo_dir: Path, output_dir: Path):
        self.photo_dir: Path = photo_dir
        self.output_dir: Path = output_dir

    def generate_description_file(self, overwrite=False) -> str:
        """
        Generate a template description file for all collages
        based on the generated photo directories
        """
        global_description_text: list[str] = []

        for element in sorted(os.listdir(self.photo_dir)):
            folder_path = os.path.join(self.photo_dir, element)
            if not os.path.isdir(folder_path):
                continue
            global_description_text.append(f"{element}: Description text for week {element}")
        out_path = self._descriptions_file_path()
        if overwrite or not self.description_file_exists():
            with open(out_path, "w", encoding="utf-8") as f:  # type: ignore
                f.writelines(text + "\n" for text in global_description_text)

        return out_path

    def description_file_exists(self) -> bool:
        return os.path.exists(self._descriptions_file_path())

    def _descriptions_file_path(self) -> str:
        return os.path.join(self.output_dir, "descriptions.txt")  # type: ignore


if __name__ == "__main__":
    photodir = Path("../../../images")
    outputdir = Path("../../../output")
    _description_file_generator = DescriptionsFileGenerator(photodir, outputdir)
    _description_file_generator.generate_description_file()
