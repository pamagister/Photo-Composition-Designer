# Configuration Parameters

These parameters are available to configure the behavior of your application.
The parameters in the cli category can be accessed via the command line interface.

## Category "app"

| Name      | Type | Description                       | Default | Choices                                           |
|-----------|------|-----------------------------------|---------|---------------------------------------------------|
| log_level | str  | Logging level for the application | 'INFO'  | ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] |

## Category "general"

| Name                | Type      | Description                                                                             | Default                                | Choices |
|---------------------|-----------|-----------------------------------------------------------------------------------------|----------------------------------------|---------|
| photoDirectory      | PosixPath | Path to the directory containing photos (absolute, or relative to this config.ini file) | PosixPath('../../images')              | -       |
| anniversariesConfig | PosixPath | Path to anniversaries.ini file (absolute, or relative to this config.ini file)          | PosixPath('anniversaries.ini')         | -       |
| locationsConfig     | PosixPath | Path to locations.ini file (absolute, or relative to this config.ini file)              | PosixPath('locations_en.ini')          | -       |
| compositionTitle    | str       | This is the title of the composition on the first page. Leave empty if not required.    | 'This is the title of the composition' | -       |

## Category "calendar"

| Name               | Type     | Description                                               | Default                               | Choices       |
|--------------------|----------|-----------------------------------------------------------|---------------------------------------|---------------|
| useCalendar        | bool     | True: Calendar elements are generated                     | True                                  | [True, False] |
| language           | str      | Language for the calendar (e.g., de_DE, en_US)            | 'de_DE'                               | -             |
| holidayCountries   | str      | Country/state codes for public holidays, e.g., NY,CA      | 'SN'                                  | -             |
| startDate          | datetime | Start date of the calendar                                | datetime.datetime(2025, 12, 31, 0, 0) | -             |
| collagesToGenerate | int      | Number of collages to be generated (e.g. number of weeks) | 11                                    | -             |

## Category "colors"

| Name            | Type  | Description            | Default              | Choices |
|-----------------|-------|------------------------|----------------------|---------|
| backgroundColor | Color | Background color (RGB) | Color(20, 20, 20)    | -       |
| textColor1      | Color | Primary text color     | Color(255, 255, 255) | -       |
| textColor2      | Color | Secondary text color   | Color(150, 150, 150) | -       |
| holidayColor    | Color | Color for holidays     | Color(255, 0, 0)     | -       |

## Category "geo"

| Name                 | Type | Description                             | Default | Choices       |
|----------------------|------|-----------------------------------------|---------|---------------|
| usePhotoLocationMaps | bool | Use GPS data to generate maps           | True    | [True, False] |
| minimalExtension     | int  | Minimum range for map display (degrees) | 7       | -             |

## Category "size"

| Name           | Type | Description                       | Default | Choices |
|----------------|------|-----------------------------------|---------|---------|
| width          | int  | Width of the collage in mm        | 216     | -       |
| height         | int  | Height of the collage in mm       | 154     | -       |
| calendarHeight | int  | Height of the calendar area in mm | 18      | -       |
| mapWidth       | int  | Width of the locations map in mm  | 20      | -       |
| mapHeight      | int  | Height of the locations map in mm | 20      | -       |
| dpi            | int  | Resolution of the image in dpi    | 150     | -       |
| jpgQuality     | int  | JPG compression quality (1-100)   | 90      | -       |

## Category "layout"

| Name                  | Type  | Description                                 | Default | Choices       |
|-----------------------|-------|---------------------------------------------|---------|---------------|
| fontSizeLarge         | float | Font size for large text                    | 0.5     | -             |
| fontSizeSmall         | float | Font size for small text                    | 0.14    | -             |
| fontSizeAnniversaries | float | Font size for anniversaries                 | 0.115   | -             |
| marginTop             | int   | Top margin in mm                            | 6       | -             |
| marginBottom          | int   | Bottom margin in mm                         | 3       | -             |
| marginSides           | int   | Side margins in mm                          | 3       | -             |
| spacing               | int   | Spacing between elements in mm              | 2       | -             |
| useShortDayNames      | bool  | Use short weekday names (e.g., Mon, Tue)    | False   | [True, False] |
| useShortMonthNames    | bool  | Use short month names (e.g., Jan, Feb)      | True    | [True, False] |
| usePhotoDescription   | bool  | Include photo descriptions in the collage   | True    | [True, False] |
| generatePdf           | bool  | Combine all generated collages into one pdf | True    | [True, False] |

