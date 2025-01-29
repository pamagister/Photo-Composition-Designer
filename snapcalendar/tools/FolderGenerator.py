import os
from datetime import timedelta

from snapcalendar.common.Config import Config


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
        self.outputDir = self.photoDirectory.parent / 'folders'
        self.startDate = self.config.startDate

        self.generateDescriptionFile = False
        self.generateLocationFile = False

    def generateFolders(self, weeksToGenerate=55):
        """Generates the desired folders with optional files."""
        if not os.path.exists(self.outputDir):
            os.makedirs(self.outputDir)

        for week in range(weeksToGenerate):
            weekDate = self.startDate + timedelta(weeks=week)
            folderName = f"Week_{week:02d}_{weekDate.strftime('%Y-%m-%d')}"
            folderPath = os.path.join(self.outputDir, folderName)

            os.makedirs(folderPath, exist_ok=True)
            print(f"Folder created: {folderPath}")

            if self.generateDescriptionFile:
                descriptionFile = f"description_{week:02d}.txt"
                descriptionPath = os.path.join(folderPath, descriptionFile)
                with open(descriptionPath, 'w', encoding="utf-8") as f:
                    f.close()
                    print(f"  → {descriptionFile} created")

            if self.generateLocationFile:
                locationFile = f"location_{week:02d}.txt"
                locationPath = os.path.join(folderPath, locationFile)
                with open(locationPath, 'w', encoding="utf-8") as loc_file:
                    loc_file.write("51.0504, 13.7373\n")
                    print(f"  → {locationFile} created")


if __name__ == "__main__":
    folderGen = FolderGenerator()
    folderGen.generateFolders(56)
