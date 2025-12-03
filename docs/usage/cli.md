# Command Line Interface

Command line options for app

```bash
python -m app [OPTIONS] photoDirectory
```

## Options

| Option           | Type      | Description                                                                             | Default                               | Choices |
|------------------|-----------|-----------------------------------------------------------------------------------------|---------------------------------------|---|
| `photoDirectory` | PosixPath | Path to the directory containing photos (absolute, or relative to this config.ini file) | *required*                            | - |
| `--startDate`    | datetime  | Start date of the calendar                                                              | datetime.datetime(2025, 12, 29, 0, 0) | - |
| `--width`        | int       | Width of the collage in mm                                                              | 216                                   | - |
| `--height`       | int       | Height of the collage in mm                                                             | 154                                   | - |
| `--dpi`          | int       | Resolution of the image in dpi                                                          | 150                                   | - |


## Examples


### 1. Basic usage

```bash
python -m app photoDirectory
```

### 2. With verbose logging

```bash
python -m app -v photoDirectory
python -m app --verbose photoDirectory
```

### 3. With quiet mode

```bash
python -m app -q photoDirectory
python -m app --quiet photoDirectory
```

### 4. With startDate parameter

```bash
python -m app --startDate 2025-12-29 00:00:00 photoDirectory
```

### 5. With width parameter

```bash
python -m app --width 216 photoDirectory
```

### 6. With height parameter

```bash
python -m app --height 154 photoDirectory
```