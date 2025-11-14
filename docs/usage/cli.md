# Command Line Interface

Command line options for Photo_Composition_Designer

```bash
python -m Photo_Composition_Designer [OPTIONS] input
```

## Options

| Option                | Type | Description                                       | Default    | Choices       |
|-----------------------|------|---------------------------------------------------|------------|---------------|
| `input`               | str  | Path to input (file or folder)                    | *required* | -             |
| `--output`            | str  | Path to output destination                        | *required* | -             |
| `--min_dist`          | int  | Maximum distance between two waypoints            | 25         | -             |
| `--extract_waypoints` | bool | Extract starting points of each track as waypoint | True       | [True, False] |
| `--elevation`         | bool | Include elevation data in waypoints               | True       | [True, False] |


## Examples


### 1. Basic usage

```bash
python -m Photo_Composition_Designer input
```

### 2. With verbose logging

```bash
python -m Photo_Composition_Designer -v input
python -m Photo_Composition_Designer --verbose input
```

### 3. With quiet mode

```bash
python -m Photo_Composition_Designer -q input
python -m Photo_Composition_Designer --quiet input
```

### 4. With min_dist parameter

```bash
python -m Photo_Composition_Designer --min_dist 25 input
```

### 5. With extract_waypoints parameter

```bash
python -m Photo_Composition_Designer --extract_waypoints True input
```

### 6. With elevation parameter

```bash
python -m Photo_Composition_Designer --elevation True input
```