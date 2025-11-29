# Command Line Interface

Command line options for app

```bash
python -m app [OPTIONS] 
```

## Options

| Option             | Type      | Description                                                                             | Default                               | Choices |
|--------------------|-----------|-----------------------------------------------------------------------------------------|---------------------------------------|---|
| `--photoDirectory` | PosixPath | Path to the directory containing photos (absolute, or relative to this config.ini file) | PosixPath('images')                   | - |
| `--startDate`      | datetime  | Start date of the calendar                                                              | datetime.datetime(2025, 12, 31, 0, 0) | - |
| `--width`          | int       | Width of the collage in mm                                                              | 216                                   | - |
| `--height`         | int       | Height of the collage in mm                                                             | 154                                   | - |


## Examples


### 1. Basic usage

```bash
python -m app example.input
```

### 2. With verbose logging

```bash
python -m app -v example.input
python -m app --verbose example.input
```

### 3. With quiet mode

```bash
python -m app -q example.input
python -m app --quiet example.input
```

### 4. With photoDirectory parameter

```bash
python -m app --photoDirectory images example.input
```

### 5. With startDate parameter

```bash
python -m app --startDate 2025-12-31 00:00:00 example.input
```

### 6. With width parameter

```bash
python -m app --width 216 example.input
```