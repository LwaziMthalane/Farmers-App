# Farmer calculator

An offline KivyMD 2 Android app for crop and livestock costing.

Enter seed/feed costs, labor, other costs, target yield, and expected price. The app calculates total expenses, expected revenue, profit, and profit margin. It remembers the latest saved price for a matching item, while keeping that price editable. Category, unit, preset item, JSON storage, and CSV export are included.

## Test on Windows

```powershell
.\.venv\Scripts\python.exe main.py
```

The local test storage is kept in the Kivy app data directory. The app starts with no saved entries after a reset.

## Build the APK locally

Buildozer requires Linux. Use Ubuntu, WSL2, or GitHub Actions:

```bash
buildozer android debug
```

The generated APK is placed in `bin/`. The GitHub Actions workflow builds the same APK and uploads it as the `farmer-costing-apk` artifact.
