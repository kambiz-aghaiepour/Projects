# Threading

Concurrent utilities and background processing.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Create a Progress Bar for Downloads](Create-A-Progress-Bar-for-Downloads/) — Create a progress bar for applications that can keep track of a download in progress. The progress bar will be on a separate thread and will communicate with the main thread using delegates.
- [Bulk Thumbnail Creator](Bulk-Thumbnail-Creator/) — Create an image program which can take hundreds of images and convert them to a specified size in a background thread while you do other things. For added complexity, have one thread handling resizing and another bulk renaming of thumbnails.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
