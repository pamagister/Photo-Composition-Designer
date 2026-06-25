import shutil

from Photo_Composition_Designer.tools.DescriptionsFileGenerator import DescriptionsFileGenerator

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def test_generate_description_file_creates_real_file(temp_dir):
    # Create a fake photo directory inside the pytest temp directory
    photo_dir = temp_dir / "photos"
    output_dir = temp_dir / "output"

    # cleanup
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.rmtree(photo_dir, ignore_errors=True)

    # Create some folder structure in the photo directory
    photo_dir.mkdir()
    (photo_dir / "set1").mkdir()
    (photo_dir / "set2").mkdir()

    # Create a non-folder file (should be ignored)
    (photo_dir / "not_a_dir.txt").write_text("ignore me")

    # Create output directory
    output_dir.mkdir()

    # Run the generator
    generator = DescriptionsFileGenerator(photo_dir, output_dir)
    generator.generate_description_file(overwrite=True)

    # Verify file was actually created
    desc_file = photo_dir / "descriptions.txt"
    assert desc_file.exists(), "descriptions.txt was not created"

    # Read the file contents
    content = desc_file.read_text(encoding="utf-8").splitlines()

    # Expected lines (sorted lexicographically by folder name)
    # Based on the generator: `element: `
    expected = [
        "set1: Description text for week set1",
        "set2: Description text for week set2",
    ]

    assert content == expected
