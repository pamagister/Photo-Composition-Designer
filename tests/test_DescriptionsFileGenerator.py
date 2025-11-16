from Photo_Composition_Designer.tools.DescriptionsFileGenerator import DescriptionsFileGenerator


def test_generate_description_file_creates_real_file(tmp_path):
    # Create a fake photo directory inside the pytest temp directory
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()

    # Create some folder structure in the photo directory
    (photo_dir / "set1").mkdir()
    (photo_dir / "set2").mkdir()

    # Create a non-folder file (should be ignored)
    (photo_dir / "not_a_dir.txt").write_text("ignore me")

    # Create output directory
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Run the generator
    generator = DescriptionsFileGenerator(photo_dir, output_dir)
    generator.generateDescriptionFile()

    # Verify file was actually created
    desc_file = output_dir / "descriptions.txt"
    assert desc_file.exists(), "descriptions.txt was not created"

    # Read the file contents
    content = desc_file.read_text(encoding="utf-8").splitlines()

    # Expected lines (sorted lexicographically by folder name)
    # Based on the generator: `element: `
    expected = [
        "set1: ",
        "set2: ",
    ]

    assert content == expected
