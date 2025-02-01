# 📖 Photo-Composition-Designer Documentation

![Photo-Composition-Designer Logo](res/images/logo.png)

Photo-Composition-Designer is a tool designed to automate the creation of beautiful image-based calendars. The system sorts images, generates collages, adds descriptions and maps, and formats everything into a structured calendar layout.


## 🛠️ Features
✅ **Automated Calendar Generation** – Generates a full image-based calendar.
✅ **Configurable Settings** – Modify sizes, layouts, and text via `config.ini`.
✅ **Anniversaries & Events** – Load anniversaries and special dates.
✅ **Location-Based Maps** – Integrate maps showing image locations.
✅ **GUI Configuration Tool** – Easily modify configurations via a dynamic UI.
✅ **Folder Management** – Automatically structures images into necessary folders.

## 📂 Project Structure
```plaintext
📁 Photo-Composition-Designer/
├── 📁 config/        # Configuration files (config.ini, anniversaries.ini, locations.ini)
├── 📁 images/        # Source images for the calendar
├── 📁 collages/      # Generated calendar collages
├── 📁 res/
│   ├── 📁 icons/     # UI icons
│   ├── 📁 images/    # Documentation images
├── 📁 designer/  # Core application
├── 📄 README.md      # Project overview
├── 📄 requirements.txt # Dependencies
```

## 🔄 Workflow
### 1️⃣ **Sorting Images into Folders**
Organize your images in the `images/` directory before running the generator.
```plaintext
📁 images/
├── 2024-01-01_ski_trip.jpg
├── 2024-02-14_valentines_dinner.jpg
```

### 2️⃣ **Configuring the Settings**
Modify `config.ini` for:
- Image sizes (mm converted to pixels internally)
- Calendar layout
- Paths to `anniversaries.ini` and `locations.ini`

### 3️⃣ **Running the GUI** 🖥️
Launch the graphical interface:
```sh
python gui.py
```
Use the GUI to:
- Edit settings
- Choose files
- Generate required folders
- Start the calendar generator

### 4️⃣ **Generating the Calendar** 🖼️📅
Run the generator:
```sh
python generate_calendar.py
```

## ⚙️ Configuration Files
### `config.ini`
Example settings:
```ini
[GENERAL]
photoDirectory = images/
anniversariesConfig = anniversaries.ini
locationsConfig = locations.ini

[SIZE]
width = 210 ; in mm
height = 148 ; in mm
dpi = 300
```

### `anniversaries.ini`
```ini
[Birthdays]
John Doe = 15.04.1990
```

To extract birthdays of your contacts, use this regex to parse them from an *.ical file:
```ini
[search expression]
(?s)BEGIN:VEVENT.*?DTSTART[^:]*:(\d{4})(\d{2})(\d{2}).*?SUMMARY:\s*([^(\r\n]+)\s*\(\d{4}\).*?END:VEVENT

[replacement expression]
$4 = $3.$2.$1
```

## 🏗️ Development Setup
### Install Dependencies
```sh
pip install -r requirements.txt
```

### Run Tests
```sh
pytest tests/
```

## 📜 License
This project is licensed under the MIT License.

---

📷 _Photo-Composition-Designer - Turning moments into memories!_

